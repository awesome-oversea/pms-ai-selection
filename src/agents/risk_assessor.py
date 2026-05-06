"""
风险评估Agent
=============

独立风险评估Agent，集成多源风险信号:
    - RAG检索: 历史风险案例、行业风险报告
    - CRM反馈: 客户投诉、评价情感分析
    - 竞品动态: 爬虫采集的竞品价格/排名变化
    - 供应链风险: SCM供应商交付/质量评分
    - 合规风险: 专利/商标/法规变更

使用方式:
    from src.agents.risk_assessor import RiskAssessorAgent

    agent = RiskAssessorAgent()
    result = await agent.run({
        "query": "评估蓝牙耳机进入美国市场风险",
        "category": "bluetooth_earbuds",
        "target_market": "US",
    })
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import AgentTool, AgentType, BaseAgent
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RiskSignal:
    risk_id: str = ""
    category: str = ""
    severity: str = "medium"
    description: str = ""
    source: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    mitigation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence[:3],
            "mitigation": self.mitigation,
        }


@dataclass
class RiskAssessmentResult:
    overall_risk_score: float = 0.0
    risk_level: str = "medium"
    signals: list[RiskSignal] = field(default_factory=list)
    market_risk: float = 0.0
    supply_chain_risk: float = 0.0
    compliance_risk: float = 0.0
    competitive_risk: float = 0.0
    operational_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    assessed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_risk_score": round(self.overall_risk_score, 1),
            "risk_level": self.risk_level,
            "signals": [s.to_dict() for s in self.signals],
            "dimension_scores": {
                "market_risk": round(self.market_risk, 1),
                "supply_chain_risk": round(self.supply_chain_risk, 1),
                "compliance_risk": round(self.compliance_risk, 1),
                "competitive_risk": round(self.competitive_risk, 1),
                "operational_risk": round(self.operational_risk, 1),
            },
            "recommendations": self.recommendations[:8],
            "assessed_at": self.assessed_at,
        }


class RiskAssessorAgent(BaseAgent):
    name = "risk_assessor"
    agent_type = AgentType.COORDINATOR
    version = "1.0.0"
    description = "风险评估Agent - 多源风险信号聚合、RAG案例检索、合规/供应链/竞品风险分析"
    timeout_seconds = 120

    REQUIRED_INPUT_KEYS = {"query", "category"}

    RISK_WEIGHTS = {
        "market": 0.25,
        "supply_chain": 0.20,
        "compliance": 0.20,
        "competitive": 0.20,
        "operational": 0.15,
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        self.register_tool(AgentTool(
            name="search_risk_cases",
            description="RAG检索历史风险案例",
            func=self._search_risk_cases,
            parameters={"query": {"type": "string"}, "category": {"type": "string"}, "top_k": {"type": "integer", "default": 5}},
        ))
        self.register_tool(AgentTool(
            name="analyze_crm_feedback_risks",
            description="分析CRM客户反馈中的风险信号",
            func=self._analyze_crm_feedback_risks,
            parameters={"category": {"type": "string"}, "target_market": {"type": "string"}},
        ))
        self.register_tool(AgentTool(
            name="analyze_competitor_risks",
            description="分析竞品动态风险信号",
            func=self._analyze_competitor_risks,
            parameters={"category": {"type": "string"}, "target_market": {"type": "string"}},
        ))
        self.register_tool(AgentTool(
            name="analyze_supply_chain_risks",
            description="分析供应链风险信号",
            func=self._analyze_supply_chain_risks,
            parameters={"category": {"type": "string"}},
        ))
        self.register_tool(AgentTool(
            name="analyze_compliance_risks",
            description="分析合规风险信号（专利/商标/法规）",
            func=self._analyze_compliance_risks,
            parameters={"category": {"type": "string"}, "target_market": {"type": "string"}},
        ))

    async def execute(self, input_data: dict[str, Any]) -> RiskAssessmentResult:
        query = input_data.get("query", "")
        category = input_data.get("category", "")
        target_market = input_data.get("target_market", "US")

        await self.call_tool("search_risk_cases", query=query, category=category, top_k=5)
        crm_signals = await self.call_tool("analyze_crm_feedback_risks", category=category, target_market=target_market)
        competitor_signals = await self.call_tool("analyze_competitor_risks", category=category, target_market=target_market)
        supply_chain_signals = await self.call_tool("analyze_supply_chain_risks", category=category)
        compliance_signals = await self.call_tool("analyze_compliance_risks", category=category, target_market=target_market)

        all_signals: list[RiskSignal] = []
        all_signals.extend(crm_signals if isinstance(crm_signals, list) else [])
        all_signals.extend(competitor_signals if isinstance(competitor_signals, list) else [])
        all_signals.extend(supply_chain_signals if isinstance(supply_chain_signals, list) else [])
        all_signals.extend(compliance_signals if isinstance(compliance_signals, list) else [])

        market_score = self._compute_dimension_score(all_signals, "market")
        supply_chain_score = self._compute_dimension_score(all_signals, "supply_chain")
        compliance_score = self._compute_dimension_score(all_signals, "compliance")
        competitive_score = self._compute_dimension_score(all_signals, "competitive")
        operational_score = self._compute_dimension_score(all_signals, "operational")

        overall = (
            market_score * self.RISK_WEIGHTS["market"]
            + supply_chain_score * self.RISK_WEIGHTS["supply_chain"]
            + compliance_score * self.RISK_WEIGHTS["compliance"]
            + competitive_score * self.RISK_WEIGHTS["competitive"]
            + operational_score * self.RISK_WEIGHTS["operational"]
        )

        risk_level = self._score_to_level(overall)
        recommendations = self._generate_recommendations(all_signals, overall)

        return RiskAssessmentResult(
            overall_risk_score=overall,
            risk_level=risk_level,
            signals=all_signals,
            market_risk=market_score,
            supply_chain_risk=supply_chain_score,
            compliance_risk=compliance_score,
            competitive_risk=competitive_score,
            operational_risk=operational_score,
            recommendations=recommendations,
            assessed_at=datetime.now(UTC).isoformat(),
        )

    async def format_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, RiskAssessmentResult):
            return raw_output.to_dict()
        return raw_output

    @staticmethod
    def _compute_dimension_score(signals: list[RiskSignal], dimension: str) -> float:
        matching = [s for s in signals if s.category == dimension]
        if not matching:
            return 30.0
        severity_map = {"critical": 90.0, "high": 70.0, "medium": 50.0, "low": 25.0, "info": 10.0}
        total = 0.0
        for s in matching:
            base = severity_map.get(s.severity, 50.0)
            total += base * s.confidence
        avg = total / len(matching) if matching else 30.0
        return min(max(avg, 0.0), 100.0)

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 75:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 40:
            return "medium"
        if score >= 20:
            return "low"
        return "minimal"

    @staticmethod
    def _generate_recommendations(signals: list[RiskSignal], overall_score: float) -> list[str]:
        recs: list[str] = []
        critical = [s for s in signals if s.severity == "critical"]
        high = [s for s in signals if s.severity == "high"]
        if critical:
            recs.append(f"立即处理{len(critical)}项严重风险: " + "; ".join(s.description[:50] for s in critical[:3]))
        if high:
            recs.append(f"优先关注{len(high)}项高风险: " + "; ".join(s.description[:50] for s in high[:3]))
        if overall_score >= 60:
            recs.append("建议暂缓推进，等待高风险项缓解后再决策")
        elif overall_score >= 40:
            recs.append("建议制定风险缓解计划后谨慎推进")
        else:
            recs.append("风险可控，建议按计划推进并持续监控")
        for s in signals[:5]:
            if s.mitigation:
                recs.append(f"[{s.category}] {s.mitigation}")
        return recs

    async def _search_risk_cases(self, query: str, category: str = "", top_k: int = 5) -> list[RiskSignal]:
        try:
            from src.infrastructure.hybrid_retrieval import HybridRetriever
            retriever = HybridRetriever()
            results = await retriever.search(f"风险案例 {query} {category}", top_k=top_k)
            signals = []
            for doc in results:
                signals.append(RiskSignal(
                    risk_id=f"rag-{doc.doc_id[:8]}",
                    category="market",
                    severity="medium",
                    description=doc.content[:200],
                    source=f"rag:{doc.source}",
                    confidence=min(doc.score, 1.0),
                    evidence=[doc.content[:100]],
                    mitigation="参考历史案例制定应对方案",
                ))
            return signals
        except Exception as e:
            logger.warning(f"RAG风险案例检索失败: {e}")
            return []

    async def _analyze_crm_feedback_risks(self, category: str = "", target_market: str = "US") -> list[RiskSignal]:
        signals: list[RiskSignal] = []
        try:
            from src.infrastructure.database import get_async_session_factory
            from src.services.erp_integration_service import ErpIntegrationService
            session = get_async_session_factory()()
            try:
                service = ErpIntegrationService(session)
                crm_status = await service.get_crm_operational_status()
                feedback = crm_status.get("feedback_summary", {})
                complaint_count = int(feedback.get("complaint_count", 0))
                avg_rating = float(feedback.get("avg_rating", 4.0))
                if complaint_count > 10:
                    signals.append(RiskSignal(
                        risk_id="crm-complaint-high",
                        category="operational",
                        severity="high" if complaint_count > 50 else "medium",
                        description=f"CRM客诉数量偏高: {complaint_count}条",
                        source="crm",
                        confidence=0.85,
                        evidence=[f"近30天客诉{complaint_count}条"],
                        mitigation="排查产品质量问题，联系供应商整改",
                    ))
                if avg_rating < 3.5:
                    signals.append(RiskSignal(
                        risk_id="crm-rating-low",
                        category="market",
                        severity="high" if avg_rating < 3.0 else "medium",
                        description=f"客户评分偏低: {avg_rating:.1f}/5.0",
                        source="crm",
                        confidence=0.80,
                        evidence=[f"平均评分{avg_rating:.1f}"],
                        mitigation="分析差评原因，优化产品设计和质量控制",
                    ))
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"CRM风险分析失败，使用默认评估: {e}")
            signals.append(RiskSignal(
                risk_id="crm-unavailable",
                category="operational",
                severity="low",
                description="CRM数据暂不可用，使用默认风险评估",
                source="crm_fallback",
                confidence=0.3,
                mitigation="确保CRM服务可用后重新评估",
            ))
        return signals

    async def _analyze_competitor_risks(self, category: str = "", target_market: str = "US") -> list[RiskSignal]:
        signals: list[RiskSignal] = []
        try:
            from src.infrastructure.database import get_async_session_factory
            from src.services.erp_integration_service import ErpIntegrationService
            session = get_async_session_factory()()
            try:
                service = ErpIntegrationService(session)
                oms_status = await service.get_oms_operational_status()
                sales = oms_status.get("sales_summary", {})
                conversion = float(sales.get("avg_conversion_rate", 5.0))
                if conversion < 3.0:
                    signals.append(RiskSignal(
                        risk_id="competitor-conversion-low",
                        category="competitive",
                        severity="high",
                        description=f"转化率偏低({conversion:.1f}%)，可能存在竞品分流",
                        source="oms_sales",
                        confidence=0.70,
                        evidence=[f"转化率{conversion:.1f}%"],
                        mitigation="优化Listing，加强差异化卖点，调整定价策略",
                    ))
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"竞品风险分析失败: {e}")
        return signals

    async def _analyze_supply_chain_risks(self, category: str = "") -> list[RiskSignal]:
        signals: list[RiskSignal] = []
        try:
            from src.infrastructure.database import get_async_session_factory
            from src.services.erp_integration_service import ErpIntegrationService
            session = get_async_session_factory()()
            try:
                service = ErpIntegrationService(session)
                scm_status = await service.get_scm_operational_status()
                quote_summary = scm_status.get("quote_summary", {})
                supplier_count = int(quote_summary.get("supplier_count", 0))
                if supplier_count <= 1:
                    signals.append(RiskSignal(
                        risk_id="scm-single-supplier",
                        category="supply_chain",
                        severity="high",
                        description="供应商集中度过高，仅1家供应商",
                        source="scm",
                        confidence=0.90,
                        evidence=[f"供应商数量: {supplier_count}"],
                        mitigation="开发备选供应商，降低单源依赖风险",
                    ))
                wms_status = await service.get_wms_operational_status()
                fulfillment = wms_status.get("fulfillment_status", {})
                if fulfillment.get("backorder_risk"):
                    signals.append(RiskSignal(
                        risk_id="wms-backorder-risk",
                        category="supply_chain",
                        severity="medium",
                        description="存在缺货风险，库存低于安全水位",
                        source="wms",
                        confidence=0.75,
                        evidence=["库存低于安全水位"],
                        mitigation="加快补货计划，与供应商协商加急交货",
                    ))
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"供应链风险分析失败: {e}")
        return signals

    async def _analyze_compliance_risks(self, category: str = "", target_market: str = "US") -> list[RiskSignal]:
        signals: list[RiskSignal] = []
        compliance_rules: dict[str, list[dict[str, str]]] = {
            "US": [
                {"category_hint": "electronics", "regulation": "FCC认证", "severity": "high"},
                {"category_hint": "toys", "regulation": "CPSIA认证", "severity": "critical"},
                {"category_hint": "food", "regulation": "FDA注册", "severity": "critical"},
                {"category_hint": "cosmetics", "regulation": "FDA化妆品注册", "severity": "high"},
                {"category_hint": "medical", "regulation": "FDA医疗器械510(k)", "severity": "critical"},
            ],
            "EU": [
                {"category_hint": "electronics", "regulation": "CE认证+RoHS", "severity": "high"},
                {"category_hint": "toys", "regulation": "EN71认证", "severity": "critical"},
                {"category_hint": "cosmetics", "regulation": "CPNP通报", "severity": "high"},
            ],
        }
        rules = compliance_rules.get(target_market, compliance_rules.get("US", []))
        for rule in rules:
            if rule["category_hint"] in category.lower():
                signals.append(RiskSignal(
                    risk_id=f"compliance-{rule['category_hint']}-{target_market}",
                    category="compliance",
                    severity=rule["severity"],
                    description=f"目标市场{target_market}要求{rule['regulation']}，需确保合规",
                    source="compliance_rules",
                    confidence=0.95,
                    evidence=[f"法规: {rule['regulation']}"],
                    mitigation=f"提前办理{rule['regulation']}认证，预留认证周期和费用",
                ))
        if not signals:
            signals.append(RiskSignal(
                risk_id="compliance-general",
                category="compliance",
                severity="medium",
                description=f"目标市场{target_market}可能存在特定法规要求，需进一步调研",
                source="compliance_rules",
                confidence=0.50,
                evidence=[f"类目{category}在{target_market}的合规要求待确认"],
                mitigation="咨询法务或合规团队，确认目标市场准入要求",
            ))
        return signals
