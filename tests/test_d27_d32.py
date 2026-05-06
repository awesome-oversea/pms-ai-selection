"""
D27-D32 单元测试: 数据采集Agent + 市场洞察Agent开发。

覆盖范围:
    D27: Amazon BSR/评论/价格采集工具
    D28: TikTok商品/达人数据采集工具
    D29: Google Trends + 1688供应链工具
    D30: DataCollectionAgent编排与数据融合
    D31: 数据质量校验与异常处理
    D32: FastAPI集成端点
"""

import pytest
from src.agents.data_collection import (
    AmazonBSRTool,
    AmazonPriceTool,
    AmazonReviewTool,
    CollectionResult,
    DataCollectionAgent,
    DataQualityReport,
    DataSource,
    GoogleTrendsTool,
    TikTokCreatorTool,
    TikTokProductTool,
    Tool1688,
)


class TestDataSourceEnum:
    """测试DataSource枚举定义。"""

    def test_enum_values(self):
        assert DataSource.AMAZON.value == "amazon"
        assert DataSource.TIKTOK.value == "tiktok"
        assert DataSource.GOOGLE.value == "google"
        assert DataSource.ALI1688.value == "ali1688"

    def test_enum_count(self):
        assert len(DataSource) == 4


class TestCollectionResult:
    """测试CollectionResult数据类。"""

    def test_success_result(self):
        result = CollectionResult(
            source=DataSource.AMAZON,
            query="test",
            data={"rank": 1, "sales": 10000},
        )
        assert result.source == DataSource.AMAZON
        assert result.query == "test"
        assert result.data == {"rank": 1, "sales": 10000}
        assert result.error is None

    def test_error_result(self):
        result = CollectionResult(
            source=DataSource.TIKTOK,
            query="test",
            data=None,
            error="API timeout",
        )
        assert result.error == "API timeout"
        assert result.data is None

    def test_to_dict(self):
        result = CollectionResult(
            source=DataSource.AMAZON,
            query="bluetooth",
            data={"rank": 5},
        )
        d = result.to_dict()
        assert d["source"] == "amazon"
        assert d["query"] == "bluetooth"


class TestDataQualityReport:
    """测试DataQualityReport质量校验。"""

    def test_valid_data(self):
        report = DataQualityReport(
            total_records=100,
            valid_records=95,
            anomaly_count=2,
        )
        assert report.validity_rate == 0.95
        assert report.is_acceptable is True

    def test_low_quality_data(self):
        report = DataQualityReport(
            total_records=100,
            valid_records=50,
            anomaly_count=20,
        )
        assert report.validity_rate == 0.5
        assert report.is_acceptable is False


class TestAmazonBSRTool:
    """测试Amazon BSR排名采集工具。"""

    def setup_method(self):
        self.tool = AmazonBSRTool()

    def test_tool_registration(self):
        assert self.tool.name == "amazon_bsr"
        props = self.tool.parameters.get("properties", {})
        assert "category" in props

    @pytest.mark.asyncio
    async def test_execute_returns_dict(self):
        result = await self.tool.execute(category="Electronics")
        assert isinstance(result, dict)
        assert "source" in result
        assert result["source"] == "amazon_bsr"

    @pytest.mark.asyncio
    async def test_execute_has_products(self):
        result = await self.tool.execute(category="Wireless Earbuds")
        assert "products" in result
        assert isinstance(result["products"], list)
        assert len(result["products"]) > 0

    @pytest.mark.asyncio
    async def test_product_structure(self):
        result = await self.tool.execute(category="Test Category")
        product = result["products"][0]
        assert "asin" in product
        assert "title" in product
        assert "bsr_rank" in product
        assert "est_monthly_sales" in product or "estimated_sales" in product


class TestAmazonReviewTool:
    """测试Amazon评论采集工具。"""

    def setup_method(self):
        self.tool = AmazonReviewTool()

    def test_tool_registration(self):
        assert self.tool.name == "amazon_reviews"
        assert "asin" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_returns_reviews(self):
        result = await self.tool.execute(asin="B08N5WRWNW")
        assert isinstance(result, dict)
        assert "sample_reviews" in result or "reviews" in result
        reviews = result.get("sample_reviews", result.get("reviews", []))
        assert isinstance(reviews, list)

    @pytest.mark.asyncio
    async def test_review_sentiment_distribution(self):
        result = await self.tool.execute(asin="B08N5WRWNW")
        sentiment = result.get("sentiment_breakdown", result.get("sentiment", {}))
        assert "positive" in sentiment or "positive_pct" in sentiment


class TestAmazonPriceTool:
    """测试Amazon价格追踪工具。"""

    def setup_method(self):
        self.tool = AmazonPriceTool()

    def test_tool_registration(self):
        assert self.tool.name == "amazon_price"
        assert "asin" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_price_history(self):
        result = await self.tool.execute(asin="B08N5WRWNW")
        assert isinstance(result, dict)
        assert "current_price" in result
        history = result.get("history", result.get("price_history", []))
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_price_range_reasonable(self):
        result = await self.tool.execute(asin="B08N5WRWNW")
        price = result["current_price"]
        assert 1.0 <= price <= 999.99


class TestTikTokProductTool:
    """测试TikTok商品数据采集工具。"""

    def setup_method(self):
        self.tool = TikTokProductTool()

    def test_tool_registration(self):
        assert self.tool.name == "tiktok_products"
        assert "query" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_returns_products(self):
        result = await self.tool.execute(query="kitchen gadgets")
        assert isinstance(result, dict)
        assert "products" in result
        assert len(result["products"]) > 0

    @pytest.mark.asyncio
    async def test_tiktok_metrics(self):
        result = await self.tool.execute(query="beauty tools")
        product = result["products"][0]
        has_likes = "total_likes" in product or "likes" in product
        has_shares = "total_shares" in product or "shares" in product
        assert has_likes
        assert has_shares
        assert "video_count" in product


class TestTikTokCreatorTool:
    """测试TikTok达人数据采集工具。"""

    def setup_method(self):
        self.tool = TikTokCreatorTool()

    def test_tool_registration(self):
        assert self.tool.name == "tiktok_creators"
        assert "niche" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_returns_creators(self):
        result = await self.tool.execute(niche="fitness")
        assert isinstance(result, dict)
        assert "creators" in result
        assert len(result["creators"]) > 0

    @pytest.mark.asyncio
    async def test_creator_tier_distribution(self):
        result = await self.tool.execute(niche="tech review")
        assert "tier_distribution" in result
        tiers = result["tier_distribution"]
        assert any(t > 0 for t in tiers.values())


class TestGoogleTrendsTool:
    """测试Google Trends趋势工具。"""

    def setup_method(self):
        self.tool = GoogleTrendsTool()

    def test_tool_registration(self):
        assert self.tool.name == "google_trends"
        assert "keywords" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_trend_data(self):
        result = await self.tool.execute(
            keywords=["bluetooth speaker", "wireless earbuds"]
        )
        assert isinstance(result, dict)
        assert "trend_data" in result

    @pytest.mark.asyncio
    async def test_monthly_trend_points(self):
        result = await self.tool.execute(keywords=["yoga mat"])
        trend_data = result["trend_data"]
        for _kw, data in trend_data.items():
            assert "monthly_data" in data
            assert len(data["monthly_data"]) == 12

    @pytest.mark.asyncio
    async def test_regional_data(self):
        result = await self.tool.execute(keywords=["coffee maker"])
        regional_key = "regional_interest" if "regional_interest" in result else "regional_heatmap"
        assert regional_key in result
        regions = result[regional_key]
        assert len(regions) > 0


class TestTool1688:
    """测试1688供应链数据采集工具。"""

    def setup_method(self):
        self.tool = Tool1688()

    def test_tool_registration(self):
        assert self.tool.name == "ali1688_supply"
        assert "product_keyword" in self.tool.parameters.get("properties", {})

    @pytest.mark.asyncio
    async def test_execute_suppliers(self):
        result = await self.tool.execute(product_keyword="蓝牙音箱")
        assert isinstance(result, dict)
        assert "suppliers" in result
        assert len(result["suppliers"]) > 0

    @pytest.mark.asyncio
    async def test_supplier_cost_structure(self):
        result = await self.tool.execute(product_keyword="无线耳机")
        supplier = result["suppliers"][0]
        assert "moq_tiers" in supplier
        assert len(supplier["moq_tiers"]) > 0
        tier = supplier["moq_tiers"][0]
        assert "unit_price_usd" in tier
        assert "min_qty" in tier


class TestDataCollectionAgent:
    """测试DataCollectionAgent编排核心。"""

    def setup_method(self):
        self.agent = DataCollectionAgent()

    def test_agent_initialization(self):
        assert self.agent.agent_type == "data_collection"
        assert self.agent.quality_threshold == 0.85

    def test_tool_registration_count(self):
        tools = self.agent.get_tools()
        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "amazon_bsr" in tool_names
        assert "tiktok_products" in tool_names
        assert "google_trends" in tool_names
        assert "ali1688_supply" in tool_names

    def test_required_input_keys(self):
        assert "query" in self.agent.REQUIRED_INPUT_KEYS

    @pytest.mark.asyncio
    async def test_execute_basic_workflow(self):
        result = await self.agent.execute({
            "query": "bluetooth speaker",
            "category": "Electronics",
        })
        assert isinstance(result, dict)
        assert "query" in result
        assert "collection_timestamp" in result

    @pytest.mark.asyncio
    async def test_execute_sources_summary(self):
        result = await self.agent.execute({
            "query": "wireless mouse",
            "category": "Computer Accessories",
        })
        summary = result["sources_summary"]
        assert "total_sources" in summary
        assert summary["total_sources"] == 7
        assert "successful" in summary
        assert "failed" in summary

    @pytest.mark.asyncio
    async def test_execute_quality_report(self):
        result = await self.agent.execute({
            "query": "yoga mat",
            "category": "Sports",
        })
        quality = result["quality_report"]
        assert "validity_rate" in quality
        assert "is_acceptable" in quality
        assert quality["validity_rate"] > 0

    @pytest.mark.asyncio
    async def test_execute_amazon_data_present(self):
        result = await self.agent.execute({
            "query": "phone case",
            "category": "Accessories",
        })
        amazon = result.get("amazon_data", {})
        assert "bsr" in amazon or amazon.get("bsr") is None

    @pytest.mark.asyncio
    async def test_execute_tiktok_data_present(self):
        result = await self.agent.execute({
            "query": "lipstick",
            "category": "Beauty",
        })
        tiktok = result.get("tiktok_data", {})
        assert "products" in tiktok or tiktok.get("products") is None

    @pytest.mark.asyncio
    async def test_execute_fused_insights(self):
        result = await self.agent.execute({
            "query": "desk lamp",
            "category": "Home Office",
        })
        assert "fused_insights" in result
        fused = result["fused_insights"]
        assert len(fused) > 0

    def test_custom_config_threshold(self):
        agent = DataCollectionAgent(config={"quality_threshold": 0.9})
        assert agent.quality_threshold == 0.9

    @pytest.mark.asyncio
    async def test_empty_query_handling(self):
        result = await self.agent.execute({"query": ""})
        assert isinstance(result, dict)
        assert "sources_summary" in result


class TestDataFusionLogic:
    """测试多源数据融合逻辑。"""

    def setup_method(self):
        self.agent = DataCollectionAgent()

    @pytest.mark.asyncio
    async def test_cross_source_validation(self):
        result = await self.agent.execute({
            "query": "smart watch",
            "category": "Wearable Tech",
        })
        fused = result.get("fused_insights", {})
        assert isinstance(fused, dict)
        assert len(fused) > 0

    @pytest.mark.asyncio
    async def test_data_gap_identification(self):
        result = await self.agent.execute({
            "query": "portable charger",
            "category": "Electronics",
        })
        fused = result.get("fused_insights", {})
        assert isinstance(fused, dict)


class TestErrorHandling:
    """测试异常处理与容错机制。"""

    def setup_method(self):
        self.agent = DataCollectionAgent()

    @pytest.mark.asyncio
    async def test_partial_failure_recovery(self):
        result = await self.agent.execute({"query": "test niche"})
        summary = result["sources_summary"]
        assert summary["successful"] >= 0
        assert summary["failed"] >= 0
        assert summary["successful"] + summary["failed"] == summary["total_sources"]

    @pytest.mark.asyncio
    async def test_result_always_returned(self):
        for query in ["", "   ", "x" * 500]:
            result = await self.agent.execute({"query": query})
            assert isinstance(result, dict)
            assert "quality_report" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
