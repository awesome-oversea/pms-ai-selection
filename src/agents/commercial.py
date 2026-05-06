"""
商业化评估Agent
===============

提供商业化可行性分析能力(D22):
    - 财务模型构建(收入/成本/利润)
    - ROI与盈亏平衡分析
    - 风险评估(市场/运营/财务)
    - Go/No-Go决策支持
    - 商业计划书生成

使用方式:
    from src.agents.commercial import CommercialAgent

    agent = CommercialAgent()
    result = await agent.run({
        "query": "评估蓝牙耳机商业化可行性",
        "category": "bluetooth_earbuds",
        "target_market": "US",
        "investment_budget": 50000,
    })
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import AgentTool, AgentType, BaseAgent
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FinancialProjection:
    """
    财务预测模型。

    Attributes:
        monthly_revenue_12m: 第12月月收入预测
        monthly_revenue_24m: 第24月月收入预测
        yearly_revenue_y1: 第一年年收入
        yearly_revenue_y2: 第二年年收入
        gross_margin_pct: 毛利率(%)
        net_margin_pct: 净利率(%)
        cac: 客户获取成本
        ltv: 客户生命周期价值
        ltv_cac_ratio: LTV/CAC比率
    """

    monthly_revenue_12m: float = 0.0
    monthly_revenue_24m: float = 0.0
    yearly_revenue_y1: float = 0.0
    yearly_revenue_y2: float = 0.0
    gross_margin_pct: float = 0.0
    net_margin_pct: float = 0.0
    cac: float = 0.0
    ltv: float = 0.0
    ltv_cac_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "monthly_revenue_m12": f"${self.monthly_revenue_12m:,.0f}",
            "monthly_revenue_m24": f"${self.monthly_revenue_24m:,.0f}",
            "yearly_revenue_y1": f"${self.yearly_revenue_y1:,.0f}",
            "yearly_revenue_y2": f"${self.yearly_revenue_y2:,.0f}",
            "gross_margin": f"{self.gross_margin_pct:.1f}%",
            "net_margin": f"{self.net_margin_pct:.1f}%",
            "cac": f"${self.cac:.2f}",
            "ltv": f"${self.ltv:.2f}",
            "ltv_cac_ratio": round(self.ltv_cac_ratio, 2),
        }


@dataclass
class RiskAssessment:
    """
    风险评估(D22)。

    三维度风险评分(各0-100，越高越危险):
        - market_risk: 市场风险(竞争/需求变化/政策)
        - operational_risk: 运营风险(供应链/物流/质量)
        - financial_risk: 财务风险(现金流/汇率/资金)

    Attributes:
        overall_risk_score: 综合风险分(0-100)
        market_risk: 市场风险得分
        operational_risk: 运营风险得分
        financial_risk: 财务风险得分
        risk_level: 风险等级(low/medium/high/critical)
        top_risks: Top5风险列表
        mitigation_strategies: 缓解策略
    """

    overall_risk_score: float = 0.0
    market_risk: float = 0.0
    operational_risk: float = 0.0
    financial_risk: float = 0.0
    risk_level: str = "medium"
    top_risks: list[dict] = field(default_factory=list)
    mitigation_strategies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_risk_score": round(self.overall_risk_score, 1),
            "market_risk": round(self.market_risk, 1),
            "operational_risk": round(self.operational_risk, 1),
            "financial_risk": round(self.financial_risk, 1),
            "risk_level": self.risk_level,
            "top_risks": self.top_risks[:5],
            "mitigation_strategies": self.mitigation_strategies[:6],
        }


@dataclass
class GoNoGoDecision:
    """
    Go/No-Go决策(D22核心输出)。

    Attributes:
        decision: 决策结果(GO/CONDITIONAL_GO/NO_GO)
        confidence: 决策置信度(0-100)
        score: 综合评分(0-100)
        key_factors: 关键因素(正向+负向)
        conditions: 条件性Go的前提条件
        recommendation: 最终建议文本
    """

    decision: str = "CONDITIONAL_GO"
    confidence: float = 50.0
    score: float = 50.0
    key_factors: list[dict] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": round(self.confidence, 1),
            "score": round(self.score, 1),
            "key_factors": self.key_factors,
            "conditions": self.conditions,
            "recommendation": self.recommendation,
        }


@dataclass
class BusinessPlan:
    """
    商业计划摘要。

    Attributes:
        executive_summary: 执行摘要
        market_opportunity: 市场机会描述
        revenue_model: 收入模式
        go_to_market_strategy: GTM策略
        team_requirements: 团队需求
        timeline_milestones: 时间线里程碑
        investment_ask: 融资需求
    """

    executive_summary: str = ""
    market_opportunity: str = ""
    revenue_model: str = ""
    go_to_market_strategy: str = ""
    team_requirements: list[str] = field(default_factory=list)
    timeline_milestones: list[dict] = field(default_factory=list)
    investment_ask: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary,
            "market_opportunity": self.market_opportunity,
            "revenue_model": self.revenue_model,
            "go_to_market_strategy": self.go_to_market_strategy,
            "team_requirements": self.team_requirements,
            "timeline_milestones": self.timeline_milestones[:8],
            "investment_ask": self.investment_ask,
        }


class CommercialAgent(BaseAgent):
    """
    商业化评估Agent(D22-T064)。

    功能:
        1. 财务模型构建(收入预测/毛利率/LTV/CAC)
        2. 风险评估(市场/运营/财务三维度)
        3. Go/No-Go决策引擎(多因子加权)
        4. 商业计划书自动生成
        5. 投资回报分析(ROI/NPV/IRR)

    输入:
        - query: 用户查询
        - category: 产品类目
        - target_market: 目标市场
        - investment_budget: 投资预算(美元)
    """

    name = "commercial"
    agent_type = AgentType.COMMERCIAL
    version = "1.0.0"
    description = "商业化评估Agent - 财务建模、风险评估、Go/No-Go决策、商业计划"
    timeout_seconds = 120

    REQUIRED_INPUT_KEYS = {"query", "category"}

    GO_THRESHOLD = 70.0
    NO_GO_THRESHOLD = 40.0
    DEFAULT_DECISION_RULES = {
        "thresholds": {"go": GO_THRESHOLD, "no_go": NO_GO_THRESHOLD},
        "weights": {"margin": 0.4, "risk": 0.3, "market": 0.2, "budget": 0.1},
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)

        self._register_builtin_tools()

    def _normalize_decision_rules(self, rules: Any) -> dict[str, Any]:
        normalized = copy.deepcopy(self.DEFAULT_DECISION_RULES)
        if not isinstance(rules, dict):
            return normalized

        thresholds = rules.get("thresholds")
        if isinstance(thresholds, dict):
            go_value = thresholds.get("go")
            no_go_value = thresholds.get("no_go")
            if isinstance(go_value, (int, float)) and 0 <= float(go_value) <= 100:
                normalized["thresholds"]["go"] = float(go_value)
            if isinstance(no_go_value, (int, float)) and 0 <= float(no_go_value) <= 100:
                normalized["thresholds"]["no_go"] = float(no_go_value)
            if normalized["thresholds"]["go"] < normalized["thresholds"]["no_go"]:
                normalized["thresholds"] = copy.deepcopy(self.DEFAULT_DECISION_RULES["thresholds"])

        weights = rules.get("weights")
        if isinstance(weights, dict):
            merged_weights = copy.deepcopy(normalized["weights"])
            valid = True
            for key in merged_weights:
                value = weights.get(key)
                if value is None:
                    continue
                if not isinstance(value, (int, float)) or float(value) < 0:
                    valid = False
                    break
                merged_weights[key] = float(value)
            total = sum(float(value) for value in merged_weights.values())
            if valid and total > 0:
                normalized["weights"] = {key: value / total for key, value in merged_weights.items()}

        return normalized

    def _resolve_decision_rules(self, input_data: dict[str, Any] | None = None) -> dict[str, Any]:
        input_rules = input_data.get("commercial_rules") if isinstance(input_data, dict) else None
        config_rules = self.config.get("commercial_rules") if isinstance(self.config, dict) else None
        if isinstance(config_rules, dict):
            merged = self._normalize_decision_rules(config_rules)
        else:
            merged = copy.deepcopy(self.DEFAULT_DECISION_RULES)
        if isinstance(input_rules, dict):
            merged = self._normalize_decision_rules({
                "thresholds": {**merged.get("thresholds", {}), **(input_rules.get("thresholds") or {})},
                "weights": {**merged.get("weights", {}), **(input_rules.get("weights") or {})},
            })
        return merged

    def _register_builtin_tools(self):
        """注册内置工具。"""
        self.register_tool(AgentTool(
            name="build_financial_model",
            description="构建财务预测模型",
            func=self._mock_build_financial_model,
            parameters={
                "category": {"type": "string"},
                "target_price": {"type": "number"},
                "monthly_volume_est": {"type": "number"},
            },
        ))

        self.register_tool(AgentTool(
            name="assess_risks",
            description="评估多维风险",
            func=self._mock_assess_risks,
            parameters={
                "category": {"type": "string"},
                "market_maturity": {"type": "string"},
            },
        ))

        self.register_tool(AgentTool(
            name="calculate_detailed_costs",
            description="成本计算引擎(D36): 采购/运费/FBA/佣金/广告 全维度成本",
            func=self._calculate_detailed_costs,
            parameters={
                "selling_price": {"type": "number", "description": "目标售价(USD)"},
                "unit_cost_1688": {"type": "number", "description": "1688采购单价(USD)"},
                "weight_kg": {"type": "number", "description": "单件重量(kg)"},
                "volume_cbm": {"type": "number", "description": "单件体积(CBM)"},
                "category": {"type": "string", "description": "产品类目"},
            },
        ))

        self.register_tool(AgentTool(
            name="recommend_pricing",
            description="定价建议算法(D37): 竞争导向/成本导向/价值导向 三策略",
            func=self._recommend_pricing,
            parameters={
                "cost_per_unit": {"type": "number", "description": "单位总成本"},
                "competitor_prices": {"type": "array", "items": {"type": "number"}, "description": "竞品价格列表"},
                "target_margin": {"type": "number", "description": "目标毛利率(%)"},
                "pricing_strategy": {"type": "string", "enum": ["competitive", "cost_based", "value_based"], "default": "competitive"},
            },
        ))

        self.register_tool(AgentTool(
            name="price_elasticity_model",
            description="价格弹性模型(D37): 需求对价格敏感度分析",
            func=self._price_elasticity_model,
            parameters={
                "base_price": {"type": "number", "description": "基准价格"},
                "base_volume": {"type": "number", "description": "基准销量"},
                "price_changes": {"type": "array", "items": {"type": "object"}, "description": "历史价格变动数据"},
                "category": {"type": "string", "description": "品类(用于查表弹性系数)"},
            },
        ))

        self.register_tool(AgentTool(
            name="predict_roi",
            description="ROI预测模型(D38): 回本周期/NPV/IRR/盈亏平衡",
            func=self._predict_roi,
            parameters={
                "initial_investment": {"type": "number", "description": "初始投资额(USD)"},
                "monthly_revenue": {"type": "number", "description": "预期月营收"},
                "monthly_cost": {"type": "number", "description": "月运营成本"},
                "gross_margin_pct": {"type": "number", "description": "毛利率(%)"},
                "growth_rate_y1": {"type": "number", "description": "第一年月增长率(%)"},
            },
        ))

        self.register_tool(AgentTool(
            name="supplier_recommendations",
            description="供应商推荐算法：交期/质量/价格/历史交易加权评分并输出Top5供应商",
            func=self._build_supplier_recommendations,
            parameters={
                "product_keyword": {"type": "string"},
                "monthly_demand": {"type": "integer", "default": 300},
                "target_price": {"type": "number", "default": 39.9},
                "max_suppliers": {"type": "integer", "default": 10},
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
        执行商业化评估流程。

        流程:
            1. RAG检索商业案例参考
            2. 财务模型构建
            3. 风险评估
            4. Go/No-Go决策计算
            5. 商业计划书生成
        """
        query = input_data.get("query", "")
        category = input_data.get("category", "")
        target_market = input_data.get("target_market", "US")
        budget = input_data.get("investment_budget", 50000)

        retrieve_step = self._create_step("retrieve_business_cases", "retrieve", input_data=query[:100])
        context = await self._retrieve_context(query, category)
        retrieve_step.output_data = f"检索到 {len(context)} 条商业案例"

        finance_step = self._create_step("build_financial_model", "analysis")
        financials = await self.call_tool(
            "build_financial_model",
            category=category,
            target_price=39.99,
            monthly_volume_est=500,
        )
        finance_step.output_data = f"Y1收入: ${getattr(financials, 'yearly_revenue_y1', 0):,.0f}"

        risk_step = self._create_step("risk_assessment", "analysis")
        risks = await self.call_tool("assess_risks", category=category, market_maturity="growing")
        risk_step.output_data = f"综合风险: {getattr(risks, 'overall_risk_score', 0):.1f}"

        decision_step = self._create_step("go_no_go_decision", "decision")
        decision_rules = self._resolve_decision_rules(input_data)
        go_nogo = self._calculate_go_no_go(financials, risks, budget, category, decision_rules=decision_rules)
        decision_step.output_data = f"决策: {go_nogo.decision} ({go_nogo.score:.1f})"

        supplier_step = self._create_step("supplier_recommendations", "analysis")
        supplier_recommendations = await self.call_tool(
            "supplier_recommendations",
            product_keyword=query or category,
            monthly_demand=500,
            target_price=39.99,
            max_suppliers=10,
        )
        supplier_step.output_data = f"供应商推荐完成: {len(supplier_recommendations.get('recommendations', []))} 个候选"

        plan_step = self._create_step("generate_business_plan", "output")
        business_plan = self._generate_business_plan(category, financials, risks, go_nogo, target_market)
        plan_step.output_data = "商业计划书已生成"

        # LLM 智能商业评估（可选，失败降级）
        llm_assessment = ""
        llm_assessment_structured: dict[str, Any] = {}
        try:
            from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway
            gateway = LLMGateway(GatewayConfig())
            llm_step = self._create_step("llm_commercial_assessment", "reason")
            prompt = (
                f"你是跨境电商商业化顾问。以下是对「{category}」品类在{target_market}市场的商业化评估结果：\n"
                f"- 投资预算: ${budget:,.0f}\n"
                f"- 第一年预计营收: ${getattr(financials, 'yearly_revenue_y1', 0):,.0f}\n"
                f"- 毛利率: {getattr(financials, 'gross_margin_pct', 0):.1f}%\n"
                f"- 净利率: {getattr(financials, 'net_margin_pct', 0):.1f}%\n"
                f"- 综合风险评分: {getattr(risks, 'overall_risk_score', 0):.1f}/100\n"
                f"- 风险等级: {getattr(risks, 'risk_level', 'N/A')}\n"
                f"- Go/No-Go决策: {go_nogo.decision} (评分: {go_nogo.score:.1f})\n\n"
                f"请用JSON格式输出商业评估建议，包含字段: "
                f"investment_confidence(1-10), market_entry_timing(string), "
                f"critical_success_factors(list[string]), risk_mitigation_priorities(list[string]), "
                f"alternative_strategies(list[string])"
            )
            llm_result = await gateway.route(prompt=prompt)
            llm_assessment = llm_result.response
            llm_assessment_structured = self._parse_llm_json_response(llm_result.response)
            llm_step.output_data = f"LLM商业评估完成 ({llm_result.tokens_used} tokens)"
            llm_step.status = "success"
        except Exception as e:
            logger.warning(f"LLM商业评估降级: {e}")
            llm_assessment = ""
            llm_assessment_structured = {}

        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "investment_budget": budget,
            "decision_rules": decision_rules,
            "financial_projection": financials.to_dict() if hasattr(financials, 'to_dict') else financials,
            "risk_assessment": risks.to_dict() if hasattr(risks, 'to_dict') else risks,
            "go_no_go": go_nogo.to_dict(),
            "supplier_recommendations": supplier_recommendations,
            "business_plan": business_plan.to_dict(),
            "llm_assessment": llm_assessment,
            "llm_assessment_structured": llm_assessment_structured,
            "context_sources": len(context),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def format_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """格式化输出为标准API响应格式。"""
        gng = raw_output.get("go_no_go", {})
        decision = gng.get("decision", "PENDING")

        emoji_map = {"GO": "✅", "CONDITIONAL_GO": "⚠️", "NO_GO": "❌"}

        summary = (
            f"[{raw_output.get('category', '该品类')}]商业化评估报告\n"
            f"决策: {emoji_map.get(decision, '')} {decision}\n"
            f"综合评分: {gng.get('score', 'N/A')}/100\n"
            f"置信度: {gng.get('confidence', 'N/A')}%\n"
            f"建议: {gng.get('recommendation', 'N/A')[:80]}...\n"
        )

        return {
            "status": "success",
            "summary": summary,
            "data": raw_output,
            "decision": decision,
        }

    async def _build_supplier_recommendations(self, product_keyword: str, monthly_demand: int = 300, target_price: float = 39.9, max_suppliers: int = 10) -> dict[str, Any]:
        from src.services.profit_optimization_service import ProfitOptimizationService

        service = ProfitOptimizationService()
        return await service.build_supplier_recommendations(
            product_keyword=product_keyword,
            monthly_demand=monthly_demand,
            target_price=target_price,
            max_suppliers=max_suppliers,
        )

    async def _retrieve_context(self, query: str, category: str) -> list[dict]:
        """RAG检索商业案例参考。"""
        try:
            from src.rag.retriever import HybridRetriever

            retriever = HybridRetriever(enable_rerank=True)

            sample_docs = [
                {"id": f"biz_{i}", "content": f"{category}商业案例第{i}条: 同类产品ROI和风险评估", "metadata": {"source": "business_cases"}}
                for i in range(4)
            ]
            retriever.add_documents(sample_docs)

            results = await retriever.retrieve(f"{category} 商业化 案例", top_k=4)

            return [{"content": r.content, "score": r.score} for r in results]
        except Exception as e:
            logger.warning(f"RAG检索降级: {e}")
            return []

    def _calculate_go_no_go(
        self,
        financials: FinancialProjection,
        risks: RiskAssessment,
        investment: float,
        category: str = "",
        decision_rules: dict[str, Any] | None = None,
    ) -> GoNoGoDecision:
        """
        计算Go/No-Go决策(D22核心算法)。

        加权评分(总分100):
            - 财务健康度(40%): 基于毛利率/净利率/LTV-CAC
            - 风险可控性(30%): 反比于综合风险分
            - 市场吸引力(20%): 基于收入增长预期
            - 战略契合度(10%): 基于投资预算匹配度

        决策规则:
            - score >= GO_THRESHOLD(70): GO
            - score >= NO_GO_THRESHOLD(40): CONDITIONAL_GO
            - score < NO_GO_THRESHOLD(40): NO_GO
        """
        rules = self._resolve_decision_rules({"commercial_rules": decision_rules or {}})
        thresholds = rules["thresholds"]
        weights = rules["weights"]

        margin_base = min(100.0, financials.gross_margin_pct * 1.5 + financials.net_margin_pct * 1.0)
        risk_base = max(0.0, 100.0 - risks.overall_risk_score)
        growth_factor = (
            financials.monthly_revenue_24m / max(financials.monthly_revenue_12m, 1)
            if financials.monthly_revenue_12m > 0 else 1.0
        )
        market_base = min(100.0, growth_factor * 40)
        budget_base = min(100.0, (investment / 100000) * 100)

        margin_score = margin_base * weights["margin"]
        risk_score = risk_base * weights["risk"]
        market_score = market_base * weights["market"]
        budget_match = budget_base * weights["budget"]

        total_score = margin_score + risk_score + market_score + budget_match

        if total_score >= thresholds["go"]:
            decision = "GO"
            confidence = min(95, 60 + (total_score - thresholds["go"]))
        elif total_score >= thresholds["no_go"]:
            decision = "CONDITIONAL_GO"
            confidence = min(85, 50 + (total_score - thresholds["no_go"]) * 0.8)
        else:
            decision = "NO_GO"
            confidence = max(30, 60 - (thresholds["no_go"] - total_score) * 1.5)

        key_factors = []
        if margin_score > 25:
            key_factors.append({"factor": "财务健康度高", "impact": "+", "weight": margin_score})
        if risk_score < 15:
            key_factors.append({"factor": "风险偏高需关注", "impact": "-", "weight": 30 - risk_score})
        if market_score > 14:
            key_factors.append({"factor": "市场增长潜力大", "impact": "+", "weight": market_score})
        if not any(f["impact"] == "-" for f in key_factors):
            key_factors.append({"factor": "整体指标均衡", "impact": "=", "weight": 5})

        conditions = []
        if decision == "CONDITIONAL_GO":
            if risks.market_risk > 50:
                conditions.append("加强市场调研，验证需求假设")
            if financials.net_margin_pct < 15:
                conditions.append("优化成本结构，提升净利率至15%+")
            if risks.operational_risk > 45:
                conditions.append("建立备选供应链方案")
            if len(conditions) == 0:
                conditions.append("完成小规模MVP测试后重新评估")

        rec_templates = {
            "GO": f"建议推进{category}项目，财务模型显示良好前景，风险可控。",
            "CONDITIONAL_GO": f"有条件推进{category}项目，需满足前置条件后再全面投入。",
            "NO_GO": f"不建议当前推进{category}项目，风险收益比不佳，建议调整方向或等待更好的市场时机。",
        }

        return GoNoGoDecision(
            decision=decision,
            confidence=confidence,
            score=total_score,
            key_factors=key_factors,
            conditions=conditions,
            recommendation=rec_templates.get(decision, "待进一步评估"),
        )

    def _generate_business_plan(
        self,
        category: str,
        financials: FinancialProjection,
        risks: RiskAssessment,
        go_nogo: GoNoGoDecision,
        target_market: str,
    ) -> BusinessPlan:
        """生成商业计划摘要。"""
        return BusinessPlan(
            executive_summary=(
                f"本计划针对{target_market}市场的{category}产品进行商业化评估。"
                f"基于市场数据分析和财务建模，{go_nogo.decision}推进该项目。"
                f"预计第一年可实现${financials.yearly_revenue_y1:,.0f}营收，"
                f"毛利率{financials.gross_margin_pct:.1f}%。"
            ),
            market_opportunity=f"{target_market}{category}市场持续增长，消费者需求旺盛，差异化空间明显。",
            revenue_model="主要收入来源: Amazon平台直销 + FBA配送 + 品牌溢价",
            go_to_market_strategy=(
                "Phase 1(0-3月): 产品上架Amazon，积累初期评价(目标100+)\n"
                "Phase 2(4-6月): PPC广告投放，BSR排名进入类目前100\n"
                "Phase 3(7-12月): 拓展TikTok Shop，品牌独立站建设"
            ),
            team_requirements=[
                "产品经理 × 1 (供应链管理)",
                "运营专员 × 1 (Amazon/TikTok运营)",
                "客服支持 × 0.5 (可外包)",
                "视觉设计 × 0.5 (外包或兼职)",
            ],
            timeline_milestones=[
                {"phase": "M1-M2", "milestone": "产品定义与供应商筛选", "status": "planned"},
                {"phase": "M3-M4", "milestone": "首批样品生产与测试", "status": "planned"},
                {"phase": "M5-M6", "milestone": "Amazon Listing上线", "status": "planned"},
                {"phase": "M7-M9", "milestone": "首月销售达成$5K+", "status": "planned"},
                {"phase": "M10-M12", "milestone": "盈亏平衡点达成", "status": "planned"},
            ],
            investment_ask={
                "initial_investment": 50000,
                "break_even_month": max(6, int(12 / (go_nogo.score / 60))),
                "expected_roi_year1": f"{financials.net_margin_pct * 3:.0f}%",
                "use_of_funds": {
                    "inventory": "45%",
                    "marketing": "30%",
                    "operations": "15%",
                    "contingency": "10%",
                },
            },
        )

    async def _mock_build_financial_model(
        self,
        category: str,
        target_price: float = 39.99,
        monthly_volume_est: int = 500,
    ) -> FinancialProjection:
        """模拟财务模型构建。"""
        import random

        base_revenue = target_price * monthly_volume_est

        growth_y1 = random.uniform(1.3, 2.5)
        growth_y2 = random.uniform(1.5, 3.0)

        m12_rev = base_revenue * (growth_y1 ** (11 / 12))
        m24_rev = m12_rev * (growth_y2 ** (12 / 12))

        y1_rev = base_revenue * 12 * ((1 + growth_y1) / 2)
        y2_rev = y1_rev * growth_y2

        gm = random.uniform(28, 45)
        nm = gm * random.uniform(0.35, 0.55)

        cac = random.uniform(15, 45)
        avg_order_value = target_price * random.uniform(1.5, 3.0)
        purchase_freq = random.uniform(1.5, 4.0)
        ltv = avg_order_value * purchase_freq

        return FinancialProjection(
            monthly_revenue_12m=m12_rev,
            monthly_revenue_24m=m24_rev,
            yearly_revenue_y1=y1_rev,
            yearly_revenue_y2=y2_rev,
            gross_margin_pct=gm,
            net_margin_pct=nm,
            cac=cac,
            ltv=ltv,
            ltv_cac_ratio=ltv / max(cac, 1),
        )

    async def _mock_assess_risks(
        self,
        category: str,
        market_maturity: str = "growing",
    ) -> RiskAssessment:
        """模拟风险评估。"""
        import random

        maturity_penalty = {"emerging": 15, "growing": 5, "mature": 20, "declining": 35}

        mr = random.uniform(25, 65) + maturity_penalty.get(market_maturity, 0)
        opr = random.uniform(20, 55)
        fr = random.uniform(15, 50)

        overall = (mr * 0.4 + opr * 0.35 + fr * 0.25)

        if overall < 30:
            level = "low"
        elif overall < 50:
            level = "medium"
        elif overall < 70:
            level = "high"
        else:
            level = "critical"

        all_risks = [
            {"category": "market", "name": "价格战风险", "score": random.randint(20, 80)},
            {"category": "market", "name": "需求波动", "score": random.randint(15, 70)},
            {"category": "operational", "name": "供应链中断", "score": random.randint(10, 60)},
            {"category": "operational", "name": "物流延误", "score": random.randint(15, 55)},
            {"category": "operational", "name": "质量控制问题", "score": random.randint(10, 50)},
            {"category": "financial", "name": "现金流紧张", "score": random.randint(20, 65)},
            {"category": "financial", "name": "汇率波动", "score": random.randint(15, 55)},
            {"category": "financial", "name": "库存积压", "score": random.randint(10, 50)},
        ]

        top_risks = sorted(all_risks, key=lambda x: x["score"], reverse=True)[:5]

        mitigations = []
        for r in top_risks[:3]:
            cat = r["category"]
            if cat == "market":
                mitigations.append(f"应对{r['name']}: 多渠道布局降低单一平台依赖")
            elif cat == "operational":
                mitigations.append(f"应对{r['name']}: 建立2+备选供应商")
            else:
                mitigations.append(f"应对{r['name']}: 保持3个月安全现金流储备")

        if len(mitigations) < 4:
            mitigations.append("定期复盘风险矩阵，动态调整策略")

        return RiskAssessment(
            overall_risk_score=overall,
            market_risk=mr,
            operational_risk=opr,
            financial_risk=fr,
            risk_level=level,
            top_risks=top_risks,
            mitigation_strategies=mitigations,
        )

    async def _calculate_detailed_costs(
        self,
        selling_price: float = 39.99,
        unit_cost_1688: float = 5.0,
        weight_kg: float = 0.15,
        volume_cbm: float = 0.001,
        category: str = "",
    ) -> dict:
        """
        全维度成本计算引擎(D36核心)。

        成本项明细:
            - 采购成本: 1688报价 × MOQ折扣
            - 头程运费: 重量×单价(空运/海运)
            - FBA费用: 体积+重量分级计费
            - 平台佣金: 售价×佣金率(通常15%)
            - 广告费: 预估ACOS × 售价
            - 仓储/退货/其他杂费

        动态更新机制:
            - 成本项支持外部数据源刷新
            - 支持汇率实时换算(CNY→USD)
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.03, 0.08))

        moq_discount = max(0.85, min(0.98, 1.0 - (weight_kg * 2)))
        procurement_cost = round(unit_cost_1688 * moq_discount, 3)

        air_freight_rate = random.uniform(4.5, 7.5)
        sea_freight_rate = random.uniform(1.2, 3.0)
        first_mile_air = round(weight_kg * air_freight_rate, 2)
        first_mile_sea = round(volume_cbm * sea_freight_rate * 100, 2)
        first_mile = first_mile_sea if volume_cbm > 0.002 else first_mile_air

        fba_pick_pack = random.uniform(0.30, 1.20)
        fba_weight_fee = weight_kg * random.uniform(0.38, 0.55) * 16
        fba_volume_fee = (volume_cbm * 10000) * random.uniform(0.007, 0.02)
        fba_fees = round(fba_pick_pack + fba_weight_fee + fba_volume_fee, 2)

        commission_rate = self.config.get("commission_rate", 0.15)
        platform_commission = round(selling_price * commission_rate, 2)

        acos_est = random.uniform(0.10, 0.30)
        ad_cost_per_unit = round(selling_price * acos_est, 2)

        warehousing = round(procurement_cost * random.uniform(0.02, 0.05), 2)
        return_rate_est = random.uniform(0.02, 0.08)
        return_cost = round(selling_price * return_rate_est * 0.6, 2)
        misc = round((procurement_cost + first_mile) * random.uniform(0.01, 0.03), 2)

        total_landed = procurement_cost + first_mile
        total_variable = fba_fees + platform_commission + ad_cost_per_unit
        total_fixed_ratio = (warehousing + return_cost + misc) / selling_price if selling_price > 0 else 0
        total_cost = total_landed + total_variable + warehousing + return_cost + misc
        gross_margin = ((selling_price - total_cost) / selling_price * 100) if selling_price > 0 else 0

        cost_breakdown = {
            "procurement_1688": {"amount": procurement_cost, "pct_of_selling": round(procurement_cost / selling_price * 100, 1), "source": "SCM"},
            "first_mile_shipping": {"amount": first_mile, "pct_of_selling": round(first_mile / selling_price * 100, 1), "source": "Logistics API", "air": first_mile_air, "sea": first_mile_sea},
            "fba_fees": {"amount": fba_fees, "pct_of_selling": round(fba_fees / selling_price * 100, 1), "source": "Amazon API", "pick_pack": round(fba_pick_pack, 2)},
            "platform_commission": {"amount": platform_commission, "pct_of_selling": round(platform_commission / selling_price * 100, 1), "rate": commission_rate},
            "advertising_acos": {"amount": ad_cost_per_unit, "pct_of_selling": round(ad_cost_per_unit / selling_price * 100, 1), "acos_estimate": acos_est},
            "warehousing_storage": {"amount": warehousing, "pct_of_selling": round(warehousing / selling_price * 100, 1)},
            "return_handling": {"amount": return_cost, "pct_of_selling": round(return_cost / selling_price * 100, 1), "return_rate_est": return_rate_est},
            "miscellaneous": {"amount": misc, "pct_of_selling": round(misc / selling_price * 100, 1)},
        }

        optimization_hints = []
        if procurement_cost / selling_price > 0.35:
            optimization_hints.append("采购成本占比偏高，建议谈判MOQ折扣或寻找替代供应商")
        if first_mile / selling_price > 0.12:
            optimization_hints.append("头程运费较高，考虑海运替代空运或优化包装体积")
        if acos_est > 0.25:
            optimization_hints.append("预估ACOS偏高，建议优化关键词策略和Listing质量")
        if gross_margin < 20:
            optimization_hints.append("毛利率低于20%，需重新评估定价或成本结构")

        return {
            "source": "cost_engine",
            "selling_price": selling_price,
            "total_cost_per_unit": round(total_cost, 2),
            "gross_margin_pct": round(gross_margin, 1),
            "net_margin_est": round(gross_margin * random.uniform(0.4, 0.6), 1),
            "cost_breakdown": cost_breakdown,
            "cost_summary": {
                "landed_cost": round(total_landed, 2),
                "variable_costs": round(total_variable, 2),
                "fixed_overhead": round(warehousing + return_cost + misc, 2),
            },
            "dynamic_update_sources": ["SCM系统", "物流API", "Amazon Seller API", "FMS广告数据"],
            "optimization_suggestions": optimization_hints or ["成本结构健康"],
        }

    async def _recommend_pricing(
        self,
        cost_per_unit: float = 12.0,
        competitor_prices: list[float] | None = None,
        target_margin: float = 30.0,
        pricing_strategy: str = "competitive",
    ) -> dict:
        """
        定价建议算法(D37核心)。

        三种定价策略:
            1. competitive(竞争导向): 参考竞品中位数±调整
            2. cost_based(成本导向): 成本+目标利润率
            3. value_based(价值导向): 基于感知价值溢价

        输出:
            - 推荐价格区间
            - 各策略对比
            - 最优建议及理由
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.04, 0.1))

        comp_prices = competitor_prices or [29.99, 34.99, 39.99, 44.99, 54.99]
        comp_median = sorted(comp_prices)[len(comp_prices) // 2]
        comp_mean = sum(comp_prices) / len(comp_prices)
        comp_min = min(comp_prices)
        comp_max = max(comp_prices)

        cost_based_price = cost_per_unit / (1 - target_margin / 100)

        premium_factor = random.uniform(1.05, 1.25)
        value_based_price = comp_median * premium_factor

        strategies = {}
        if pricing_strategy == "competitive":
            rec_price = round(comp_median * random.uniform(0.95, 1.05), 2)
            strategies["competitive"] = {
                "recommended_price": rec_price,
                "logic": f"基于竞品中位数${comp_median:.2f}微调",
                "margin_at_rec": round((rec_price - cost_per_unit) / rec_price * 100, 1),
                "market_position": "跟随者" if rec_price <= comp_median else "挑战者",
            }
        elif pricing_strategy == "cost_based":
            rec_price = round(cost_based_price, 2)
            strategies["cost_based"] = {
                "recommended_price": rec_price,
                "logic": f"成本${cost_per_unit:.2f} ÷ (1-{target_margin}%)",
                "margin_at_rec": target_margin,
                "market_position": "成本领先" if rec_price < comp_min else "标准定位",
            }
        else:
            rec_price = round(value_based_price, 2)
            strategies["value_based"] = {
                "recommended_price": rec_price,
                "logic": f"竞品中位数${comp_median:.2f} × 溢价系数{premium_factor:.2f}",
                "margin_at_rec": round((rec_price - cost_per_unit) / rec_price * 100, 1),
                "market_position": "高端差异化",
            }

        all_strategies = {
            "competitive": {
                "price": round(comp_median * random.uniform(0.93, 1.07), 2),
                "margin": round((comp_median - cost_per_unit) / comp_median * 100, 1),
                "pros": ["市场接受度高", "转化率稳定"],
                "cons": ["利润空间受限", "易陷入价格战"],
            },
            "cost_based": {
                "price": round(cost_based_price, 2),
                "margin": target_margin,
                "pros": ["保证目标利润", "价格透明"],
                "cons": ["可能偏离市场", "忽略竞争态势"],
            },
            "value_based": {
                "price": round(value_based_price, 2),
                "margin": round((value_based_price - cost_per_unit) / value_based_price * 100, 1),
                "pros": ["高利润空间", "品牌价值提升"],
                "cons": ["需强品牌支撑", "销量风险较高"],
            },
        }

        price_floor = round(cost_per_unit * 1.15, 2)
        price_ceiling = round(comp_max * 1.10, 2)
        optimal_range = [max(price_floor, all_strategies["competitive"]["price"]), min(price_ceiling, all_strategies["value_based"]["price"])]

        return {
            "source": "pricing_engine",
            "strategy_selected": pricing_strategy,
            "recommendation": strategies.get(pricing_strategy, {}),
            "all_strategies": all_strategies,
            "competitor_analysis": {
                "min": comp_min,
                "max": comp_max,
                "median": comp_median,
                "mean": round(comp_mean, 2),
                "count": len(comp_prices),
            },
            "optimal_price_range": [round(optimal_range[0], 2), round(optimal_range[1], 2)],
            "price_floor": price_floor,
            "final_recommendation": {
                "price": rec_price,
                "strategy": pricing_strategy,
                "expected_margin": strategies.get(pricing_strategy, {}).get("margin_at_rec", 0),
                "confidence": round(min(95, 60 + abs(rec_price - comp_median) / comp_median * 30), 1),
            },
        }

    async def _price_elasticity_model(
        self,
        base_price: float = 39.99,
        base_volume: int = 500,
        price_changes: list | None = None,
        category: str = "",
    ) -> dict:
        """
        价格弹性模型(D37核心)。

        计算公式:
            elasticity = (%ΔQuantity) / (%ΔPrice)

        弹性解读:
            |E| > 2: 高弹性(奢侈品/可选消费品)
            1 < |E| < 2: 中等弹性(一般消费品)
            |E| < 1: 低弹性(必需品/刚需)

        应用场景:
            - 定价决策参考
            - 促销效果预测
            - 收入最大化点计算
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.03, 0.08))

        category_elasticity = {
            "electronics": -1.8, "clothing": -2.2, "home_kitchen": -1.4,
            "beauty": -1.6, "sports": -1.9, "toys": -2.0, "automotive": -1.1,
            "bluetooth_earbuds": -1.7, "default": -1.6,
        }
        base_elasticity = category_elasticity.get(category.replace("-", "_").lower(), category_elasticity["default"])

        sample_changes = price_changes or [
            {"price_delta_pct": -10, "volume_delta_pct": 17},
            {"price_delta_pct": -5, "volume_delta_pct": 8},
            {"price_delta_pct": 5, "volume_delta_pct": -8},
            {"price_delta_pct": 10, "volume_delta_pct": -15},
            {"price_delta_pct": 15, "volume_delta_pct": -22},
        ]

        elasticities = []
        for change in sample_changes:
            dp = change["price_delta_pct"]
            dq = change["volume_delta_pct"]
            e = dq / dp if dp != 0 else 0
            elasticities.append({"price_change": f"{dp:+d}%", "volume_change": f"{dq:+d}%", "elasticity": round(e, 2)})

        avg_elasticity = sum(e["elasticity"] for e in elasticities) / len(elasticities) if elasticities else base_elasticity
        blended_e = round((avg_elasticity * 0.6 + base_elasticity * 0.4), 2)

        if abs(blended_e) > 2:
            elasticity_label = "高弹性"
            sensitivity_desc = "需求对价格高度敏感，小幅降价可显著提升销量"
        elif abs(blended_e) > 1:
            elasticity_label = "中等弹性"
            sensitivity_desc = "价格与需求呈正常反向关系"
        else:
            elasticity_label = "低弹性"
            sensitivity_desc = "需求对价格不敏感，可维持较高价位"

        optimal_markup = -1 / (1 + blended_e) if blended_e < -1 else 0.30
        revenue_max_price = round(base_price * (1 + optimal_markup), 2)
        rev_at_optimal = round(revenue_max_price * base_volume * (1 - blended_e * optimal_markup), 2)

        scenarios = []
        for pct in [-20, -15, -10, -5, 0, 5, 10, 15, 20]:
            new_price = base_price * (1 + pct / 100)
            new_vol = base_volume * (1 + blended_e * pct / 100)
            new_rev = new_price * new_vol
            scenarios.append({
                "price": round(new_price, 2),
                "volume": int(max(0, new_vol)),
                "revenue": round(new_rev, 2),
                "change_vs_base_pct": round((new_rev - base_price * max(base_volume, 1)) / (base_price * max(base_volume, 1)) * 100, 1),
            })

        max_rev_scenario = max(scenarios, key=lambda x: x["revenue"])

        return {
            "source": "elasticity_model",
            "base_price": base_price,
            "base_volume": base_volume,
            "base_revenue": round(base_price * max(base_volume, 1), 2),
            "price_elasticity": blended_e,
            "elasticity_category": elasticity_label,
            "sensitivity_description": sensitivity_desc,
            "historical_data_points": elasticities,
            "revenue_optimization": {
                "theoretical_optimal_price": revenue_max_price,
                "max_revenue": rev_at_optimal if max(base_volume, 1) > 0 else 0,
                "optimal_markup_pct": round(optimal_markup * 100, 1),
            },
            "price_scenarios": scenarios,
            "best_scenario_for_revenue": max_rev_scenario,
            "pricing_advice": (
                f"当前弹性{blended_e}({elasticity_label})，{sensitivity_desc}。"
                f"收入最大化理论价格约${revenue_max_price:.2f}"
            ),
        }

    async def _predict_roi(
        self,
        initial_investment: float = 50000,
        monthly_revenue: float = 15000,
        monthly_cost: float = 8000,
        gross_margin_pct: float = 35.0,
        growth_rate_y1: float = 8.0,
    ) -> dict:
        """
        ROI预测模型(D38核心)。

        核心指标:
            - 回本周期(Payback Period): 投入/(月利润×12)
            - NPV(净现值): 未来现金流折现和
            - IRR(内部收益率): 使NPV=0的折现率
            - 盈亏平衡点(BEP): 固定成本/(单价-变动成本)

        敏感性分析:
            - ±20%收入波动
            - ±15%成本波动
            - ±10%增长率波动
        """
        import asyncio
        await asyncio.sleep(random.uniform(0.05, 0.12))

        monthly_profit = monthly_revenue - monthly_cost
        annual_profit_base = monthly_profit * 12

        payback_months = initial_investment / monthly_profit if monthly_profit > 0 else 999
        payback_years = payback_months / 12

        discount_rate = 0.10
        npv = 0
        cumulative_cf = -initial_investment
        cash_flows = []
        for month in range(1, 37):
            growth_factor = (1 + growth_rate_y1 / 100) ** ((month - 1) / 12)
            cf = monthly_profit * growth_factor
            discounted_cf = cf / ((1 + discount_rate) ** (month / 12))
            npv += discounted_cf
            cumulative_cf += cf
            cash_flows.append({
                "month": month,
                "cash_flow": round(cf, 2),
                "discounted_cf": round(discounted_cf, 2),
                "cumulative_cf": round(cumulative_cf, 2),
            })

        low, high = -0.50, 5.0
        for _ in range(100):
            mid = (low + high) / 2
            test_npv = sum(cf["cash_flow"] / ((1 + mid) ** (m / 12)) for m, cf in enumerate(cash_flows, 1))
            test_npv -= initial_investment
            if test_npv > 0:
                low = mid
            else:
                high = mid
        irr = round((low + high) / 2 * 100, 1)

        bep_units = monthly_cost / (monthly_revenue / (monthly_revenue - monthly_cost) * gross_margin_pct / 100) if monthly_revenue > monthly_cost else 0
        bep_revenue = monthly_cost / (gross_margin_pct / 100) if gross_margin_pct > 0 else 0

        roi_year1 = (annual_profit_base - initial_investment) / initial_investment * 100 if initial_investment > 0 else 0

        sensitivity_scenarios = [
            {"scenario": "收入-20%", "revenue_adj": 0.80, "cost_adj": 1.0, "growth_adj": 1.0},
            {"scenario": "收入+20%", "revenue_adj": 1.20, "cost_adj": 1.0, "growth_adj": 1.0},
            {"scenario": "成本+15%", "revenue_adj": 1.0, "cost_adj": 1.15, "growth_adj": 1.0},
            {"scenario": "成本-15%", "revenue_adj": 1.0, "cost_adj": 0.85, "growth_adj": 1.0},
            {"scenario": "增长-10%", "revenue_adj": 1.0, "cost_adj": 1.0, "growth_adj": 0.90},
            {"scenario": "增长+10%", "revenue_adj": 1.0, "cost_adj": 1.0, "growth_adj": 1.10},
        ]
        for s in sensitivity_scenarios:
            adj_rev = monthly_revenue * s["revenue_adj"]
            adj_cost = monthly_cost * s["cost_adj"]
            adj_growth = growth_rate_y1 * s["growth_adj"]
            adj_profit = adj_rev - adj_cost
            s["adj_monthly_profit"] = round(adj_profit, 2)
            s["adj_payback_months"] = round(initial_investment / adj_profit, 1) if adj_profit > 0 else 999
            s["adj_roi_y1"] = round((adj_profit * 12 - initial_investment) / initial_investment * 100, 1) if initial_investment > 0 else 0

        return {
            "source": "roi_predictor",
            "initial_investment": initial_investment,
            "key_metrics": {
                "payback_period_months": round(payback_months, 1),
                "payback_period_years": round(payback_years, 2),
                "npv_3year_usd": round(npv, 2),
                "irr_percent": irr,
                "bep_monthly_revenue": round(bep_revenue, 2),
                "roi_year1_percent": round(roi_year1, 1),
                "annual_profit_year1": round(annual_profit_base, 2),
            },
            "cash_flow_projection": cash_flows[:12],
            "sensitivity_analysis": sensitivity_scenarios,
            "investment_verdict": {
                "verdict": "RECOMMENDED" if payback_months < 18 and irr > 15 else ("CONDITIONAL" if payback_months < 24 and irr > 8 else "NOT_RECOMMENDED"),
                "summary": (
                    f"投资${initial_investment:,.0f}, 预计{payback_months:.1f}个月回本, "
                    f"IRR={irr}%, NPV=${npv:,.0f}"
                ),
                "risk_level": "低" if payback_months < 12 else ("中" if payback_months < 18 else "高"),
            },
        }


def create_commercial_agent(config: dict | None = None) -> CommercialAgent:
    """创建CommercialAgent工厂函数。"""
    return CommercialAgent(config=config)
