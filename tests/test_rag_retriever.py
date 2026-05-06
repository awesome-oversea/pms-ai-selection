"""
任务 3.3 验收测试：RRF 混合检索
================================

验收标准:
- [x] BM25Scorer 对索引文档返回合理的 TF-IDF 分数
- [x] HybridRetriever.search() 返回融合排序的 RetrievalResult 列表
- [x] 融合结果的 score 字段值在 0-1 范围内
- [x] 向量和关键词结果正确去重（同一文档不重复出现）
"""

import pytest
from src.rag.retriever import (
    BM25Scorer,
    HybridRetriever,
    KeywordSearchResult,
    RetrievalResult,
    RRFusion,
    VectorSearchResult,
    create_hybrid_retriever,
)

# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {"id": "doc1", "content": "跨境电商AI选品系统支持智能数据采集和市场分析功能", "metadata": {"source": "a"}},
    {"id": "doc2", "content": "向量检索技术使得语义搜索成为可能基于余弦相似度匹配", "metadata": {"source": "b"}},
    {"id": "doc3", "content": "BM25算法在关键词匹配方面仍然具有不可替代的优势", "metadata": {"source": "c"}},
    {"id": "doc4", "content": "无线蓝牙耳机市场规模持续增长成为热门品类之一", "metadata": {"source": "d"}},
    {"id": "doc5", "content": "人工智能大语言模型在自然语言处理领域取得突破性进展", "metadata": {"source": "e"}},
]


# ---------------------------------------------------------------------------
# 1. BM25Scorer 测试
# ---------------------------------------------------------------------------

class TestBM25Scorer:
    def test_index_and_search(self):
        """BM25 索引后搜索返回合理分数。"""
        scorer = BM25Scorer()
        results = scorer.search("AI选品数据采集", SAMPLE_DOCS, top_k=5)

        assert len(results) > 0
        # 最高分应归一化为 1.0
        assert results[0].score == pytest.approx(1.0, abs=1e-6)
        # 所有分数在 [0, 1]
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"BM25 score {r.score} 超出范围"

    def test_search_returns_keyword_search_result(self):
        """返回类型为 KeywordSearchResult。"""
        scorer = BM25Scorer()
        results = scorer.search("蓝牙耳机", SAMPLE_DOCS, top_k=3)
        assert all(isinstance(r, KeywordSearchResult) for r in results)

    def test_relevant_doc_ranked_higher(self):
        """包含查询关键词的文档排名更高。"""
        scorer = BM25Scorer()
        results = scorer.search("蓝牙耳机", SAMPLE_DOCS, top_k=5)
        # doc4 包含"蓝牙耳机"，应该排名靠前
        top_ids = [r.id for r in results[:2]]
        assert "doc4" in top_ids

    def test_empty_query(self):
        """空查询返回 0 分结果。"""
        scorer = BM25Scorer()
        results = scorer.search("", SAMPLE_DOCS, top_k=5)
        # 所有分数应为 0
        for r in results:
            assert r.score == pytest.approx(0.0, abs=1e-6)

    def test_index_documents_updates_state(self):
        """index_documents 后内部状态正确更新。"""
        scorer = BM25Scorer()
        scorer.index_documents(SAMPLE_DOCS)
        assert scorer._indexed is True
        assert scorer._corpus_size == 5
        assert scorer._avg_dl > 0


# ---------------------------------------------------------------------------
# 2. RRFusion 测试
# ---------------------------------------------------------------------------

class TestRRFusion:
    def test_fuse_basic(self):
        """基本融合：两组结果合并去重。"""
        vec_results = [
            VectorSearchResult(id="doc1", content="内容1", score=0.95),
            VectorSearchResult(id="doc2", content="内容2", score=0.80),
        ]
        kw_results = [
            KeywordSearchResult(id="doc2", content="内容2", score=1.0),
            KeywordSearchResult(id="doc3", content="内容3", score=0.6),
        ]

        rrf = RRFusion(k=60)
        fused = rrf.fuse(vec_results, kw_results, top_k=5)

        assert len(fused) == 3  # doc1, doc2, doc3 去重后 3 个
        ids = [r.content for r in fused]
        assert len(set(ids)) == len(ids)  # 无重复

    def test_fuse_scores_in_range(self):
        """融合后分数在 0-1 范围内。"""
        vec_results = [
            VectorSearchResult(id=f"v{i}", content=f"vec内容{i}", score=0.9 - i * 0.1)
            for i in range(5)
        ]
        kw_results = [
            KeywordSearchResult(id=f"k{i}", content=f"kw内容{i}", score=1.0 - i * 0.2)
            for i in range(5)
        ]
        rrf = RRFusion(k=60)
        fused = rrf.fuse(vec_results, kw_results, top_k=10)

        for r in fused:
            assert 0.0 <= r.score <= 1.0, f"RRF score {r.score} 超出 [0,1]"

    def test_fuse_dedup_same_doc(self):
        """同一文档同时出现在两组结果中时，只出现一次。"""
        vec = [VectorSearchResult(id="shared", content="共享", score=0.9)]
        kw = [KeywordSearchResult(id="shared", content="共享", score=0.8)]

        rrf = RRFusion(k=60)
        fused = rrf.fuse(vec, kw, top_k=5)

        assert len(fused) == 1
        # 共享文档应同时有 vector_score 和 keyword_score
        assert fused[0].vector_score is not None
        assert fused[0].keyword_score is not None

    def test_fuse_returns_retrieval_result(self):
        """返回类型为 RetrievalResult。"""
        rrf = RRFusion()
        fused = rrf.fuse(
            [VectorSearchResult(id="a", content="a", score=0.5)],
            [KeywordSearchResult(id="b", content="b", score=0.5)],
        )
        assert all(isinstance(r, RetrievalResult) for r in fused)


# ---------------------------------------------------------------------------
# 3. HybridRetriever 集成测试
# ---------------------------------------------------------------------------

class TestHybridRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_results(self):
        """HybridRetriever.retrieve() 返回融合排序的结果。"""
        retriever = create_hybrid_retriever(
            vector_top_k=10, keyword_top_k=10, fusion_top_k=5,
        )
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve("AI选品数据采集")

        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)

    @pytest.mark.asyncio
    async def test_retrieve_exposes_runtime_status(self):
        retriever = create_hybrid_retriever()
        retriever.add_documents(SAMPLE_DOCS)

        await retriever.retrieve("蓝牙耳机市场分析")
        status = retriever.get_runtime_status()

        assert status["vector_backend"] in {"qdrant", "embedding-memory"}
        assert status["vector_backend_status"] in {"active", "fallback", "unavailable"}
        assert status["document_count"] == len(SAMPLE_DOCS)

    @pytest.mark.asyncio
    async def test_retrieve_scores_in_range(self):
        """所有结果 score 在 [0, 1]。"""
        retriever = create_hybrid_retriever()
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve("蓝牙耳机市场分析")

        for r in results:
            assert 0.0 <= r.score <= 1.0, f"score {r.score} 超出范围"

    @pytest.mark.asyncio
    async def test_retrieve_no_duplicates(self):
        """融合结果中无重复文档。"""
        retriever = create_hybrid_retriever()
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve("向量检索语义搜索")

        contents = [r.content for r in results]
        assert len(contents) == len(set(contents)), "检索结果存在重复文档"

    @pytest.mark.asyncio
    async def test_retrieve_with_filters(self):
        """带 filters 的检索应过滤不匹配的文档。"""
        retriever = create_hybrid_retriever()
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve(
            "AI", filters={"source": "a"},
        )
        for r in results:
            assert r.source == "a"

    @pytest.mark.asyncio
    async def test_retrieve_with_in_memory_only_mode_skips_qdrant(self, monkeypatch):
        class _FakeEmbeddingService:
            def encode_single(self, text: str):
                base = float(len(text.split()) or len(text) or 1)
                return [base, base / 2.0, 1.0]

        async def _unexpected_qdrant_search(*_args, **_kwargs):
            raise AssertionError("qdrant search should be disabled")

        monkeypatch.setattr("src.services.embedding.EmbeddingService", _FakeEmbeddingService)

        retriever = HybridRetriever(enable_qdrant_vector_search=False)
        retriever._search_qdrant = _unexpected_qdrant_search  # type: ignore[method-assign]
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve("AIѡƷ���ݲɼ�")

        assert len(results) > 0
        assert retriever.vector_backend == "embedding-memory"
        assert retriever.vector_backend_status == "active"
        assert retriever.vector_backend_reason == "qdrant disabled for in-memory document set"

    @pytest.mark.asyncio
    async def test_retrieve_with_rerank_promotes_keyword_relevant_document(self):
        """启用 rerank 后应对 RRF 结果进行精排。"""
        retriever = create_hybrid_retriever(
            vector_top_k=5,
            keyword_top_k=5,
            fusion_top_k=5,
            enable_qdrant_vector_search=False,
            enable_rerank=True,
            rerank_top_k=3,
            cache_enabled=False,
        )
        retriever.add_documents(SAMPLE_DOCS)

        results = await retriever.retrieve("蓝牙耳机 市场", top_k=5)

        assert len(results) == 3
        assert results[0].content == "无线蓝牙耳机市场规模持续增长成为热门品类之一"
        assert results[0].rank == 1

    @pytest.mark.asyncio
    async def test_hybrid_retrieval_mrr_reaches_phase32_threshold(self):
        """Phase 3.2 验收：混合检索 MRR 应达到 0.7。"""
        retriever = create_hybrid_retriever(
            vector_top_k=10,
            keyword_top_k=10,
            fusion_top_k=5,
            enable_qdrant_vector_search=False,
            enable_rerank=True,
            rerank_top_k=5,
            cache_enabled=False,
        )
        retriever.add_documents(SAMPLE_DOCS)
        cases = [
            ("AI选品 数据采集", "doc1"),
            ("向量检索 语义搜索", "doc2"),
            ("BM25 关键词匹配", "doc3"),
            ("蓝牙耳机 市场规模", "doc4"),
            ("大语言模型 自然语言处理", "doc5"),
        ]
        reciprocal_ranks = []

        for query, expected_id in cases:
            results = await retriever.retrieve(query, top_k=5)
            ranked_ids = [item.metadata.get("id") for item in results]
            matched_rank = next((idx for idx, doc_id in enumerate(ranked_ids, 1) if doc_id == expected_id), None)
            reciprocal_ranks.append(0.0 if matched_rank is None else 1.0 / matched_rank)

        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
        assert mrr >= 0.7

    def test_document_count(self):
        """add_documents 后 document_count 正确。"""
        retriever = create_hybrid_retriever()
        assert retriever.document_count == 0
        retriever.add_documents(SAMPLE_DOCS)
        assert retriever.document_count == 5

    def test_clear(self):
        """clear() 后文档数为 0。"""
        retriever = create_hybrid_retriever()
        retriever.add_documents(SAMPLE_DOCS)
        retriever.clear()
        assert retriever.document_count == 0
