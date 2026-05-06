"""
Selection Master状态机
=====================

实现选品系统的核心编排逻辑:
- 状态定义(SelectionState)
- 4个Agent阶段编排
- 条件分支与重试
- 统一 session_id 链路
- 输出结果收敛
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.core.logging import get_logger
from src.services.selection_scoring_service import SelectionScoringService

logger = get_logger(__name__)


class SelectionPhase(StrEnum):
    START = "start"
    DATA_COLLECTION = "data_collection"
    MARKET_ANALYSIS = "market_analysis"
    PRODUCT_PLANNING = "product_planning"
    COMMERCIAL_EVALUATION = "commercial_evaluation"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SelectionStatus(StrEnum):
    PROCEED = "proceed"
    PAUSED = "paused"
    RETRY_DATA = "retry_data"
    ABORT_MARKET = "abort_market"
    REVISE_PRODUCT = "revise_product"
    TERMINATE = "terminate"


@dataclass
class SelectionState:
    session_id: str = ""
    query: str = ""
    category: str = ""
    target_market: str = "US"
    budget_range: list[float] = field(default_factory=lambda: [10.0, 100.0])
    investment_budget: float = 50000.0
    priority: str = "normal"
    auto_approve: bool = False

    current_phase: SelectionPhase = SelectionPhase.START
    status: SelectionStatus = SelectionStatus.PROCEED

    data_collection_result: dict[str, Any] = field(default_factory=dict)
    market_analysis_result: dict[str, Any] = field(default_factory=dict)
    product_planning_result: dict[str, Any] = field(default_factory=dict)
    commercial_evaluation_result: dict[str, Any] = field(default_factory=dict)

    retry_count: int = 0
    max_retries: int = 3
    error_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: str = ""
    updated_at: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None

    def __post_init__(self):
        if not self.session_id:
            self.session_id = str(uuid.uuid4())[:12]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        self._touch()

    def _touch(self):
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "category": self.category,
            "target_market": self.target_market,
            "budget_range": self.budget_range,
            "current_phase": self.current_phase.value,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_count": len(self.error_log),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def log_error(self, phase: str, message: str, details: dict | None = None):
        entry = {
            "phase": phase,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }
        self.error_log.append(entry)
        logger.error(f"[{self.session_id}] {phase}: {message}")


@dataclass
class TransitionResult:
    success: bool = True
    next_phase: SelectionPhase | None = None
    status: SelectionStatus = SelectionStatus.PROCEED
    output: dict[str, Any] = field(default_factory=dict)
    should_terminate: bool = False
    error_message: str = ""


class SelectionMaster:
    MAX_RETRIES = 3
    PHASE_SEQUENCE = [
        SelectionPhase.DATA_COLLECTION,
        SelectionPhase.MARKET_ANALYSIS,
        SelectionPhase.PRODUCT_PLANNING,
        SelectionPhase.COMMERCIAL_EVALUATION,
    ]
    LANGGRAPH_COMPATIBLE_BREAKPOINTS = {SelectionPhase.COMMERCIAL_EVALUATION.value, "risk_assessment", "report_generation"}

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._phase_handlers: dict[SelectionPhase, Callable] = {}
        self._condition_checkers: dict[SelectionPhase, Callable] = {}
        self._register_default_handlers()

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @classmethod
    def _parse_price_range(cls, value: Any) -> list[float]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            start = cls._coerce_number(value[0])
            end = cls._coerce_number(value[1])
            if start is not None and end is not None:
                return [round(start, 2), round(end, 2)]
        if isinstance(value, str) and "-" in value:
            parts = value.split("-", 1)
            start = cls._coerce_number(parts[0])
            end = cls._coerce_number(parts[1])
            if start is not None and end is not None:
                return [round(start, 2), round(end, 2)]
        return []

    @staticmethod
    def _resolve_data_source_readiness_entry(source_name: str, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict) or not payload:
            return None
        signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
        signal_readiness = payload.get("signal_readiness") if isinstance(payload.get("signal_readiness"), dict) else {}
        mode = str(payload.get("mode") or "unknown").strip().lower()
        provider = str(signal_context.get("provider") or "").strip().lower() or None
        source_channel = str(signal_context.get("source_channel") or "").strip().lower() or None
        local_business_ready = False
        enterprise_ready = False
        readiness_tier = ""

        if signal_readiness:
            local_business_ready = bool(signal_readiness.get("local_business_ready", signal_readiness.get("enterprise_ready", False)))
            enterprise_ready = bool(signal_readiness.get("enterprise_ready", False))
            readiness_tier = str(signal_readiness.get("readiness_tier") or "").strip().lower()
        elif mode == "real":
            local_business_ready = True
            enterprise_ready = True
            readiness_tier = "enterprise_ready"
        elif mode == "mock":
            readiness_tier = "mock_only"
        else:
            readiness_tier = "not_ready"

        if not readiness_tier:
            if enterprise_ready:
                readiness_tier = "enterprise_ready"
            elif local_business_ready:
                readiness_tier = "local_business_ready"
            elif mode == "mock":
                readiness_tier = "mock_only"
            else:
                readiness_tier = "not_ready"

        business_interpretation = "not_ready"
        if enterprise_ready:
            business_interpretation = "enterprise_ready"
        elif local_business_ready and provider == "external_signal_service":
            business_interpretation = "local_validation_only"
        elif local_business_ready:
            business_interpretation = "enterprise_ready"
        elif mode == "mock":
            business_interpretation = "mock_only"

        return {
            "source": source_name,
            "mode": mode,
            "provider": provider,
            "source_channel": source_channel,
            "local_business_ready": local_business_ready,
            "enterprise_ready": enterprise_ready,
            "readiness_tier": readiness_tier,
            "business_interpretation": business_interpretation,
        }

    @classmethod
    def _build_data_source_governance(cls, data_collection: dict[str, Any]) -> dict[str, Any]:
        source_readiness: dict[str, dict[str, Any]] = {}
        local_validation_only_sources: list[str] = []
        enterprise_ready_sources: list[str] = []
        mock_only_sources: list[str] = []
        not_ready_sources: list[str] = []
        supply_payload = data_collection.get("supplier_data") if isinstance(data_collection.get("supplier_data"), dict) else {}
        if not supply_payload:
            alt_supply_payload = data_collection.get("supply_chain_data")
            supply_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}

        for source_name, payload in {
            "amazon": data_collection.get("amazon_data"),
            "tiktok": data_collection.get("tiktok_data"),
            "google_trends": data_collection.get("trend_data"),
            "ali1688": supply_payload,
        }.items():
            readiness = cls._resolve_data_source_readiness_entry(source_name, payload)
            if readiness is None:
                continue
            source_readiness[source_name] = readiness
            interpretation = readiness.get("business_interpretation")
            if interpretation == "local_validation_only":
                local_validation_only_sources.append(source_name)
            elif interpretation == "enterprise_ready":
                enterprise_ready_sources.append(source_name)
            elif interpretation == "mock_only":
                mock_only_sources.append(source_name)
            else:
                not_ready_sources.append(source_name)

        governance_status = "mixed"
        if local_validation_only_sources:
            governance_status = "local_validation_only"
        elif enterprise_ready_sources and not mock_only_sources and not not_ready_sources:
            governance_status = "enterprise_ready"
        elif mock_only_sources and not enterprise_ready_sources and not local_validation_only_sources:
            governance_status = "mock_only"
        elif not source_readiness:
            governance_status = "unknown"
        elif not_ready_sources and not (enterprise_ready_sources or local_validation_only_sources):
            governance_status = "not_ready"

        external_signal_summary = data_collection.get("external_signal_summary") if isinstance(data_collection.get("external_signal_summary"), dict) else {}
        return {
            "governance_status": governance_status,
            "source_readiness": source_readiness,
            "local_validation_only_sources": sorted(local_validation_only_sources),
            "enterprise_ready_sources": sorted(enterprise_ready_sources),
            "mock_only_sources": sorted(mock_only_sources),
            "not_ready_sources": sorted(not_ready_sources),
            "has_external_signal_fallbacks": bool(external_signal_summary.get("has_external_signal_fallbacks")) or bool(local_validation_only_sources),
            "external_signal_summary": external_signal_summary,
        }

    @classmethod
    def _build_decision_output(cls, state: SelectionState, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
        return SelectionScoringService().build_decision_output(
            session_id=state.session_id,
            query=state.query,
            category=state.category,
            target_market=state.target_market,
            data_collection_result=state.data_collection_result,
            market_analysis_result=state.market_analysis_result,
            product_planning_result=state.product_planning_result,
            commercial_evaluation_result=state.commercial_evaluation_result,
            metadata=state.metadata,
            error_log=state.error_log,
            execution_log=execution_log,
            current_phase=state.current_phase.value,
            retry_count=state.retry_count,
        )
        data_collection = state.data_collection_result if isinstance(state.data_collection_result, dict) else {}
        market = state.market_analysis_result if isinstance(state.market_analysis_result, dict) else {}
        product = state.product_planning_result if isinstance(state.product_planning_result, dict) else {}
        commercial = state.commercial_evaluation_result if isinstance(state.commercial_evaluation_result, dict) else {}

        go_no_go = commercial.get("go_no_go", "PENDING")
        if isinstance(go_no_go, dict):
            decision = go_no_go.get("decision", "PENDING")
            decision_reason = go_no_go.get("recommendation", "")
            decision_confidence = cls._coerce_number(go_no_go.get("confidence"))
            decision_score = cls._coerce_number(go_no_go.get("score"))
            key_factors = go_no_go.get("key_factors", [])
            pending_items = list(go_no_go.get("conditions", []))
        else:
            decision = str(go_no_go)
            decision_reason = ""
            decision_confidence = None
            decision_score = None
            key_factors = []
            pending_items = []

        top_recommendation = product.get("top_recommendation", {}) if isinstance(product.get("top_recommendation"), dict) else {}
        product_spec = product.get("product_spec", {}) if isinstance(product.get("product_spec"), dict) else {}
        supply_chain = product.get("supply_chain", {}) if isinstance(product.get("supply_chain"), dict) else {}
        opportunity = market.get("opportunity_score", {}) if isinstance(market.get("opportunity_score"), dict) else {}
        trends = market.get("trends", {}) if isinstance(market.get("trends"), dict) else {}
        risk_assessment = commercial.get("risk_assessment", {}) if isinstance(commercial.get("risk_assessment"), dict) else {}
        financial_projection = commercial.get("financial_projection", {}) if isinstance(commercial.get("financial_projection"), dict) else {}
        pricing_suggestion = commercial.get("pricing_suggestion", {}) if isinstance(commercial.get("pricing_suggestion"), dict) else {}
        quality_report = data_collection.get("quality_report", {}) if isinstance(data_collection.get("quality_report"), dict) else {}
        data_source_governance = cls._build_data_source_governance(data_collection)
        supply_payload = data_collection.get("supplier_data") if isinstance(data_collection.get("supplier_data"), dict) else {}
        if not supply_payload:
            alt_supply_payload = data_collection.get("supply_chain_data")
            supply_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}

        recommendation_name = (
            top_recommendation.get("product_name")
            or product.get("product_name")
            or product_spec.get("name")
            or state.query
        )
        recommendation_confidence = cls._coerce_number(top_recommendation.get("confidence"))
        recommendation_roi = cls._coerce_number(top_recommendation.get("expected_roi"))
        pricing_range = cls._parse_price_range(product_spec.get("target_price"))
        recommended_price = cls._coerce_number(pricing_suggestion.get("recommended_price"))
        if recommended_price is None and pricing_range:
            recommended_price = round(sum(pricing_range) / len(pricing_range), 2)

        risk_items: list[dict[str, Any]] = []
        for item in risk_assessment.get("top_risks", [])[:5]:
            if isinstance(item, dict):
                risk_items.append(
                    {
                        "name": item.get("name") or item.get("factor") or item.get("category") or "unknown_risk",
                        "category": item.get("category", "general"),
                        "score": cls._coerce_number(item.get("score") or item.get("weight")),
                    }
                )
        for text in opportunity.get("risk_factors", [])[:5]:
            if isinstance(text, str):
                risk_items.append({"name": text, "category": "market", "score": None})
        metadata = state.metadata if isinstance(state.metadata, dict) else {}
        business_warnings = list(metadata.get("business_warnings") or [])
        historical_context = metadata.get("historical_context") if isinstance(metadata.get("historical_context"), dict) else {}
        similar_history_cases = (
            historical_context.get("similar_history_cases")
            if isinstance(historical_context.get("similar_history_cases"), dict)
            else {}
        )
        review_cases = (
            historical_context.get("review_cases")
            if isinstance(historical_context.get("review_cases"), dict)
            else {}
        )
        similar_history_results = [
            item for item in list(similar_history_cases.get("results") or []) if isinstance(item, dict)
        ]
        review_case_results = [
            item for item in list(review_cases.get("results") or []) if isinstance(item, dict)
        ]
        if not risk_items and state.error_log:
            risk_items.append({"name": state.error_log[-1].get("message", "执行出现异常"), "category": "execution", "score": None})

        if not risk_items and business_warnings:
            latest_warning = business_warnings[-1] if isinstance(business_warnings[-1], dict) else {"message": str(business_warnings[-1])}
            risk_items.append(
                {
                    "name": latest_warning.get("message", "business gate warning"),
                    "category": "business_gate",
                    "score": cls._coerce_number(latest_warning.get("score")),
                }
            )

        evidence_sources = [
            source
            for source, enabled in {
                "amazon": bool(data_collection.get("amazon_data")),
                "tiktok": bool(data_collection.get("tiktok_data")),
                "google_trends": bool(data_collection.get("trend_data")),
                "ali1688": bool(supply_payload),
                "market_analysis": bool(market),
                "product_planning": bool(product),
                "commercial_evaluation": bool(commercial),
            }.items()
            if enabled
        ]
        if similar_history_results:
            evidence_sources.append("selection_history_case")
        if review_case_results:
            evidence_sources.append("crm_review_case")
        evidence_sources = list(dict.fromkeys(evidence_sources))

        historical_case_evidence: list[dict[str, Any]] = []
        for case_type, items in (
            ("selection_history_case", similar_history_results),
            ("crm_review_case", review_case_results),
        ):
            for item in items[:3]:
                item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                historical_case_evidence.append(
                    {
                        "case_type": case_type,
                        "source": item.get("source") or item_metadata.get("source") or item_metadata.get("filename"),
                        "score": cls._coerce_number(item.get("score")),
                        "snippet": str(item.get("content") or "")[:180],
                        "citation": item.get("citation"),
                    }
                )

        recommendation_reasons: list[str] = []
        if trends.get("description"):
            recommendation_reasons.append(trends["description"])
        if opportunity.get("recommendation"):
            recommendation_reasons.append(f"市场建议: {opportunity['recommendation']}")
        if top_recommendation.get("pros"):
            recommendation_reasons.extend(str(item) for item in top_recommendation.get("pros", [])[:3])
        if key_factors:
            recommendation_reasons.extend(
                str(item.get("factor")) for item in key_factors[:3] if isinstance(item, dict) and item.get("factor")
            )
        if not recommendation_reasons and decision_reason:
            recommendation_reasons.append(decision_reason)

        supply_recommendations = supply_chain.get("recommendations", []) if isinstance(supply_chain.get("recommendations"), list) else []
        differentiation = product.get("differentiation", {}) if isinstance(product.get("differentiation"), dict) else {}

        top_recommendations = []
        raw_recommendations = product.get("recommendations", []) if isinstance(product.get("recommendations"), list) else []
        for index, item in enumerate(raw_recommendations[:50], start=1):
            if not isinstance(item, dict):
                continue
            top_recommendations.append(
                {
                    "rank": int(item.get("rank") or index),
                    "product_name": item.get("product_name") or recommendation_name,
                    "confidence": cls._coerce_number(item.get("confidence")),
                    "expected_roi": cls._coerce_number(item.get("expected_roi")),
                    "time_to_market_weeks": item.get("time_to_market_weeks"),
                    "risk_rating": item.get("risk_rating"),
                    "pros": item.get("pros", []),
                    "cons": item.get("cons", []),
                    "action_items": item.get("action_items", []),
                    "recommendation_reasons": recommendation_reasons[:3],
                }
            )
        if not top_recommendations:
            for index in range(1, 51):
                confidence = max(0.0, round((recommendation_confidence or 85.0) - (index - 1) * 0.6, 1))
                expected_roi = round((recommendation_roi or 30.0) - (index - 1) * 0.25, 1)
                top_recommendations.append(
                    {
                        "rank": index,
                        "product_name": f"{recommendation_name} 候选#{index}",
                        "confidence": confidence,
                        "expected_roi": expected_roi,
                        "time_to_market_weeks": supply_chain.get("lead_time_days"),
                        "risk_rating": supply_chain.get("risk_level"),
                        "pros": recommendation_reasons[:2],
                        "cons": [risk_items[0]["name"]] if risk_items else [],
                        "action_items": supply_recommendations[:2],
                        "recommendation_reasons": recommendation_reasons[:3],
                    }
                )

        return {
            "session_id": state.session_id,
            "query": state.query,
            "category": state.category,
            "target_market": state.target_market,
            "decision": {
                "recommendation": recommendation_name,
                "decision": decision,
                "confidence": decision_confidence,
                "score": decision_score,
                "reason": decision_reason,
            },
            "recommendation_reasons": recommendation_reasons[:8],
            "top_recommendations": top_recommendations,
            "product": {
                "name": recommendation_name,
                "positioning": product_spec.get("positioning"),
                "core_features": product_spec.get("core_features", []),
                "selling_points": product_spec.get("selling_points", []),
                "confidence": recommendation_confidence,
            },
            "pricing": {
                "target_price_range": pricing_range,
                "recommended_price": recommended_price,
                "pricing_strategy": pricing_suggestion.get("pricing_strategy"),
            },
            "profitability": {
                "expected_roi": recommendation_roi,
                "gross_margin_pct": cls._coerce_number(financial_projection.get("gross_margin")),
                "net_margin_pct": cls._coerce_number(financial_projection.get("net_margin")),
                "ltv_cac_ratio": cls._coerce_number(financial_projection.get("ltv_cac_ratio")),
            },
            "supply_chain": {
                "sourcing_difficulty": supply_chain.get("sourcing_difficulty"),
                "lead_time_days": supply_chain.get("lead_time_days"),
                "supplier_count": supply_chain.get("supplier_count"),
                "risk_level": supply_chain.get("risk_level"),
                "recommendations": supply_recommendations[:5],
            },
            "risks": risk_items[:8],
            "evidence_sources": evidence_sources,
            "historical_case_summary": {
                "similar_history_case_count": len(similar_history_results),
                "review_case_count": len(review_case_results),
                "top_evidence": historical_case_evidence[:6],
            },
            "quality_summary": {
                "validity_rate": cls._coerce_number(quality_report.get("validity_rate")),
                "is_acceptable": quality_report.get("is_acceptable"),
                "data_sources": quality_report.get("sources_checked", []),
                "signal_governance_status": data_source_governance.get("governance_status"),
            },
            "data_source_governance": data_source_governance,
            "market_summary": {
                "trend_direction": trends.get("direction"),
                "trend_strength": cls._coerce_number(trends.get("strength")),
                "trend_confidence": cls._coerce_number(trends.get("confidence")),
                "opportunity_score": cls._coerce_number(opportunity.get("overall_score") or market.get("opportunity_score_value")),
                "differentiation_score": cls._coerce_number(differentiation.get("overall_score") or product.get("differentiation_score")),
            },
            "pending_items": pending_items[:8],
            "execution_summary": {
                "final_phase": state.current_phase.value,
                "retry_count": state.retry_count,
                "error_count": len(state.error_log),
                "steps": execution_log,
            },
        }

    def register_phase_handler(self, phase: SelectionPhase, handler: Callable):
        self._phase_handlers[phase] = handler
        logger.debug(f"注册阶段处理器: {phase.value}")

    def register_condition_checker(self, phase: SelectionPhase, checker: Callable):
        self._condition_checkers[phase] = checker
        logger.debug(f"注册条件检查器: {phase.value}")

    def build_langgraph_compatible_summary(self) -> dict[str, Any]:
        return {
            "framework": "langgraph-compatible",
            "graph_type": "StateGraph",
            "entry_point": self.PHASE_SEQUENCE[0].value,
            "nodes": [phase.value for phase in self.PHASE_SEQUENCE] + ["risk_assessment", "report_generation"],
            "edges": [
                {"from": SelectionPhase.DATA_COLLECTION.value, "to": SelectionPhase.MARKET_ANALYSIS.value, "condition": "success"},
                {"from": SelectionPhase.MARKET_ANALYSIS.value, "to": SelectionPhase.PRODUCT_PLANNING.value, "condition": "opportunity_score >= 30"},
                {"from": SelectionPhase.MARKET_ANALYSIS.value, "to": SelectionPhase.COMPLETED.value, "condition": "opportunity_score < 30"},
                {"from": SelectionPhase.PRODUCT_PLANNING.value, "to": SelectionPhase.PRODUCT_PLANNING.value, "condition": "differentiation_score < 35 and revision_count < 2"},
                {"from": SelectionPhase.PRODUCT_PLANNING.value, "to": SelectionPhase.COMMERCIAL_EVALUATION.value, "condition": "differentiation_score >= 35"},
                {"from": SelectionPhase.PRODUCT_PLANNING.value, "to": SelectionPhase.COMPLETED.value, "condition": "differentiation_score < 35 and revision_count >= 2"},
                {"from": SelectionPhase.COMMERCIAL_EVALUATION.value, "to": "risk_assessment", "condition": "success"},
                {"from": "risk_assessment", "to": "report_generation", "condition": "success"},
            ],
            "conditional_nodes": [SelectionPhase.MARKET_ANALYSIS.value, SelectionPhase.PRODUCT_PLANNING.value],
            "breakpoints": sorted(self.LANGGRAPH_COMPATIBLE_BREAKPOINTS),
            "human_in_the_loop": True,
            "resume_supported": True,
        }

    @staticmethod
    def _describe_signal_governance_status(status: str | None) -> str:
        normalized = str(status or "unknown")
        descriptions = {
            "enterprise_ready": "企业正式接入已完成，可直接用于业务运行",
            "local_validation_only": "当前仅可用于本地业务验证，尚未完成企业正式接入",
            "mock_only": "当前仍为 mock 演示数据，不可直接用于真实业务判断",
            "mixed": "当前混用本地验证、正式接入和未就绪来源，业务使用前需逐源确认",
            "not_ready": "当前外部信号尚未就绪，不能作为业务判断依据",
            "unknown": "当前缺少稳定的信号治理结论，需要补充校验",
        }
        return descriptions.get(normalized, descriptions["unknown"])

    def _register_default_handlers(self):
        def _to_payload(result: Any) -> dict[str, Any]:
            payload: Any = result
            if hasattr(result, "output"):
                payload = result.output
            elif hasattr(result, "to_dict"):
                payload = result.to_dict()

            if not isinstance(payload, dict):
                return {"raw": payload}

            inner = payload.get("data")
            if isinstance(inner, dict):
                return inner
            return payload

        async def handle_data_collection(state: SelectionState) -> TransitionResult:
            state.current_phase = SelectionPhase.DATA_COLLECTION
            try:
                from src.agents.data_collection import DataCollectionAgent

                agent = DataCollectionAgent()
                result = await agent.run(
                    {
                        "query": state.query,
                        "category": state.category,
                        "target_market": state.target_market,
                    }
                )
                output = _to_payload(result)
                quality_score = 0.85
                qr = output.get("quality_report", {}) if isinstance(output, dict) else {}
                if isinstance(qr, dict):
                    quality_score = qr.get("validity_rate", 0.85)
                return TransitionResult(
                    success=True,
                    next_phase=SelectionPhase.MARKET_ANALYSIS,
                    output={**output, "quality_score": quality_score},
                )
            except Exception as e:
                logger.error(f"数据采集Agent执行失败: {e}")
                state.log_error("data_collection", str(e))
                return TransitionResult(success=False, status=SelectionStatus.RETRY_DATA, error_message=str(e))

        async def handle_market_analysis(state: SelectionState) -> TransitionResult:
            state.current_phase = SelectionPhase.MARKET_ANALYSIS
            try:
                from src.agents.market_insight import MarketInsightAgent

                agent = MarketInsightAgent()
                result = await agent.run(
                    {
                        "query": state.query,
                        "category": state.category,
                        "target_market": state.target_market,
                    }
                )
                output = _to_payload(result)
                opportunity = output.get("opportunity_score", {}) if isinstance(output, dict) else {}
                opp_score = opportunity.get("overall", 70.0) if isinstance(opportunity, dict) else 70.0

                if opp_score < 30:
                    return TransitionResult(
                        success=True,
                        status=SelectionStatus.ABORT_MARKET,
                        should_terminate=True,
                        error_message=f"市场机会评分过低 ({opp_score})",
                    )

                return TransitionResult(
                    success=True,
                    next_phase=SelectionPhase.PRODUCT_PLANNING,
                    output={**output, "opportunity_score_value": opp_score},
                )
            except Exception as e:
                logger.error(f"市场分析Agent执行失败: {e}")
                state.log_error("market_analysis", str(e))
                return TransitionResult(success=False, status=SelectionStatus.RETRY_DATA, error_message=str(e))

        async def handle_product_planning(state: SelectionState) -> TransitionResult:
            state.current_phase = SelectionPhase.PRODUCT_PLANNING
            try:
                from src.agents.product_planner import ProductPlannerAgent

                agent = ProductPlannerAgent()
                result = await agent.run(
                    {
                        "query": state.query,
                        "category": state.category,
                        "target_market": state.target_market,
                        "budget_range": state.budget_range,
                    }
                )
                output = _to_payload(result)
                differentiation = output.get("differentiation", {}) if isinstance(output, dict) else {}
                diff_score = differentiation.get("overall", 60.0) if isinstance(differentiation, dict) else 60.0

                if diff_score < 35:
                    return TransitionResult(
                        success=True,
                        status=SelectionStatus.REVISE_PRODUCT,
                        next_phase=SelectionPhase.PRODUCT_PLANNING,
                        error_message=f"产品差异化不足 ({diff_score}), 需重新规划",
                    )

                return TransitionResult(
                    success=True,
                    next_phase=SelectionPhase.COMMERCIAL_EVALUATION,
                    output={**output, "differentiation_score": diff_score},
                )
            except Exception as e:
                logger.error(f"产品规划Agent执行失败: {e}")
                state.log_error("product_planning", str(e))
                return TransitionResult(success=False, error_message=str(e))

        async def handle_commercial_eval(state: SelectionState) -> TransitionResult:
            state.current_phase = SelectionPhase.COMMERCIAL_EVALUATION
            try:
                from src.agents.commercial import CommercialAgent

                agent = CommercialAgent(config={"commercial_rules": self.config.get("commercial_rules")})
                result = await agent.run(
                    {
                        "query": state.query,
                        "category": state.category,
                        "target_market": state.target_market,
                        "investment_budget": self.config.get("investment_budget", 50000),
                        "commercial_rules": self.config.get("commercial_rules"),
                    }
                )
                output = _to_payload(result)
                gng = output.get("go_no_go", {}) if isinstance(output, dict) else {}
                if isinstance(gng, dict):
                    go_decision = gng.get("decision", "CONDITIONAL_GO")
                elif isinstance(gng, str):
                    go_decision = gng
                else:
                    go_decision = "CONDITIONAL_GO"

                return TransitionResult(
                    success=True,
                    next_phase=SelectionPhase.COMPLETED,
                    output={**output, "go_no_go_decision": go_decision},
                )
            except Exception as e:
                logger.error(f"商业评估Agent执行失败: {e}")
                state.log_error("commercial_evaluation", str(e))
                return TransitionResult(success=False, error_message=str(e))

        self.register_phase_handler(SelectionPhase.DATA_COLLECTION, handle_data_collection)
        self.register_phase_handler(SelectionPhase.MARKET_ANALYSIS, handle_market_analysis)
        self.register_phase_handler(SelectionPhase.PRODUCT_PLANNING, handle_product_planning)
        self.register_phase_handler(SelectionPhase.COMMERCIAL_EVALUATION, handle_commercial_eval)

    async def run_legacy(self, input_data: dict[str, Any]) -> dict[str, Any]:
        state = SelectionState(
            session_id=input_data.get("session_id") or self.config.get("session_id", ""),
            query=input_data.get("query", ""),
            category=input_data.get("category", ""),
            target_market=input_data.get("target_market", "US"),
            budget_range=input_data.get("budget_range", [10.0, 100.0]),
            max_retries=self.MAX_RETRIES,
        )

        execution_log: list[dict[str, Any]] = []
        current_phase = SelectionPhase.DATA_COLLECTION
        result = TransitionResult()

        try:
            while current_phase and current_phase != SelectionPhase.COMPLETED:
                handler = self._phase_handlers.get(current_phase)
                if not handler:
                    state.log_error(current_phase.value, f"未找到阶段处理器: {current_phase.value}")
                    break

                result = await handler(state)
                exec_entry = {
                    "phase": current_phase.value,
                    "success": result.success,
                    "status": result.status.value,
                    "duration_hint": "simulated",
                }

                if not result.success:
                    state.retry_count += 1
                    if state.retry_count >= state.max_retries:
                        exec_entry["action"] = "terminate_max_retries"
                        state.status = SelectionStatus.TERMINATE
                        execution_log.append(exec_entry)
                        break
                    exec_entry["action"] = f"retry_{state.retry_count}"
                    if result.status == SelectionStatus.RETRY_DATA:
                        current_phase = SelectionPhase.DATA_COLLECTION
                elif result.should_terminate:
                    exec_entry["action"] = "terminate"
                    state.status = result.status
                    execution_log.append(exec_entry)
                    break
                elif result.next_phase:
                    exec_entry["action"] = f"transition_to_{result.next_phase.value}"
                    if current_phase == SelectionPhase.DATA_COLLECTION:
                        state.data_collection_result = result.output
                    elif current_phase == SelectionPhase.MARKET_ANALYSIS:
                        state.market_analysis_result = result.output
                    elif current_phase == SelectionPhase.PRODUCT_PLANNING:
                        state.product_planning_result = result.output
                    elif current_phase == SelectionPhase.COMMERCIAL_EVALUATION:
                        state.commercial_evaluation_result = result.output
                    current_phase = result.next_phase
                    state.status = SelectionStatus.PROCEED

                execution_log.append(exec_entry)
                state._touch()

            if current_phase == SelectionPhase.COMPLETED or (
                not result.should_terminate and state.status == SelectionStatus.PROCEED
            ):
                state.current_phase = SelectionPhase.COMPLETED
                state.status = SelectionStatus.PROCEED
        except Exception as e:
            state.log_error("runtime", str(e))
            state.status = SelectionStatus.TERMINATE

        final_output = {
            "session_id": state.session_id,
            "status": state.status.value,
            "final_phase": state.current_phase.value,
            "execution_log": execution_log,
            "results": {
                "data_collection": state.data_collection_result,
                "market_analysis": state.market_analysis_result,
                "product_planning": state.product_planning_result,
                "commercial_evaluation": state.commercial_evaluation_result,
            },
            "state_summary": state.to_dict(),
            "retry_count": state.retry_count,
            "error_count": len(state.error_log),
            "generated_at": datetime.now(UTC).isoformat(),
        }

        go_value = state.commercial_evaluation_result.get("go_no_go", "PENDING")
        if isinstance(go_value, dict):
            final_output["go_no_go"] = go_value
            final_output["go_no_go_decision"] = go_value.get("decision")
        else:
            final_output["go_no_go"] = go_value
            final_output["go_no_go_decision"] = str(go_value)

        final_output["decision_output"] = self._build_decision_output(state, execution_log)
        final_output["summary"] = self._generate_summary(final_output, state)
        final_output["framework"] = "native-python"
        return final_output

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        if self.config.get("force_legacy"):
            return await self.run_legacy(input_data)

        from src.agents.langgraph_compatible import LangGraphCompatibleRunner

        runner = LangGraphCompatibleRunner()
        result = await runner.invoke(input_data=input_data, breakpoints=[], single_step=False)
        payload = result.get("selection_master_output")
        if isinstance(payload, dict):
            return payload
        return await self.run_legacy(input_data)

    def _generate_summary(self, output: dict[str, Any], state: SelectionState) -> str:
        results = output.get("results", {})
        market = results.get("market_analysis", {})
        product = results.get("product_planning", {})
        commercial = results.get("commercial_evaluation", {})
        decision_output = output.get("decision_output") if isinstance(output.get("decision_output"), dict) else {}
        data_source_governance = (
            decision_output.get("data_source_governance")
            if isinstance(decision_output.get("data_source_governance"), dict)
            else {}
        )
        quality_summary = decision_output.get("quality_summary") if isinstance(decision_output.get("quality_summary"), dict) else {}
        historical_case_summary = (
            decision_output.get("historical_case_summary")
            if isinstance(decision_output.get("historical_case_summary"), dict)
            else {}
        )
        signal_governance_status = (
            data_source_governance.get("governance_status")
            or quality_summary.get("signal_governance_status")
        )
        similar_history_case_count = int(historical_case_summary.get("similar_history_case_count") or 0)
        review_case_count = int(historical_case_summary.get("review_case_count") or 0)

        lines = [
            f"[{state.category}]选品流程报告",
            f"会话ID: {state.session_id}",
            f"最终状态: {output['status']} ({output['final_phase']})",
            "",
            f"市场机会评分: {market.get('opportunity_score', 'N/A')}",
            f"趋势方向: {market.get('trends', {}).get('direction', market.get('trend', 'N/A')) if isinstance(market, dict) else 'N/A'}",
            f"推荐产品: {product.get('top_recommendation', {}).get('product_name', product.get('product_name', 'N/A')) if isinstance(product, dict) else 'N/A'}",
            f"目标售价: {product.get('product_spec', {}).get('target_price', product.get('target_price', 'N/A')) if isinstance(product, dict) else 'N/A'}",
            f"预期ROI: {commercial.get('financial_projection', {}).get('roi_pct', commercial.get('estimated_roi', 'N/A')) if isinstance(commercial, dict) else 'N/A'}",
            f"Go/No-Go: {output.get('go_no_go_decision', commercial.get('go_no_go', output.get('go_no_go', 'N/A')))}",
        ]

        if output.get("status_reason"):
            lines.append(f"状态说明: {output.get('status_reason')}")

        if signal_governance_status:
            lines.extend([
                "",
                f"信号治理: {self._describe_signal_governance_status(signal_governance_status)}",
            ])
            if data_source_governance.get("local_validation_only_sources"):
                lines.append(
                    "本地验证来源: "
                    + ", ".join(str(item) for item in data_source_governance.get("local_validation_only_sources", []))
                )
            if data_source_governance.get("enterprise_ready_sources"):
                lines.append(
                    "企业接入来源: "
                    + ", ".join(str(item) for item in data_source_governance.get("enterprise_ready_sources", []))
                )
            if data_source_governance.get("mock_only_sources"):
                lines.append(
                    "仅 Mock 来源: "
                    + ", ".join(str(item) for item in data_source_governance.get("mock_only_sources", []))
                )
            if data_source_governance.get("not_ready_sources"):
                lines.append(
                    "待补齐来源: "
                    + ", ".join(str(item) for item in data_source_governance.get("not_ready_sources", []))
                )
            if data_source_governance.get("next_action"):
                lines.append(f"后续动作: {data_source_governance.get('next_action')}")

        if similar_history_case_count or review_case_count:
            lines.extend([
                "",
                f"历史案例参考: 选品案例 {similar_history_case_count} 条, CRM 评价案例 {review_case_count} 条",
            ])

        if state.error_log:
            lines.append(f"\n⚠️ 问题记录: {len(state.error_log)}条")

        return "\n".join(lines)


def create_selection_master(config: dict | None = None) -> SelectionMaster:
    """创建SelectionMaster工厂函数。"""
    return SelectionMaster(config=config)
