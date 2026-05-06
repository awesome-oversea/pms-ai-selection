"""
混合检索引擎
============

提供向量+关键词双路检索能力(D51-D55):
    - Qdrant向量检索(BGE Embedding)
    - ES关键词检索(BM25)
    - RRF/加权融合算法
    - 并行查询优化
    - 缓存策略

使用方式:
    from src.infrastructure.hybrid_retrieval import HybridRetriever

    retriever = HybridRetriever()
    results = await retriever.search("户外储能电源", top_k=10)
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class RetrievalPath(StrEnum):
    """检索路径。"""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass
class RetrievedDocument:
    """检索结果文档。"""
    doc_id: str
    content: str
    score: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_score: float | None = None
    keyword_score: float | None = None
    final_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "content": self.content[:500],
            "score": round(self.score, 4),
            "source": self.source,
            "metadata": self.metadata,
            "vector_score": self.vector_score,
            "keyword_score": self.keyword_score,
            "final_rank": self.final_rank,
        }


@dataclass
class RetrievalResult:
    """检索结果集。"""
    query: str
    documents: list[RetrievedDocument]
    total: int
    latency_ms: float
    path: RetrievalPath
    vector_latency_ms: float | None = None
    keyword_latency_ms: float | None = None
    fusion_method: str | None = None
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total": self.total,
            "latency_ms": round(self.latency_ms, 2),
            "path": self.path.value,
            "vector_latency_ms": self.vector_latency_ms,
            "keyword_latency_ms": self.keyword_latency_ms,
            "fusion_method": self.fusion_method,
            "cache_hit": self.cache_hit,
            "documents": [d.to_dict() for d in self.documents],
        }


class VectorStore:
    """
    向量存储模拟(Qdrant)。

    功能:
        - 文档Embedding存储
        - HNSW近似最近邻检索
        - 余弦相似度计算
    """

    def __init__(self, collection_name: str = "fms_documents"):
        self._collection_name = collection_name
        self._documents: dict[str, dict] = {}
        self._vectors: dict[str, list[float]] = {}
        logger.info(f"VectorStore初始化: {collection_name}")

    async def upsert(
        self,
        doc_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """插入/更新文档。"""
        vector = self._embed(content)
        self._documents[doc_id] = {
            "id": doc_id,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._vectors[doc_id] = vector

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_dict: dict | None = None,
    ) -> list[tuple[str, float]]:
        """向量检索。"""
        start = time.monotonic()
        query_vector = self._embed(query)
        scores = []
        for doc_id, doc_vector in self._vectors.items():
            if filter_dict:
                doc = self._documents.get(doc_id, {})
                if not self._match_filter(doc.get("metadata", {}), filter_dict):
                    continue
            score = self._cosine_similarity(query_vector, doc_vector)
            scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        latency = (time.monotonic() - start) * 1000
        logger.debug(f"向量检索完成: {len(scores)}条, {latency:.1f}ms")
        return scores[:top_k]

    def get_document(self, doc_id: str) -> dict | None:
        return self._documents.get(doc_id)

    def _embed(self, text: str) -> list[float]:
        """模拟BGE Embedding(实际应调用模型)。"""
        h = hashlib.md5(text.encode()).hexdigest()
        vector = [float(int(h[i : i + 2], 16) - 128) / 128 for i in range(0, 32, 2)]
        norm = sum(v * v for v in vector) ** 0.5
        return [v / max(norm, 0.001) for v in vector]

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        return dot / max(norm1 * norm2, 0.001)

    def _match_filter(self, metadata: dict, filter_dict: dict) -> bool:
        return all(metadata.get(k) == v for k, v in filter_dict.items())

    def get_stats(self) -> dict[str, Any]:
        return {
            "collection": self._collection_name,
            "document_count": len(self._documents),
            "vector_dimension": 16,
        }


class KeywordStore:
    """
    关键词存储模拟(Elasticsearch)。

    功能:
        - IK分词
        - BM25排序
        - 倒排索引检索
    """

    def __init__(self, index_name: str = "fms_documents"):
        self._index_name = index_name
        self._documents: dict[str, dict] = {}
        self._inverted_index: dict[str, set[str]] = {}
        self._doc_lengths: dict[str, int] = {}
        self._avg_doc_length = 100.0
        logger.info(f"KeywordStore初始化: {index_name}")

    async def index(
        self,
        doc_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """索引文档。"""
        tokens = self._tokenize(content)
        self._documents[doc_id] = {
            "id": doc_id,
            "content": content,
            "metadata": metadata or {},
            "tokens": tokens,
        }
        self._doc_lengths[doc_id] = len(tokens)
        for token in set(tokens):
            if token not in self._inverted_index:
                self._inverted_index[token] = set()
            self._inverted_index[token].add(doc_id)
        if self._doc_lengths:
            self._avg_doc_length = sum(self._doc_lengths.values()) / len(self._doc_lengths)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_dict: dict | None = None,
    ) -> list[tuple[str, float]]:
        """BM25检索。"""
        start = time.monotonic()
        query_tokens = self._tokenize(query)
        scores: dict[str, float] = {}
        k1, b = 1.5, 0.75
        N = len(self._documents)

        for token in query_tokens:
            posting = self._inverted_index.get(token, set())
            df = len(posting)
            if df == 0:
                continue
            idf = (N - df + 0.5) / (df + 0.5) + 1
            idf = max(idf, 0.1)

            for doc_id in posting:
                if filter_dict:
                    doc = self._documents.get(doc_id, {})
                    if not self._match_filter(doc.get("metadata", {}), filter_dict):
                        continue
                tf = self._documents[doc_id]["tokens"].count(token)
                doc_len = self._doc_lengths.get(doc_id, self._avg_doc_length)
                score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / self._avg_doc_length))
                scores[doc_id] = scores.get(doc_id, 0) + score

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        latency = (time.monotonic() - start) * 1000
        logger.debug(f"关键词检索完成: {len(sorted_scores)}条, {latency:.1f}ms")
        return sorted_scores[:top_k]

    def get_document(self, doc_id: str) -> dict | None:
        return self._documents.get(doc_id)

    def _tokenize(self, text: str) -> list[str]:
        """模拟IK分词。"""
        import re

        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        return tokens

    def _match_filter(self, metadata: dict, filter_dict: dict) -> bool:
        return all(metadata.get(k) == v for k, v in filter_dict.items())

    def get_stats(self) -> dict[str, Any]:
        return {
            "index": self._index_name,
            "document_count": len(self._documents),
            "term_count": len(self._inverted_index),
            "avg_doc_length": round(self._avg_doc_length, 1),
        }


class FusionAlgorithm:
    """
    融合算法(D52核心)。

    支持的融合方法:
        - RRF (Reciprocal Rank Fusion)
        - Weighted (加权融合)
        - Max (取最大分)
    """

    @staticmethod
    def rrf_fusion(
        vector_results: list[tuple[str, float]],
        keyword_results: list[tuple[str, float]],
        k: int = 60,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        RRF融合算法。

        公式: score(d) = Σ 1/(k + rank(d))
        """
        scores: dict[str, float] = {}
        for rank, (doc_id, _) in enumerate(vector_results):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        for rank, (doc_id, _) in enumerate(keyword_results):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    @staticmethod
    def weighted_fusion(
        vector_results: list[tuple[str, float]],
        keyword_results: list[tuple[str, float]],
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """加权融合。"""
        scores: dict[str, float] = {}
        for doc_id, score in vector_results:
            scores[doc_id] = scores.get(doc_id, 0) + score * vector_weight
        for doc_id, score in keyword_results:
            scores[doc_id] = scores.get(doc_id, 0) + score * keyword_weight
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    @staticmethod
    def max_fusion(
        vector_results: list[tuple[str, float]],
        keyword_results: list[tuple[str, float]],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """取最大分融合。"""
        scores: dict[str, float] = {}
        for doc_id, score in vector_results:
            scores[doc_id] = max(scores.get(doc_id, 0), score)
        for doc_id, score in keyword_results:
            scores[doc_id] = max(scores.get(doc_id, 0), score)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]


class QueryCache:
    """查询缓存。"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[list[tuple[str, float]], float]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, query: str, path: str) -> list[tuple[str, float]] | None:
        key = f"{path}:{hashlib.md5(query.encode()).hexdigest()}"
        if key in self._cache:
            results, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return results
            del self._cache[key]
        return None

    def set(self, query: str, path: str, results: list[tuple[str, float]]) -> None:
        if len(self._cache) >= self._max_size:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
        key = f"{path}:{hashlib.md5(query.encode()).hexdigest()}"
        self._cache[key] = (results, time.time())


class HybridRetriever:
    """
    混合检索引擎(D51-D55核心)。

    架构:
        Query → [Vector Path] → Qdrant ─┐
                                      ├→ Fusion → Top-K
               [Keyword Path] → ES ────┘

    功能:
        1. 双路并行检索
        2. RRF/加权融合
        3. 查询缓存
        4. 性能监控
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        keyword_store: KeywordStore | None = None,
        fusion_method: str = "rrf",
        cache_enabled: bool = True,
    ):
        self._vector_store = vector_store or VectorStore()
        self._keyword_store = keyword_store or KeywordStore()
        self._fusion_method = fusion_method
        self._cache = QueryCache() if cache_enabled else None
        self._stats = {
            "total_queries": 0,
            "cache_hits": 0,
            "avg_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
        }
        self._latencies: list[float] = []

    async def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """索引文档到双路存储。"""
        await asyncio.gather(
            self._vector_store.upsert(doc_id, content, metadata),
            self._keyword_store.index(doc_id, content, metadata),
        )
        logger.info(f"文档索引完成: {doc_id}")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_dict: dict | None = None,
        fusion_method: str | None = None,
    ) -> RetrievalResult:
        """
        混合检索(D53优化)。

        流程:
            1. 检查缓存
            2. 并行执行双路检索
            3. 融合排序
            4. 构建结果
        """
        start = time.monotonic()
        self._stats["total_queries"] += 1
        fusion = fusion_method or self._fusion_method

        if self._cache:
            cached = self._cache.get(query, "hybrid")
            if cached:
                self._stats["cache_hits"] += 1
                documents = self._build_documents(cached, {}, {})
                return RetrievalResult(
                    query=query,
                    documents=documents,
                    total=len(documents),
                    latency_ms=(time.monotonic() - start) * 1000,
                    path=RetrievalPath.HYBRID,
                    cache_hit=True,
                )

        vector_task = self._vector_store.search(query, top_k * 2, filter_dict)
        keyword_task = self._keyword_store.search(query, top_k * 2, filter_dict)
        vector_start = time.monotonic()
        keyword_start = time.monotonic()
        vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)
        vector_latency = (time.monotonic() - vector_start) * 1000
        keyword_latency = (time.monotonic() - keyword_start) * 1000

        if fusion == "rrf":
            fused = FusionAlgorithm.rrf_fusion(vector_results, keyword_results, top_k=top_k)
        elif fusion == "weighted":
            fused = FusionAlgorithm.weighted_fusion(vector_results, keyword_results, top_k=top_k)
        else:
            fused = FusionAlgorithm.max_fusion(vector_results, keyword_results, top_k=top_k)

        if self._cache:
            self._cache.set(query, "hybrid", fused)

        documents = self._build_documents(fused, dict(vector_results), dict(keyword_results))
        latency = (time.monotonic() - start) * 1000
        self._update_stats(latency)

        return RetrievalResult(
            query=query,
            documents=documents,
            total=len(documents),
            latency_ms=latency,
            path=RetrievalPath.HYBRID,
            vector_latency_ms=round(vector_latency, 2),
            keyword_latency_ms=round(keyword_latency, 2),
            fusion_method=fusion,
        )

    async def vector_search(
        self,
        query: str,
        top_k: int = 10,
        filter_dict: dict | None = None,
    ) -> RetrievalResult:
        """纯向量检索。"""
        start = time.monotonic()
        results = await self._vector_store.search(query, top_k, filter_dict)
        documents = self._build_documents(results, dict(results), {})
        latency = (time.monotonic() - start) * 1000
        return RetrievalResult(
            query=query,
            documents=documents,
            total=len(documents),
            latency_ms=latency,
            path=RetrievalPath.VECTOR,
        )

    async def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        filter_dict: dict | None = None,
    ) -> RetrievalResult:
        """纯关键词检索。"""
        start = time.monotonic()
        results = await self._keyword_store.search(query, top_k, filter_dict)
        documents = self._build_documents(results, {}, dict(results))
        latency = (time.monotonic() - start) * 1000
        return RetrievalResult(
            query=query,
            documents=documents,
            total=len(documents),
            latency_ms=latency,
            path=RetrievalPath.KEYWORD,
        )

    def _build_documents(
        self,
        fused: list[tuple[str, float]],
        vector_scores: dict[str, float],
        keyword_scores: dict[str, float],
    ) -> list[RetrievedDocument]:
        documents = []
        for rank, (doc_id, score) in enumerate(fused):
            vec_doc = self._vector_store.get_document(doc_id)
            kw_doc = self._keyword_store.get_document(doc_id)
            doc_data = vec_doc or kw_doc or {}
            documents.append(
                RetrievedDocument(
                    doc_id=doc_id,
                    content=doc_data.get("content", ""),
                    score=score,
                    source=doc_data.get("metadata", {}).get("source", "unknown"),
                    metadata=doc_data.get("metadata", {}),
                    vector_score=vector_scores.get(doc_id),
                    keyword_score=keyword_scores.get(doc_id),
                    final_rank=rank + 1,
                )
            )
        return documents

    def _update_stats(self, latency: float) -> None:
        self._latencies.append(latency)
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]
        self._stats["avg_latency_ms"] = round(sum(self._latencies) / len(self._latencies), 2)
        if self._latencies:
            self._stats["p99_latency_ms"] = round(sorted(self._latencies)[int(len(self._latencies) * 0.99)], 2)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "cache_hit_rate": round(self._stats["cache_hits"] / max(self._stats["total_queries"], 1), 4),
            "vector_store": self._vector_store.get_stats(),
            "keyword_store": self._keyword_store.get_stats(),
        }
