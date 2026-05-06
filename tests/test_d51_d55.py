"""D51-D55 单元测试: 混合检索增强"""


import pytest
from src.infrastructure.hybrid_retrieval import (
    FusionAlgorithm,
    HybridRetriever,
    KeywordStore,
    QueryCache,
    RetrievalPath,
    RetrievalResult,
    RetrievedDocument,
    VectorStore,
)


class TestVectorStore:
    """测试向量存储(D51)"""

    def setup_method(self):
        self.store = VectorStore("test_collection")

    def test_initialization(self):
        assert self.store._collection_name == "test_collection"
        assert len(self.store._documents) == 0

    @pytest.mark.asyncio
    async def test_upsert_document(self):
        await self.store.upsert("doc_1", "户外储能电源产品介绍")
        assert "doc_1" in self.store._documents
        assert "doc_1" in self.store._vectors

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        await self.store.upsert("doc_1", "户外储能电源")
        await self.store.upsert("doc_2", "蓝牙耳机产品")
        results = await self.store.search("储能电源", top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_ranking(self):
        await self.store.upsert("doc_1", "户外储能电源大容量")
        await self.store.upsert("doc_2", "蓝牙耳机无线")
        results = await self.store.search("储能电源", top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_document(self):
        await self.store.upsert("doc_1", "测试内容", {"source": "test"})
        doc = self.store.get_document("doc_1")
        assert doc["content"] == "测试内容"
        assert doc["metadata"]["source"] == "test"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.store.upsert("doc_1", "内容1")
        await self.store.upsert("doc_2", "内容2")
        stats = self.store.get_stats()
        assert stats["document_count"] == 2


class TestKeywordStore:
    """测试关键词存储(D51)"""

    def setup_method(self):
        self.store = KeywordStore("test_index")

    def test_initialization(self):
        assert self.store._index_name == "test_index"
        assert len(self.store._documents) == 0

    @pytest.mark.asyncio
    async def test_index_document(self):
        await self.store.index("doc_1", "户外储能电源产品")
        assert "doc_1" in self.store._documents
        assert len(self.store._inverted_index) > 0

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        await self.store.index("doc_1", "outdoor power station battery")
        await self.store.index("doc_2", "bluetooth earphone wireless")
        results = await self.store.search("power station", top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_bm25_ranking(self):
        await self.store.index("doc_1", "储能电源 储能电源 储能电源")
        await self.store.index("doc_2", "储能")
        results = await self.store.search("储能电源", top_k=5)
        assert results[0][0] == "doc_1"

    def test_tokenize_chinese(self):
        tokens = self.store._tokenize("户外储能电源产品")
        assert len(tokens) >= 1
        assert any("储" in t or "能" in t for t in tokens)

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.store.index("doc_1", "测试内容")
        stats = self.store.get_stats()
        assert stats["document_count"] == 1


class TestFusionAlgorithm:
    """测试融合算法(D52)"""

    def test_rrf_fusion(self):
        vector_results = [("doc_1", 0.9), ("doc_2", 0.8), ("doc_3", 0.7)]
        keyword_results = [("doc_2", 5.0), ("doc_4", 4.0), ("doc_1", 3.0)]
        fused = FusionAlgorithm.rrf_fusion(vector_results, keyword_results, top_k=5)
        assert len(fused) == 4
        assert fused[0][0] in ["doc_1", "doc_2"]

    def test_rrf_fusion_empty_vector(self):
        keyword_results = [("doc_1", 5.0), ("doc_2", 4.0)]
        fused = FusionAlgorithm.rrf_fusion([], keyword_results, top_k=5)
        assert len(fused) == 2

    def test_rrf_fusion_empty_keyword(self):
        vector_results = [("doc_1", 0.9), ("doc_2", 0.8)]
        fused = FusionAlgorithm.rrf_fusion(vector_results, [], top_k=5)
        assert len(fused) == 2

    def test_weighted_fusion(self):
        vector_results = [("doc_1", 0.9), ("doc_2", 0.8)]
        keyword_results = [("doc_1", 0.5), ("doc_3", 0.4)]
        fused = FusionAlgorithm.weighted_fusion(
            vector_results, keyword_results,
            vector_weight=0.6, keyword_weight=0.4, top_k=5
        )
        assert len(fused) == 3

    def test_weighted_fusion_weights(self):
        vector_results = [("doc_1", 1.0)]
        keyword_results = [("doc_1", 1.0)]
        fused = FusionAlgorithm.weighted_fusion(
            vector_results, keyword_results,
            vector_weight=0.7, keyword_weight=0.3, top_k=1
        )
        assert abs(fused[0][1] - 1.0) < 0.001

    def test_max_fusion(self):
        vector_results = [("doc_1", 0.9), ("doc_2", 0.5)]
        keyword_results = [("doc_1", 0.3), ("doc_2", 0.8)]
        fused = FusionAlgorithm.max_fusion(vector_results, keyword_results, top_k=5)
        assert len(fused) == 2
        doc_scores = dict(fused)
        assert doc_scores["doc_1"] == 0.9
        assert doc_scores["doc_2"] == 0.8


class TestQueryCache:
    """测试查询缓存(D53)"""

    def setup_method(self):
        self.cache = QueryCache(max_size=10, ttl_seconds=60)

    def test_cache_miss(self):
        result = self.cache.get("测试查询", "hybrid")
        assert result is None

    def test_cache_set_and_get(self):
        results = [("doc_1", 0.9), ("doc_2", 0.8)]
        self.cache.set("测试查询", "hybrid", results)
        cached = self.cache.get("测试查询", "hybrid")
        assert cached == results

    def test_cache_max_size(self):
        small_cache = QueryCache(max_size=2, ttl_seconds=60)
        small_cache.set("query1", "hybrid", [("doc_1", 0.9)])
        small_cache.set("query2", "hybrid", [("doc_2", 0.8)])
        small_cache.set("query3", "hybrid", [("doc_3", 0.7)])
        assert small_cache.get("query1", "hybrid") is None or small_cache.get("query2", "hybrid") is None


class TestHybridRetriever:
    """测试混合检索器(D51-D55)"""

    def setup_method(self):
        self.retriever = HybridRetriever()

    def test_initialization(self):
        assert self.retriever._fusion_method == "rrf"
        assert self.retriever._cache is not None

    @pytest.mark.asyncio
    async def test_index_document(self):
        await self.retriever.index_document(
            "doc_1", "户外储能电源产品介绍", {"source": "amazon"}
        )
        stats = self.retriever.get_stats()
        assert stats["vector_store"]["document_count"] == 1
        assert stats["keyword_store"]["document_count"] == 1

    @pytest.mark.asyncio
    async def test_hybrid_search(self):
        await self.retriever.index_document("doc_1", "户外储能电源大容量便携")
        await self.retriever.index_document("doc_2", "蓝牙耳机降噪无线")
        result = await self.retriever.search("储能电源", top_k=5)
        assert result.total >= 1
        assert result.path == RetrievalPath.HYBRID
        assert result.fusion_method == "rrf"

    @pytest.mark.asyncio
    async def test_vector_search_only(self):
        await self.retriever.index_document("doc_1", "户外储能电源")
        result = await self.retriever.vector_search("储能电源", top_k=5)
        assert result.path == RetrievalPath.VECTOR

    @pytest.mark.asyncio
    async def test_keyword_search_only(self):
        await self.retriever.index_document("doc_1", "户外储能电源")
        result = await self.retriever.keyword_search("储能电源", top_k=5)
        assert result.path == RetrievalPath.KEYWORD

    @pytest.mark.asyncio
    async def test_search_with_cache(self):
        await self.retriever.index_document("doc_1", "户外储能电源")
        await self.retriever.search("储能电源", top_k=5)
        result = await self.retriever.search("储能电源", top_k=5)
        assert result.cache_hit is True

    @pytest.mark.asyncio
    async def test_fusion_methods(self):
        retriever = HybridRetriever(cache_enabled=False)
        await retriever.index_document("doc_1", "户外储能电源")
        await retriever.index_document("doc_2", "蓝牙耳机")

        rrf_result = await retriever.search("储能", top_k=5, fusion_method="rrf")
        weighted_result = await retriever.search("储能", top_k=5, fusion_method="weighted")
        max_result = await retriever.search("储能", top_k=5, fusion_method="max")

        assert rrf_result.fusion_method == "rrf"
        assert weighted_result.fusion_method == "weighted"
        assert max_result.fusion_method == "max"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.retriever.index_document("doc_1", "测试")
        await self.retriever.search("测试", top_k=5)
        stats = self.retriever.get_stats()
        assert stats["total_queries"] == 1
        assert "avg_latency_ms" in stats


class TestRetrievedDocument:
    """测试检索结果文档"""

    def test_document_creation(self):
        doc = RetrievedDocument(
            doc_id="doc_1",
            content="测试内容",
            score=0.95,
            source="test",
            metadata={"key": "value"},
        )
        assert doc.doc_id == "doc_1"
        assert doc.score == 0.95

    def test_document_to_dict(self):
        doc = RetrievedDocument(
            doc_id="doc_1",
            content="测试内容" * 100,
            score=0.95,
            source="test",
        )
        d = doc.to_dict()
        assert d["doc_id"] == "doc_1"
        assert len(d["content"]) <= 500


class TestRetrievalResult:
    """测试检索结果集"""

    def test_result_creation(self):
        docs = [RetrievedDocument(doc_id="doc_1", content="test", score=0.9, source="test")]
        result = RetrievalResult(
            query="测试",
            documents=docs,
            total=1,
            latency_ms=50.0,
            path=RetrievalPath.HYBRID,
        )
        assert result.total == 1
        assert result.path == RetrievalPath.HYBRID

    def test_result_to_dict(self):
        docs = [RetrievedDocument(doc_id="doc_1", content="test", score=0.9, source="test")]
        result = RetrievalResult(
            query="测试",
            documents=docs,
            total=1,
            latency_ms=50.0,
            path=RetrievalPath.HYBRID,
            fusion_method="rrf",
        )
        d = result.to_dict()
        assert d["query"] == "测试"
        assert d["fusion_method"] == "rrf"
        assert len(d["documents"]) == 1


class TestPerformance:
    """性能测试(D53)"""

    @pytest.mark.asyncio
    async def test_parallel_search_latency(self):
        """测试并行检索延迟(D53)"""
        import time
        retriever = HybridRetriever()
        for i in range(10):
            await retriever.index_document(f"doc_{i}", f"产品{i} 描述内容")

        start = time.time()
        result = await retriever.search("产品", top_k=5)
        latency = (time.time() - start) * 1000

        assert latency < 200
        assert result.latency_ms < 200

    @pytest.mark.asyncio
    async def test_cache_improves_latency(self):
        retriever = HybridRetriever()
        await retriever.index_document("doc_1", "测试内容")

        await retriever.search("测试", top_k=5)
        cached_result = await retriever.search("测试", top_k=5)

        assert cached_result.cache_hit is True
        assert cached_result.latency_ms < 10


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
