"""
混合检索引擎
============

提供向量+关键词混合检索能力(D14-T050):
    - 向量检索路(Qdrant HNSW)
    - 关键词检索路(BM25模拟)
    - RRF(Reciprocal Rank Fusion)融合排序
    - 结果合并去重

使用方式:
    from src.rag.retriever import HybridRetriever

    retriever = HybridRetriever()
    results = await retriever.retrieve("无线蓝牙耳机推荐", top_k=10)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from src.config.settings import get_settings
from src.core.logging import get_logger
from src.infrastructure.redis import CacheService, get_redis_connection
from src.rag.collections import resolve_qdrant_collection_name

logger = get_logger(__name__)

_RETRIEVER_CACHE_FALLBACK: dict[str, str] = {}


@dataclass
class RetrievalResult:
    """
    检索结果项。

    Attributes:
        content: 文档内容片段
        score: 综合相关性得分(0-1)
        vector_score: 向量检索得分
        keyword_score: 关键词检索得分
        source: 来源标识
        metadata: 额外元数据
        rank: 融合后的排名
    """

    content: str
    score: float = 0.0
    vector_score: float | None = None
    keyword_score: float | None = None
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    rank: int = 0


@dataclass
class VectorSearchResult:
    """向量检索中间结果。"""
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KeywordSearchResult:
    """关键词检索中间结果。"""
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class BM25Scorer:
    """
    BM25关键词评分器(D14-T050)。

    实现BM25算法用于文本相关性评分:
        - TF-IDF加权
        - 文档长度归一化
        - 参数k1(词频饱和度), b(长度惩罚)

    用于模拟ES的BM25检索能力。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._doc_freqs: dict[str, int] = {}
        self._doc_lengths: list[int] = []
        self._avg_dl: float = 0.0
        self._corpus_size: int = 0
        self._indexed: bool = False

    def index_documents(self, documents: list[dict[str, Any]]):
        """
        索引文档集合用于BM25评分。

        Args:
            documents: 文档列表，每项包含id和content
        """
        self._doc_freqs.clear()
        self._doc_lengths.clear()

        total_length = 0

        for doc in documents:
            tokens = self._tokenize(doc.get("content", ""))
            unique_tokens = set(tokens)

            for token in unique_tokens:
                self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1

            self._doc_lengths.append(len(tokens))
            total_length += len(tokens)

        self._corpus_size = len(documents)
        self._avg_dl = total_length / max(self._corpus_size, 1)
        self._indexed = True

        logger.info(f"📚 BM25索引完成: {self._corpus_size}篇文档, {len(self._doc_freqs)}个唯一词")

    def search(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[KeywordSearchResult]:
        """
        BM25搜索。

        Args:
            query: 查询文本
            documents: 候选文档列表
            top_k: 返回Top-K结果

        Returns:
            list[KeywordSearchResult]: BM25评分结果
        """
        if not self._indexed:
            self.index_documents(documents)

        query_tokens = self._tokenize(query)

        scored_docs = []

        for idx, doc in enumerate(documents):
            content = doc.get("content", "")
            doc_tokens = self._tokenize(content)

            tf_map: dict[str, int] = {}
            for token in doc_tokens:
                tf_map[token] = tf_map.get(token, 0) + 1

            dl = self._doc_lengths[idx] if idx < len(self._doc_lengths) else len(doc_tokens)

            score = 0.0
            for token in query_tokens:
                if token not in tf_map:
                    continue

                tf = tf_map[token]
                df = self._doc_freqs.get(token, 0)

                idf = math.log(
                    (self._corpus_size - df + 0.5) / (df + 0.5) + 1.0
                )

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * dl / max(self._avg_dl, 1)
                )

                score += idf * numerator / denominator

            scored_docs.append(KeywordSearchResult(
                id=doc.get("id", str(idx)),
                content=content,
                score=score,
                metadata=doc.get("metadata", {}),
            ))

        scored_docs.sort(key=lambda x: x.score, reverse=True)

        results = scored_docs[:top_k]

        max_score = results[0].score if results else 1.0
        for r in results:
            r.score = r.score / max(max_score, 1e-10)

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        简单分词器(D14-T050)。

        中文按字符切分 + 英文按空格切分，
        生产环境应替换为jieba等专用分词器。
        """
        text = text.lower().strip()

        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        english_words = re.findall(r"[a-z0-9]+", text)

        return chinese_chars + english_words


class RRFusion:
    """
    Reciprocal Rank Fusion融合器(D14-T050)。

    RRF算法:
        score(d) = Σ 1/(k + rank_i(d))

        其中k通常取60，rank_i(d)是文档在第i个检索结果中的排名。

    优势:
        - 无需归一化不同检索器的得分
        - 对异常分数鲁棒
        - 计算简单高效
    """

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(
        self,
        vector_results: list[VectorSearchResult],
        keyword_results: list[KeywordSearchResult],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """
        融合两组检索结果。

        Args:
            vector_results: 向量检索结果列表
            keyword_results: 关键词检索结果列表
            top_k: 最终返回数量

        Returns:
            list[RetrievalResult]: 融合排序后的结果
        """
        scores: dict[str, dict] = {}

        for rank, result in enumerate(vector_results, 1):
            doc_id = result.id
            if doc_id not in scores:
                scores[doc_id] = {
                    "rrf_score": 0.0,
                    "vector_score": result.score,
                    "keyword_score": None,
                    "content": result.content,
                    "source": result.metadata.get("source", ""),
                    "metadata": {**result.metadata, "id": doc_id},
                }
            scores[doc_id]["rrf_score"] += 1.0 / (self.k + rank)
            scores[doc_id]["vector_score"] = result.score

        for rank, result in enumerate(keyword_results, 1):
            doc_id = result.id
            if doc_id not in scores:
                scores[doc_id] = {
                    "rrf_score": 0.0,
                    "vector_score": None,
                    "keyword_score": result.score,
                    "content": result.content,
                    "source": result.metadata.get("source", ""),
                    "metadata": {**result.metadata, "id": doc_id},
                }
            scores[doc_id]["rrf_score"] += 1.0 / (self.k + rank)
            scores[doc_id]["keyword_score"] = result.score

        fused = sorted(
            scores.items(),
            key=lambda x: x[1]["rrf_score"],
            reverse=True,
        )[:top_k]

        max_rrf = fused[0][1]["rrf_score"] if fused else 1.0

        results = []
        for rank, (doc_id, data) in enumerate(fused, 1):
            normalized_score = data["rrf_score"] / max(max_rrf, 1e-10)

            results.append(RetrievalResult(
                content=data["content"],
                score=round(normalized_score, 6),
                vector_score=data["vector_score"],
                keyword_score=data["keyword_score"],
                source=data["source"],
                metadata=data["metadata"],
                rank=rank,
            ))

        logger.debug(f"🔗 RRF融合完成: {len(vector_results)}向量 + {len(keyword_results)}关键词 → {len(results)}结果")
        return results


class HybridRetriever:
    """
    混合检索引擎(D14-T050)。

    整合两条检索路径:
        1. 向量检索: Embedding → Qdrant HNSW → Top-K
        2. 关键词检索: BM25 → Top-K

    通过RRF融合后输出最终排序结果，
    可选接Rerank精排(D14-T051)。

    Attributes:
        vector_top_k: 向量检索返回数量
        keyword_top_k: 关键词检索返回数量
        fusion_top_k: 融合后最终返回数量
        enable_rerank: 是否启用Rerank精排
    """

    def __init__(
        self,
        vector_top_k: int = 20,
        keyword_top_k: int = 20,
        fusion_top_k: int = 10,
        enable_rerank: bool = False,
        rerank_top_k: int = 5,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 3600,
        cache_similarity_threshold: float = 0.95,
        qdrant_collection_name: str | None = None,
        enable_qdrant_vector_search: bool = True,
    ):
        self.vector_top_k = vector_top_k
        self.keyword_top_k = keyword_top_k
        self.fusion_top_k = fusion_top_k
        self.enable_rerank = enable_rerank
        self.rerank_top_k = rerank_top_k
        self.cache_enabled = cache_enabled
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_similarity_threshold = cache_similarity_threshold
        self.cache_backend = "disabled" if not cache_enabled else "auto"
        self.cache_hits = 0
        self.cache_misses = 0
        self.qdrant_collection_name = (qdrant_collection_name or "").strip() or None
        self.enable_qdrant_vector_search = enable_qdrant_vector_search
        self.vector_backend = "embedding-memory"
        self.vector_backend_status = "active"
        self.vector_backend_reason: str | None = None

        self._bm25 = BM25Scorer()
        self._rrf = RRFusion()
        self._documents: list[dict[str, Any]] = []

    def add_documents(self, documents: list[dict[str, Any]]):
        """
        添加文档到检索库。

        Args:
            documents: 文档列表 [{"id": ..., "content": ..., "metadata": ...}, ...]
        """
        self._documents.extend(documents)
        self._bm25.index_documents(self._documents)
        logger.info(f"📥 添加 {len(documents)} 篇文档到检索库 (总计: {len(self._documents)})")

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """
        执行混合检索。

        Args:
            query: 用户查询
            top_k: 返回数量(None=使用fusion_top_k)
            filters: 元数据过滤条件

        Returns:
            list[RetrievalResult]: 检索结果列表(按score降序)
        """
        k = top_k or self.fusion_top_k
        if self.cache_enabled:
            cached = await self._read_cache(query=query, top_k=k, filters=filters)
            if cached is not None:
                return cached

        vector_results = await self._vector_search(query, self.vector_top_k)
        keyword_results = self._keyword_search(query, self.keyword_top_k)

        if filters:
            vector_results = [r for r in vector_results if self._match_filters(r.metadata, filters)]
            keyword_results = [r for r in keyword_results if self._match_filters(r.metadata, filters)]

        fused = self._rrf.fuse(vector_results, keyword_results, top_k=k)

        if self.enable_rerank and fused:
            from src.services.rerank import RerankService

            reranker = RerankService()
            docs = [r.content for r in fused]
            reranked = reranker.rerank(query, docs, top_k=self.rerank_top_k)

            reranked_map = {r["document"]: r["score"] for r in reranked}

            for r in fused:
                r.score = reranked_map.get(r.content, r.score)

            fused.sort(key=lambda x: x.score, reverse=True)
            fused = fused[:self.rerank_top_k]
            for rank, item in enumerate(fused, 1):
                item.rank = rank
        if self.cache_enabled:
            await self._write_cache(query=query, top_k=k, filters=filters, results=fused)

        return fused

    async def _read_cache(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None,
    ) -> list[RetrievalResult] | None:
        entries, backend = await self._load_cache_entries()
        self.cache_backend = backend
        now = datetime.now(UTC)
        normalized_query = self._normalize_cache_query(query)
        filters_fingerprint = self._filters_fingerprint(filters)
        corpus_fingerprint = self._corpus_fingerprint()
        best_payload: dict[str, Any] | None = None
        best_similarity = 0.0
        for raw in entries.values():
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if int(payload.get("top_k") or 0) != int(top_k):
                continue
            if payload.get("filters_fingerprint") != filters_fingerprint:
                continue
            if payload.get("corpus_fingerprint") != corpus_fingerprint:
                continue
            try:
                expires_at = datetime.fromisoformat(str(payload.get("expires_at")))
            except Exception:
                continue
            if expires_at < now:
                continue
            similarity = SequenceMatcher(a=normalized_query, b=str(payload.get("normalized_query") or "")).ratio()
            if similarity >= self.cache_similarity_threshold and similarity > best_similarity:
                best_payload = payload
                best_similarity = similarity
        if best_payload is None:
            self.cache_misses += 1
            return None
        self.cache_hits += 1
        return [self._deserialize_result(item, best_similarity=best_similarity, cached_query=str(best_payload.get("query") or query), cache_backend=backend) for item in best_payload.get("results") or []]

    async def _write_cache(
        self,
        *,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None,
        results: list[RetrievalResult],
    ) -> None:
        payload = {
            "query": query,
            "normalized_query": self._normalize_cache_query(query),
            "top_k": int(top_k),
            "filters_fingerprint": self._filters_fingerprint(filters),
            "corpus_fingerprint": self._corpus_fingerprint(),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=self.cache_ttl_seconds)).isoformat(),
            "results": [self._serialize_result(item) for item in results],
        }
        cache_key = hashlib.sha256(f"{query}:{top_k}:{payload['filters_fingerprint']}:{payload['corpus_fingerprint']}".encode()).hexdigest()
        serialized = json.dumps(payload, ensure_ascii=False)
        hash_name = self._cache_hash_name()
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            await cache.hset(hash_name, cache_key, serialized)
            await cache.expire(hash_name, self.cache_ttl_seconds)
            self.cache_backend = "redis"
        except Exception:
            _RETRIEVER_CACHE_FALLBACK[cache_key] = serialized
            self.cache_backend = "memory"

    async def _load_cache_entries(self) -> tuple[dict[str, str], str]:
        try:
            redis_client = get_redis_connection()
            cache = CacheService(redis_client)
            payload = await cache.hgetall(self._cache_hash_name())
            return payload if isinstance(payload, dict) else {}, "redis"
        except Exception:
            return dict(_RETRIEVER_CACHE_FALLBACK), "memory"

    @staticmethod
    def _cache_hash_name() -> str:
        return "rag:hybrid-retriever:query-cache"

    @staticmethod
    def _normalize_cache_query(query: str) -> str:
        return "".join(str(query).lower().split())

    @staticmethod
    def _filters_fingerprint(filters: dict[str, Any] | None) -> str:
        return hashlib.sha256(json.dumps(filters or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _corpus_fingerprint(self) -> str:
        source = [
            {
                "id": doc.get("id"),
                "content": doc.get("content"),
                "metadata": doc.get("metadata", {}),
            }
            for doc in self._documents
        ]
        return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_result(result: RetrievalResult) -> dict[str, Any]:
        return {
            "content": result.content,
            "score": result.score,
            "vector_score": result.vector_score,
            "keyword_score": result.keyword_score,
            "source": result.source,
            "metadata": result.metadata,
            "rank": result.rank,
        }

    @staticmethod
    def _deserialize_result(payload: dict[str, Any], *, best_similarity: float, cached_query: str, cache_backend: str) -> RetrievalResult:
        metadata = dict(payload.get("metadata") or {})
        metadata["cache_hit"] = True
        metadata["cache_backend"] = cache_backend
        metadata["cache_similarity"] = round(best_similarity, 6)
        metadata["cached_query"] = cached_query
        return RetrievalResult(
            content=str(payload.get("content") or ""),
            score=float(payload.get("score") or 0.0),
            vector_score=payload.get("vector_score"),
            keyword_score=payload.get("keyword_score"),
            source=str(payload.get("source") or ""),
            metadata=metadata,
            rank=int(payload.get("rank") or 0),
        )

    def get_cache_stats(self) -> dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        return {
            "enabled": self.cache_enabled,
            "backend": self.cache_backend,
            "ttl_seconds": self.cache_ttl_seconds,
            "similarity_threshold": self.cache_similarity_threshold,
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": round(self.cache_hits / max(total, 1), 4),
        }

    async def _vector_search(
        self,
        query: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        """向量检索路径。"""
        try:
            from src.services.embedding import EmbeddingService

            embedder = EmbeddingService()
            query_vector = embedder.encode_single(query)
            if self.enable_qdrant_vector_search:
                qdrant_results = await self._search_qdrant(query_vector=query_vector, top_k=top_k)
                if qdrant_results:
                    return qdrant_results
            else:
                self.vector_backend = "embedding-memory"
                self.vector_backend_status = "active"
                self.vector_backend_reason = "qdrant disabled for in-memory document set"

            results = []
            for idx, doc in enumerate(self._documents[:top_k * 3]):
                import numpy as np

                doc_text = doc.get("content", "")
                doc_vector = embedder.encode_single(doc_text[:200])

                cosine_sim = np.dot(query_vector, doc_vector) / (
                    np.linalg.norm(query_vector) * np.linalg.norm(doc_vector) + 1e-10
                )

                metadata = dict(doc.get("metadata", {}))
                metadata.setdefault("vector_backend", self.vector_backend)
                metadata.setdefault("vector_backend_status", self.vector_backend_status)
                if self.vector_backend_reason:
                    metadata.setdefault("vector_backend_reason", self.vector_backend_reason)
                results.append(VectorSearchResult(
                    id=doc.get("id", str(idx)),
                    content=doc_text,
                    score=float(cosine_sim),
                    metadata=metadata,
                ))

            self.vector_backend = "embedding-memory"
            if self.enable_qdrant_vector_search:
                self.vector_backend_status = "fallback"
                self.vector_backend_reason = self.vector_backend_reason or "qdrant unavailable or returned no results"
            else:
                self.vector_backend_status = "active"
                self.vector_backend_reason = "qdrant disabled for in-memory document set"
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

        except Exception as e:
            self.vector_backend = "embedding-memory"
            self.vector_backend_status = "unavailable"
            self.vector_backend_reason = str(e)
            logger.warning(f"⚠️ 向量检索失败，降级为空结果: {e}")
            return []

    async def _search_qdrant(self, *, query_vector: list[float], top_k: int) -> list[VectorSearchResult]:
        try:
            from src.infrastructure.qdrant import QdrantService, get_qdrant_client

            settings = get_settings()
            client = get_qdrant_client()
            service = QdrantService(client)
            collection_name = resolve_qdrant_collection_name(
                self.qdrant_collection_name or getattr(settings.qdrant, "collection_name", None)
            )
            raw_results = await service.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=0.0,
            )
            if not raw_results:
                self.vector_backend = "qdrant"
                self.vector_backend_status = "active"
                self.vector_backend_reason = "qdrant returned no hits"
                return []

            self.vector_backend = "qdrant"
            self.vector_backend_status = "active"
            self.vector_backend_reason = None
            return [
                VectorSearchResult(
                    id=str(item.get("id") or f"qdrant-{index}"),
                    content=str((item.get("payload") or {}).get("content") or (item.get("payload") or {}).get("text") or ""),
                    score=float(item.get("score") or 0.0),
                    metadata={
                        **dict(item.get("payload") or {}),
                        "vector_backend": "qdrant",
                        "vector_backend_status": "active",
                    },
                )
                for index, item in enumerate(raw_results)
            ]
        except Exception as exc:
            self.vector_backend = "embedding-memory"
            self.vector_backend_status = "fallback"
            self.vector_backend_reason = str(exc)
            logger.info(f"Qdrant 检索不可用，回退内存向量检索: {exc}")
            return []

    def _keyword_search(
        self,
        query: str,
        top_k: int,
    ) -> list[KeywordSearchResult]:
        """关键词检索路径(BM25)。"""
        if not self._documents:
            return []

        return self._bm25.search(query, self._documents, top_k=top_k)

    @staticmethod
    def _match_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        """检查元数据是否匹配过滤条件。"""
        for key, value in filters.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def clear(self):
        """清空文档库。"""
        self._documents.clear()
        self._bm25 = BM25Scorer()

    def get_runtime_status(self) -> dict[str, Any]:
        return {
            "vector_backend": self.vector_backend,
            "vector_backend_status": self.vector_backend_status,
            "vector_backend_reason": self.vector_backend_reason,
            "cache_backend": self.cache_backend,
            "cache_enabled": self.cache_enabled,
            "document_count": self.document_count,
        }


def create_hybrid_retriever(
    vector_top_k: int = 20,
    keyword_top_k: int = 20,
    fusion_top_k: int = 10,
    qdrant_collection_name: str | None = None,
    enable_qdrant_vector_search: bool = True,
    enable_rerank: bool = False,
    rerank_top_k: int = 5,
    cache_enabled: bool = True,
) -> HybridRetriever:
    """创建HybridRetriever工厂函数。"""
    return HybridRetriever(
        vector_top_k=vector_top_k,
        keyword_top_k=keyword_top_k,
        fusion_top_k=fusion_top_k,
        qdrant_collection_name=qdrant_collection_name,
        enable_qdrant_vector_search=enable_qdrant_vector_search,
        enable_rerank=enable_rerank,
        rerank_top_k=rerank_top_k,
        cache_enabled=cache_enabled,
    )
