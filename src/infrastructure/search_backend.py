from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.config.settings import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class _DefaultSearchSettings:
    enabled = False
    backend = "memory"
    endpoint = None
    username = None
    password = None
    index_prefix = "pms_knowledge_"
    timeout_seconds = 5.0


class SearchBackend:
    INDEX_MAPPING_FIELDS = ["content", "tenant_id", "document_id", "chunk_index", "source"]

    def __init__(self) -> None:
        self.settings = getattr(get_settings(), "search", _DefaultSearchSettings())
        self._memory_docs: list[dict[str, Any]] = []
        self._client = None
        self._last_reindex: dict[str, Any] | None = None
        self._last_probe: dict[str, Any] | None = None

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.enabled)

    @property
    def backend_name(self) -> str:
        return self.settings.backend

    def build_index_name(self, tenant_id: str) -> str:
        return f"{self.settings.index_prefix}{tenant_id.replace('-', '')}"

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.endpoint or self.settings.backend == "memory":
            return None
        try:
            if self.settings.backend == "opensearch":
                from opensearchpy import OpenSearch

                self._client = OpenSearch(
                    hosts=[self.settings.endpoint],
                    http_auth=(self.settings.username, self.settings.password) if self.settings.username else None,
                    timeout=self.settings.timeout_seconds,
                )
            else:
                from elasticsearch import Elasticsearch

                self._client = Elasticsearch(
                    self.settings.endpoint,
                    basic_auth=(self.settings.username, self.settings.password) if self.settings.username else None,
                    request_timeout=self.settings.timeout_seconds,
                )
        except Exception as e:
            logger.warning(f"搜索后端 client 初始化失败，回退 memory: {e}")
            self._client = None
        return self._client

    def _build_index_mapping(self) -> dict[str, Any]:
        return {
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "tenant_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "source": {"type": "keyword"},
                }
            }
        }

    def probe_backend(self) -> dict[str, Any]:
        client = self._get_client()
        probed_at = datetime.now(UTC).isoformat()
        if client is None:
            self._last_probe = {
                "probed_at": probed_at,
                "reachable": False,
                "backend": self.backend_name,
                "endpoint": self.settings.endpoint,
                "reason": "search client unavailable, using memory bm25 fallback",
            }
            return dict(self._last_probe)
        try:
            info = client.info() if hasattr(client, "info") else {}
            self._last_probe = {
                "probed_at": probed_at,
                "reachable": True,
                "backend": self.backend_name,
                "endpoint": self.settings.endpoint,
                "cluster_name": info.get("cluster_name") if isinstance(info, dict) else None,
                "version": ((info.get("version") or {}).get("number") if isinstance(info, dict) else None),
                "reason": None,
            }
        except Exception as e:
            logger.warning(f"搜索后端探测失败，回退 memory: {e}")
            self._last_probe = {
                "probed_at": probed_at,
                "reachable": False,
                "backend": self.backend_name,
                "endpoint": self.settings.endpoint,
                "reason": str(e),
            }
        return dict(self._last_probe)

    def ensure_index(self, index_name: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            if hasattr(client, "indices") and not client.indices.exists(index=index_name):
                client.indices.create(index=index_name, body=self._build_index_mapping())
            return True
        except Exception as e:
            logger.warning(f"搜索后端索引初始化失败，回退 memory: {e}")
            return False

    async def index_documents(self, index_name: str, documents: list[dict[str, Any]]) -> None:
        self._memory_docs = documents
        client = self._get_client()
        if client is None:
            return
        try:
            self.ensure_index(index_name)
            for i, doc in enumerate(documents):
                payload = {**doc.get("metadata", {}), "content": doc.get("content", "")}
                if self.settings.backend == "opensearch":
                    client.index(index=index_name, id=doc.get("id", str(i)), body=payload)
                else:
                    client.index(index=index_name, id=doc.get("id", str(i)), document=payload)
            if hasattr(client, "indices"):
                client.indices.refresh(index=index_name)
        except Exception as e:
            logger.warning(f"搜索后端写入失败，保留 memory fallback: {e}")

    async def reindex_documents(self, index_name: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
        client = self._get_client()
        index_ready = self.ensure_index(index_name) if client is not None else False
        await self.index_documents(index_name, documents)
        self._last_reindex = {
            "index_name": index_name,
            "document_count": len(documents),
            "backend": self.backend_name,
            "client_configured": client is not None,
            "index_ready": index_ready,
            "effective_mode": self.backend_name if index_ready and self.backend_name != "memory" else "memory",
            "fallback_used": not index_ready,
            "reindexed_at": datetime.now(UTC).isoformat(),
        }
        return dict(self._last_reindex)

    async def delete_by_document(self, index_name: str, document_id: str, tenant_id: str) -> None:
        self._memory_docs = [
            doc
            for doc in self._memory_docs
            if not (
                str((doc.get("metadata") or {}).get("document_id")) == str(document_id)
                and str((doc.get("metadata") or {}).get("tenant_id")) == str(tenant_id)
            )
        ]
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete_by_query(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"document_id": document_id}},
                                {"term": {"tenant_id": tenant_id}},
                            ]
                        }
                    }
                },
            )
        except Exception as e:
            logger.warning(f"搜索后端删除失败，保留 memory fallback: {e}")

    async def keyword_search(
        self,
        index_name: str,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        if client is not None:
            try:
                must_filters = []
                for key, value in (filters or {}).items():
                    must_filters.append({"term": {key: value}})
                body = {
                    "size": top_k,
                    "query": {
                        "bool": {
                            "must": [{"match": {"content": query}}],
                            "filter": must_filters,
                        }
                    },
                }
                resp = client.search(index=index_name, body=body)
                hits = resp.get("hits", {}).get("hits", [])
                return [
                    {
                        "content": hit.get("_source", {}).get("content", ""),
                        "score": float(hit.get("_score", 0.0)),
                        "source": hit.get("_source", {}).get("source"),
                        "document_id": hit.get("_source", {}).get("document_id"),
                        "chunk_index": hit.get("_source", {}).get("chunk_index"),
                        "metadata": hit.get("_source", {}),
                    }
                    for hit in hits
                ]
            except Exception as e:
                logger.warning(f"搜索后端查询失败，回退 memory fallback: {e}")

        query_terms = set(query.lower().split())
        scored: list[dict[str, Any]] = []
        for doc in self._memory_docs:
            metadata = doc.get("metadata", {})
            if filters and any(metadata.get(k) != v for k, v in filters.items()):
                continue
            content = doc.get("content", "")
            terms = set(content.lower().split())
            score = len(query_terms & terms)
            if score <= 0:
                continue
            scored.append(
                {
                    "content": content,
                    "score": float(score),
                    "source": metadata.get("source"),
                    "document_id": metadata.get("document_id"),
                    "chunk_index": metadata.get("chunk_index"),
                    "metadata": metadata,
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def build_status(self) -> dict[str, Any]:
        probe = self.probe_backend()
        client_configured = bool(probe.get("reachable"))
        effective_mode = self.backend_name if client_configured and self.backend_name != "memory" else "memory"
        return {
            "enabled": self.is_enabled,
            "backend": self.backend_name,
            "endpoint": self.settings.endpoint,
            "index_prefix": self.settings.index_prefix,
            "client_configured": self._get_client() is not None,
            "client_available": client_configured,
            "effective_mode": effective_mode,
            "fallback_mode": "memory-bm25",
            "fallback_reason": None if client_configured else probe.get("reason") or "search client unavailable, using memory bm25 fallback",
            "reindex_ready": True,
            "index_mapping_fields": self.INDEX_MAPPING_FIELDS,
            "memory_doc_count": len(self._memory_docs),
            "last_probe": probe,
            "last_reindex": self._last_reindex,
        }


_search_backend_singleton: SearchBackend | None = None


def get_search_backend() -> SearchBackend:
    global _search_backend_singleton
    if _search_backend_singleton is None:
        _search_backend_singleton = SearchBackend()
    return _search_backend_singleton
