"""
市场洞察Agent
============

提供市场数据分析与趋势预测能力(D16-T053):
    - 市场规模估算(TAM/SAM/SOM)
    - 竞品格局分析
    - 价格带分布分析
    - 销量趋势识别
    - 机会评分计算

使用方式:
    from src.agents.market_insight import MarketInsightAgent

    agent = MarketInsightAgent()
    result = await agent.run({"query": "蓝牙耳机市场分析", "category": "electronics"})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import AgentTool, AgentType, BaseAgent
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MarketSizeEstimate:
    """
    市场规模估算(D16)。

    TAM: Total Addressable Market(总潜在市场)
    SAM: Serviceable Available Market(可服务市场)
    SOM: Serviceable Obtainable Market(可获得市场)

    Attributes:
        tam_usd: 总市场规模(美元)
        sam_usd: 可服务市场规模(美元)
        som_usd: 可获得市场规模(美元)
        cagr: 年复合增长率(%)
        source_year: 数据基准年份
    """

    tam_usd: float = 0.0
    sam_usd: float = 0.0
    som_usd: float = 0.0
    cagr: float = 0.0
    source_year: int = 2025

    def to_dict(self) -> dict[str, Any]:
        return {
            "TAM": f"${self.tam_usd:,.0f}",
            "SAM": f"${self.sam_usd:,.0f}",
            "SOM": f"${self.som_usd:,.0f}",
            "CAGR": f"{self.cagr:.1f}%",
            "source_year": self.source_year,
        }


@dataclass
class CompetitorLandscape:
    """
    竞品格局分析(D16)。

    Attributes:
        total_competitors: 竞品总数
        top_players: 头部玩家列表
        market_concentration: 市场集中度(HHI指数)
        avg_price: 平均价格
        price_range: 价格区间
        entry_barrier: 进入壁垒评估(low/medium/high)
    """

    total_competitors: int = 0
    top_players: list[dict] = field(default_factory=list)
    market_concentration: float = 0.0
    avg_price: float = 0.0
    price_range: tuple[float, float] = (0.0, 0.0)
    entry_barrier: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_competitors": self.total_competitors,
            "top_players": self.top_players[:10],
            "HHI": round(self.market_concentration, 2),
            "avg_price": f"${self.avg_price:.2f}",
            "price_range": f"${self.price_range[0]:.2f} - ${self.price_range[1]:.2f}",
            "entry_barrier": self.entry_barrier,
            "concentration_level": self._get_concentration_level(),
        }

    def _get_concentration_level(self) -> str:
        if self.market_concentration < 1500:
            return "competitive"
        elif self.market_concentration < 2500:
            return "moderate_concentration"
        else:
            return "highly_concentrated"


@dataclass
class TrendSignal:
    """
    趋势信号。

    Attributes:
        direction: 趋势方向(up/down/stable/volatile)
        strength: 信号强度(0-100)
        confidence: 置信度(0-100)
        description: 趋势描述
        key_drivers: 关键驱动因素
    """

    direction: str = "stable"
    strength: int = 50
    confidence: int = 50
    description: str = ""
    key_drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "description": self.description,
            "key_drivers": self.key_drivers,
        }


@dataclass
class OpportunityScore:
    """
    机会评分(D16)。

    综合多维度评分:
        - market_size_score: 市场规模得分(0-25)
        - growth_score: 增长潜力得分(0-25)
        - competition_score: 竞争态势得分(0-25，低竞争=高分)
        - profit_margin_score: 利润空间得分(0-25)

    Attributes:
        overall: 综合得分(0-100)
        dimensions: 各维度得分详情
        recommendation: 推荐等级(strong_recommend/recommend/caution/avoid)
        risk_factors: 风险因素列表
    """

    overall: float = 0.0
    market_size_score: float = 0.0
    growth_score: float = 0.0
    competition_score: float = 0.0
    profit_margin_score: float = 0.0
    recommendation: str = "caution"
    risk_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall, 1),
            "market_size": round(self.market_size_score, 1),
            "growth_potential": round(self.growth_score, 1),
            "competition": round(self.competition_score, 1),
            "profit_margin": round(self.profit_margin_score, 1),
            "recommendation": self.recommendation,
            "risk_factors": self.risk_factors,
        }


class MarketInsightAgent(BaseAgent):
    """
    市场洞察Agent(D16-T053)。

    功能:
        1. 市场规模估算(TAM/SAM/SOM)
        2. 竞品格局分析(HHI集中度/头部玩家)
        3. 价格带分布分析
        4. 销量趋势识别(上升/下降/稳定)
        5. 机会评分(多维度加权)

    数据来源:
        - Amazon BSR数据
        - 产品评论情感分析
        - 搜索趋势数据
        - 行业报告(RAG知识库)
    """

    name = "market_insight"
    agent_type = AgentType.MARKET_INSIGHT
    version = "1.0.0"
    description = "市场洞察Agent - 分析市场规模、竞品格局、价格趋势和机会评分"
    timeout_seconds = 120

    REQUIRED_INPUT_KEYS = {"query", "category"}

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)

        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """注册内置工具。"""
        self.register_tool(AgentTool(
            name="search_products",
            description="搜索产品数据(按关键词/类目)",
            func=self._mock_search_products,
            parameters={
                "keyword": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回数量限制"},
            },
        ))

        self.register_tool(AgentTool(
            name="analyze_pricing",
            description="分析产品价格分布",
            func=self._mock_analyze_pricing,
            parameters={
                "category": {"type": "string", "description": "产品类目"},
            },
        ))

        self.register_tool(AgentTool(
            name="estimate_market_size",
            description="估算市场规模",
            func=self._mock_estimate_market_size,
            parameters={
                "category": {"type": "string", "description": "产品类目"},
                "region": {"type": "string", "description": "地区(默认US)"},
            },
        ))

    async def validate_input(self, input_data: dict[str, Any]):
        """校验输入: 必须包含query和category。"""
        await super().validate_input(input_data)

        missing = self.REQUIRED_INPUT_KEYS - set(input_data.keys())
        if missing:
            raise ValueError(f"缺少必填字段: {missing}")

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        执行市场洞察分析。

        流程:
            1. RAG检索行业背景信息
            2. 产品数据采集与分析
            3. 市场规模估算
            4. 竞品格局分析
            5. 趋势识别
            6. 机会评分计算
        """
        query = input_data.get("query", "")
        category = input_data.get("category", "")

        retrieve_step = self._create_step("retrieve_context", "retrieve", input_data=query[:100])
        context = await self._retrieve_context(query, category)
        retrieve_step.output_data = f"检索到 {len(context)} 条上下文"
        retrieve_step.duration_ms = 50.0

        products_step = self._create_step("analyze_products", "analysis")
        product_data = await self.call_tool("search_products", keyword=category, limit=50)
        products_step.output_data = f"获取 {len(product_data)} 个产品"

        pricing_step = self._create_step("pricing_analysis", "analysis")
        pricing_data = await self.call_tool("analyze_pricing", category=category)
        pricing_step.output_data = "价格分布分析完成"

        market_step = self._create_step("market_size_estimation", "analysis")
        market_size = await self.call_tool("estimate_market_size", category=category)
        market_step.output_data = f"TAM={market_size.get('tam', 0)}"

        competitor_step = self._create_step("competitor_analysis", "analysis")
        landscape = self._analyze_competitor_landscape(product_data)
        competitor_step.output_data = f"发现 {landscape.total_competitors} 个竞品"

        trend_step = self._create_step("trend_identification", "analysis")
        trends = self._identify_trends(product_data, pricing_data)
        trend_step.output_data = f"趋势方向: {trends.direction}"

        score_step = self._create_step("opportunity_scoring", "scoring")
        opportunity = self._calculate_opportunity(market_size, landscape, trends)
        score_step.output_data = f"综合评分: {opportunity.overall}"

        # LLM 推理：市场洞察综合分析
        llm_insight = ""
        llm_insight_structured: dict[str, Any] = {}
        try:
            from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway
            gateway = LLMGateway(GatewayConfig())
            llm_step = self._create_step("llm_market_reasoning", "reason")
            prompt = (
                f"你是跨境电商市场分析师。请分析以下「{category}」品类在{input_data.get('target_market', 'US')}市场的数据：\n"
                f"- 市场规模(TAM): ${market_size.get('tam', 0):,.0f}\n"
                f"- 竞品数量: {landscape.total_competitors}家, HHI集中度: {landscape.market_concentration:.0f}\n"
                f"- 趋势方向: {trends.direction}, 强度: {trends.strength}/100\n"
                f"- 机会评分: {opportunity.overall:.1f}/100\n\n"
                f"请用JSON格式输出分析结论，包含字段: opportunity_summary(string), entry_timing(now/wait/avoid), "
                f"key_risks(list[string]), suggested_strategy(string)"
            )
            llm_result = await gateway.route(prompt=prompt)
            llm_insight = llm_result.response
            llm_insight_structured = self._parse_llm_json_response(llm_result.response)
            llm_step.output_data = f"LLM分析完成 ({llm_result.tokens_used} tokens)"
            llm_step.status = "success"
        except Exception as e:
            logger.warning(f"LLM市场分析降级: {e}")

        return {
            "query": query,
            "category": category,
            "market_size": market_size,
            "competitor_landscape": landscape.to_dict(),
            "pricing_analysis": pricing_data,
            "trends": trends.to_dict(),
            "opportunity_score": opportunity.to_dict(),
            "context_sources": len(context),
            "llm_insight": llm_insight,
            "llm_insight_structured": llm_insight_structured,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def format_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """格式化输出为标准API响应格式。"""
        opportunity = raw_output.get("opportunity_score", {})
        rec = opportunity.get("recommendation", "caution")

        summary = self._generate_summary(raw_output, rec)

        return {
            "status": "success",
            "summary": summary,
            "data": raw_output,
            "recommendation": rec,
        }

    async def _retrieve_context(
        self,
        query: str,
        category: str,
    ) -> list[dict]:
        """RAG检索相关背景信息。"""
        try:
            from src.rag.retriever import HybridRetriever

            retriever = HybridRetriever(enable_rerank=True)

            sample_docs = [
                {"id": f"kb_{i}", "content": f"{category}市场报告第{i}条: 行业增长稳定，消费者需求持续上升", "metadata": {"source": "industry_report"}}
                for i in range(5)
            ]
            retriever.add_documents(sample_docs)

            results = await retriever.retrieve(f"{category} {query}", top_k=5)

            return [{"content": r.content, "score": r.score} for r in results]
        except Exception as e:
            logger.warning(f"RAG检索降级: {e}")
            return []

    def _analyze_competitor_landscape(self, products: list) -> CompetitorLandscape:
        """分析竞品格局。"""
        if not products:
            return CompetitorLandscape()

        prices = [p.get("price", 0) for p in products if p.get("price")]

        sorted_by_sales = sorted(products, key=lambda x: x.get("sales_rank", 99999))[:10]
        top_players = [
            {
                "name": p.get("name", "Unknown"),
                "asin": p.get("asin", ""),
                "price": p.get("price"),
                "rating": p.get("rating"),
                "review_count": p.get("review_count"),
            }
            for p in sorted_by_sales
        ]

        avg_price = sum(prices) / max(len(prices), 1)
        hhi = self._calculate_hhi(products)

        barrier = "low"
        if hhi > 2000:
            barrier = "high"
        elif hhi > 1000:
            barrier = "medium"

        return CompetitorLandscape(
            total_competitors=len(products),
            top_players=top_players,
            market_concentration=hhi,
            avg_price=avg_price,
            price_range=(min(prices), max(prices)) if prices else (0, 0),
            entry_barrier=barrier,
        )

    def _calculate_hhi(self, products: list) -> float:
        """
        计算Herfindahl-Hirschman Index(市场集中度)。

        HHI = Σ(si²) × 10000
        其中si是第i个企业的市场份额占比。
        """
        if not products or len(products) < 2:
            return 0.0

        reviews = [max(p.get("review_count", 1), 1) for p in products]
        total = sum(reviews)

        shares = [r / total for r in reviews]
        hhi = sum(s * s for s in shares) * 10000

        return round(hhi, 2)

    def _identify_trends(
        self,
        products: list,
        pricing: dict,
    ) -> TrendSignal:
        """识别市场趋势。"""
        if not products:
            return TrendSignal(direction="stable", description="数据不足")

        prices = [p.get("price", 0) for p in products if p.get("price")]
        ratings = [p.get("rating", 0) for p in products if p.get("rating")]

        avg_rating = sum(ratings) / max(len(ratings), 1)
        avg_price = sum(prices) / max(len(prices), 1)

        high_rating_ratio = len([r for r in ratings if r >= 4.0]) / max(len(ratings), 1)

        if high_rating_ratio > 0.6 and avg_price > 30:
            direction = "up"
            desc = "市场需求旺盛，高品质产品受欢迎"
            drivers = ["高用户满意度", "溢价能力较强"]
        elif high_rating_ratio > 0.4:
            direction = "stable"
            desc = "市场平稳发展，竞争适中"
            drivers = ["需求稳定", "价格敏感度中等"]
        else:
            direction = "down"
            desc = "市场竞争激烈，需差异化突围"
            drivers = ["价格战风险", "同质化严重"]

        strength = min(100, int(high_rating_ratio * 100))
        confidence = min(95, 50 + len(products) // 2)

        return TrendSignal(
            direction=direction,
            strength=strength,
            confidence=confidence,
            description=desc,
            key_drivers=drivers,
        )

    def _calculate_opportunity(
        self,
        market_size: dict,
        landscape: CompetitorLandscape,
        trends: TrendSignal,
    ) -> OpportunityScore:
        """
        计算机会评分(D16核心算法)。

        四维度各25分:
            1. market_size_score: 基于SOM大小
            2. growth_score: 基于趋势强度+置信度
            3. competition_score: 反比于HHI(低集中度=高机会)
            4. profit_margin_score: 基于价格区间宽度
        """
        som = market_size.get("som", 0)
        size_score = min(25, (som / 1e8) * 25) if som > 0 else 5

        growth_score = ((trends.strength + trends.confidence) / 2) / 4

        hhi = landscape.market_concentration
        if hhi < 1000:
            comp_score = 22
        elif hhi < 2000:
            comp_score = 15
        elif hhi < 3000:
            comp_score = 8
        else:
            comp_score = 3

        price_low, price_high = landscape.price_range
        margin_width = price_high - price_low
        margin_score = min(25, (margin_width / 100) * 25) if margin_width > 0 else 5

        overall = size_score + growth_score + comp_score + margin_score

        if overall >= 75:
            rec = "strong_recommend"
        elif overall >= 55:
            rec = "recommend"
        elif overall >= 35:
            rec = "caution"
        else:
            rec = "avoid"

        risks = []
        if hhi > 2500:
            risks.append("市场高度集中，头部效应明显")
        if trends.direction == "down":
            risks.append("下行趋势，进入时机不佳")
        if margin_width < 20:
            risks.append("价格带狭窄，利润空间有限")

        return OpportunityScore(
            overall=overall,
            market_size_score=size_score,
            growth_score=growth_score,
            competition_score=comp_score,
            profit_margin_score=margin_score,
            recommendation=rec,
            risk_factors=risks,
        )

    def _generate_summary(self, output: dict, recommendation: str) -> str:
        """生成自然语言摘要。"""
        opp = output.get("opportunity_score", {})
        market = output.get("market_size", {})
        landscape = output.get("competitor_landscape", {})
        trends = output.get("trends", {})

        cat = output.get("category", "该品类")
        score = opp.get("overall", 0)

        rec_map = {
            "strong_recommend": "强烈推荐进入",
            "recommend": "推荐进入",
            "caution": "谨慎考虑",
            "avoid": "不建议进入",
        }

        summary = (
            f"[{cat}]市场洞察报告\n"
            f"综合评分: {score}/100 ({rec_map.get(recommendation, '待评估')})\n"
            f"市场规模: TAM=${market.get('tam', 0):,.0f}\n"
            f"竞品数量: {landscape.get('total_competitors', 0)}家 "
            f"(集中度: {landscape.get('concentration_level', 'N/A')})\n"
            f"趋势方向: {trends.get('direction', 'stable')} "
            f"(置信度: {trends.get('confidence', 0)}%)\n"
        )

        risks = opp.get("risk_factors", [])
        if risks:
            summary += f"⚠️ 风险提示: {'; '.join(risks[:3])}\n"

        return summary

    async def _mock_search_products(self, keyword: str, limit: int = 50) -> list[dict]:
        """模拟产品搜索(实际应调用Amazon爬虫)。"""
        import random

        products = []
        base_names = ["Premium", "Basic", "Pro", "Ultra", "Mini", "Max"]
        suffixes = ["Wireless", "Bluetooth", "Smart", "HD", "Plus"]

        for i in range(min(limit, 20)):
            name = f"{random.choice(base_names)} {random.choice(suffixes)} {keyword}"
            products.append({
                "id": f"P{i+1:04d}",
                "name": name,
                "asin": f"B{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=10))}",
                "price": round(random.uniform(9.99, 199.99), 2),
                "rating": round(random.uniform(3.0, 5.0), 1),
                "review_count": random.randint(10, 50000),
                "sales_rank": random.randint(1, 10000),
            })

        return products

    async def _mock_analyze_pricing(self, category: str) -> dict:
        """模拟价格分析(实际应基于真实数据统计)。"""
        import random

        return {
            "category": category,
            "avg_price": round(random.uniform(20, 80), 2),
            "median_price": round(random.uniform(15, 70), 2),
            "price_std": round(random.uniform(10, 40), 2),
            "min_price": round(random.uniform(5, 15), 2),
            "max_price": round(random.uniform(150, 300), 2),
            "quartiles": {
                "q1": round(random.uniform(12, 35), 2),
                "q2": round(random.uniform(25, 60), 2),
                "q3": round(random.uniform(45, 90), 2),
            },
        }

    async def _mock_estimate_market_size(self, category: str, region: str = "US") -> dict:
        """模拟市场规模估算(实际应调用外部API或知识库)。"""
        import random

        base = random.uniform(1e8, 5e10)

        return {
            "category": category,
            "region": region,
            "tam": round(base, 0),
            "sam": round(base * random.uniform(0.15, 0.35), 0),
            "som": round(base * random.uniform(0.01, 0.08), 0),
            "cagr": round(random.uniform(5, 25), 1),
            "source_year": 2025,
        }


def create_market_insight_agent(config: dict | None = None) -> MarketInsightAgent:
    """创建MarketInsightAgent工厂函数。"""
    return MarketInsightAgent(config=config)
