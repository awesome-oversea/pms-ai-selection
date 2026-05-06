"""
Qdrant向量数据库客户端
======================

提供:
    - Qdrant异步客户端封装
    - Collection管理(创建/删除/配置)
    - 向量增删改查(CRUD)
    - 多节点读写分离与故障切换
    - 本地嵌入式回退

D7-T018: Qdrant集群部署与Collection配置
    - product_knowledge: 产品知识库(HNSW m=16, ef=100)
    - market_data: 市场数据向量库
    - report_chunks: 报告分块向量库
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

try:
    from qdrant_client import AsyncQdrantClient, models
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    _QDRANT_AVAILABLE = True
except ImportError:
    AsyncQdrantClient = Any  # type: ignore
    models = None  # type: ignore
    Distance = Any  # type: ignore
    FieldCondition = Any  # type: ignore
    Filter = Any  # type: ignore
    MatchValue = Any  # type: ignore
    PointStruct = Any  # type: ignore
    VectorParams = Any  # type: ignore
    _QDRANT_AVAILABLE = False

from src.config.settings import get_settings
from src.core.logging import get_logger
from src.core.metrics import observe_qdrant_search

logger = get_logger(__name__)

_qdrant_client: Any | None = None
_qdrant_mode: str | None = None
_qdrant_topology: dict[str, Any] | None = None


def _normalize_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    if "://" not in normalized:
        normalized = f"http://{normalized}"
    return normalized


def _unique_endpoints(endpoints: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for endpoint in endpoints:
        if endpoint and endpoint not in seen:
            seen.add(endpoint)
            result.append(endpoint)
    return result


def _default_qdrant_endpoint() -> str:
    settings = get_settings()
    if settings.qdrant.url:
        return _normalize_endpoint(settings.qdrant.url)
    return _normalize_endpoint(f"{settings.qdrant.host}:{settings.qdrant.port}")


def _can_use_remote_qdrant(endpoint: str, timeout_seconds: float) -> bool:
    try:
        response = httpx.get(f"{endpoint}/collections", timeout=timeout_seconds)
        return response.status_code < 500
    except Exception:
        return False


def _cache_qdrant_topology(
    *,
    writer_endpoint: str | None,
    read_endpoints: list[str],
    mode: str,
    local_fallback: bool,
) -> dict[str, Any]:
    global _qdrant_mode, _qdrant_topology

    _qdrant_mode = mode
    _qdrant_topology = {
        "writer_endpoint": writer_endpoint,
        "read_endpoints": list(read_endpoints),
        "mode": mode,
        "local_fallback": local_fallback,
    }
    return dict(_qdrant_topology)


def get_qdrant_topology() -> dict[str, Any]:
    global _qdrant_topology
    if _qdrant_topology is not None:
        return dict(_qdrant_topology)

    settings = get_settings()
    default_endpoint = _default_qdrant_endpoint()
    configured_write = _normalize_endpoint(settings.qdrant.write_url) if settings.qdrant.write_url else default_endpoint
    configured_reads = _unique_endpoints([_normalize_endpoint(url) for url in settings.qdrant.read_urls])
    cluster_requested = settings.qdrant.cluster_enabled and bool(configured_reads)
    candidate_write_endpoints = _unique_endpoints([configured_write, *configured_reads, default_endpoint])

    if settings.app.environment == "production":
        read_endpoints = configured_reads if cluster_requested else [configured_write]
        return _cache_qdrant_topology(
            writer_endpoint=configured_write,
            read_endpoints=read_endpoints or [configured_write],
            mode="cluster-rw-split" if cluster_requested else "remote",
            local_fallback=False,
        )

    healthy_write_candidates = [
        endpoint
        for endpoint in candidate_write_endpoints
        if _can_use_remote_qdrant(endpoint, settings.qdrant.timeout_seconds)
    ]

    if healthy_write_candidates:
        writer_endpoint = healthy_write_candidates[0]
        healthy_read_endpoints: list[str] = []
        if cluster_requested:
            for endpoint in configured_reads:
                if _can_use_remote_qdrant(endpoint, settings.qdrant.timeout_seconds):
                    healthy_read_endpoints.append(endpoint)
                else:
                    logger.warning("Qdrant read endpoint probe failed for %s; skipping it", endpoint)

        if not healthy_read_endpoints:
            healthy_read_endpoints = [writer_endpoint]

        return _cache_qdrant_topology(
            writer_endpoint=writer_endpoint,
            read_endpoints=healthy_read_endpoints,
            mode="cluster-rw-split" if cluster_requested and any(ep != writer_endpoint for ep in healthy_read_endpoints) else "remote",
            local_fallback=False,
        )

    if settings.qdrant.prefer_local_fallback:
        return _cache_qdrant_topology(
            writer_endpoint=None,
            read_endpoints=[],
            mode="local-fallback",
            local_fallback=True,
        )

    raise RuntimeError("Qdrant remote endpoints are unavailable and local fallback is disabled")


class QdrantClusterClient:
    """统一封装写节点和读节点的Qdrant客户端。"""

    def __init__(
        self,
        *,
        writer_client: Any,
        writer_endpoint: str | None,
        read_clients: list[Any],
        read_endpoints: list[str],
        mode: str,
    ) -> None:
        self._writer_client = writer_client
        self._writer_endpoint = writer_endpoint or "local-path"
        self._read_clients = read_clients or [writer_client]
        self._read_endpoints = read_endpoints or [self._writer_endpoint]
        self._mode = mode
        self._read_index = 0
        self._read_lock = Lock()

    def describe_topology(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "writer_endpoint": self._writer_endpoint,
            "read_endpoints": list(self._read_endpoints),
        }

    def _ordered_read_candidates(self) -> list[tuple[str, Any]]:
        candidates = list(zip(self._read_endpoints, self._read_clients, strict=False))
        if not candidates:
            return [(self._writer_endpoint, self._writer_client)]
        if len(candidates) == 1:
            return candidates
        with self._read_lock:
            start = self._read_index % len(candidates)
            self._read_index += 1
        return candidates[start:] + candidates[:start]

    async def _call_write(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._writer_client, method_name)
        return await method(*args, **kwargs)

    async def _call_read(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        errors: list[str] = []
        for endpoint, client in self._ordered_read_candidates():
            try:
                method = getattr(client, method_name)
                return await method(*args, **kwargs)
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")
        raise RuntimeError(f"All Qdrant read endpoints failed for {method_name}: {' | '.join(errors)}")

    async def get_collections(self) -> Any:
        return await self._call_read("get_collections")

    async def get_collection(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_read("get_collection", *args, **kwargs)

    async def count(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_read("count", *args, **kwargs)

    async def query_points(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_read("query_points", *args, **kwargs)

    async def search(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._call_read("search", *args, **kwargs)
        except RuntimeError as exc:
            if "attribute 'search'" not in str(exc):
                raise
            query_kwargs = dict(kwargs)
            if "query_vector" in query_kwargs and "query" not in query_kwargs:
                query_kwargs["query"] = query_kwargs.pop("query_vector")
            response = await self._call_read("query_points", *args, **query_kwargs)
            return getattr(response, "points", response)

    async def create_collection(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_write("create_collection", *args, **kwargs)

    async def delete_collection(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_write("delete_collection", *args, **kwargs)

    async def upsert(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_write("upsert", *args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call_write("delete", *args, **kwargs)

    async def close(self) -> None:
        closed: set[int] = set()
        for client in [self._writer_client, *self._read_clients]:
            if client is None or id(client) in closed:
                continue
            closed.add(id(client))
            close_method = getattr(client, "close", None)
            if callable(close_method):
                await close_method()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._writer_client, name)


def _create_remote_client(endpoint: str) -> Any:
    settings = get_settings()
    return AsyncQdrantClient(
        url=endpoint,
        api_key=settings.qdrant.api_key or None,
        timeout=settings.qdrant.timeout_seconds,
        check_compatibility=False,
        trust_env=False,
    )


def _create_local_fallback_client() -> Any:
    settings = get_settings()
    local_path = (Path("artifacts") / "runtime" / "qdrant_local").resolve()
    local_path.mkdir(parents=True, exist_ok=True)
    logger.warning("Qdrant remote endpoints are unavailable; falling back to local path %s", local_path)
    return AsyncQdrantClient(
        path=str(local_path),
        timeout=settings.qdrant.timeout_seconds,
        check_compatibility=False,
    )


def _create_qdrant_client() -> Any:
    """
    创建Qdrant异步客户端。

    支持:
        - 单节点远端
        - 多节点读写分离
        - 本地嵌入式回退
    """
    if not _QDRANT_AVAILABLE:
        raise RuntimeError("qdrant-client 未安装，Qdrant 功能不可用")

    topology = get_qdrant_topology()
    if topology["local_fallback"]:
        local_client = _create_local_fallback_client()
        return QdrantClusterClient(
            writer_client=local_client,
            writer_endpoint="local-path",
            read_clients=[local_client],
            read_endpoints=["local-path"],
            mode="local-fallback",
        )

    writer_endpoint = topology["writer_endpoint"]
    if writer_endpoint is None:
        raise RuntimeError("Qdrant writer endpoint is not configured")

    client_cache: dict[str, Any] = {}

    def _client_for(endpoint: str) -> Any:
        if endpoint not in client_cache:
            client_cache[endpoint] = _create_remote_client(endpoint)
        return client_cache[endpoint]

    writer_client = _client_for(writer_endpoint)
    read_clients = [_client_for(endpoint) for endpoint in topology["read_endpoints"]]

    return QdrantClusterClient(
        writer_client=writer_client,
        writer_endpoint=writer_endpoint,
        read_clients=read_clients,
        read_endpoints=topology["read_endpoints"],
        mode=topology["mode"],
    )


def get_qdrant_client() -> Any:
    """
    获取全局Qdrant客户端单例。

    Returns:
        QdrantClusterClient: 全局唯一客户端实例
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = _create_qdrant_client()
        logger.info("🔵 Qdrant客户端已创建 (mode=%s)", _qdrant_mode or "unknown")
    return _qdrant_client


class QdrantService:
    """
    Qdrant高级服务封装。

    提供类型安全的Collection管理和向量操作，
    屏蔽底层API细节。
    """

    def __init__(self, client: Any):
        self._client = client

    async def ensure_collection(
        self,
        collection_name: str,
        vector_size: int = 1024,
        distance: Any | None = None,
        hnsw_m: int = 16,
        hnsw_ef_construct: int = 100,
    ) -> bool:
        """
        确保Collection存在(不存在则创建)。

        D7-T018:
            - 配置HNSW索引参数(m=16, ef=100)
            - 支持分片、副本与写一致性配置
        """
        if not _QDRANT_AVAILABLE or models is None:
            raise RuntimeError("qdrant-client 未安装，无法创建 collection")

        settings = get_settings()
        if distance is None:
            distance = models.Distance.COSINE

        collections = await self._client.get_collections()
        existing = [collection.name for collection in collections.collections]
        if collection_name in existing:
            logger.debug("Collection '%s' 已存在", collection_name)
            return False

        try:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance,
                    hnsw_config=models.HnswConfigDiff(
                        m=hnsw_m,
                        ef_construct=hnsw_ef_construct,
                    ),
                ),
                shard_number=settings.qdrant.shard_number,
                replication_factor=settings.qdrant.replication_factor,
                write_consistency_factor=settings.qdrant.write_consistency_factor,
            )
        except Exception as exc:
            message = str(exc).lower()
            if "already exists" in message or "409" in message:
                logger.info("Collection '%s' already exists during create; reusing it", collection_name)
                return False
            raise

        logger.info(
            "✅ Collection '%s' 已创建 (dim=%s, dist=%s, shard=%s, repl=%s)",
            collection_name,
            vector_size,
            distance,
            settings.qdrant.shard_number,
            settings.qdrant.replication_factor,
        )
        return True

    async def upsert_points(
        self,
        collection_name: str,
        points: list[PointStruct],
        batch_size: int = 100,
    ) -> int:
        """批量插入/更新向量点。"""
        total = 0
        for index in range(0, len(points), batch_size):
            batch = points[index : index + batch_size]
            await self._client.upsert(
                collection_name=collection_name,
                points=batch,
            )
            total += len(batch)

        logger.info("📥 upsert %s points → %s", total, collection_name)
        return total

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float = 0.5,
        filter_: Filter | None = None,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> list[dict[str, Any]]:
        """向量相似度搜索。"""
        started_at = time.monotonic()
        try:
            search_method = getattr(self._client, "search", None)
            if callable(search_method):
                results = await search_method(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    query_filter=filter_,
                    score_threshold=score_threshold,
                    with_payload=with_payload,
                    with_vectors=with_vectors,
                )
            else:
                query_response = await self._client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit,
                    query_filter=filter_,
                    score_threshold=score_threshold,
                    with_payload=with_payload,
                    with_vectors=with_vectors,
                )
                results = getattr(query_response, "points", query_response)

            observe_qdrant_search(collection_name, "sdk", "success", time.monotonic() - started_at)
            return [
                {
                    "id": str(result.id),
                    "score": result.score,
                    "payload": result.payload if with_payload else None,
                    "vector": result.vector if with_vectors else None,
                }
                for result in results
            ]
        except Exception as exc:
            observe_qdrant_search(collection_name, "sdk", "fallback", time.monotonic() - started_at)
            logger.warning("Qdrant SDK search 失败，回退 REST 查询: %s", exc)

            try:
                query_response = await self._client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit,
                    query_filter=filter_,
                    score_threshold=score_threshold,
                    with_payload=with_payload,
                    with_vectors=with_vectors,
                )
                results = getattr(query_response, "points", query_response)
                observe_qdrant_search(collection_name, "query_points", "success", time.monotonic() - started_at)
                return [
                    {
                        "id": str(result.id),
                        "score": result.score,
                        "payload": result.payload if with_payload else None,
                        "vector": result.vector if with_vectors else None,
                    }
                    for result in results
                ]
            except Exception as query_exc:
                logger.warning("Qdrant query_points 回退失败，继续尝试 REST 查询: %s", query_exc)

            topology = get_qdrant_topology()
            rest_endpoint = None
            if topology["read_endpoints"]:
                rest_endpoint = topology["read_endpoints"][0]
            elif topology["writer_endpoint"]:
                rest_endpoint = topology["writer_endpoint"]

            if not rest_endpoint or rest_endpoint == "local-path":
                raise

            payload: dict[str, Any] = {
                "vector": query_vector,
                "limit": limit,
                "with_payload": with_payload,
                "with_vector": with_vectors,
                "score_threshold": score_threshold,
            }
            if filter_ is not None and hasattr(filter_, "model_dump"):
                payload["filter"] = filter_.model_dump(by_alias=True, exclude_none=True)

            rest_started_at = time.monotonic()
            async with httpx.AsyncClient(timeout=get_settings().qdrant.timeout_seconds) as client:
                response = await client.post(
                    f"{rest_endpoint}/collections/{collection_name}/points/search",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            observe_qdrant_search(collection_name, "rest", "success", time.monotonic() - rest_started_at)
            return [
                {
                    "id": str(item.get("id")),
                    "score": item.get("score", 0.0),
                    "payload": item.get("payload") if with_payload else None,
                    "vector": item.get("vector") if with_vectors else None,
                }
                for item in data.get("result", [])
            ]

    async def delete_by_filter(
        self,
        collection_name: str,
        filter_: Filter,
    ) -> int:
        """按条件删除点，返回删除数量。"""
        result = await self._client.delete(
            collection_name=collection_name,
            points_selector=filter_,
        )
        logger.info("🗑️ 删除 %s 条记录 from %s", getattr(result, "operation_id", "unknown"), collection_name)
        return getattr(result, "deleted_count", 0) or 0

    async def count(self, collection_name: str) -> int:
        """获取Collection中的总点数。"""
        result = await self._client.count(collection_name=collection_name)
        return result.count

    async def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """获取Collection详细信息(向量维度/点数/状态等)。"""
        info = await self._client.get_collection(collection_name=collection_name)
        return {
            "name": collection_name,
            "vectors_count": info.vectors_count,
            "status": info.status.value,
            "config": {
                "params": {
                    "size": info.config.params.vectors.size if info.config.params.vectors else 0,
                    "distance": info.config.params.vectors.distance.value if info.config.params.vectors else None,
                    "hnsw_m": (
                        info.config.params.vectors.hnsw_config.m
                        if (info.config.params.vectors and info.config.params.vectors.hnsw_config)
                        else None
                    ),
                },
            },
        }

    async def close(self):
        """关闭Qdrant客户端连接。"""
        global _qdrant_client
        if _qdrant_client is not None:
            await _qdrant_client.close()
            _qdrant_client = None
            logger.info("🔌 Qdrant连接已关闭")


async def close_qdrant():
    """关闭Qdrant客户端连接池。"""
    global _qdrant_client, _qdrant_mode, _qdrant_topology
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
    _qdrant_mode = None
    _qdrant_topology = None
    logger.info("🔌 Qdrant连接已关闭")


async def check_qdrant_health() -> dict:
    """
    检查Qdrant健康状态(D7验收标准)。

    Returns:
        dict: 健康状态信息
    """
    try:
        client = get_qdrant_client()
        collections = await client.get_collections()
        topology = client.describe_topology() if hasattr(client, "describe_topology") else get_qdrant_topology()
        return {
            "status": "healthy",
            "collections_count": len(collections.collections),
            "collection_names": [collection.name for collection in collections.collections],
            "backend_mode": topology.get("mode", _qdrant_mode or "unknown"),
            "writer_endpoint": topology.get("writer_endpoint"),
            "read_endpoints": topology.get("read_endpoints", []),
        }
    except Exception as exc:
        logger.error("❌ Qdrant健康检查失败: %s", exc)
        return {"status": "unhealthy", "error": str(exc), "backend_mode": _qdrant_mode or "unknown"}
