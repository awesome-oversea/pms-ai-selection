"""
任务 3.2 验收测试：文本分块与向量入库流程
==========================================

验收标准:
- [x] RecursiveCharacterTextSplitter 对 5000 字文本正确分块（每块 ≤ chunk_size）
- [x] indexer.py 的 index_documents() 将文本分块 → 编码 → 写入 Qdrant
- [x] mock 模式下全流程可执行（不依赖真实 Embedding 模型和 Qdrant 服务）
- [x] 入库后通过 QdrantService.search() 可检索到对应文档
"""

import pytest
from src.rag.chunkers import RecursiveCharacterTextSplitter
from src.rag.indexer import DocumentIndexer, IndexResult, MockQdrantBackend

# ---------------------------------------------------------------------------
# 辅助数据
# ---------------------------------------------------------------------------

def _make_long_text(char_count: int = 5000) -> str:
    """生成指定长度的中文测试文本。"""
    paragraphs = [
        "跨境电商行业近年来呈现出爆发式增长态势。根据最新的市场研究报告，全球跨境电商市场规模已经突破了万亿美元大关。",
        "在产品选品过程中，数据采集是至关重要的第一步。我们需要从多个电商平台获取产品信息、价格走势、用户评价等关键数据。",
        "市场分析阶段需要对采集到的数据进行深度挖掘。通过分析市场趋势、竞争格局和消费者偏好，可以识别出具有潜力的产品机会。",
        "人工智能技术在选品领域的应用正在改变传统的决策模式。基于大语言模型的智能分析系统能够快速处理海量数据并给出专业建议。",
        "向量检索技术使得语义化搜索成为可能。通过将文本转换为高维向量表示，我们可以实现基于语义相似度的精准匹配。",
        "BM25算法作为经典的文本检索方法，在关键词匹配方面仍然具有不可替代的优势。结合向量检索的混合检索方案是当前主流趋势。",
        "产品规划阶段需要综合考虑市场需求、竞争态势、供应链能力等多维度因素，制定出切实可行的产品开发计划。",
        "商业化评估是选品流程的最后一道关卡。需要对产品的盈利能力、投资回报率、风险因素等进行全面的量化评估。",
    ]
    text = ""
    while len(text) < char_count:
        for p in paragraphs:
            text += p + "\n\n"
            if len(text) >= char_count:
                break
    return text[:char_count]


# ---------------------------------------------------------------------------
# 1. RecursiveCharacterTextSplitter 分块验证
# ---------------------------------------------------------------------------

class TestChunker:
    def test_5000_char_text_all_chunks_within_limit(self):
        """5000 字文本分块后每块 ≤ chunk_size。"""
        text = _make_long_text(5000)
        splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
        chunks = splitter.split_text(text)

        assert len(chunks) >= 5, f"5000字应至少分5块，实际 {len(chunks)}"
        for i, c in enumerate(chunks):
            assert len(c) <= 512, f"块 {i} 长度 {len(c)} 超出 chunk_size=512"

    def test_short_text_not_split(self):
        """短文本不拆分。"""
        splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
        chunks = splitter.split_text("这是一段短文本。")
        assert len(chunks) == 1

    def test_empty_text(self):
        """空文本返回空列表。"""
        splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
        assert splitter.split_text("") == []
        assert splitter.split_text("   ") == []


# ---------------------------------------------------------------------------
# 2. DocumentIndexer 全流程 (mock 模式)
# ---------------------------------------------------------------------------

class TestDocumentIndexer:
    @pytest.fixture
    def mock_backend(self):
        return MockQdrantBackend()

    @pytest.fixture
    def indexer(self, mock_backend):
        return DocumentIndexer(
            collection_name="test_collection",
            chunk_size=256,
            chunk_overlap=30,
            qdrant_backend=mock_backend,
        )

    @pytest.mark.asyncio
    async def test_index_documents_full_pipeline(self, indexer, mock_backend):
        """完整流程: 文本分块 → Embedding → Qdrant upsert。"""
        docs = [
            _make_long_text(1000),
            "短文档：无线蓝牙耳机市场分析。",
        ]

        result = await indexer.index_documents(docs)

        assert isinstance(result, IndexResult)
        assert result.success is True
        assert result.total_documents == 2
        assert result.total_chunks > 0
        assert result.total_vectors_upserted == result.total_chunks
        assert result.collection_name == "test_collection"

        # 验证 mock backend 中确实存储了数据
        stored = mock_backend.get_all_points("test_collection")
        assert len(stored) == result.total_vectors_upserted

    @pytest.mark.asyncio
    async def test_index_then_search(self, indexer, mock_backend):
        """入库后通过 search() 可检索到对应文档。"""
        docs = [
            "跨境电商AI选品系统支持智能数据采集和市场分析功能。",
            "向量检索技术让语义搜索成为可能，基于余弦相似度匹配。",
            "BM25算法在关键词匹配方面具有优势。",
        ]

        result = await indexer.index_documents(docs)
        assert result.success is True

        # 使用与第一条文档相关的查询进行检索
        search_results = await indexer.search("AI选品数据采集", limit=5, score_threshold=0.0)

        assert len(search_results) > 0
        # 结果包含 payload 且有 text 字段
        assert "payload" in search_results[0]
        assert "text" in search_results[0]["payload"]

    @pytest.mark.asyncio
    async def test_index_empty_documents(self, indexer):
        """空文档列表 → errors 非空。"""
        result = await indexer.index_documents([])
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_index_result_has_correct_counts(self, indexer, mock_backend):
        """验证 IndexResult 中的统计数字一致性。"""
        docs = [_make_long_text(2000)]
        result = await indexer.index_documents(docs)

        assert result.total_documents == 1
        assert result.total_chunks > 1  # 2000字 / 256 chunk_size ≈ 8+
        assert result.total_vectors_upserted == result.total_chunks

    @pytest.mark.asyncio
    async def test_index_with_metadata(self, indexer, mock_backend):
        """入库时附带元数据，payload 中能查到。"""
        docs = ["产品A描述信息，包含多项技术参数和市场定位分析。"]
        result = await indexer.index_documents(
            docs, metadata={"source": "report.pdf", "category": "electronics"}
        )
        assert result.success is True

        stored = mock_backend.get_all_points("test_collection")
        assert len(stored) > 0
        payload = stored[0]["payload"]
        assert payload.get("source") == "report.pdf"


# ---------------------------------------------------------------------------
# 3. MockQdrantBackend 单元测试
# ---------------------------------------------------------------------------

class TestMockQdrantBackend:
    @pytest.mark.asyncio
    async def test_ensure_collection(self):
        backend = MockQdrantBackend()
        created = await backend.ensure_collection("col1", vector_size=128)
        assert created is True
        created2 = await backend.ensure_collection("col1", vector_size=128)
        assert created2 is False  # 已存在

    @pytest.mark.asyncio
    async def test_count(self):
        backend = MockQdrantBackend()
        await backend.ensure_collection("col1")
        assert await backend.count("col1") == 0

    @pytest.mark.asyncio
    async def test_search_empty_collection(self):
        backend = MockQdrantBackend()
        results = await backend.search("nonexist", [0.1] * 128)
        assert results == []
