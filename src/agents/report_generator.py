"""
报告生成Agent
=============

独立报告生成Agent，汇总所有Agent结果生成结构化报告:
    - 汇总数据采集/市场洞察/产品规划/商业化评估/风险评估5大Agent输出
    - 生成结构化JSON报告
    - 支持多格式导出(HTML/Markdown/JSON)
    - 与ReportCenterService集成持久化

设计文档当前口径: CrewAI顺序任务 + 本地 Ollama / Qwen2.5-1.5B 生成报告

使用方式:
    from src.agents.report_generator import ReportGeneratorAgent

    agent = ReportGeneratorAgent()
    result = await agent.run({
        "query": "蓝牙耳机选品报告",
        "category": "bluetooth_earbuds",
        "target_market": "US",
        "agent_results": {...},
    })
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.base import AgentTool, AgentType, BaseAgent
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ReportSection:
    section_id: str = ""
    title: str = ""
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    charts: list[dict[str, Any]] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content[:2000],
            "data": self.data,
            "charts": self.charts,
            "order": self.order,
        }


@dataclass
class GeneratedReport:
    report_id: str = ""
    title: str = ""
    query: str = ""
    category: str = ""
    target_market: str = ""
    executive_summary: str = ""
    sections: list[ReportSection] = field(default_factory=list)
    overall_score: float = 0.0
    decision: str = ""
    risk_level: str = ""
    generated_at: str = ""
    format: str = "json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "query": self.query,
            "category": self.category,
            "target_market": self.target_market,
            "executive_summary": self.executive_summary,
            "sections": [s.to_dict() for s in sorted(self.sections, key=lambda x: x.order)],
            "overall_score": round(self.overall_score, 1),
            "decision": self.decision,
            "risk_level": self.risk_level,
            "generated_at": self.generated_at,
            "format": self.format,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            f"> 查询: {self.query} | 类目: {self.category} | 目标市场: {self.target_market}",
            f"> 生成时间: {self.generated_at}",
            f"> 综合评分: {self.overall_score:.1f} | 决策: {self.decision} | 风险等级: {self.risk_level}",
            "",
            "## 执行摘要",
            "",
            self.executive_summary,
            "",
        ]
        for section in sorted(self.sections, key=lambda x: x.order):
            lines.extend([
                f"## {section.title}",
                "",
                section.content,
                "",
            ])
            if section.charts:
                lines.append("### 图表数据")
                for chart in section.charts:
                    lines.append(f"- {chart.get('title', '图表')}: {json.dumps(chart.get('data', {}), ensure_ascii=False, default=str)[:200]}")
                lines.append("")
        return "\n".join(lines)

    def to_html(self) -> str:
        md = self.to_markdown()
        html_parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"]
        html_parts.append(f"<title>{self.title}</title>")
        html_parts.append("<style>body{font-family:sans-serif;max-width:960px;margin:0 auto;padding:20px;}h1{color:#1a1a2e;}h2{color:#16213e;border-bottom:1px solid #eee;padding-bottom:8px;}blockquote{background:#f8f9fa;padding:12px 16px;border-left:4px solid #0f3460;}</style>")
        html_parts.append("</head><body>")
        for line in md.split("\n"):
            if line.startswith("# "):
                html_parts.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_parts.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_parts.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("> "):
                html_parts.append(f"<blockquote>{line[2:]}</blockquote>")
            elif line.startswith("- "):
                html_parts.append(f"<li>{line[2:]}</li>")
            elif line.strip():
                html_parts.append(f"<p>{line}</p>")
        html_parts.append("</body></html>")
        return "\n".join(html_parts)


class ReportGeneratorAgent(BaseAgent):
    name = "report_generator"
    agent_type = AgentType.COORDINATOR
    version = "1.0.0"
    description = "报告生成Agent - 汇总5大Agent结果，生成结构化选品报告，支持多格式导出"
    timeout_seconds = 180

    REQUIRED_INPUT_KEYS = {"query", "category"}

    def __init__(self, config: dict | None = None):
        super().__init__(config=config)
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        self.register_tool(AgentTool(
            name="collect_agent_results",
            description="收集各Agent执行结果",
            func=self._collect_agent_results,
            parameters={"task_id": {"type": "string"}},
        ))
        self.register_tool(AgentTool(
            name="generate_executive_summary",
            description="生成执行摘要",
            func=self._generate_executive_summary,
            parameters={"query": {"type": "string"}, "decision": {"type": "string"}, "score": {"type": "number"}},
        ))
        self.register_tool(AgentTool(
            name="persist_report",
            description="持久化报告到ReportCenter",
            func=self._persist_report,
            parameters={"report": {"type": "object"}},
        ))

    async def execute(self, input_data: dict[str, Any]) -> GeneratedReport:
        query = input_data.get("query", "")
        category = input_data.get("category", "")
        target_market = input_data.get("target_market", "US")
        agent_results = input_data.get("agent_results") or {}
        report_format = input_data.get("format", "json")

        if not agent_results:
            agent_results = await self.call_tool("collect_agent_results", task_id=input_data.get("task_id", ""))

        sections = self._build_sections(agent_results)
        decision, overall_score, risk_level = self._compute_decision(agent_results)
        summary = await self.call_tool(
            "generate_executive_summary",
            query=query,
            decision=decision,
            score=overall_score,
        )

        report = GeneratedReport(
            report_id=f"RPT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            title=f"选品报告: {query}",
            query=query,
            category=category,
            target_market=target_market,
            executive_summary=summary if isinstance(summary, str) else str(summary),
            sections=sections,
            overall_score=overall_score,
            decision=decision,
            risk_level=risk_level,
            generated_at=datetime.now(UTC).isoformat(),
            format=report_format,
        )

        await self.call_tool("persist_report", report=report.to_dict())

        return report

    async def format_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, GeneratedReport):
            result = raw_output.to_dict()
            fmt = raw_output.format
            if fmt == "markdown":
                result["markdown"] = raw_output.to_markdown()
            elif fmt == "html":
                result["html"] = raw_output.to_html()
            return result
        return raw_output

    def _build_sections(self, agent_results: dict[str, Any]) -> list[ReportSection]:
        sections: list[ReportSection] = []
        order = 0

        data_collection = agent_results.get("data_collection") or agent_results.get("DataCollector") or {}
        if data_collection:
            order += 1
            sections.append(ReportSection(
                section_id="data_collection",
                title="1. 数据采集分析",
                content=self._format_data_collection_section(data_collection),
                data=data_collection,
                order=order,
            ))

        market_insight = agent_results.get("market_insight") or agent_results.get("MarketInsight") or {}
        if market_insight:
            order += 1
            sections.append(ReportSection(
                section_id="market_insight",
                title="2. 市场洞察",
                content=self._format_market_insight_section(market_insight),
                data=market_insight,
                order=order,
            ))

        product_planning = agent_results.get("product_planning") or agent_results.get("ProductPlanner") or {}
        if product_planning:
            order += 1
            sections.append(ReportSection(
                section_id="product_planning",
                title="3. 产品规划",
                content=self._format_product_planning_section(product_planning),
                data=product_planning,
                order=order,
            ))

        commercial = agent_results.get("commercial") or agent_results.get("Commercial") or {}
        if commercial:
            order += 1
            sections.append(ReportSection(
                section_id="commercial",
                title="4. 商业化评估",
                content=self._format_commercial_section(commercial),
                data=commercial,
                order=order,
            ))

        risk = agent_results.get("risk_assessment") or agent_results.get("RiskAssessor") or {}
        if risk:
            order += 1
            sections.append(ReportSection(
                section_id="risk_assessment",
                title="5. 风险评估",
                content=self._format_risk_section(risk),
                data=risk,
                order=order,
            ))

        if not sections:
            order += 1
            sections.append(ReportSection(
                section_id="summary",
                title="综合分析",
                content="暂无Agent执行结果，请先完成选品流程各阶段分析。",
                order=order,
            ))

        return sections

    @staticmethod
    def _compute_decision(agent_results: dict[str, Any]) -> tuple[str, float, str]:
        commercial = agent_results.get("commercial") or agent_results.get("Commercial") or {}
        risk = agent_results.get("risk_assessment") or agent_results.get("RiskAssessor") or {}

        decision_data = commercial.get("decision") or commercial.get("go_no_go") or {}
        if isinstance(decision_data, dict):
            decision = str(decision_data.get("decision", "CONDITIONAL_GO")).upper()
            score = float(decision_data.get("score", 50.0))
        else:
            decision = "CONDITIONAL_GO"
            score = 50.0

        risk_data = risk.get("risk_assessment") or risk if isinstance(risk, dict) else {}
        risk_level = str(risk_data.get("risk_level", "medium")) if isinstance(risk_data, dict) else "medium"

        return decision, score, risk_level

    @staticmethod
    def _resolve_data_collection_counts(data: dict[str, Any]) -> dict[str, int]:
        amazon_bundle = data.get("amazon_data") if isinstance(data.get("amazon_data"), dict) else {}
        tiktok_bundle = data.get("tiktok_data") if isinstance(data.get("tiktok_data"), dict) else {}
        amazon_bsr = amazon_bundle.get("bsr") if isinstance(amazon_bundle.get("bsr"), dict) else amazon_bundle
        tiktok_products = tiktok_bundle.get("products") if isinstance(tiktok_bundle.get("products"), dict) else tiktok_bundle
        trend_payload = data.get("trend_data") if isinstance(data.get("trend_data"), dict) else {}
        supplier_payload = data.get("supplier_data") if isinstance(data.get("supplier_data"), dict) else {}
        if not supplier_payload:
            alt_supply_payload = data.get("supply_chain_data")
            supplier_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}
        return {
            "amazon_products": len(amazon_bsr.get("products") or []) if isinstance(amazon_bsr, dict) else 0,
            "tiktok_products": len(tiktok_products.get("products") or []) if isinstance(tiktok_products, dict) else 0,
            "google_keywords": len(trend_payload.get("trend_data") or {}) if isinstance(trend_payload, dict) else 0,
            "supplier_count": len(supplier_payload.get("suppliers") or []) if isinstance(supplier_payload, dict) else 0,
        }

    @staticmethod
    def _describe_data_collection_governance(status: str) -> str:
        mapping = {
            "enterprise_ready": "企业正式接入已就绪，可作为正式业务证据使用。",
            "local_validation_only": "当前仅达到本地业务验证可用，未完成企业正式接入。",
            "mock_only": "当前仍以 mock 或本地兼容数据为主，不能作为真实接入证明。",
            "not_ready": "当前数据源尚未达到业务验证可用，需要继续补联调。",
            "mixed": "当前为混合状态，需要区分正式接入与本地验证来源。",
            "unknown": "当前未形成明确的信号治理结论。",
        }
        return mapping.get(status, mapping["unknown"])

    @classmethod
    def _resolve_data_collection_governance(cls, data: dict[str, Any]) -> dict[str, Any]:
        data_source_governance = data.get("data_source_governance") if isinstance(data.get("data_source_governance"), dict) else {}
        collection_readiness = data.get("collection_readiness") if isinstance(data.get("collection_readiness"), dict) else {}
        external_signal_summary = data.get("external_signal_summary") if isinstance(data.get("external_signal_summary"), dict) else {}
        sources_summary = data.get("sources_summary") if isinstance(data.get("sources_summary"), dict) else {}
        fallback_records = list(sources_summary.get("external_signal_fallbacks") or [])

        governance_status = str(
            data_source_governance.get("governance_status")
            or collection_readiness.get("governance_status")
            or ("local_validation_only" if external_signal_summary.get("has_external_signal_fallbacks") else "unknown")
        )
        fallback_tool_count = int(
            collection_readiness.get("fallback_tool_count")
            or external_signal_summary.get("fallback_tool_count")
            or len(fallback_records)
        )
        fallback_business_sources = list(
            collection_readiness.get("fallback_business_sources")
            or external_signal_summary.get("fallback_business_sources")
            or sorted({str(item.get("source") or "") for item in fallback_records if str(item.get("source") or "")})
        )
        local_validation_only_sources = list(
            data_source_governance.get("local_validation_only_sources")
            or collection_readiness.get("local_validation_only_sources")
            or external_signal_summary.get("local_validation_only_sources")
            or []
        )
        next_actions = list(collection_readiness.get("next_actions") or [])
        return {
            "governance_status": governance_status,
            "fallback_tool_count": fallback_tool_count,
            "fallback_business_sources": fallback_business_sources,
            "local_validation_only_sources": local_validation_only_sources,
            "next_actions": next_actions,
        }

    @classmethod
    def _format_data_collection_section(cls, data: dict[str, Any]) -> str:
        lines = ["数据采集阶段完成，以下为关键发现与治理结论:"]
        quality = data.get("quality_report") or data.get("data_quality") or {}
        if quality:
            lines.append(f"- 数据质量: 有效率 {quality.get('validity_rate', 'N/A')}")
        counts = cls._resolve_data_collection_counts(data)
        count_parts = []
        if counts["amazon_products"]:
            count_parts.append(f"Amazon候选 {counts['amazon_products']}")
        if counts["tiktok_products"]:
            count_parts.append(f"TikTok商品 {counts['tiktok_products']}")
        if counts["google_keywords"]:
            count_parts.append(f"Google关键词 {counts['google_keywords']}")
        if counts["supplier_count"]:
            count_parts.append(f"1688供应商 {counts['supplier_count']}")
        if count_parts:
            lines.append(f"- 采集概览: {'，'.join(count_parts)}")
        products = data.get("products") or data.get("collected_products") or []
        if products and not count_parts:
            lines.append(f"- 采集商品数: {len(products)}")
        trends = data.get("trends") or data.get("trend_signals") or []
        if trends and not counts["google_keywords"]:
            lines.append(f"- 趋势信号数: {len(trends)}")
        runtime_mode = data.get("runtime_mode") or data.get("requested_mode")
        if runtime_mode:
            lines.append(f"- 运行模式: {runtime_mode}")
        if data.get("degraded"):
            lines.append("- 当前状态: 已发生降级，需按来源明细复核。")
        governance = cls._resolve_data_collection_governance(data)
        lines.append(f"- 信号治理: {cls._describe_data_collection_governance(governance['governance_status'])}")
        if governance["fallback_tool_count"]:
            lines.append(
                f"- 回退情况: external signal fallback {governance['fallback_tool_count']} 个工具 / "
                f"{len(governance['fallback_business_sources'])} 个业务源"
            )
        if governance["local_validation_only_sources"]:
            lines.append(f"- 本地验证来源: {', '.join(governance['local_validation_only_sources'])}")
        if governance["next_actions"]:
            lines.append(f"- 后续动作: {'；'.join(governance['next_actions'][:3])}")
        if len(lines) == 1:
            lines.append("数据采集结果已汇总，详见下方数据。")
        return "\n".join(lines)

    @staticmethod
    def _format_market_insight_section(data: dict[str, Any]) -> str:
        lines = ["市场洞察阶段完成，以下为关键发现:"]
        market_size = data.get("market_size") or data.get("tam_sam_som") or {}
        if market_size:
            lines.append(f"- 市场规模: TAM ${market_size.get('tam', 'N/A')}B")
        competitors = data.get("competitors") or data.get("competitor_landscape") or {}
        if competitors:
            lines.append(f"- 竞争格局: HHI {competitors.get('hhi', 'N/A')}")
        opportunity = data.get("opportunity_score") or data.get("opportunity") or {}
        if opportunity:
            lines.append(f"- 机会评分: {opportunity.get('total_score', opportunity.get('score', 'N/A'))}")
        if len(lines) == 1:
            lines.append("市场洞察结果已汇总，详见下方数据。")
        return "\n".join(lines)

    @staticmethod
    def _format_product_planning_section(data: dict[str, Any]) -> str:
        lines = ["产品规划阶段完成，以下为关键发现:"]
        spec = data.get("product_spec") or data.get("specification") or {}
        if spec:
            lines.append(f"- 产品定位: {spec.get('positioning', 'N/A')}")
            lines.append(f"- 核心卖点: {', '.join(spec.get('core_features', ['N/A'])[:3])}")
        diff = data.get("differentiation") or data.get("differentiation_score") or {}
        if diff:
            lines.append(f"- 差异化评分: {diff.get('total_score', diff.get('score', 'N/A'))}")
        supply = data.get("supply_chain") or {}
        if supply:
            lines.append(f"- 供应链难度: {supply.get('procurement_difficulty', 'N/A')}")
        if len(lines) == 1:
            lines.append("产品规划结果已汇总，详见下方数据。")
        return "\n".join(lines)

    @staticmethod
    def _format_commercial_section(data: dict[str, Any]) -> str:
        lines = ["商业化评估阶段完成，以下为关键发现:"]
        financial = data.get("financial_projection") or data.get("financial") or {}
        if financial:
            lines.append(f"- 毛利率: {financial.get('gross_margin', financial.get('gross_margin_pct', 'N/A'))}")
            lines.append(f"- LTV/CAC: {financial.get('ltv_cac_ratio', 'N/A')}")
        pricing = data.get("pricing") or data.get("pricing_suggestion") or {}
        if pricing:
            lines.append(f"- 建议售价: ${pricing.get('recommended_price', pricing.get('suggested_price', 'N/A'))}")
        decision = data.get("decision") or data.get("go_no_go") or {}
        if decision:
            lines.append(f"- 决策: {decision.get('decision', 'N/A')} (置信度: {decision.get('confidence', 'N/A')}%)")
        if len(lines) == 1:
            lines.append("商业化评估结果已汇总，详见下方数据。")
        return "\n".join(lines)

    @staticmethod
    def _format_risk_section(data: dict[str, Any]) -> str:
        lines = ["风险评估阶段完成，以下为关键发现:"]
        risk_assessment = data.get("risk_assessment") or data
        if isinstance(risk_assessment, dict):
            overall = risk_assessment.get("overall_risk_score", "N/A")
            level = risk_assessment.get("risk_level", "N/A")
            lines.append(f"- 综合风险分: {overall} (等级: {level})")
            signals = risk_assessment.get("signals") or risk_assessment.get("top_risks") or []
            if signals:
                lines.append(f"- 风险信号数: {len(signals)}")
                for s in signals[:3]:
                    if isinstance(s, dict):
                        lines.append(f"  - [{s.get('severity', '?').upper()}] {s.get('description', '')[:80]}")
            recs = risk_assessment.get("recommendations") or risk_assessment.get("mitigation_strategies") or []
            if recs:
                lines.append("- 建议:")
                for r in recs[:3]:
                    lines.append(f"  - {r[:100]}")
        if len(lines) == 1:
            lines.append("风险评估结果已汇总，详见下方数据。")
        return "\n".join(lines)

    async def _collect_agent_results(self, task_id: str = "") -> dict[str, Any]:
        if not task_id:
            return {}
        try:
            from src.infrastructure.database import get_async_session_factory
            from src.services.selection_service import SelectionTaskService
            session = get_async_session_factory()()
            try:
                from src.repositories.selection_repository import SelectionTaskRepository
                repo = SelectionTaskRepository(session)
                from uuid import UUID
                try:
                    normalized_id = UUID(str(task_id))
                except ValueError:
                    normalized_id = task_id
                task = await repo.get_task(normalized_id)
                if task and task.config:
                    config = task.config or {}
                    return config.get("execution_result") or {}
            finally:
                await session.close()
        except Exception as e:
            logger.warning(f"收集Agent结果失败: {e}")
        return {}

    async def _generate_executive_summary(self, query: str = "", decision: str = "", score: float = 50.0) -> str:
        decision_text = {
            "GO": "建议推进",
            "CONDITIONAL_GO": "建议有条件推进",
            "NO_GO": "建议暂缓",
            "REVIEW": "建议进一步评估",
        }.get(decision.upper(), "建议进一步评估")
        return (
            f"针对「{query}」的选品分析已完成。"
            f"综合评分{score:.1f}/100，决策建议: {decision_text}。"
            f"本报告涵盖数据采集、市场洞察、产品规划、商业化评估和风险评估五大维度，"
            f"请结合各章节详细分析做出最终决策。"
        )

    async def _persist_report(self, report: dict[str, Any] = None) -> dict[str, Any]:
        if not report:
            return {"persisted": False, "reason": "empty_report"}
        try:
            from src.services.report_center_service import ReportCenterService
            service = ReportCenterService()
            result = service.create_report(
                title=report.get("title", "选品报告"),
                report_type="selection",
                content=json.dumps(report, ensure_ascii=False, default=str),
                summary=report.get("executive_summary", ""),
            )
            return {"persisted": True, "report_id": result.report_id if hasattr(result, "report_id") else "unknown"}
        except Exception as e:
            logger.warning(f"报告持久化失败: {e}")
            return {"persisted": False, "reason": str(e)}
