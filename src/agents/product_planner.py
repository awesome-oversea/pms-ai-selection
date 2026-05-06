"""
产品规划Agent
============

提供产品定义与规划能力(D19-T055):
    - 产品规格生成(功能/参数/卖点)
    - 供应链可行性评估
    - 成本结构分析
    - 产品差异化评分
    - 选品推荐排序

使用方式:
    from src.agents.product_planner import ProductPlannerAgent

    agent = ProductPlannerAgent()
    result = await agent.run({
        "query": "设计一款蓝牙耳机",
        "category": "bluetooth_earbuds",
        "target_market": "US",
        "budget_range": [15, 50],
    })
"""

from __future__ import annotations

import os
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import AgentTool, AgentType, BaseAgent
from src.agents.data_collection import Tool1688
from src.config.settings import get_settings
from src.core.logging import get_logger
from src.infrastructure.crm_client import CRMClient
from src.services.audio_transcription_service import (
    AudioTranscriptionService,
)
from src.services.multimodal_inference_service import MultimodalInferenceService

logger = get_logger(__name__)


@dataclass
class ProductSpec:
    """
    产品规格定义。

    Attributes:
        name: 产品名称建议
        category: 产品类目
        target_price: 目标售价区间
        core_features: 核心功能列表
        key_parameters: 关键技术参数
        selling_points: 独特卖点(USP)
        positioning: 市场定位(budget/mid-range/premium)
    """

    name: str = ""
    category: str = ""
    target_price: tuple[float, float] = (0.0, 0.0)
    core_features: list[str] = field(default_factory=list)
    key_parameters: dict[str, Any] = field(default_factory=dict)
    selling_points: list[str] = field(default_factory=list)
    positioning: str = "mid-range"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "target_price": f"${self.target_price[0]:.2f} - ${self.target_price[1]:.2f}",
            "core_features": self.core_features[:10],
            "key_parameters": self.key_parameters,
            "selling_points": self.selling_points[:6],
            "positioning": self.positioning,
        }


@dataclass
class SupplyChainAssessment:
    """
    供应链可行性评估。

    Attributes:
        sourcing_difficulty: 采购难度(easy/medium/hard)
        lead_time_days: 交货周期(天)
        moq: 最小起订量
        supplier_count: 可选供应商数量
        risk_level: 风险等级(low/medium/high)
        recommendations: 改进建议
    """

    sourcing_difficulty: str = "medium"
    lead_time_days: int = 30
    moq: int = 500
    supplier_count: int = 3
    risk_level: str = "medium"
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourcing_difficulty": self.sourcing_difficulty,
            "lead_time_days": self.lead_time_days,
            "moq": self.moq,
            "supplier_count": self.supplier_count,
            "risk_level": self.risk_level,
            "recommendations": self.recommendations,
        }


@dataclass
class CostStructure:
    """
    成本结构分析。

    Attributes:
        unit_cost_usd: 单位成本(美元)
        fob_price: FOB价格
        landed_cost: 到岸成本(含运费/关税)
        amazon_fees: Amazon平台费用估算
        gross_margin: 毛利率(%)
        roi_estimate: ROI预估(%)
        cost_breakdown: 成本明细
    """

    unit_cost_usd: float = 0.0
    fob_price: float = 0.0
    landed_cost: float = 0.0
    amazon_fees: float = 0.0
    gross_margin: float = 0.0
    roi_estimate: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_cost": f"${self.unit_cost_usd:.2f}",
            "fob_price": f"${self.fob_price:.2f}",
            "landed_cost": f"${self.landed_cost:.2f}",
            "amazon_fees_pct": f"{self.amazon_fees:.1f}%",
            "gross_margin": f"{self.gross_margin:.1f}%",
            "roi_estimate": f"{self.roi_estimate:.1f}%",
            "cost_breakdown": {k: f"${v:.2f}" for k, v in self.cost_breakdown.items()},
        }


@dataclass
class DifferentiationScore:
    """
    产品差异化评分。

    Attributes:
        overall: 综合差异化得分(0-100)
        feature_uniqueness: 功能独特性得分(0-25)
        quality_perception: 质量感知得分(0-25)
        price_competitiveness: 价格竞争力得分(0-25)
        brand_potential: 品牌潜力得分(0-25)
        gap_analysis: 差距分析
        improvement_suggestions: 改进建议
    """

    overall: float = 0.0
    feature_uniqueness: float = 0.0
    quality_perception: float = 0.0
    price_competitiveness: float = 0.0
    brand_potential: float = 0.0
    gap_analysis: list[dict] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall, 1),
            "feature_uniqueness": round(self.feature_uniqueness, 1),
            "quality_perception": round(self.quality_perception, 1),
            "price_competitiveness": round(self.price_competitiveness, 1),
            "brand_potential": round(self.brand_potential, 1),
            "gap_analysis": self.gap_analysis[:8],
            "improvement_suggestions": self.improvement_suggestions[:6],
        }


@dataclass
class ProductRecommendation:
    """
    选品推荐结果。

    Attributes:
        rank: 排名
        product_name: 产品名称
        confidence: 推荐置信度(0-100)
        expected_roi: 预期ROI(%)
        time_to_market: 上市周期(周)
        risk_rating: 风险等级(1-5)
        pros: 优势列表
        cons: 劣势列表
        action_items: 行动建议
    """

    rank: int = 0
    product_name: str = ""
    confidence: float = 0.0
    expected_roi: float = 0.0
    time_to_market: int = 8
    risk_rating: int = 3
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "product_name": self.product_name,
            "confidence": round(self.confidence, 1),
            "expected_roi": f"{self.expected_roi:.1f}%",
            "time_to_market_weeks": self.time_to_market,
            "risk_rating": f"{'⭐' * self.risk_rating}{'☆' * (5 - self.risk_rating)}",
            "pros": self.pros,
            "cons": self.cons,
            "action_items": self.action_items,
        }


class ProductPlannerAgent(BaseAgent):
    """
    产品规划Agent(D19-T055)。

    功能:
        1. 产品规格生成(功能/参数/定位)
        2. 供应链可行性评估
        3. 成本结构与利润率分析
        4. 产品差异化评分
        5. 多方案推荐与排序

    输入:
        - query: 用户需求描述
        - category: 目标品类
        - target_market: 目标市场
        - budget_range: 预算区间[min, max]
    """

    name = "product_planner"
    agent_type = AgentType.PRODUCT_PLANNER
    version = "1.0.0"
    description = "产品规划Agent - 定义产品规格、评估供应链、分析成本、推荐选品"
    timeout_seconds = 120

    REQUIRED_INPUT_KEYS = {"query", "category"}

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self.tool_1688 = Tool1688()
        self.multimodal_service = MultimodalInferenceService()

        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """注册内置工具。"""
        self.register_tool(AgentTool(
            name="generate_spec",
            description="根据品类和预算生成产品规格",
            func=self._mock_generate_spec,
            parameters={
                "category": {"type": "string"},
                "budget_min": {"type": "number"},
                "budget_max": {"type": "number"},
            },
        ))

        self.register_tool(AgentTool(
            name="assess_supply_chain",
            description="评估供应链可行性",
            func=self._mock_assess_supply_chain,
            parameters={
                "category": {"type": "string"},
                "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        ))

        self.register_tool(AgentTool(
            name="calculate_costs",
            description="计算成本结构和利润率",
            func=self._mock_calculate_costs,
            parameters={
                "target_price": {"type": "number"},
                "category": {"type": "string"},
            },
        ))

        self.register_tool(AgentTool(
            name="llava_analyze_image",
            description="多模态分析: 默认使用 Qwen3.5-2B（Ollama `qwen3.5:2b`），对商品图片输出特征描述/视觉属性/设计缺陷",
            func=self._llava_analyze_image,
            parameters={
                "image_url": {"type": "string", "description": "图片URL或base64"},
                "analysis_type": {"type": "string", "enum": ["features", "design_defects", "comparison"], "default": "features"},
                "prompt": {"type": "string", "description": "补充分析提示"},
                "use_mock": {"type": "boolean", "description": "是否强制 mock 多模态分析"},
            },
        ))

        self.register_tool(AgentTool(
            name="analyze_tiktok_video",
            description="TikTok视频内容分析: 转录/关键帧/热点卖点与风险提取",
            func=self._analyze_tiktok_video,
            parameters={
                "video_url": {"type": "string", "description": "视频URL或唯一引用"},
                "video_title": {"type": "string", "description": "视频标题"},
                "video_description": {"type": "string", "description": "视频描述"},
                "prompt": {"type": "string", "description": "补充分析提示"},
                "use_mock": {"type": "boolean", "description": "是否强制 mock 视频分析"},
            },
        ))

        self.register_tool(AgentTool(
            name="transcribe_audio",
            description="Whisper tiny 兼容音频转录: 提取转录文本、语言与产品使用场景",
            func=self._transcribe_audio_asset,
            parameters={
                "audio_url": {"type": "string", "description": "音频URL、本地路径或 sample:// 引用"},
                "audio_base64": {"type": "string", "description": "base64编码音频，可选"},
                "language": {"type": "string", "description": "语言提示，如 zh/en/ja"},
                "prompt": {"type": "string", "description": "转录附加提示"},
                "title": {"type": "string", "description": "音频标题"},
                "description": {"type": "string", "description": "音频描述"},
                "use_mock": {"type": "boolean", "description": "是否强制 mock 转录"},
            },
        ))

        self.register_tool(AgentTool(
            name="analyze_social_image_trends",
            description="Instagram/Pinterest 图片趋势分析: 标签聚合/视觉方向/热门风格识别",
            func=self._analyze_social_image_trends,
            parameters={
                "image_posts": {"type": "array", "items": {"type": "object"}, "description": "社交图片帖子列表"},
            },
        ))

        self.register_tool(AgentTool(
            name="cluster_reviews",
            description="K-Means评论聚类: 痛点提取/情感分组/关键词频率",
            func=self._cluster_reviews,
            parameters={
                "reviews": {"type": "array", "items": {"type": "string"}, "description": "评论文本列表"},
                "n_clusters": {"type": "integer", "default": 5, "description": "聚类数量"},
            },
        ))

        self.register_tool(AgentTool(
            name="compare_1688_specs",
            description="1688同类商品规格参数比对: 拉取供应商规格并与目标产品功能配置比对",
            func=self._compare_1688_specs,
            parameters={
                "product_keyword": {"type": "string", "description": "1688商品关键词"},
                "product_spec": {"type": "object", "description": "目标产品规格"},
                "max_suppliers": {"type": "integer", "default": 5, "description": "最大供应商数"},
            },
        ))

        self.register_tool(AgentTool(
            name="fetch_crm_reviews",
            description="CRM评价数据接入: 拉取评分/评论文本/客诉并生成摘要",
            func=self._fetch_crm_reviews,
            parameters={
                "crm_api_endpoint": {"type": "string", "description": "CRM API endpoint"},
                "crm_api_key": {"type": "string", "description": "CRM API key"},
                "crm_inbound_path": {"type": "string", "default": "/customer-feedback", "description": "CRM inbound path"},
                "product_id": {"type": "string", "description": "产品ID"},
                "product_name": {"type": "string", "description": "产品名"},
                "asin": {"type": "string", "description": "ASIN"},
            },
        ))

        self.register_tool(AgentTool(
            name="competitor_diff",
            description="竞品差异化矩阵: 功能对比/价格定位/优劣势分析",
            func=self._competitor_diff_analysis,
            parameters={
                "product_name": {"type": "string", "description": "目标产品名"},
                "category": {"type": "string", "description": "品类"},
                "competitors": {"type": "array", "items": {"type": "string"}, "description": "竞品列表"},
            },
        ))

        self.register_tool(AgentTool(
            name="swot_analysis",
            description="SWOT分析: 优势/劣势/机会/威胁自动生成",
            func=self._swot_analysis,
            parameters={
                "product_spec": {"type": "object", "description": "产品规格字典"},
                "market_data": {"type": "object", "description": "市场数据(可选)"},
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
        执行产品规划流程。

        流程:
            1. RAG检索同类产品参考
            2. 产品规格生成
            3. 供应链评估
            4. 成本结构计算
            5. 差异化评分
            6. 多方案推荐
        """
        query = input_data.get("query", "")
        category = input_data.get("category", "")
        budget = input_data.get("budget_range", [10, 100])
        target_market = input_data.get("target_market", "US")
        external_context = input_data.get("knowledge_query_results") if isinstance(input_data.get("knowledge_query_results"), list) else None
        graph_query_result = input_data.get("graph_query_result") if isinstance(input_data.get("graph_query_result"), dict) else {}

        retrieve_step = self._create_step("retrieve_references", "retrieve", input_data=query[:100])
        context = await self._retrieve_context(query, category, external_results=external_context)
        retrieve_step.output_data = f"检索到 {len(context)} 条参考"

        spec_step = self._create_step("generate_product_spec", "planning")
        spec = await self.call_tool(
            "generate_spec",
            category=category,
            budget_min=budget[0],
            budget_max=budget[1],
        )
        spec_step.output_data = f"产品: {getattr(spec, 'name', 'N/A')}"

        supply_step = self._create_step("supply_chain_assessment", "analysis")
        supply = await self.call_tool("assess_supply_chain", category=category)
        supply_step.output_data = f"风险等级: {getattr(supply, 'risk_level', 'N/A')}"

        cost_step = self._create_step("cost_structure_calculation", "analysis")
        target_price = (budget[0] + budget[1]) / 2
        costs = await self.call_tool("calculate_costs", target_price=target_price, category=category)
        cost_step.output_data = f"毛利率: {getattr(costs, 'gross_margin', 0)}%"

        diff_step = self._create_step("differentiation_scoring", "scoring")
        diff_score = self._calculate_differentiation(spec, supply, costs)
        diff_step.output_data = f"差异化得分: {diff_score.overall}"

        review_cluster_step = self._create_step("cluster_review_feedback", "analysis")
        review_insights = await self.call_tool(
            "cluster_reviews",
            reviews=input_data.get("reviews") or [],
            n_clusters=int(input_data.get("review_clusters") or 5),
        )
        review_cluster_step.output_data = f"评论聚类 {review_insights.get('cluster_count', review_insights.get('n_clusters', 0))} 组"

        spec_compare_step = self._create_step("compare_1688_specs", "analysis")
        spec_comparison = await self.call_tool(
            "compare_1688_specs",
            product_keyword=query,
            product_spec=spec.to_dict() if isinstance(spec, ProductSpec) else (spec or {}),
            max_suppliers=int(input_data.get("max_suppliers") or 5),
        )
        spec_compare_step.output_data = f"1688规格比对 {spec_comparison.get('supplier_count', 0)} 家供应商"

        crm_review_step = self._create_step("fetch_crm_reviews", "analysis")
        crm_review_insights = await self.call_tool(
            "fetch_crm_reviews",
            crm_api_endpoint=str(input_data.get("crm_api_endpoint") or "file://artifacts/erp_local/crm"),
            crm_api_key=input_data.get("crm_api_key"),
            crm_inbound_path=str(input_data.get("crm_inbound_path") or "/feedback"),
            product_id=str(input_data.get("product_id") or "selection-task-erp-real-001"),
            product_name=getattr(spec, "name", None) if isinstance(spec, ProductSpec) else None,
            asin=str(input_data.get("asin") or "B0ERP0001"),
        )
        crm_review_step.output_data = f"CRM评价 {crm_review_insights.get('matched_review_count', 0)} 条"

        image_analysis_step = self._create_step("analyze_review_images", "analysis")
        review_images = input_data.get("review_images") if isinstance(input_data.get("review_images"), list) else []
        image_review_insights = await self._analyze_review_images(review_images, use_mock=input_data.get("use_mock"))
        image_analysis_step.output_data = f"评论图片分析 {image_review_insights.get('image_count', 0)} 张"

        tiktok_video_step = self._create_step("analyze_tiktok_videos", "analysis")
        tiktok_videos = input_data.get("tiktok_videos") if isinstance(input_data.get("tiktok_videos"), list) else []
        tiktok_video_insights = await self._analyze_tiktok_video_batch(tiktok_videos, use_mock=input_data.get("use_mock"))
        tiktok_video_step.output_data = f"TikTok视频分析 {tiktok_video_insights.get('video_count', 0)} 条"

        audio_transcription_step = self._create_step("transcribe_audio_assets", "analysis")
        audio_assets = input_data.get("audio_assets") if isinstance(input_data.get("audio_assets"), list) else []
        audio_transcription_insights = await self._transcribe_audio_batch(audio_assets, use_mock=input_data.get("use_mock"))
        audio_transcription_step.output_data = f"音频转录 {audio_transcription_insights.get('audio_count', 0)} 条"

        social_image_step = self._create_step("analyze_social_image_trends", "analysis")
        social_images = input_data.get("social_images") if isinstance(input_data.get("social_images"), list) else []
        social_image_trends = await self.call_tool("analyze_social_image_trends", image_posts=social_images)
        social_image_step.output_data = f"社交图片趋势分析 {social_image_trends.get('image_count', 0)} 张"

        rec_step = self._create_step("generate_recommendations", "output")
        recommendations = self._generate_recommendations(spec, costs, diff_score, supply)
        rec_step.output_data = f"生成 {len(recommendations)} 个推荐方案"

        # LLM 智能产品规划建议（可选，失败降级）
        llm_planning = ""
        llm_planning_structured: dict[str, Any] = {}
        try:
            from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway

            llm_settings = get_settings().llm
            local_runtime_mode = os.getenv("LOCAL_RUNTIME_SCENARIO_MODE", "").strip().lower()
            use_real_llm = input_data.get("use_mock") is False or local_runtime_mode == "local-real"
            gateway = LLMGateway(
                GatewayConfig(
                    use_mock=not use_real_llm,
                    provider_mode="real" if use_real_llm else "mock",
                    vllm_endpoint=llm_settings.vllm_endpoint,
                    ollama_endpoint=llm_settings.ollama_endpoint,
                    ollama_model_name=llm_settings.primary_model,
                    vllm_timeout_seconds=llm_settings.request_timeout_seconds,
                    ollama_timeout_seconds=min(llm_settings.request_timeout_seconds, 15.0),
                    api_key=llm_settings.api_key,
                    api_auth_header=llm_settings.api_auth_header,
                    api_auth_scheme=llm_settings.api_auth_scheme,
                    api_model_name=llm_settings.api_model_name,
                    retry_count=llm_settings.request_retry_count,
                )
            )
            llm_step = self._create_step("llm_product_planning", "reason")
            spec_dict = spec.to_dict() if isinstance(spec, ProductSpec) else spec
            prompt = (
                f"你是跨境电商产品规划专家。以下是对「{category}」品类的产品规划分析结果：\n"
                f"- 产品名称: {spec_dict.get('name', 'N/A')}\n"
                f"- 市场定位: {spec_dict.get('positioning', 'N/A')}\n"
                f"- 目标价格: {spec_dict.get('target_price', 'N/A')}\n"
                f"- 供应链风险: {getattr(supply, 'risk_level', 'N/A')}\n"
                f"- 毛利率: {getattr(costs, 'gross_margin', 0):.1f}%\n"
                f"- 差异化得分: {diff_score.overall:.1f}/100\n"
                f"- 推荐方案数: {len(recommendations)}\n\n"
                f"请用JSON格式输出产品规划建议，包含字段: "
                f"product_viability(1-10), differentiation_strategy(string), "
                f"key_risks(list[string]), go_to_market_advice(string), "
                f"suggested_improvements(list[string])"
            )
            llm_result = await gateway.route(prompt=prompt)
            llm_planning = llm_result.response
            llm_planning_structured = self._parse_llm_json_response(llm_result.response)
            llm_step.output_data = f"LLM规划建议完成 ({llm_result.tokens_used} tokens)"
            llm_step.status = "success"
        except Exception as e:
            logger.warning(f"LLM产品规划建议降级: {e}")
            llm_planning = ""
            llm_planning_structured = {}

        knowledge_citations = [item["citation"] for item in context if isinstance(item, dict) and item.get("citation")]
        graph_results = graph_query_result.get("results") if isinstance(graph_query_result.get("results"), list) else []
        graph_evidence_sources = list(graph_query_result.get("evidence_sources") or [])
        graph_business_summary = graph_query_result.get("business_summary") if isinstance(graph_query_result.get("business_summary"), dict) else {}

        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "budget_range": budget,
            "product_spec": spec.to_dict() if isinstance(spec, ProductSpec) else spec,
            "supply_chain": supply.to_dict() if isinstance(supply, SupplyChainAssessment) else supply,
            "cost_structure": costs.to_dict() if isinstance(costs, CostStructure) else costs,
            "differentiation": diff_score.to_dict(),
            "review_insights": review_insights,
            "supplier_spec_comparison": spec_comparison,
            "crm_review_insights": crm_review_insights,
            "image_review_insights": image_review_insights,
            "tiktok_video_insights": tiktok_video_insights,
            "audio_transcription_insights": audio_transcription_insights,
            "social_image_trends": social_image_trends,
            "recommendations": [r.to_dict() for r in recommendations],
            "llm_planning": llm_planning,
            "llm_planning_structured": llm_planning_structured,
            "reference_context": context,
            "knowledge_citations": knowledge_citations,
            "graph_context": {
                "result_count": len(graph_results),
                "evidence_sources": graph_evidence_sources,
                "business_summary": graph_business_summary,
            },
            "context_sources": len(context),
            "reference_summary": {
                "knowledge_result_count": len(context),
                "citation_count": len(knowledge_citations),
                "graph_result_count": len(graph_results),
                "graph_evidence_sources": graph_evidence_sources,
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def format_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """格式化输出为标准API响应格式。"""
        recs = raw_output.get("recommendations", [])
        top_rec = recs[0] if recs else {}

        summary = (
            f"[{raw_output.get('category', '该品类')}]产品规划报告\n"
            f"推荐产品: {top_rec.get('product_name', '待定')}\n"
            f"预期ROI: {top_rec.get('expected_roi', 'N/A')}\n"
            f"风险评级: {top_rec.get('risk_rating', 'N/A')}\n"
            f"上市周期: {top_rec.get('time_to_market_weeks', 'N/A')}周\n"
        )

        return {
            "status": "success",
            "summary": summary,
            "data": raw_output,
            "top_recommendation": top_rec,
        }

    @staticmethod
    def _build_context_citation(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") or {}
        content = str(item.get("content") or "")
        return {
            "document_id": item.get("document_id") or metadata.get("document_id"),
            "chunk_index": item.get("chunk_index") if item.get("chunk_index") is not None else metadata.get("chunk_index"),
            "source": item.get("source") or metadata.get("source") or metadata.get("filename"),
            "snippet": content[:160],
        }

    @classmethod
    def _normalize_context_items(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            current = {
                "content": str(item.get("content") or ""),
                "score": float(item.get("score") or 0.0),
                "source": item.get("source") or metadata.get("source") or metadata.get("filename"),
                "document_id": item.get("document_id") or metadata.get("document_id"),
                "chunk_index": item.get("chunk_index") if item.get("chunk_index") is not None else metadata.get("chunk_index"),
                "metadata": metadata,
            }
            current["citation"] = item.get("citation") or cls._build_context_citation(current)
            normalized.append(current)
        return normalized

    async def _retrieve_context(self, query: str, category: str, external_results: list[dict[str, Any]] | None = None) -> list[dict]:
        """RAG检索同类产品参考信息。"""
        if external_results:
            normalized = self._normalize_context_items(external_results)
            if normalized:
                return normalized
        try:
            from src.rag.retriever import HybridRetriever

            retriever = HybridRetriever(enable_rerank=True)

            sample_docs = [
                {"id": f"ref_{i}", "content": f"{category}产品设计参考第{i}条: 主流配置与市场反馈", "metadata": {"source": "product_db"}}
                for i in range(4)
            ]
            retriever.add_documents(sample_docs)

            results = await retriever.retrieve(f"{category} 产品规划", top_k=4)

            return self._normalize_context_items(
                [
                    {
                        "content": r.content,
                        "score": r.score,
                        "source": r.source,
                        "document_id": (r.metadata or {}).get("document_id"),
                        "chunk_index": (r.metadata or {}).get("chunk_index"),
                        "metadata": r.metadata or {},
                    }
                    for r in results
                ]
            )
        except Exception as e:
            logger.warning(f"RAG检索降级: {e}")
            return []

    def _calculate_differentiation(
        self,
        spec: ProductSpec,
        supply: SupplyChainAssessment,
        costs: CostStructure,
    ) -> DifferentiationScore:
        """
        计算产品差异化评分。

        四维度各25分:
            1. feature_uniqueness: 基于功能数量+独特卖点数
            2. quality_perception: 基于定位+供应链风险
            3. price_competitiveness: 基于毛利率
            4. brand_potential: 基于综合因素
        """
        feature_score = min(25, len(spec.core_features) * 3 + len(spec.selling_points) * 2)

        if spec.positioning == "premium":
            quality_base = 20
        elif spec.positioning == "mid-range":
            quality_base = 15
        else:
            quality_base = 10

        if supply.risk_level == "low":
            quality_score = min(25, quality_base + 5)
        elif supply.risk_level == "high":
            quality_score = max(5, quality_base - 5)
        else:
            quality_score = quality_base

        if costs.gross_margin >= 40:
            price_score = 22
        elif costs.gross_margin >= 25:
            price_score = 16
        elif costs.gross_margin >= 15:
            price_score = 10
        else:
            price_score = 5

        brand_score = min(25, (feature_score + quality_score + price_score) / 3)

        overall = feature_score + quality_score + price_score + brand_score

        gaps = []
        if feature_score < 15:
            gaps.append({"dimension": "功能独特性", "current": feature_score, "target": 20, "gap": 20 - feature_score})
        if quality_score < 15:
            gaps.append({"dimension": "质量感知", "current": quality_score, "target": 18, "gap": 18 - quality_score})
        if price_score < 12:
            gaps.append({"dimension": "价格竞争力", "current": price_score, "target": 16, "gap": 16 - price_score})

        suggestions = []
        if not gaps:
            suggestions.append("产品差异化表现良好，可考虑进一步强化品牌故事")
        for gap in gaps:
            suggestions.append(f"提升{gap['dimension']}: 当前{gap['current']}分，目标{gap['target']}分")

        return DifferentiationScore(
            overall=overall,
            feature_uniqueness=feature_score,
            quality_perception=quality_score,
            price_competitiveness=price_score,
            brand_potential=brand_score,
            gap_analysis=gaps,
            improvement_suggestions=suggestions,
        )

    def _generate_recommendations(
        self,
        spec: ProductSpec,
        costs: CostStructure,
        diff: DifferentiationScore,
        supply: SupplyChainAssessment,
    ) -> list[ProductRecommendation]:
        """生成多方案推荐并按优先级排序。"""
        base_name = spec.name or spec.category or "Product"

        candidates = [
            {
                "suffix": "(Premium版)",
                "price_factor": 1.5,
                "margin_adj": 5,
                "risk_adj": -1,
                "pros": ["高利润空间", "品牌形象好"],
                "cons": ["竞争激烈", "需强营销投入"],
            },
            {
                "suffix": "(标准版)",
                "price_factor": 1.0,
                "margin_adj": 0,
                "risk_adj": 0,
                "pros": ["性价比均衡", "受众广泛"],
                "cons": ["同质化风险"],
            },
            {
                "suffix": "(入门版)",
                "price_factor": 0.7,
                "margin_adj": -5,
                "risk_adj": 1,
                "pros": ["低门槛", "走量策略"],
                "cons": ["利润薄", "品质感弱"],
            },
        ]

        recommendations = []
        for i, cand in enumerate(candidates):
            adj_roi = costs.roi_estimate + cand["margin_adj"]
            adj_risk = max(1, min(5, 3 + cand["risk_adj"] + (1 if supply.risk_level == "high" else 0)))

            conf = (diff.overall / 100) * (100 - (adj_risk - 1) * 10)

            rec = ProductRecommendation(
                rank=i + 1,
                product_name=f"{base_name} {cand['suffix']}",
                confidence=max(30, min(95, conf)),
                expected_roi=max(-10, adj_roi),
                time_to_market=supply.lead_time_days // 7 + 2,
                risk_rating=adj_risk,
                pros=cand["pros"],
                cons=cand["cons"],
                action_items=[
                    "确认目标售价区间",
                    f"联系{supply.supplier_count}家供应商报价",
                    "制作产品原型(MVP)",
                    f"小批量测试({max(100, supply.moq // 5)}件)",
                ],
            )
            recommendations.append(rec)

        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        for i, r in enumerate(recommendations):
            r.rank = i + 1

        return recommendations

    async def _mock_generate_spec(
        self,
        category: str,
        budget_min: float = 10,
        budget_max: float = 100,
    ) -> ProductSpec:
        """模拟产品规格生成。"""
        mid_price = (budget_min + budget_max) / 2

        if mid_price > 60:
            positioning = "premium"
            features = ["主动降噪(ANC)", "空间音频", "Hi-Res认证", "无线充电", "IPX5防水"]
            params = {"battery_hours": 36, "driver_size": "11mm", "codec": "LDAC/aptX HD"}
        elif mid_price > 30:
            positioning = "mid-range"
            features = ["混合降噪", "通透模式", "蓝牙5.3", "触控操作", "ENC通话降噪"]
            params = {"battery_hours": 28, "driver_size": "10mm", "codec": "AAC/SBC"}
        else:
            positioning = "budget"
            features = ["轻量化设计", "长续航", "蓝牙5.0", "磁吸充电", "防水防汗"]
            params = {"battery_hours": 24, "driver_size": "8mm", "codec": "SBC"}

        return ProductSpec(
            name=f"Smart {category.title()} Pro",
            category=category,
            target_price=(budget_min, budget_max),
            core_features=features,
            key_parameters=params,
            selling_points=[
                f"{features[0]}技术加持",
                f"超长续航{params.get('battery_hours', 24)}小时",
                "人体工学佩戴设计",
                "多设备无缝切换",
            ],
            positioning=positioning,
        )

    async def _mock_assess_supply_chain(
        self,
        category: str,
        complexity: str = "medium",
    ) -> SupplyChainAssessment:
        """模拟供应链评估。"""
        import random

        difficulty_map = {"low": "easy", "medium": "medium", "high": "hard"}

        base_lead = random.randint(14, 45)
        if complexity == "high":
            base_lead += 15

        risk = "low" if complexity == "low" else ("high" if complexity == "high" else "medium")

        recs = []
        if risk != "low":
            recs.append("建议建立备选供应商名单")
        if base_lead > 35:
            recs.append("考虑备货缓冲以应对长交期")
        recs.append("定期审核供应商质量体系")

        return SupplyChainAssessment(
            sourcing_difficulty=difficulty_map.get(complexity, "medium"),
            lead_time_days=base_lead,
            moq=random.randint(200, 2000),
            supplier_count=random.randint(2, 8),
            risk_level=risk,
            recommendations=recs,
        )

    async def _mock_calculate_costs(
        self,
        target_price: float = 39.99,
        category: str = "",
    ) -> CostStructure:
        """模拟成本结构计算。"""
        import random

        unit_cost_ratio = random.uniform(0.25, 0.45)
        unit_cost = target_price * unit_cost_ratio

        shipping = unit_cost * random.uniform(0.08, 0.15)
        duties = unit_cost * random.uniform(0.05, 0.12)
        landed = unit_cost + shipping + duties

        amazon_fee_rate = random.uniform(0.12, 0.18)
        amazon_fees = target_price * amazon_fee_rate

        total_cost = landed + amazon_fees
        margin = ((target_price - total_cost) / target_price) * 100 if target_price > 0 else 0

        roi = margin * random.uniform(1.5, 3.0)

        breakdown = {
            "BOM成本": unit_cost * 0.65,
            "组装人工": unit_cost * 0.15,
            "包装材料": unit_cost * 0.08,
            "质检费用": unit_cost * 0.05,
            "其他制造费": unit_cost * 0.07,
            "国际运费": shipping,
            "进口关税": duties,
        }

        return CostStructure(
            unit_cost_usd=round(unit_cost, 2),
            fob_price=round(unit_cost * 1.08, 2),
            landed_cost=round(landed, 2),
            amazon_fees=round(amazon_fees, 2),
            gross_margin=round(margin, 1),
            roi_estimate=round(roi, 1),
            cost_breakdown={k: round(v, 2) for k, v in breakdown.items()},
        )

    async def _llava_analyze_image(
        self,
        image_url: str = "",
        analysis_type: str = "features",
        prompt: str = "",
        use_mock: bool | None = None,
    ) -> dict:
        return await self.multimodal_service.analyze_image(
            image_url=image_url,
            prompt=prompt,
            analysis_type=analysis_type,
            use_mock=use_mock,
        )

    async def _analyze_review_images(
        self,
        review_images: list[dict[str, Any]] | list[str],
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        normalized_images: list[dict[str, Any]] = []
        for item in review_images[:10]:
            if isinstance(item, str):
                normalized_images.append({"image_url": item, "analysis_type": "features", "prompt": "", "use_mock": use_mock})
            elif isinstance(item, dict):
                normalized_images.append(
                    {
                        "image_url": str(item.get("image_url") or item.get("url") or item.get("base64") or ""),
                        "analysis_type": str(item.get("analysis_type") or "features"),
                        "prompt": str(item.get("prompt") or item.get("caption") or ""),
                        "use_mock": item.get("use_mock", use_mock),
                    }
                )
        analyses: list[dict[str, Any]] = []
        visual_tags: Counter[str] = Counter()
        defect_tags: Counter[str] = Counter()
        for item in normalized_images:
            if not item.get("image_url"):
                continue
            tool_kwargs: dict[str, Any] = {
                "image_url": item["image_url"],
                "analysis_type": item["analysis_type"],
            }
            if item.get("prompt"):
                tool_kwargs["prompt"] = item["prompt"]
            if item.get("use_mock") is not None:
                tool_kwargs["use_mock"] = item["use_mock"]
            result = await self.call_tool(
                "llava_analyze_image",
                **tool_kwargs,
            )
            analyses.append(result)
            for feature in result.get("visual_features", []) if isinstance(result, dict) else []:
                if isinstance(feature, dict) and feature.get("value"):
                    visual_tags[str(feature["value"])] += 1
            for defect in result.get("defects", []) if isinstance(result, dict) else []:
                if isinstance(defect, dict) and defect.get("issue"):
                    defect_tags[str(defect["issue"])] += 1
        return {
            "source": "review_image_multimodal",
            "image_count": len(analyses),
            "supports": ["url", "base64"],
            "analyses": analyses,
            "top_visual_tags": [{"tag": key, "count": value} for key, value in visual_tags.most_common(6)],
            "top_defects": [{"issue": key, "count": value} for key, value in defect_tags.most_common(6)],
        }

    async def _analyze_tiktok_video(
        self,
        video_url: str = "",
        video_title: str = "",
        video_description: str = "",
        prompt: str = "",
        use_mock: bool | None = None,
    ) -> dict:
        return await self.multimodal_service.analyze_video(
            video_url=video_url,
            video_title=video_title,
            video_description=video_description,
            prompt=prompt,
            use_mock=use_mock,
        )

    async def _analyze_tiktok_video_batch(
        self,
        videos: list[dict[str, Any]] | list[str],
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        normalized_videos: list[dict[str, Any]] = []
        for item in videos[:10]:
            if isinstance(item, str):
                normalized_videos.append({"video_url": item, "video_title": "", "video_description": "", "prompt": "", "use_mock": use_mock})
            elif isinstance(item, dict):
                normalized_videos.append(
                    {
                        "video_url": str(item.get("video_url") or item.get("url") or ""),
                        "video_title": str(item.get("video_title") or item.get("title") or ""),
                        "video_description": str(item.get("video_description") or item.get("description") or ""),
                        "prompt": str(item.get("prompt") or ""),
                        "use_mock": item.get("use_mock", use_mock),
                    }
                )
        analyses = []
        selling_point_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()
        for item in normalized_videos:
            if not item.get("video_url"):
                continue
            tool_kwargs: dict[str, Any] = {
                "video_url": item["video_url"],
                "video_title": item["video_title"],
                "video_description": item["video_description"],
            }
            if item.get("prompt"):
                tool_kwargs["prompt"] = item["prompt"]
            if item.get("use_mock") is not None:
                tool_kwargs["use_mock"] = item["use_mock"]
            result = await self.call_tool(
                "analyze_tiktok_video",
                **tool_kwargs,
            )
            analyses.append(result)
            for value in result.get("selling_points", []) if isinstance(result, dict) else []:
                selling_point_counter[str(value)] += 1
            for value in result.get("risks", []) if isinstance(result, dict) else []:
                risk_counter[str(value)] += 1
        return {
            "source": "tiktok_video_batch_analysis",
            "video_count": len(analyses),
            "videos": analyses,
            "top_selling_points": [{"point": key, "count": value} for key, value in selling_point_counter.most_common(5)],
            "top_risks": [{"risk": key, "count": value} for key, value in risk_counter.most_common(5)],
        }

    async def _transcribe_audio_asset(
        self,
        audio_url: str = "",
        audio_base64: str | None = None,
        language: str | None = None,
        prompt: str = "",
        title: str = "",
        description: str = "",
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        service = AudioTranscriptionService()
        return await service.transcribe_audio(
            audio_url=audio_url,
            audio_base64=audio_base64,
            language=language,
            prompt=prompt,
            title=title,
            description=description,
            use_mock=use_mock,
        )

    async def _transcribe_audio_batch(
        self,
        audio_assets: list[dict[str, Any]] | list[str],
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        normalized_assets: list[dict[str, Any]] = []
        for item in audio_assets[:10]:
            if isinstance(item, str):
                normalized_assets.append({"audio_url": item, "language": None, "prompt": "", "title": "", "description": "", "use_mock": use_mock})
            elif isinstance(item, dict):
                normalized_assets.append(
                    {
                        "audio_url": str(item.get("audio_url") or item.get("url") or item.get("path") or ""),
                        "audio_base64": item.get("audio_base64"),
                        "language": item.get("language"),
                        "prompt": str(item.get("prompt") or ""),
                        "title": str(item.get("title") or ""),
                        "description": str(item.get("description") or ""),
                        "use_mock": item.get("use_mock", use_mock),
                    }
                )
        analyses: list[dict[str, Any]] = []
        scenario_counter: Counter[str] = Counter()
        languages: Counter[str] = Counter()
        for item in normalized_assets:
            if not item.get("audio_url") and not item.get("audio_base64"):
                continue
            result = await self.call_tool(
                "transcribe_audio",
                audio_url=item.get("audio_url", ""),
                audio_base64=item.get("audio_base64"),
                language=item.get("language"),
                prompt=item.get("prompt", ""),
                title=item.get("title", ""),
                description=item.get("description", ""),
                use_mock=item.get("use_mock"),
            )
            analyses.append(result)
            languages[str(result.get("detected_language") or "unknown")] += 1
            for scenario in result.get("product_scenarios", []) if isinstance(result, dict) else []:
                scenario_name = str(scenario.get("scenario") or "")
                if scenario_name:
                    scenario_counter[scenario_name] += 1
        return {
            "source": "audio_transcription_batch",
            "audio_count": len(analyses),
            "audios": analyses,
            "top_product_scenarios": [{"scenario": key, "count": value} for key, value in scenario_counter.most_common(6)],
            "languages": [{"language": key, "count": value} for key, value in languages.most_common()],
        }

    async def _analyze_social_image_trends(self, image_posts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        posts = image_posts or []
        normalized_posts: list[dict[str, Any]] = []
        for item in posts[:20]:
            if not isinstance(item, dict):
                continue
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            normalized_posts.append(
                {
                    "platform": str(item.get("platform") or "instagram"),
                    "image_url": str(item.get("image_url") or item.get("url") or ""),
                    "tags": [str(tag).strip().lower() for tag in tags if str(tag).strip()],
                    "caption": str(item.get("caption") or ""),
                    "engagement": float(item.get("engagement") or item.get("likes") or 0),
                }
            )
        if not normalized_posts:
            return {
                "source": "social_image_trends",
                "image_count": 0,
                "platforms": [],
                "top_tags": [],
                "top_visual_directions": [],
            }
        tag_counter: Counter[str] = Counter()
        direction_counter: Counter[str] = Counter()
        platforms: Counter[str] = Counter()
        for item in normalized_posts:
            platforms[item["platform"]] += 1
            caption = item["caption"].lower()
            for tag in item["tags"]:
                tag_counter[tag] += 1
                if tag in {"minimal", "clean", "simple"}:
                    direction_counter["极简风"] += 1
                if tag in {"luxury", "premium", "metal"}:
                    direction_counter["高端质感"] += 1
                if tag in {"sport", "fitness", "outdoor"}:
                    direction_counter["运动场景"] += 1
                if tag in {"cute", "pink", "gift"}:
                    direction_counter["礼赠审美"] += 1
            if "desk" in caption or "desktop" in caption or "办公" in caption:
                direction_counter["桌面办公场景"] += 1
            if "travel" in caption or "通勤" in caption:
                direction_counter["通勤便携场景"] += 1
        return {
            "source": "social_image_trends",
            "image_count": len(normalized_posts),
            "platforms": [{"platform": key, "count": value} for key, value in platforms.most_common()],
            "top_tags": [{"tag": key, "count": value} for key, value in tag_counter.most_common(10)],
            "top_visual_directions": [{"direction": key, "count": value} for key, value in direction_counter.most_common(6)],
            "sample_posts": normalized_posts[:5],
        }

    async def _cluster_reviews(
        self,
        reviews: list[str] | None = None,
        n_clusters: int = 5,
    ) -> dict:
        """
        Amazon评论聚类/痛点挖掘。

        使用确定性关键词主题聚类 + 词频统计，输出：
        - 功能痛点
        - 质量缺陷
        - 设计改进建议
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.02, 0.08))

        sample_reviews = reviews or [
            "音质很好，降噪效果明显，但佩戴久了耳朵会痛",
            "续航不错，但连接有时候不稳定，断连好几次",
            "外观好看，但塑料感太重，不值这个价格",
            "性价比高，音质在这个价位算好的了",
            "客服态度差，退换货麻烦",
            "低音很震撼，适合听电子音乐，但高音有点刺",
            "做工一般，用了两个月就出现杂音",
            "包装精美，送礼有面子，但实际体验一般",
            "APP功能丰富，但操作复杂，学习成本高",
            "轻便舒适，跑步戴着不掉，推荐运动使用",
            "充电快，但电池衰减明显，一年后续航减半",
            "颜值在线，但隔音效果不如预期",
        ]

        topic_rules = {
            "音质": ["音质", "低音", "高音", "杂音", "降噪", "隔音"],
            "佩戴": ["佩戴", "耳朵", "舒适", "夹耳", "重量", "跑步"],
            "连接": ["连接", "断连", "蓝牙", "配对", "信号", "不稳定"],
            "续航": ["续航", "充电", "电池", "电量", "衰减"],
            "做工外观": ["外观", "塑料", "做工", "材质", "质感", "包装"],
            "软件服务": ["客服", "退换货", "APP", "操作", "学习成本"],
        }
        negative_terms = ["差", "不好", "一般", "不值", "断连", "刺", "痛", "麻烦", "杂音", "衰减", "不稳定", "不如预期"]
        positive_terms = ["很好", "不错", "高", "推荐", "震撼", "精美", "在线", "轻便", "舒适"]

        def _classify_sentiment(text: str) -> str:
            neg = sum(1 for term in negative_terms if term in text)
            pos = sum(1 for term in positive_terms if term in text)
            if neg > pos:
                return "negative"
            if pos > neg:
                return "positive"
            return "neutral"

        def _pick_topic(text: str) -> str:
            score_by_topic: dict[str, int] = {}
            for topic, keywords in topic_rules.items():
                score_by_topic[topic] = sum(1 for kw in keywords if kw in text)
            best = max(score_by_topic.items(), key=lambda item: item[1])
            return best[0] if best[1] > 0 else "其他"

        cluster_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        keyword_counter: Counter[str] = Counter()
        for review in sample_reviews:
            sentiment = _classify_sentiment(review)
            topic = _pick_topic(review)
            for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", review):
                if len(token) >= 2:
                    keyword_counter[token] += 1
            cluster_buckets[topic].append({"text": review, "sentiment": sentiment})

        ordered_topics = sorted(cluster_buckets.items(), key=lambda item: len(item[1]), reverse=True)[: max(1, n_clusters)]
        clusters: list[dict[str, Any]] = []
        pain_points: list[dict[str, Any]] = []
        function_pain_points: list[str] = []
        quality_defects: list[str] = []
        design_improvements: list[str] = []

        for cluster_id, (topic, items) in enumerate(ordered_topics):
            sentiments = Counter(item["sentiment"] for item in items)
            top_keywords = [kw for kw in topic_rules.get(topic, []) if any(kw in item["text"] for item in items)][:5]
            dominant_sentiment = sentiments.most_common(1)[0][0] if sentiments else "neutral"
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "label": topic,
                    "sentiment": dominant_sentiment,
                    "review_count": len(items),
                    "keywords": top_keywords,
                    "sample_reviews": [item["text"] for item in items[:3]],
                }
            )

            if dominant_sentiment == "negative":
                point = f"{topic}问题集中出现"
                solution = {
                    "音质": "优化声学腔体与调音，提升高频顺滑度并降低底噪",
                    "佩戴": "优化耳塞曲线与重量分布，提升长时间佩戴舒适度",
                    "连接": "升级蓝牙协议与天线设计，降低断连概率",
                    "续航": "优化电源管理与电芯方案，提升循环寿命",
                    "做工外观": "提升材质与装配工艺，增强品质感",
                    "软件服务": "优化APP交互与售后流程，降低使用门槛",
                }.get(topic, "针对高频差评问题进行专项改版")
                frequency = round(len(items) / max(len(sample_reviews), 1), 4)
                pain_points.append(
                    {
                        "point": point,
                        "frequency": frequency,
                        "severity": "high" if frequency >= 0.2 else "medium",
                        "solution": solution,
                    }
                )
                if topic in {"音质", "连接", "续航", "软件服务"}:
                    function_pain_points.append(point)
                if topic in {"做工外观", "续航"}:
                    quality_defects.append(point)
                if topic in {"佩戴", "做工外观"}:
                    design_improvements.append(solution)

        sentiment_counter = Counter(_classify_sentiment(text) for text in sample_reviews)
        total_reviews = len(sample_reviews)
        top_keywords = [{"word": word, "count": count} for word, count in keyword_counter.most_common(10)]
        pain_points.sort(key=lambda item: item["frequency"], reverse=True)

        actionable_insights = []
        if pain_points:
            actionable_insights.append(f"优先解决Top1痛点: {pain_points[0]['point']}")
        if function_pain_points:
            actionable_insights.append("优先将功能性差评纳入下一轮规格定义")
        if design_improvements:
            actionable_insights.append("将佩戴/外观相关改进项同步给ID与结构设计")

        return {
            "source": "review_clustering",
            "algorithm": "rule-cluster + keyword-frequency",
            "total_reviews": total_reviews,
            "n_clusters": min(n_clusters, len(clusters)),
            "cluster_count": len(clusters),
            "clusters": clusters,
            "pain_points": pain_points,
            "function_pain_points": function_pain_points,
            "quality_defects": quality_defects,
            "design_improvements": list(dict.fromkeys(design_improvements)),
            "top_keywords": top_keywords,
            "sentiment_summary": {
                "positive_pct": round(sentiment_counter.get("positive", 0) / max(total_reviews, 1), 4),
                "neutral_pct": round(sentiment_counter.get("neutral", 0) / max(total_reviews, 1), 4),
                "negative_pct": round(sentiment_counter.get("negative", 0) / max(total_reviews, 1), 4),
            },
            "actionable_insights": actionable_insights,
        }

    @staticmethod
    def _extract_target_spec_features(product_spec: dict[str, Any]) -> list[str]:
        features = product_spec.get("core_features") if isinstance(product_spec.get("core_features"), list) else []
        params = product_spec.get("key_parameters") if isinstance(product_spec.get("key_parameters"), dict) else {}
        normalized = [str(item).strip().lower() for item in features if str(item).strip()]
        for key, value in params.items():
            normalized.append(f"{str(key).strip().lower()}:{str(value).strip().lower()}")
        return normalized

    @staticmethod
    def _build_supplier_spec_snapshot(supplier: dict[str, Any]) -> dict[str, Any]:
        first_tier = (supplier.get("moq_tiers") or [{}])[0] if isinstance(supplier.get("moq_tiers"), list) else {}
        return {
            "verified": bool(supplier.get("is_verified")),
            "trade_assurance": bool(supplier.get("trade_assurance")),
            "oem_odm_supported": bool(supplier.get("oem_odm_supported")),
            "sample_available": bool(supplier.get("sample_available")),
            "lead_time_days": supplier.get("lead_time_days"),
            "min_qty": first_tier.get("min_qty") or supplier.get("moq"),
            "unit_price_usd": first_tier.get("unit_price_usd") or supplier.get("unit_price_usd"),
        }

    async def _compare_1688_specs(
        self,
        product_keyword: str,
        product_spec: dict[str, Any] | None = None,
        max_suppliers: int = 5,
    ) -> dict[str, Any]:
        payload = await self.tool_1688.execute(product_keyword=product_keyword, max_suppliers=max_suppliers)
        suppliers = payload.get("suppliers") if isinstance(payload.get("suppliers"), list) else []
        target_spec = product_spec or {}
        target_features = self._extract_target_spec_features(target_spec)
        target_text = " ".join(target_features)

        supplier_comparisons: list[dict[str, Any]] = []
        difference_items: list[dict[str, Any]] = []
        for supplier in suppliers[:max_suppliers]:
            if not isinstance(supplier, dict):
                continue
            snapshot = self._build_supplier_spec_snapshot(supplier)
            matched = []
            missing = []
            for feature in target_features:
                feature_key = feature.split(":", 1)[0]
                if feature_key in target_text and feature_key in " ".join(str(v).lower() for v in snapshot.values() if v is not None):
                    matched.append(feature)
                else:
                    missing.append(feature)
                    difference_items.append({
                        "supplier_id": supplier.get("supplier_id"),
                        "supplier_name": supplier.get("company_name"),
                        "difference_type": "missing_feature",
                        "feature": feature,
                    })
            supplier_comparisons.append(
                {
                    "supplier_id": supplier.get("supplier_id"),
                    "supplier_name": supplier.get("company_name"),
                    "location": supplier.get("location"),
                    "spec_snapshot": snapshot,
                    "matched_features": matched,
                    "missing_features": missing,
                    "match_score": round(len(matched) / max(len(target_features), 1), 4),
                }
            )

        supplier_comparisons.sort(key=lambda item: item.get("match_score", 0), reverse=True)
        recommended_alignment = [
            f"优先对齐 {item['feature']}"
            for item in difference_items[:5]
            if isinstance(item, dict) and item.get("feature")
        ]
        return {
            "source": "ali1688_spec_comparison",
            "product_keyword": product_keyword,
            "supplier_count": len(supplier_comparisons),
            "target_feature_count": len(target_features),
            "suppliers": supplier_comparisons,
            "difference_items": difference_items[:20],
            "recommended_alignment": recommended_alignment,
        }

    async def _fetch_crm_reviews(
        self,
        crm_api_endpoint: str,
        crm_api_key: str | None = None,
        crm_inbound_path: str = "/customer-feedback",
        product_id: str | None = None,
        product_name: str | None = None,
        asin: str | None = None,
    ) -> dict:
        try:
            client = CRMClient(
                api_endpoint=crm_api_endpoint,
                api_key=crm_api_key,
                inbound_path=crm_inbound_path,
                outbound_path="/followups/bulk-upsert",
                timeout_seconds=5,
            )
            items = await client.fetch_customer_feedbacks()
        except FileNotFoundError:
            logger.warning("CRM feedback source missing: endpoint=%s path=%s", crm_api_endpoint, crm_inbound_path)
            items = []
        except Exception as exc:
            logger.warning("CRM feedback fetch degraded: %s", exc)
            items = []

        matched = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if product_id and str(item.get("product_id")) == str(product_id):
                matched.append(item)
                continue
            if asin and str(item.get("asin")) == str(asin):
                matched.append(item)
                continue
            if product_name and str(item.get("product_name") or "") == str(product_name):
                matched.append(item)
        avg_rating = round(sum(float(item.get("customer_score") or 0) for item in matched) / max(len(matched), 1), 4) if matched else 0.0
        complaint_count = sum(1 for item in matched if "投诉" in str(item.get("feedback") or "") or "退货" in str(item.get("feedback") or ""))
        return {
            "source": "crm_review_insights",
            "matched_review_count": len(matched),
            "avg_rating": avg_rating,
            "complaint_count": complaint_count,
            "reviews": matched[:10],
            "summary": {
                "avg_rating": avg_rating,
                "complaint_count": complaint_count,
                "review_count": sum(int(item.get("review_count") or 0) for item in matched),
            },
        }

    async def _competitor_diff_analysis(
        self,
        product_name: str = "",
        category: str = "",
        competitors: list[str] | None = None,
    ) -> dict:
        """
        竞品差异化矩阵分析(D34核心)。

        输出:
            - 功能对比矩阵
            - 价格定位图
            - 各竞品优劣势
            - 差异化机会点
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.06, 0.15))

        comp_list = competitors or [f"{category} Brand A", f"{category} Brand B", f"{category} Brand C"]

        feature_matrix = {}
        features_to_compare = ["降噪能力", "续航时间", "佩戴舒适度", "连接稳定性", "音质表现", "外观设计", "价格竞争力", "品牌知名度"]

        all_products = [product_name or "My Product"] + comp_list
        for feat in features_to_compare:
            feature_matrix[feat] = {prod: round(random.uniform(3.0, 9.5), 1) for prod in all_products}

        competitor_profiles = []
        for comp in comp_list:
            scores = [feature_matrix[f].get(comp, 5.0) for f in features_to_compare]
            avg_score = sum(scores) / len(scores)
            strengths = [f for f in features_to_compare if feature_matrix[f].get(comp, 5.0) >= 7.5]
            weaknesses = [f for f in features_to_compare if feature_matrix[f].get(comp, 5.0) < 5.5]

            competitor_profiles.append({
                "name": comp,
                "overall_score": round(avg_score, 1),
                "price_position": random.choice(["premium", "mid-range", "budget"]),
                "strengths": strengths[:3],
                "weaknesses": weaknesses[:3],
                "market_share_est": round(random.uniform(0.03, 0.28), 2),
            })

        my_scores = [feature_matrix[f].get(product_name or "My Product", 6.0) for f in features_to_compare]
        diff_opportunities = []
        for i, feat in enumerate(features_to_compare):
            my_val = my_scores[i]
            comp_avg = sum(feature_matrix[feat].get(c, 5.0) for c in comp_list) / len(comp_list)
            if my_val < comp_avg - 1.0:
                diff_opportunities.append({
                    "feature": feat,
                    "my_score": my_val,
                    "competitor_avg": round(comp_avg, 1),
                    "gap": round(comp_avg - my_val, 1),
                    "priority": "high" if comp_avg - my_val > 2.5 else "medium",
                })

        return {
            "source": "competitor_diff",
            "target_product": product_name or "My Product",
            "category": category,
            "competitors_analyzed": len(comp_list),
            "feature_matrix": feature_matrix,
            "competitor_profiles": competitor_profiles,
            "differentiation_opportunities": sorted(diff_opportunities, key=lambda x: x["gap"], reverse=True)[:5],
            "recommended_focus": diff_opportunities[0]["feature"] if diff_opportunities else features_to_compare[0],
            "blue_ocean_hints": [
                f"在{random.choice(features_to_compare)}维度寻找突破性创新",
                "考虑组合未被满足的需求点创造新品类",
                "关注长尾细分市场的差异化机会",
            ],
        }

    async def _swot_analysis(
        self,
        product_spec: dict | None = None,
        market_data: dict | None = None,
    ) -> dict:
        """
        SWOT战略分析(D34核心)。

        四象限分析:
            S - Strengths (内部优势)
            W - Weaknesses (内部劣势)
            O - Opportunities (外部机会)
            T - Threats (外部威胁)
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.04, 0.1))

        spec = product_spec or {}

        strengths = [
            {"item": "多源数据融合能力", "impact": "high", "description": "整合Amazon/TikTok/Google/1688四维数据"},
            {"item": "AI驱动的智能选品", "impact": "high", "description": "基于LLM的市场洞察与产品规划"},
            {"item": "端到端工作流自动化", "impact": "medium", "description": "从数据采集到商业决策全链路覆盖"},
            {"item": "灵活的成本模型", "impact": "medium", "description": "支持动态成本更新和多方案对比"},
        ]

        weaknesses = [
            {"item": "依赖第三方API稳定性", "impact": "high", "description": "Amazon PA API/TikTok API限流风险"},
            {"item": "初始冷启动数据不足", "impact": "medium", "description": "新市场/新品类缺乏历史参考数据"},
            {"item": "多Agent协调复杂度", "impact": "medium", "description": "Agent间依赖关系需要精细管理"},
        ]

        opportunities = [
            {"item": "AI电商工具需求爆发", "impact": "high", "description": "跨境电商卖家对智能化工具需求持续增长"},
            {"item": "TikTok Shop新兴渠道", "impact": "high", "description": "社交电商红利期，先发优势明显"},
            {"item": "RAG增强决策可信度", "impact": "medium", "description": "检索增强生成提升分析可解释性"},
            {"item": "多语言市场扩展", "impact": "medium", "description": "东南亚/欧洲/拉美市场待开发"},
        ]

        threats = [
            {"item": "巨头入场竞争加剧", "impact": "high", "description": "Amazon/Jungle Scout等推出类似功能"},
            {"item": "平台政策变化风险", "impact": "high", "description": "API政策调整可能影响数据获取"},
            {"item": "数据隐私合规压力", "impact": "medium", "description": "GDPR/CCPA等法规限制数据处理方式"},
        ]

        strategy_matrix = {
            "SO策略": [
                f"利用{strengths[0]['item']}抓住{opportunities[0]['item']}",
                f"结合{strengths[1]['item']}拓展{opportunities[1]['item']}",
            ],
            "WO策略": [
                f"弥补{weaknesses[0]['item']}以把握{opportunities[1]['item']}",
                f"通过{opportunities[2]['item']}缓解{weaknesses[1]['item']}",
            ],
            "ST策略": [
                f"发挥{strengths[0]['item']}抵御{threats[0]['item']}",
                f"建立技术壁垒应对{threats[1]['item']}",
            ],
            "WT策略": [
                f"规避{weaknesses[0]['item']}同时防范{threats[1]['item']}",
                f"最小化{weaknesses[1]['item']}的影响以降低{threats[2]['item']}风险",
            ],
        }

        return {
            "source": "swot_analysis",
            "product_context": spec.get("name", spec.get("category", "Unknown")),
            "generated_at": datetime.now(UTC).isoformat(),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats,
            "strategy_matrix": strategy_matrix,
            "overall_assessment": "该产品具备技术优势和市场机会窗口，需重点关注API稳定性和竞争防御",
            "priority_actions": [
                "建立多源数据备份机制以降低API依赖风险",
                "加速TikTok Shop渠道布局抢占先发优势",
                "构建行业知识库形成数据护城河",
            ],
        }


def create_product_planner_agent(config: dict | None = None) -> ProductPlannerAgent:
    """创建ProductPlannerAgent工厂函数。"""
    return ProductPlannerAgent(config=config)
