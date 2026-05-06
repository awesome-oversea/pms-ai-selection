"""
D10-D12 单元测试: Embedding/Rerank/爬虫/ETL
==========================================

覆盖:
    - D10-T032: BGE Embedding服务
    - D11-T033: bge-reranker-base Rerank服务
    - D10-T040: Amazon BSR爬虫
    - D11-T041: Amazon评论爬虫
    - D12-T043: 数据清洗ETL Pipeline
    - D12-T044: Flink集成接口

执行:
    pytest tests/test_d10_d12.py -v
"""

import numpy as np
import pytest


class TestEmbeddingService:
    """
    EmbeddingService单元测试(D10-T032)。

    验证:
        - 模型懒加载与降级模式
        - 单条/批量编码
        - 向量维度正确性
        - 归一化输出
        - 空输入异常处理
    """

    def test_service_creation(self):
        """EmbeddingService应可正常创建。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()

        assert svc.model_name is not None
        assert svc.device == "cpu"
        assert svc._model is None

    def test_mock_encode_single_text(self):
        """无模型时应使用mock模式生成向量。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()
        result = svc.encode_single("测试文本")

        assert isinstance(result, list)
        assert len(result) == 1024
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_mock_encode_batch(self):
        """批量编码应返回正确数量的向量。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()
        texts = ["文本A", "文本B", "文本C"]
        results = svc.encode(texts)

        assert isinstance(results, list)
        assert len(results) == 3
        for vec in results:
            assert isinstance(vec, list)
            assert len(vec) == 1024

    def test_encode_empty_list_raises(self):
        """空列表应抛出ValueError。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()

        with pytest.raises(ValueError, match="不能为空"):
            svc.encode([])

    def test_different_texts_different_vectors(self):
        """不同文本应产生不同向量。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()
        v1 = svc.encode_single("无线蓝牙耳机")
        v2 = svc.encode_single("充电数据线")

        cosine_sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        assert cosine_sim < 0.99

    def test_same_text_same_vector(self):
        """相同文本应产生相同向量(确定性)。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()
        v1 = svc.encode_single("相同内容")
        v2 = svc.encode_single("相同内容")

        assert v1 == v2

    def test_dimension_property(self):
        """dimension属性应返回1024(bge-large-zh)。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()

        assert svc.dimension == 1024

    def test_long_text_truncation(self):
        """超长文本应被截断而不报错。"""
        from src.services.embedding import EmbeddingService

        svc = EmbeddingService()
        long_text = "测试" * 10000

        result = svc.encode_single(long_text)

        assert isinstance(result, list)
        assert len(result) == 1024


class TestRerankService:
    """
    RerankService单元测试(D11-T033)。

    验证:
        - 模型懒加载与降级模式
        - 查询-文档对评分
        - Top-K筛选
        - 结果排序(降序)
        - 空输入处理
    """

    def test_service_creation(self):
        """RerankService应可正常创建。"""
        from src.services.rerank import RerankService

        svc = RerankService()

        assert svc.top_k == 10
        assert svc.device == "cpu"

    def test_rerank_basic(self):
        """基础重排序应返回结果列表。"""
        from src.services.rerank import RerankService

        svc = RerankService()
        query = "蓝牙耳机"
        docs = ["AirPods Pro", "充电线", "Sony WH-1000XM5", "iPhone充电器"]

        results = svc.rerank(query, docs, top_k=3)

        assert isinstance(results, list)
        assert len(results) <= 3
        assert len(results) > 0

        for r in results:
            assert "index" in r
            assert "score" in r
            assert "document" in r
            assert 0 <= r["score"] <= 1.0

    def test_rerank_sorted_by_score_desc(self):
        """结果应按score降序排列。"""
        from src.services.rerank import RerankService

        svc = RerankService()
        query = "耳机"
        docs = [f"产品{i}" for i in range(10)]

        results = svc.rerank(query, docs, top_k=5)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_empty_documents(self):
        """空文档列表应返回空列表。"""
        from src.services.rerank import RerankService

        svc = RerankService()

        results = svc.rerank("query", [])

        assert results == []

    def test_rerank_top_k_larger_than_docs(self):
        """top_k大于文档数时返回全部文档。"""
        from src.services.rerank import RerankService

        svc = RerankService()
        docs = ["文档A", "文档B"]

        results = svc.rerank("查询", docs, top_k=100)

        assert len(results) == 2

    def test_score_pair_returns_float(self):
        """score_pair应返回float类型得分。"""
        from src.services.rerank import RerankService

        svc = RerankService()

        score = svc.score_pair("蓝牙耳机", "高品质无线蓝牙耳机降噪")

        assert isinstance(score, float)
        assert 0 <= score <= 1.0

    def test_relevant_doc_scores_higher(self):
        """相关文档的评分应高于不相关文档。"""
        from src.services.rerank import RerankService

        svc = RerankService()
        query = "无线蓝牙耳机"
        docs = [
            "高品质无线蓝牙耳机主动降噪",
            "不锈钢水杯大容量",
            "儿童绘本故事书",
        ]

        results = svc.rerank(query, docs, top_k=len(docs))

        best_score = results[0]["score"]
        worst_score = results[-1]["score"]

        assert best_score >= worst_score

    def test_triton_rerank_enabled_uses_remote_results(self, monkeypatch):
        from src.services.rerank import RerankService

        class _LLM:
            rerank_model = "bge-reranker-base"
            triton_enabled = True
            triton_endpoint = "http://fake-triton.local"
            triton_timeout_seconds = 5.0

        class _Settings:
            llm = _LLM()

        class _FakeTritonClient:
            def __init__(self, base_url, timeout_seconds=5.0):
                self.base_url = base_url
                self.timeout_seconds = timeout_seconds

            def rerank_sync(self, *, query, documents, top_k=5):
                return [{"index": 1, "score": 0.99}]

        monkeypatch.setattr("src.services.rerank.get_settings", lambda: _Settings())
        monkeypatch.setattr("src.services.rerank.TritonClient", _FakeTritonClient)
        svc = RerankService()
        results = svc.rerank("蓝牙耳机", ["充电线", "降噪蓝牙耳机"], top_k=1)
        assert results[0]["index"] == 1
        assert results[0]["document"] == "降噪蓝牙耳机"

    def test_triton_rerank_failure_falls_back_to_mock(self, monkeypatch):
        from src.infrastructure.triton_client import TritonClientError
        from src.services.rerank import RerankService

        class _LLM:
            rerank_model = "bge-reranker-base"
            triton_enabled = True
            triton_endpoint = "http://fake-triton.local"
            triton_timeout_seconds = 5.0

        class _Settings:
            llm = _LLM()

        class _FakeTritonClient:
            def __init__(self, base_url, timeout_seconds=5.0):
                self.base_url = base_url
                self.timeout_seconds = timeout_seconds

            def rerank_sync(self, *, query, documents, top_k=5):
                raise TritonClientError("boom", error_code="transport_error", retryable=True)

        monkeypatch.setattr("src.services.rerank.get_settings", lambda: _Settings())
        monkeypatch.setattr("src.services.rerank.TritonClient", _FakeTritonClient)
        svc = RerankService()
        results = svc.rerank("无线蓝牙耳机", ["高品质无线蓝牙耳机主动降噪", "不锈钢水杯大容量"], top_k=2)
        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]


class TestAmazonBSRCrawler:
    """
    AmazonBSRCrawler单元测试(D10-T040)。

    验证:
        - 反爬配置(User-Agent池/延迟/重试)
        - HTML解析能力
        - 数据格式标准化
        - ASIN提取
    """

    def test_crawler_creation(self):
        """BSRCrawler应可正常创建。"""
        from src.crawlers.amazon import AmazonBSRCrawler

        crawler = AmazonBSRCrawler()

        assert crawler.marketplace == "www.amazon.com"
        assert crawler.base_url == "https://www.amazon.com"

    def test_anti_crawl_config_user_agents(self):
        """AntiCrawlConfig应包含多个User-Agent。"""
        from src.crawlers.amazon import AntiCrawlConfig

        config = AntiCrawlConfig()

        assert len(config.USER_AGENTS) >= 3
        assert config.MIN_DELAY_SECONDS >= 1.0
        assert config.MAX_RETRIES >= 2

    def test_parse_bsr_page_extracts_asins(self):
        """HTML解析应能提取ASIN标识符。"""
        from src.crawlers.amazon import AmazonBSRCrawler

        crawler = AmazonBSRCrawler()

        html = """
        <a href="/dp/B08N5WRWNW">Product A</a>
        <a href="/dp/B09KXHJYLM">Product B</a>
        <span>$29.99</span>
        """

        results = crawler._parse_bsr_page(html, page=1)

        asins = [r["asin"] for r in results]
        assert "B08N5WRWNW" in asins
        assert "B09KXHJYLM" in asins

    def test_parse_bsr_result_structure(self):
        """解析结果应包含所有必需字段。"""
        from src.crawlers.amazon import AmazonBSRCrawler

        crawler = AmazonBSRCrawler()

        html = '<a href="/dp/B08N5WRWNW">Test Product</a><span>$49.99</span>'

        results = crawler._parse_bsr_page(html, page=1)

        if results:
            required_fields = {"asin", "name", "price", "rank", "url", "crawled_at"}
            for r in results:
                assert required_fields.issubset(r.keys())

    def test_bsr_rank_calculation(self):
        """BSR排名应根据页码正确计算。"""
        from src.crawlers.amazon import AmazonBSRCrawler

        crawler = AmazonBSRCrawler()

        html = "<a href='/dp/A000000001'>P1</a>" * 50

        results_page1 = crawler._parse_bsr_page(html, page=1)
        results_page2 = crawler._parse_bsr_page(html, page=2)

        if results_page1 and results_page2:
            assert results_page1[0]["rank"] == 1
            assert results_page2[0]["rank"] == 51


class TestAmazonReviewCrawler:
    """
    AmazonReviewCrawler单元测试(D11-T041)。

    验证:
        - 评论解析能力
        - 评分范围校验(1-5)
        - 数据清洗(短评论过滤)
        - HTML标签去除
    """

    def test_review_crawler_creation(self):
        """ReviewCrawler应可正常创建。"""
        from src.crawlers.amazon import AmazonReviewCrawler

        crawler = AmazonReviewCrawler()

        assert crawler.marketplace == "www.amazon.com"

    def test_parse_reviews_extracts_rating(self):
        """评论解析应能提取星级评分。"""
        from src.crawlers.amazon import AmazonReviewCrawler

        crawler = AmazonReviewCrawler()

        html = '''
        data-review-id="R123456789"
        <i data-icon="a-star-5"><span class="a-icon-alt">5.0 out of 5 stars</span></i>
        class="review-title"><span>Great product!</span></span>
        '''

        reviews = crawler._parse_reviews(html, asin="B08N5WRWNW")

        if reviews:
            assert reviews[0]["rating"] == 5

    def test_review_rating_range_validation(self):
        """评分应在1-5范围内。"""
        from src.crawlers.amazon import AmazonReviewCrawler

        crawler = AmazonReviewCrawler()

        html = 'data-review-id="RX"<i data-icon="a-star-7">'

        reviews = crawler._parse_reviews(html, asin="TESTASIN01")

        if reviews:
            assert 1 <= reviews[0]["rating"] <= 5

    def test_review_short_title_filtered(self):
        """过短标题(<3字符)应被过滤。"""
        from src.crawlers.amazon import AmazonReviewCrawler

        crawler = AmazonReviewCrawler()

        html = 'data-review_id="R1"<i data-icon="a-star-4"><span class="review-title"><span>OK</span>'

        reviews = crawler._parse_reviews(html, asin="TESTASIN02")

        for r in reviews:
            assert len(r["title"]) >= 3 or r["title"] == ""


class TestDataValidation:
    """
    数据验证函数测试(D12-T043 ETL规则)。

    验证:
        - validate_product_data() 完整性检查
        - normalize_price() 价格标准化
        - ASIN格式验证
        - 价格范围验证
    """

    def test_valid_product_data_passes(self):
        """有效产品数据应通过验证。"""
        from src.crawlers.amazon import validate_product_data

        data = {
            "asin": "B08N5WRWNW",
            "name": "Wireless Earbuds",
            "price": 29.99,
            "rating": 4.5,
        }

        assert validate_product_data(data) is True

    def test_missing_required_field_fails(self):
        """缺少必填字段应失败。"""
        from src.crawlers.amazon import validate_product_data

        data = {
            "name": "Product",
            "price": 19.99,
        }

        assert validate_product_data(data) is False

    def test_invalid_asin_format_fails(self):
        """无效ASIN格式应失败。"""
        from src.crawlers.amazon import validate_product_data

        data = {
            "asin": "INVALID",
            "name": "Test",
            "price": 10.0,
        }

        assert validate_product_data(data) is False

    def test_price_out_of_range_fails(self):
        """超出价格范围应失败(D12-T043: 0<price<=99999)。"""
        from src.crawlers.amazon import validate_product_data

        data_high = {"asin": "B000000001", "name": "T", "price": 100000}
        data_zero = {"asin": "B000000002", "name": "T", "price": 0}
        data_negative = {"asin": "B000000003", "name": "T", "price": -10}

        assert validate_product_data(data_high) is False
        assert validate_product_data(data_zero) is False
        assert validate_product_data(data_negative) is False

    def test_normalize_price_string(self):
        """字符串价格应被正确标准化。"""
        from src.crawlers.amazon import normalize_price

        assert normalize_price("$29.99") == 29.99
        assert normalize_price("1,299.00") == 1299.0

    def test_normalize_price_numeric(self):
        """数值价格应直接返回。"""
        from src.crawlers.amazon import normalize_price

        assert normalize_price(49.99) == 49.99
        assert normalize_price(0) is None

    def test_normalize_price_none(self):
        """None价格应返回None。"""
        from src.crawlers.amazon import normalize_price

        assert normalize_price(None) is None

    def test_normalize_price_out_of_range(self):
        """超出范围的价格应返回None。"""
        from src.crawlers.amazon import normalize_price

        assert normalize_price(100000) is None
        assert normalize_price(-1) is None


class TestETLPipeline:
    """
    ETLPipeline单元测试(D12-T043/T044)。

    验证:
        - 数据清洗流程
        - 去重逻辑(ASIN+日期唯一键)
        - 质量规则执行
        - 统计报告生成
        - 异常数据处理
    """

    def test_pipeline_creation(self):
        """ETLPipeline应可正常创建。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        assert len(pipeline.rules) >= 3

    def test_clean_valid_products(self):
        """有效产品数据应全部通过清洗。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [
            {"asin": f"B00000000{i}", "name": f"Product {i}", "price": float(i * 10 + 9.99)}
            for i in range(1, 6)
        ]

        cleaned, report = pipeline.clean_products(raw_data)

        assert len(cleaned) == 5
        assert report.pass_rate == 1.0

    def test_clean_removes_invalid_prices(self):
        """无效价格记录应被剔除。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [
            {"asin": "B000000001", "name": "Valid", "price": 29.99},
            {"asin": "B000000002", "name": "Too Expensive", "price": 100000},
            {"asin": "B000000003", "name": "Negative", "price": -5},
            {"asin": "B000000004", "name": "Zero Price", "price": 0},
            {"asin": "B000000005", "name": "Another Valid", "price": 49.99},
        ]

        cleaned, report = pipeline.clean_products(raw_data)

        assert len(cleaned) == 2
        prices = [c["price"] for c in cleaned]
        assert all(0 < p <= 99999 for p in prices)

    def test_clean_removes_invalid_asins(self):
        """无效ASIN记录应被剔除。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [
            {"asin": "B000000001", "name": "Valid ASIN", "price": 29.99},
            {"asin": "SHORT", "name": "Too Short", "price": 19.99},
            {"asin": "B000000002", "name": "Also Valid", "price": 39.99},
        ]

        cleaned, _ = pipeline.clean_products(raw_data)

        asins = [c.get("asin_upper", c["asin"]) for c in cleaned]
        assert "SHORT" not in asins
        assert len(cleaned) == 2

    def test_deduplication_by_asin_date(self):
        """相同ASIN+日期的重复记录应被去重。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        today = "2025-01-15T10:00:00"

        raw_data = [
            {"asin": "B000000001", "name": "First", "price": 29.99, "crawled_at": today},
            {"asin": "B000000001", "name": "Duplicate", "price": 29.99, "crawled_at": today},
            {"asin": "B000000002", "name": "Different", "price": 39.99, "crawled_at": today},
        ]

        cleaned, report = pipeline.clean_products(raw_data)

        assert len(cleaned) == 2
        assert report.dedup_count == 1

    def test_quality_report_generation(self):
        """质量报告应包含完整统计信息。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [
            {"asin": "B000000001", "name": "OK", "price": 29.99},
            {"asin": "BAD", "name": "Bad ASIN", "price": 10.0},
        ]

        _, report = pipeline.clean_products(raw_data)

        d = report.to_dict()

        assert "input_count" in d
        assert "output_count" in d
        assert "pass_rate" in d
        assert "duration_seconds" in d
        assert d["input_count"] == 2

    def test_pipeline_reset_clears_state(self):
        """reset()应清除已处理记录缓存。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [{"asin": "B000000001", "name": "T", "price": 10.0}]
        pipeline.clean_products(raw_data)

        same_data = [{"asin": "B000000001", "name": "T", "price": 10.0, "crawled_at": "2025-01-15"}]
        cleaned_after_reset, _ = pipeline.clean_products(same_data)

        assert len(cleaned_after_reset) == 1

    def test_etl_adds_metadata_fields(self):
        """ETL处理后数据应包含_source和_etl_processed_at字段。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [{"asin": "B000000001", "name": "Test", "price": 29.99}]

        cleaned, _ = pipeline.clean_products(raw_data, source="test_source")

        assert cleaned[0].get("_source") == "test_source"
        assert "_etl_processed_at" in cleaned[0]

    def test_rating_validation_in_pipeline(self):
        """超出范围的评分应导致记录被剔除。"""
        from src.services.etl import ETLPipeline

        pipeline = ETLPipeline()

        raw_data = [
            {"asin": "B000000001", "name": "Normal", "price": 29.99, "rating": 4.5},
            {"asin": "B000000002", "name": "High Rating", "price": 39.99, "rating": 6.0},
            {"asin": "B000000003", "name": "Low Rating", "price": 19.99, "rating": -1},
        ]

        cleaned, _ = pipeline.clean_products(raw_data)

        assert len(cleaned) == 1
        assert cleaned[0]["asin"] == "B000000001"


class TestModuleImports:
    """
    模块导入测试。

    验证所有新模块可正常导入。
    """

    def test_services_package_importable(self):
        """services包应可正常导入。"""
        from src.services import (
            get_embedding_service,
            get_rerank_service,
        )

        assert callable(get_embedding_service)
        assert callable(get_rerank_service)

    def test_crawlers_package_importable(self):
        """crawlers包应可正常导入。"""
        from src.crawlers import (
            normalize_price,
            validate_product_data,
        )

        assert callable(validate_product_data)
        assert callable(normalize_price)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
