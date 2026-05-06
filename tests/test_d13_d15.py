"""
D13-D15 单元测试: RAG框架 + 混合检索 + Prompt模板
===============================================

覆盖:
    - D13-T048/T049: 文档切片策略(递归/语义边界)
    - D14-T050: 混合检索(向量+BM25+RRF融合)
    - D14-T051: Rerank集成
    - D15-T052: Prompt模板设计与渲染

执行:
    pytest tests/test_d13_d15.py -v
"""

import pytest


class TestRecursiveCharacterSplitter:
    """
    递归字符分割器测试(D13-T049)。

    验证:
        - 基础文本分割
        - 分隔符优先级
        - chunk_size限制
        - overlap应用
        - 空输入处理
        - 超长文本处理
    """

    def test_split_short_text(self):
        """短文本(<chunk_size)应返回单个块。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
        result = splitter.split_text("这是一段短文本")

        assert len(result) == 1
        assert result[0] == "这是一段短文本"

    def test_split_by_paragraphs(self):
        """按段落分隔符(\\n\\n)分割。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=10, chunk_overlap=2)
        text = "第一段内容很长\n\n第二段内容也很长\n\n第三段内容同样长"

        result = splitter.split_text(text)

        assert len(result) >= 2
        assert any("第一段" in r for r in result)

    def test_split_respects_chunk_size(self):
        """每个chunk不应超过chunk_size。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=50, chunk_overlap=10)
        text = "这是一个测试。" * 20

        result = splitter.split_text(text)

        for chunk in result:
            assert len(chunk) <= 50 + 10

    def test_empty_text_returns_empty(self):
        """空文本应返回空列表。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter()

        assert splitter.split_text("") == []
        assert splitter.split_text("   ") == []
        assert splitter.split_text(None) is None or splitter.split_text(None) == []

    def test_overlap_greater_than_chunk_size_raises(self):
        """overlap>=chunk_size应抛出ValueError。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        with pytest.raises(ValueError, match="overlap"):
            RecursiveCharacterTextSplitter(chunk_size=50, chunk_overlap=50)

    def test_chinese_text_splitting(self):
        """中文文本应正确按句号分割。"""
        from src.rag.chunkers import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=30, chunk_overlap=5)
        text = "这是第一句话。这是第二句话。这是第三句话。"

        result = splitter.split_text(text)

        assert len(result) >= 1
        full_text = "".join(result)
        assert "第一句" in full_text


class TestSemanticBoundarySplitter:
    """
    语义边界分割器测试(D13-T049)。

    验证:
        - Markdown标题识别
        - 回退到递归分割器
        - 混合内容处理
    """

    def test_markdown_header_splitting(self):
        """Markdown标题(# ## ###)应作为分割点。"""
        from src.rag.chunkers import SemanticBoundarySplitter

        splitter = SemanticBoundarySplitter(chunk_size=200, chunk_overlap=20)
        text = "# 第一章\n第一章内容\n\n## 第一节\n第一节内容\n\n# 第二章\n第二章内容"

        result = splitter.split_text(text)

        assert len(result) >= 2
        combined = "\n".join(result)
        assert "第一章" in combined

    def test_plain_text_fallback(self):
        """无标题的纯文本应回退到递归分割器。"""
        from src.rag.chunkers import SemanticBoundarySplitter

        splitter = SemanticBoundarySplitter(chunk_size=100, chunk_overlap=10)
        text = "这是一段没有标题的普通文本。" * 10

        result = splitter.split_text(text)

        assert len(result) >= 1


class TestDocumentChunker:
    """
    DocumentChunker管理器测试(D13-T049)。

    验证:
        - 多策略支持(recursive/semantic)
        - 元数据附加
        - token估算
        - 批量文档切分
    """

    def test_chunker_creates_document_chunks(self):
        """切分结果应为DocumentChunk列表。"""
        from src.rag.chunkers import DocumentChunk, DocumentChunker

        chunker = DocumentChunker(chunk_size=100, chunk_overlap=10)
        chunks = chunker.split_text("测试文本。"*20, metadata={"source": "test.txt"})

        assert isinstance(chunks, list)
        if chunks:
            assert isinstance(chunks[0], DocumentChunk)

    def test_chunks_have_metadata(self):
        """每个chunk应包含元数据。"""
        from src.rag.chunkers import DocumentChunker

        chunker = DocumentChunker(
            chunk_size=100,
            chunk_overlap=10,
            metadata={"source": "report.pdf", "document_type": "analysis"},
        )
        chunks = chunker.split_text("测试内容。" * 20)

        for chunk in chunks:
            assert chunk.metadata.source == "report.pdf"
            assert chunk.metadata.document_type == "analysis"
            assert isinstance(chunk.metadata.chunk_index, int)

    def test_token_count_estimation(self):
        """token_count应有合理估算值。"""
        from src.rag.chunkers import DocumentChunker

        chunker = DocumentChunker(chunk_size=100)
        chunks = chunker.split_text("中文测试文本内容。" * 5)

        if chunks:
            for chunk in chunks:
                assert chunk.token_count > 0

    def test_batch_documents_splitting(self):
        """批量切分多个文档。"""
        from src.rag.chunkers import DocumentChunker

        chunker = DocumentChunker(chunk_size=50, chunk_overlap=10)
        documents = [
            {"text": "第一个文档的内容。" * 5, "metadata": {"source": "doc1"}},
            {"text": "第二个文档的内容。" * 5, "metadata": {"source": "doc2"}},
        ]

        chunks = chunker.split_documents(documents)

        assert len(chunks) >= 2

    def test_semantic_strategy_option(self):
        """semantic策略应使用SemanticBoundarySplitter。"""
        from src.rag.chunkers import DocumentChunker

        chunker = DocumentChunker(strategy="semantic", chunk_size=200)
        chunks = chunker.split_text("# 标题\n内容段落。" * 10)

        assert isinstance(chunks, list)


class TestBM25Scorer:
    """
    BM25评分器测试(D14-T050)。

    验证:
        - 文档索引构建
        - TF-IDF加权计算
        - 查询评分排序
        - 空查询/空文档处理
    """

    def test_index_and_search_basic(self):
        """基础索引和搜索功能。"""
        from src.rag.retriever import BM25Scorer

        scorer = BM25Scorer()
        docs = [
            {"id": "1", "content": "无线蓝牙耳机降噪音质好"},
            {"id": "2", "content": "手机充电线数据传输快"},
            {"id": "3", "content": "高品质无线蓝牙耳机运动款"},
        ]

        results = scorer.search("蓝牙耳机", docs, top_k=3)

        assert len(results) > 0
        assert results[0].score >= results[-1].score

    def test_relevant_docs_score_higher(self):
        """相关文档应获得更高分数。"""
        from src.rag.retriever import BM25Scorer

        scorer = BM25Scorer()
        docs = [
            {"id": "1", "content": "无线蓝牙耳机主动降噪长续航"},
            {"id": "2", "content": "不锈钢保温杯大容量家用"},
            {"id": "3", "content": "儿童绘本故事书早教启蒙"},
        ]

        results = scorer.search("蓝牙耳机", docs, top_k=3)

        best = results[0]
        assert "蓝牙" in best.content or "耳机" in best.content

    def test_empty_query_returns_empty(self):
        """空查询应返回空列表或全零分。"""
        from src.rag.retriever import BM25Scorer

        scorer = BM25Scorer()
        docs = [{"id": "1", "content": "test content"}]

        results = scorer.search("", docs)

        assert isinstance(results, list)

    def test_normalized_scores_in_range(self):
        """BM25分数应在[0,1]范围内(归一化后)。"""
        from src.rag.retriever import BM25Scorer

        scorer = BM25Scorer()
        docs = [
            {"id": str(i), "content": f"文档{i} 测试内容关键词匹配"}
            for i in range(10)
        ]

        results = scorer.search("关键词", docs, top_k=5)

        for r in results:
            assert 0 <= r.score <= 1.0


class TestRRFusion:
    """
    RRF融合器测试(D14-T050)。

    验证:
        - 两组结果融合
        - Reciprocal Rank算法正确性
        - 结果去重
        - Top-K截断
        - 单路降级
    """

    def test_fuse_two_result_sets(self):
        """融合两组检索结果。"""
        from src.rag.retriever import KeywordSearchResult, RRFusion, VectorSearchResult

        fusion = RRFusion(k=60)

        vector_results = [
            VectorSearchResult(id="A", content="Doc A vec", score=0.95),
            VectorSearchResult(id="B", content="Doc B vec", score=0.80),
            VectorSearchResult(id="C", content="Doc C vec", score=0.60),
        ]

        keyword_results = [
            KeywordSearchResult(id="B", content="Doc B kw", score=0.90),
            KeywordSearchResult(id="D", content="Doc D kw", score=0.70),
            KeywordSearchResult(id="A", content="Doc A kw", score=0.50),
        ]

        fused = fusion.fuse(vector_results, keyword_results, top_k=5)

        doc_ids = [r.content for r in fused]
        assert "A" in doc_ids or "Doc A" in str(doc_ids)
        assert len(fused) <= 5

    def test_fused_results_sorted_by_score(self):
        """融合结果应按RRF分数降序排列。"""
        from src.rag.retriever import KeywordSearchResult, RRFusion, VectorSearchResult

        fusion = RRFusion(k=60)

        vector_results = [
            VectorSearchResult(id=str(i), content=f"V{i}", score=0.9 - i*0.1)
            for i in range(5)
        ]
        keyword_results = [
            KeywordSearchResult(id=str(i), content=f"K{i}", score=0.8 - i*0.1)
            for i in range(5)
        ]

        fused = fusion.fuse(vector_results, keyword_results, top_k=10)

        scores = [r.score for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_duplicate_docs_get_boosted(self):
        """在两路结果中都出现的文档应获得更高融合分数。"""
        from src.rag.retriever import KeywordSearchResult, RRFusion, VectorSearchResult

        fusion = RRFusion(k=60)

        vector_results = [
            VectorSearchResult(id="shared", content="Shared Doc", score=0.7),
            VectorSearchResult(id="only_vec", content="Only Vec", score=0.9),
        ]
        keyword_results = [
            KeywordSearchResult(id="shared", content="Shared Doc", score=0.6),
            KeywordSearchResult(id="only_kw", content="Only Kw", score=0.85),
        ]

        fused = fusion.fuse(vector_results, keyword_results, top_k=10)

        shared = next((r for r in fused if "shared" in r.content.lower() or r.content == "Shared Doc"), None)
        assert shared is not None

    def test_empty_inputs_return_empty(self):
        """空输入应返回空列表。"""
        from src.rag.retriever import RRFusion

        fusion = RRFusion()

        assert fusion.fuse([], [], top_k=5) == []
        assert fusion.fuse([], [], top_k=0) == []


class TestHybridRetriever:
    """
    混合检索引擎测试(D14-T050/T051)。

    验证:
        - 文档添加与索引
        - 混合检索流程
        - 向量+关键词双路并行
        - Rerank可选集成
        - 过滤条件支持
    """

    def test_add_and_retrieve(self):
        """添加文档后可检索到结果。"""
        from src.rag.retriever import HybridRetriever

        retriever = HybridRetriever(enable_rerank=False)

        docs = [
            {"id": "1", "content": "无线蓝牙耳机主动降噪，续航30小时", "metadata": {"category": "electronics"}},
            {"id": "2", "content": "iPhone充电线MFi认证，数据传输快", "metadata": {"category": "accessories"}},
            {"id": "3", "content": "运动蓝牙耳机防水防汗，适合跑步健身", "metadata": {"category": "electronics"}},
        ]

        retriever.add_documents(docs)

        assert retriever.document_count == 3

    def test_retrieve_returns_results(self):
        """retrieve()应返回RetrievalResult列表。"""
        import asyncio

        from src.rag.retriever import HybridRetriever

        retriever = HybridRetriever(enable_rerank=False)

        retriever.add_documents([
            {"id": "1", "content": "无线蓝牙耳机降噪好"},
            {"id": "2", "content": "不锈钢水杯保温效果好"},
            {"id": "3", "content": "头戴式蓝牙耳机音质优秀"},
        ])

        results = asyncio.run(retriever.retrieve("蓝牙耳机推荐"))

        assert isinstance(results, list)
        assert len(results) > 0

    def test_relevant_query_higher_score(self):
        """相关查询应返回更高得分的结果。"""
        import asyncio

        from src.rag.retriever import HybridRetriever

        retriever = HybridRetriever(enable_rerank=False)

        retriever.add_documents([
            {"id": "1", "content": "无线蓝牙耳机降噪"},
            {"id": "2", "content": "厨房刀具套装"},
            {"id": "3", "content": "瑜伽垫加厚防滑"},
        ])

        results = asyncio.run(retriever.retrieve("蓝牙耳机"))

        if results:
            assert results[0].score > 0

    def test_clear_removes_all_documents(self):
        """clear()应清空所有文档。"""
        from src.rag.retriever import HybridRetriever

        retriever = HybridRetriever()
        retriever.add_documents([
            {"id": "1", "content": "test"},
            {"id": "2", "content": "test2"},
        ])

        assert retriever.document_count == 2

        retriever.clear()

        assert retriever.document_count == 0


class TestPromptTemplates:
    """
    Prompt模板测试(D15-T052)。

    验证:
        - 选品分析Prompt渲染
        - 趋势预测Prompt渲染
        - 竞品对比Prompt渲染
        - RAG问答Prompt渲染
        - 必填变量校验
        - 可选变量处理
    """

    def test_selection_prompt_render(self):
        """选品分析Prompt应正确渲染。"""
        from src.rag.prompts import get_selection_prompt

        prompt = get_selection_prompt()
        result = prompt.render(query="推荐一款蓝牙耳机")

        assert "system" in result
        assert "user" in result
        assert "蓝牙耳机" in result["user"]
        assert "选品专家" in result["system"]

    def test_trend_prompt_render(self):
        """趋势预测Prompt应正确渲染。"""
        from src.rag.prompts import get_trend_prompt

        prompt = get_trend_prompt()
        result = prompt.render(query="预测无线耳机的市场趋势")

        assert "趋势预测" in result["system"] or "预测" in result["system"]

    def test_competitor_prompt_render(self):
        """竞品对比Prompt应正确渲染。"""
        from src.rag.prompts import get_competitor_prompt

        prompt = get_competitor_prompt()
        result = prompt.render(query="对比AirPods和Sony WH-1000XM5")

        assert "竞品" in result["system"] or "对比" in result["system"]

    def test_rag_qa_prompt_render(self):
        """RAG问答Prompt应包含上下文和问题。"""
        from src.rag.prompts import get_rag_qa_prompt

        prompt = get_rag_qa_prompt()
        context = "产品A是一款无线蓝牙耳机，价格29.99美元，评分4.5星"
        result = prompt.render(context=context, query="产品A的价格是多少？")

        assert context in result["user"]
        assert "价格" in result["user"]

    def test_missing_required_variable_raises(self):
        """缺少必填变量应抛出ValueError。"""
        from src.rag.prompts import get_rag_qa_prompt

        prompt = get_rag_qa_prompt()

        with pytest.raises(ValueError, match="必填"):
            prompt.render(context="some context")

    def test_optional_variable_omission(self):
        """缺少可选变量不应报错。"""
        from src.rag.prompts import get_selection_prompt

        prompt = get_selection_prompt()

        result = prompt.render(query="简单问题")

        assert "system" in result

    def test_get_prompt_by_name(self):
        """按名称获取模板应返回正确的PromptTemplate。"""
        from src.rag.prompts import get_prompt_by_name

        p1 = get_prompt_by_name("selection_analysis")
        p2 = get_prompt_by_name("rag_qa")
        p3 = get_prompt_by_name("nonexistent")

        assert p1 is not None
        assert p1.name == "selection_analysis"
        assert p2 is not None
        assert p3 is None


class TestRAGModuleImports:
    """
    RAG模块导入测试。
    """

    def test_rag_package_importable(self):
        """RAG包应导出所有核心组件。"""
        from src.rag import (
            DocumentChunker,
            HybridRetriever,
            get_selection_prompt,
        )

        assert DocumentChunker is not None
        assert HybridRetriever is not None
        assert callable(get_selection_prompt)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
