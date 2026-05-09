"""
选品任务应用服务
================

承接选品任务的业务编排、Repository 调用和执行器抽象，
避免 endpoint 直接处理数据库 CRUD 与后台执行细节。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.selection_master import SelectionMaster
from src.config.settings import get_settings
from src.core.authorization import require_permission, resolve_permissions
from src.core.data_masking import mask_sensitive_data
from src.core.exceptions import AuthorizationError
from src.core.logging import get_logger
from src.core.metrics import (
    AGENT_EXECUTION_DURATION,
    AGENT_EXECUTIONS_TOTAL,
    record_selection_created,
    record_selection_terminal_status,
    set_selection_accuracy_metric,
    update_selection_running_metrics,
)
from src.core.rbac import (
    ACTION_APPROVE,
    ACTION_EXECUTE,
    ACTION_MANAGE,
    ACTION_READ,
    RESOURCE_SELECTION,
    build_permission,
)
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.feature_engine import FeatureEngine
from src.infrastructure.tracing import get_request_id, get_trace_id
from src.models.enums import TaskPriority, TaskStatus
from src.repositories.selection_repository import SelectionTaskRepository
from src.services.channel_delivery_service import ChannelDeliveryService
from src.services.config_center_service import ConfigCenterService

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _safe_count_running_tasks_for_repo(repo: Any, tenant_id: str | None) -> int:
    counter = getattr(repo, "count_running_tasks_by_tenant", None)
    if callable(counter) and tenant_id is not None:
        try:
            return int(await counter(tenant_id))
        except Exception:
            return 0
    return 0


async def _safe_count_backlog_tasks_for_repo(repo: Any, tenant_id: str | None) -> int:
    counter = getattr(repo, "count_backlog_tasks_by_tenant", None)
    if callable(counter) and tenant_id is not None:
        try:
            return int(await counter(tenant_id))
        except Exception:
            return 0
    return 0


@dataclass
class SelectionTaskExecutionContext:
    task_id: str
    tenant_id: str | None = None
    query: str = ""
    category: str = ""
    investment_budget: float = 0.0
    target_market: str = "US"
    auto_approve: bool = False
    priority: str = "normal"


class TaskExecutor:
    """任务执行器抽象，便于后续替换为 Worker。"""

    async def submit(
        self,
        job: Callable[..., Awaitable[None]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        raise NotImplementedError


class InProcessTaskExecutor(TaskExecutor):
    """当前阶段默认执行器：进程内异步任务。"""

    async def submit(
        self,
        job: Callable[..., Awaitable[None]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        asyncio.create_task(job(*args, **kwargs))


class FastAPIBackgroundTaskDispatcher:
    """FastAPI BackgroundTasks 适配层。"""

    def __init__(self, background_tasks: Any):
        self.background_tasks = background_tasks

    async def dispatch(self, service: SelectionTaskService, context: SelectionTaskExecutionContext) -> None:
        self.background_tasks.add_task(service.submit_task_for_execution, context)


class SelectionTaskService:
    """选品任务应用服务。"""

    def __init__(self, session: AsyncSession, executor: TaskExecutor | None = None, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.actor = actor or {}
        self.tenant_id = tenant_id or self.actor.get("tenant_id")
        self.repo = SelectionTaskRepository(session, tenant_id=self.tenant_id)
        self.executor = executor or InProcessTaskExecutor()

    APPROVAL_STAGE_DEFINITIONS = [
        {"stage": "operator_review", "order": 1, "display_name": "运营初审", "roles": ["operator", "tenant_admin"]},
        {"stage": "procurement_review", "order": 2, "display_name": "采购复审", "roles": ["procurement", "tenant_admin"]},
        {"stage": "manager_review", "order": 3, "display_name": "管理终审", "roles": ["manager", "tenant_admin", "platform_admin"]},
    ]

    @staticmethod
    def _supports_knowledge_db_session(session: Any) -> bool:
        return session is not None and callable(getattr(session, "execute", None))

    def _has_any_permission(self, *permissions: str) -> bool:
        actor_permissions = resolve_permissions(self.actor)
        return any(permission in actor_permissions for permission in permissions)

    def _can_access_task_record(self, task: Any) -> bool:
        config = task.config or {}
        task_tenant_id = config.get("tenant_id") if isinstance(config, dict) else None
        actor_tenant_id = self.tenant_id or self.actor.get("tenant_id")
        if task_tenant_id and actor_tenant_id and str(task_tenant_id) != str(actor_tenant_id):
            return False

        if self._has_any_permission(build_permission(RESOURCE_SELECTION, ACTION_MANAGE)):
            return True

        if self._has_any_permission(build_permission(RESOURCE_SELECTION, ACTION_APPROVE)):
            return True

        if self._has_any_permission(build_permission(RESOURCE_SELECTION, ACTION_READ), build_permission(RESOURCE_SELECTION, ACTION_EXECUTE)):
            actor_user_id = self.actor.get("user_id")
            created_by = getattr(task, "created_by", None)
            if actor_user_id is not None and created_by is not None:
                return str(actor_user_id) == str(created_by)

        return False

    def _require_task_access(self, task: Any, *, action: str) -> None:
        if not self._can_access_task_record(task):
            raise AuthorizationError(action=build_permission(RESOURCE_SELECTION, action), resource="selection_task")

    @staticmethod
    def _map_priority(priority: str) -> TaskPriority:
        mapping = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.MEDIUM,
            "medium": TaskPriority.MEDIUM,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT,
        }
        return mapping.get((priority or "normal").lower(), TaskPriority.MEDIUM)

    @staticmethod
    def _extract_payload(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"raw": str(result)}

        payload = result.get("data")
        if isinstance(payload, dict):
            return payload
        return result

    @staticmethod
    def _extract_go_no_go(result_payload: dict[str, Any]) -> tuple[Any | None, str | None]:
        decision_output = result_payload.get("decision_output")
        if isinstance(decision_output, dict):
            decision_meta = decision_output.get("decision")
            if isinstance(decision_meta, dict):
                decision = decision_meta.get("decision")
                if decision is not None:
                    return decision_meta, str(decision)

        commercial = result_payload.get("results", {}).get("commercial_evaluation", {})
        if not isinstance(commercial, dict):
            return None, None

        go_no_go = commercial.get("go_no_go")
        if isinstance(go_no_go, dict):
            return go_no_go, go_no_go.get("decision")
        if isinstance(go_no_go, str):
            return go_no_go, go_no_go
        return None, None

    @staticmethod
    def _extract_decision_output(result_payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(result_payload, dict):
            return None
        decision_output = result_payload.get("decision_output")
        return decision_output if isinstance(decision_output, dict) else None

    @staticmethod
    def _infer_rejection_feedback_tags(reason: str) -> list[str]:
        normalized = str(reason or "").lower()
        keyword_mapping = (
            ("margin_risk", ("利润", "毛利", "成本", "roi", "margin", "profit", "cost")),
            ("market_misalignment", ("市场", "趋势", "需求", "market", "trend", "demand")),
            ("supply_chain_risk", ("供应", "交付", "供应链", "supplier", "supply", "delivery")),
            ("compliance_risk", ("合规", "专利", "侵权", "compliance", "patent", "ip")),
            ("quality_risk", ("质量", "评价", "差评", "quality", "review", "rating")),
        )
        tags = [tag for tag, keywords in keyword_mapping if any(keyword in normalized for keyword in keywords)]
        return tags or ["manual_rejection"]

    @staticmethod
    def _describe_signal_governance_status(status: str | None) -> str:
        normalized = str(status or "unknown")
        descriptions = {
            "enterprise_ready": "已完成企业正式接入，可直接作为业务运行依据",
            "local_validation_only": "当前仅完成本地业务验证，尚未完成企业正式接入",
            "mock_only": "当前仅有 mock 演示数据，不可作为真实业务判断依据",
            "mixed": "当前同时存在本地验证、正式接入和未就绪信号，使用时需严格区分来源",
            "not_ready": "当前外部信号尚未就绪，不能作为业务判断依据",
            "unknown": "当前缺少稳定的外部信号治理结论，需要补充校验",
        }
        return descriptions.get(normalized, descriptions["unknown"])

    @classmethod
    def _build_signal_governance_summary(cls, decision_output: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(decision_output, dict):
            return None

        quality_summary = decision_output.get("quality_summary")
        quality_payload = quality_summary if isinstance(quality_summary, dict) else {}
        governance = decision_output.get("data_source_governance")
        governance_payload = governance if isinstance(governance, dict) else {}
        status = (
            quality_payload.get("signal_governance_status")
            or governance_payload.get("governance_status")
        )
        if status is None and not governance_payload:
            return None

        summary = {
            "signal_governance_status": str(status or "unknown"),
            "summary_text": cls._describe_signal_governance_status(status),
            "local_validation_only_sources": list(governance_payload.get("local_validation_only_sources") or []),
            "enterprise_ready_sources": list(governance_payload.get("enterprise_ready_sources") or []),
            "mock_only_sources": list(governance_payload.get("mock_only_sources") or []),
            "not_ready_sources": list(governance_payload.get("not_ready_sources") or []),
            "requires_enterprise_connectors": str(status or "unknown") != "enterprise_ready",
        }
        next_action = governance_payload.get("next_action")
        if next_action:
            summary["next_action"] = str(next_action)
        return summary

    @classmethod
    def _build_approval_flow(cls) -> list[dict[str, Any]]:
        return [
            {
                "stage": item["stage"],
                "stage_order": item["order"],
                "display_name": item["display_name"],
                "roles": list(item["roles"]),
                "status": "pending",
                "reviewer": None,
                "comment": None,
                "reviewed_at": None,
            }
            for item in cls.APPROVAL_STAGE_DEFINITIONS
        ]

    @staticmethod
    def _append_approval_history(config: dict[str, Any], history_item: dict[str, Any]) -> list[dict[str, Any]]:
        history = list(config.get("approval_history", []))
        history.append(history_item)
        config["approval_history"] = history[-100:]
        return config["approval_history"]

    @staticmethod
    def _match_actor_to_stage(stage_item: dict[str, Any], actor_roles: list[str]) -> bool:
        allowed_roles = {str(role) for role in stage_item.get("roles", [])}
        return bool(allowed_roles.intersection({str(role) for role in actor_roles}))

    @classmethod
    def _resolve_stage_index(
        cls,
        flow: list[dict[str, Any]],
        *,
        requested_stage: str | None,
        requested_order: int | None,
        actor_roles: list[str],
    ) -> int:
        if requested_stage:
            for index, stage_item in enumerate(flow):
                if str(stage_item.get("stage")) == requested_stage:
                    return index
        if requested_order is not None:
            for index, stage_item in enumerate(flow):
                if int(stage_item.get("stage_order") or 0) == int(requested_order):
                    return index
        for index, stage_item in enumerate(flow):
            if str(stage_item.get("status") or "pending") == "pending" and cls._match_actor_to_stage(stage_item, actor_roles):
                return index
        for index, stage_item in enumerate(flow):
            if str(stage_item.get("status") or "pending") == "pending":
                return index
        return max(len(flow) - 1, 0)

    @staticmethod
    async def _send_approval_notification(*, channel: str, webhook_url: str, title: str, content: str) -> dict[str, Any]:
        delivery_service = ChannelDeliveryService()
        return await delivery_service.send_report(
            channel=channel,
            webhook_url=webhook_url,
            title=title,
            content=content,
        )

    @staticmethod
    def _normalize_feedback(payload: dict[str, Any]) -> dict[str, Any]:
        rating = payload.get("rating")
        try:
            rating_value = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating_value = None
        sentiment = str(payload.get("sentiment") or "neutral").lower()
        tags = [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()]
        source = str(payload.get("source") or "manual").strip() or "manual"
        comment = str(payload.get("comment") or "").strip()
        score = 50.0
        if rating_value is not None:
            score = max(0.0, min(100.0, rating_value / 5 * 100))
        if sentiment == "positive":
            score = min(100.0, score + 10)
        elif sentiment == "negative":
            score = max(0.0, score - 20)
        if any(tag.lower() in {"refund", "quality_issue", "complaint", "defect"} for tag in tags):
            score = max(0.0, score - 15)
        label = "positive" if score >= 70 else ("negative" if score < 40 else "neutral")
        return {
            "source": source,
            "rating": rating_value,
            "sentiment": sentiment,
            "tags": tags,
            "comment": comment,
            "feedback_score": round(score, 1),
            "feedback_label": label,
            "recorded_at": _now_iso(),
        }

    @classmethod
    def _apply_feedback_to_result(cls, result_payload: dict[str, Any], feedback_entry: dict[str, Any]) -> dict[str, Any]:
        decision_output = cls._extract_decision_output(result_payload) or {}
        config: dict[str, Any] = {}
        feedback_summary = decision_output.get("customer_feedback") if isinstance(decision_output.get("customer_feedback"), dict) else {
            "feedback_count": 0,
            "average_score": None,
            "latest_label": None,
            "latest_tags": [],
        }
        feedback_count = int(feedback_summary.get("feedback_count") or 0) + 1
        previous_avg = feedback_summary.get("average_score")
        previous_avg_value = float(previous_avg) if previous_avg is not None else None
        if previous_avg_value is None:
            average_score = feedback_entry["feedback_score"]
        else:
            average_score = ((previous_avg_value * (feedback_count - 1)) + feedback_entry["feedback_score"]) / feedback_count

        rejection = config.get("rejection") if isinstance(config.get("rejection"), dict) else {}
        if rejection and rejection.get("status") == "rejected":
            raise ValueError("当前任务已拒绝推荐，不能再采纳")

        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        recommended_price = pricing.get("recommended_price")
        try:
            recommended_price_value = float(recommended_price) if recommended_price is not None else None
        except (TypeError, ValueError):
            recommended_price_value = None
        adjusted_price = recommended_price_value
        if recommended_price_value is not None:
            if feedback_entry["feedback_label"] == "negative":
                adjusted_price = round(recommended_price_value * 0.97, 2)
            elif feedback_entry["feedback_label"] == "positive":
                adjusted_price = round(recommended_price_value * 1.02, 2)
            pricing["recommended_price"] = adjusted_price
            pricing["feedback_adjustment_applied"] = True

        risks = decision_output.get("risks") if isinstance(decision_output.get("risks"), list) else []
        if feedback_entry["feedback_label"] == "negative":
            risks.insert(0, {
                "name": "客户反馈预警",
                "category": "customer_feedback",
                "score": 100 - feedback_entry["feedback_score"],
            })
        recommendation_reasons = decision_output.get("recommendation_reasons") if isinstance(decision_output.get("recommendation_reasons"), list) else []
        recommendation_reasons.append(f"客户反馈标签: {feedback_entry['feedback_label']}")

        decision_output["pricing"] = pricing
        decision_output["risks"] = risks[:8]
        decision_output["recommendation_reasons"] = recommendation_reasons[:8]
        decision_output["customer_feedback"] = {
            "feedback_count": feedback_count,
            "average_score": round(average_score, 1),
            "latest_label": feedback_entry["feedback_label"],
            "latest_tags": feedback_entry.get("tags", []),
            "latest_sentiment": feedback_entry.get("sentiment"),
            "latest_source": feedback_entry.get("source"),
            "price_adjustment": adjusted_price,
        }
        result_payload["decision_output"] = decision_output
        return result_payload

    @staticmethod
    def _normalize_phase(status: TaskStatus, result_payload: dict[str, Any] | None = None) -> str:
        if status == TaskStatus.PENDING:
            return "pending"
        if status == TaskStatus.RUNNING:
            if isinstance(result_payload, dict):
                summary = result_payload.get("state_summary", {})
                if isinstance(summary, dict):
                    return summary.get("current_phase", "data_collection")
            return "data_collection"
        if status == TaskStatus.PAUSED:
            return "paused"
        if status == TaskStatus.COMPLETED:
            return "completed"
        if status == TaskStatus.FAILED:
            return "failed"
        if status == TaskStatus.CANCELLED:
            return "cancelled"
        return "unknown"

    @staticmethod
    def _build_similar_history_case_query(task_payload: dict[str, Any]) -> str:
        decision_output = task_payload.get("decision_output") if isinstance(task_payload.get("decision_output"), dict) else {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        product = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        supply_chain = decision_output.get("supply_chain") if isinstance(decision_output.get("supply_chain"), dict) else {}
        recommendation_reasons = decision_output.get("recommendation_reasons") if isinstance(decision_output.get("recommendation_reasons"), list) else []
        execution_feedback = decision_output.get("execution_feedback") if isinstance(decision_output.get("execution_feedback"), dict) else {}
        reviews = execution_feedback.get("reviews") if isinstance(execution_feedback.get("reviews"), dict) else {}
        sales = execution_feedback.get("sales") if isinstance(execution_feedback.get("sales"), dict) else {}

        raw_parts = [
            task_payload.get("query"),
            task_payload.get("category"),
            task_payload.get("target_market"),
            product.get("name") or product.get("product_name"),
            product.get("asin") or product.get("external_product_id"),
            decision_meta.get("decision"),
            pricing.get("recommended_price"),
            supply_chain.get("primary_supplier"),
            reviews.get("rating"),
            sales.get("sales_7d"),
            *recommendation_reasons[:3],
        ]
        parts: list[str] = []
        for item in raw_parts:
            text = str(item).strip() if item is not None else ""
            if text and text not in parts:
                parts.append(text)
        return " ".join(parts)

    async def _load_similar_history_cases(self, task_payload: dict[str, Any], top_k: int = 3) -> dict[str, Any]:
        query = self._build_similar_history_case_query(task_payload)
        empty_result = {
            "query": query,
            "case_type": "selection_history_case",
            "total_found": 0,
            "processing_time_ms": 0.0,
            "results": [],
        }
        if not query:
            return empty_result

        try:
            from src.services.knowledge_service import KnowledgeService
            from src.services.local_knowledge_service import LocalKnowledgeService

            knowledge_service = (
                KnowledgeService(self.session, tenant_id=self.tenant_id, actor=self.actor)
                if self._supports_knowledge_db_session(self.session)
                else LocalKnowledgeService()
            )
            result = await knowledge_service.query_selection_cases(query=query, top_k=top_k, threshold=0.1)
            return {
                "query": result.get("query", query),
                "case_type": result.get("case_type", "selection_history_case"),
                "total_found": result.get("total_found", 0),
                "processing_time_ms": result.get("processing_time_ms", 0.0),
                "results": result.get("results", []),
            }
        except ValueError:
            return empty_result
        except Exception as e:
            logger.warning(f"历史选品案例检索失败，降级为空结果: {e}")
            return {**empty_result, "error": str(e)}

    async def _load_similar_review_cases(self, task_payload: dict[str, Any], top_k: int = 3) -> dict[str, Any]:
        query = self._build_similar_history_case_query(task_payload)
        empty_result = {
            "query": query,
            "case_type": "crm_review_case",
            "total_found": 0,
            "processing_time_ms": 0.0,
            "results": [],
        }
        if not query:
            return empty_result

        try:
            from src.services.knowledge_service import KnowledgeService
            from src.services.local_knowledge_service import LocalKnowledgeService

            knowledge_service = (
                KnowledgeService(self.session, tenant_id=self.tenant_id, actor=self.actor)
                if self._supports_knowledge_db_session(self.session)
                else LocalKnowledgeService()
            )
            result = await knowledge_service.query_review_cases(query=f"{query} 评价 投诉 差评 好评", top_k=top_k, threshold=0.1)
            return {
                "query": result.get("query", query),
                "case_type": result.get("case_type", "crm_review_case"),
                "total_found": result.get("total_found", 0),
                "processing_time_ms": result.get("processing_time_ms", 0.0),
                "results": result.get("results", []),
            }
        except ValueError:
            return empty_result
        except Exception as e:
            logger.warning(f"CRM评价案例检索失败，降级为空结果: {e}")
            return {**empty_result, "error": str(e)}

    async def _load_historical_performance(self, task_payload: dict[str, Any], top_k: int = 5) -> dict[str, Any]:
        query = self._build_similar_history_case_query(task_payload)
        empty_result = {
            "query": query,
            "case_type": "historical_performance",
            "total_found": 0,
            "results": [],
        }
        if not query or self.session is None:
            return empty_result

        try:
            tasks, _ = await self.repo.list_tasks(limit=100, offset=0)
        except Exception as e:
            logger.warning(f"联合历史表现检索失败，降级为空结果: {e}")
            return {**empty_result, "error": str(e)}

        current_task_id = str(task_payload.get("task_id") or "")
        query_text = str(task_payload.get("query") or "").lower()
        category = str(task_payload.get("category") or "").lower()
        target_market = str(task_payload.get("target_market") or "").lower()
        decision_output = task_payload.get("decision_output") if isinstance(task_payload.get("decision_output"), dict) else {}
        product = decision_output.get("product") if isinstance(decision_output.get("product"), dict) else {}
        product_name = str(product.get("name") or product.get("product_name") or "").lower()
        asin = str(product.get("asin") or product.get("external_product_id") or "").lower()

        scored: list[dict[str, Any]] = []
        for task in tasks:
            serialized = self._serialize_task(task)
            if serialized.get("task_id") == current_task_id:
                continue
            adoption = serialized.get("adoption") if isinstance(serialized.get("adoption"), dict) else {}
            result_payload = serialized.get("result") if isinstance(serialized.get("result"), dict) else {}
            feedback_snapshot = result_payload.get("execution_feedback_snapshot") if isinstance(result_payload.get("execution_feedback_snapshot"), dict) else {}
            if not adoption or not feedback_snapshot:
                continue

            candidate_score = 0.0
            candidate_query = str(serialized.get("query") or "").lower()
            candidate_category = str(serialized.get("category") or "").lower()
            candidate_market = str(serialized.get("target_market") or "").lower()
            candidate_decision_output = serialized.get("decision_output") if isinstance(serialized.get("decision_output"), dict) else {}
            candidate_product = candidate_decision_output.get("product") if isinstance(candidate_decision_output.get("product"), dict) else {}
            candidate_name = str(candidate_product.get("name") or candidate_product.get("product_name") or "").lower()
            candidate_asin = str(candidate_product.get("asin") or candidate_product.get("external_product_id") or "").lower()

            if query_text and query_text in candidate_query:
                candidate_score += 0.4
            if category and category == candidate_category:
                candidate_score += 0.2
            if target_market and target_market == candidate_market:
                candidate_score += 0.15
            if product_name and product_name and (product_name in candidate_name or candidate_name in product_name):
                candidate_score += 0.15
            if asin and candidate_asin and asin == candidate_asin:
                candidate_score += 0.3
            if candidate_score <= 0:
                continue

            sales = ((feedback_snapshot.get("sales") or {}).get("orders") or {}) if isinstance((feedback_snapshot.get("sales") or {}).get("orders"), dict) else {}
            reviews = feedback_snapshot.get("reviews") if isinstance(feedback_snapshot.get("reviews"), dict) else {}
            _profit = feedback_snapshot.get("profit") if isinstance(feedback_snapshot.get("profit"), dict) else {}
            inventory = ((feedback_snapshot.get("inventory") or {}).get("summary") or {}) if isinstance((feedback_snapshot.get("inventory") or {}).get("summary"), dict) else {}
            execution_status = adoption.get("execution_status") if isinstance(adoption.get("execution_status"), dict) else {}

            scored.append({
                "task_id": serialized.get("task_id"),
                "query": serialized.get("query"),
                "category": serialized.get("category"),
                "target_market": serialized.get("target_market"),
                "score": round(candidate_score, 4),
                "adoption_status": adoption.get("status"),
                "performance": {
                    "oms": {
                        "units": sales.get("units"),
                        "sales_amount": sales.get("sales_amount"),
                        "refund_rate": sales.get("refund_rate"),
                    },
                    "crm": {
                        "avg_rating": reviews.get("avg_rating"),
                        "review_count": reviews.get("review_count"),
                        "negative_feedback_count": reviews.get("negative_feedback_count"),
                    },
                    "scm": execution_status.get("scm") if isinstance(execution_status.get("scm"), dict) else {},
                    "wms": {
                        "available_quantity_total": inventory.get("available_quantity_total"),
                        "inventory_turnover_days": inventory.get("inventory_turnover_days"),
                        "stockout_skus": inventory.get("stockout_skus"),
                    },
                },
                "feature_asset": serialized.get("result", {}).get("decision_output", {}).get("rescore_summary") if isinstance(serialized.get("result"), dict) else None,
                "snapshot_time": feedback_snapshot.get("synced_at"),
            })

        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        return {
            "query": query,
            "case_type": "historical_performance",
            "total_found": len(scored[:top_k]),
            "results": scored[:top_k],
        }

    @staticmethod
    def _compute_accuracy_point(task_payload: dict[str, Any]) -> dict[str, Any] | None:
        adoption = task_payload.get("adoption") if isinstance(task_payload.get("adoption"), dict) else {}
        result_payload = task_payload.get("result") if isinstance(task_payload.get("result"), dict) else {}
        feedback_snapshot = result_payload.get("execution_feedback_snapshot") if isinstance(result_payload.get("execution_feedback_snapshot"), dict) else {}
        if not feedback_snapshot:
            feedback_snapshot = task_payload.get("execution_feedback_snapshot") if isinstance(task_payload.get("execution_feedback_snapshot"), dict) else {}
        decision_output = task_payload.get("decision_output") if isinstance(task_payload.get("decision_output"), dict) else {}
        if not adoption or not feedback_snapshot:
            return None

        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        predicted_decision = str(decision_meta.get("decision") or task_payload.get("go_no_go_decision") or "").upper()
        predicted_positive = predicted_decision in {"GO", "REVIEW"}

        orders = ((feedback_snapshot.get("sales") or {}).get("orders") or {}) if isinstance((feedback_snapshot.get("sales") or {}).get("orders"), dict) else {}
        reviews = feedback_snapshot.get("reviews") if isinstance(feedback_snapshot.get("reviews"), dict) else {}
        profit = feedback_snapshot.get("profit") if isinstance(feedback_snapshot.get("profit"), dict) else {}
        units = int(orders.get("units") or 0)
        avg_rating = float(reviews.get("avg_rating") or 0.0)
        gross_profit_total = float(profit.get("gross_profit_total") or 0.0)
        total_amount = float(adoption.get("total_amount") or 0.0)
        actual_roi_percent = round((gross_profit_total / total_amount) * 100, 4) if total_amount > 0 else 0.0
        actual_positive = units >= 20 or (actual_roi_percent > 0 and avg_rating >= 4.0)
        matched = predicted_positive == actual_positive
        point_date = str(task_payload.get("completed_at") or adoption.get("executed_at") or adoption.get("adopted_at") or "").split("T", 1)[0]
        return {
            "date": point_date,
            "task_id": task_payload.get("task_id"),
            "query": task_payload.get("query"),
            "predicted_decision": predicted_decision,
            "predicted_positive": predicted_positive,
            "actual_positive": actual_positive,
            "matched": matched,
            "accuracy": 1.0 if matched else 0.0,
            "metrics": {
                "units": units,
                "avg_rating": avg_rating,
                "gross_profit_total": gross_profit_total,
                "actual_roi_percent": actual_roi_percent,
            },
        }

    async def get_accuracy_trend(self, *, limit: int = 100) -> dict[str, Any]:
        tasks, _ = await self.repo.list_tasks(limit=limit, offset=0)
        points: list[dict[str, Any]] = []
        for task in tasks:
            serialized = self._serialize_task(task)
            point = self._compute_accuracy_point(serialized)
            if point is not None and point.get("date"):
                points.append(point)

        points.sort(key=lambda item: (item.get("date") or "", item.get("task_id") or ""))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for point in points:
            grouped.setdefault(point["date"], []).append(point)

        trend = []
        running_total = 0
        running_correct = 0
        for date in sorted(grouped.keys()):
            day_points = grouped[date]
            day_total = len(day_points)
            day_correct = sum(1 for item in day_points if item.get("matched"))
            running_total += day_total
            running_correct += day_correct
            trend.append(
                {
                    "date": date,
                    "total": day_total,
                    "correct": day_correct,
                    "accuracy": round(day_correct / day_total, 4) if day_total else 0.0,
                    "cumulative_accuracy": round(running_correct / running_total, 4) if running_total else 0.0,
                }
            )

        accuracy_value = round(sum(1 for item in points if item.get("matched")) / len(points), 4) if points else 0.0
        set_selection_accuracy_metric(self.tenant_id, accuracy_value)
        return {
            "total_tasks": len(points),
            "correct_tasks": sum(1 for item in points if item.get("matched")),
            "accuracy": accuracy_value,
            "trend": trend,
            "points": points,
        }

    def _serialize_task(self, task: Any) -> dict[str, Any]:
        config = task.config or {}
        result_payload = config.get("execution_result") if isinstance(config, dict) else None
        go_no_go, go_no_go_decision = self._extract_go_no_go(result_payload or {})
        decision_output = self._extract_decision_output(result_payload)
        data_source_governance = (
            decision_output.get("data_source_governance")
            if isinstance(decision_output, dict) and isinstance(decision_output.get("data_source_governance"), dict)
            else None
        )
        signal_governance_summary = self._build_signal_governance_summary(decision_output)

        payload = {
            "task_id": str(task.id),
            "session_id": str(task.id),
            "tenant_id": (config.get("tenant_id") if isinstance(config, dict) else None),
            "query": task.title,
            "category": task.target_category,
            "target_market": task.target_market,
            "investment_budget": task.budget_max,
            "status": task.status.value if task.status else "pending",
            "phase": self._normalize_phase(task.status, result_payload),
            "priority": task.priority.value if task.priority else None,
            "created_by": str(task.created_by) if getattr(task, "created_by", None) else None,
            "created_by_username": config.get("created_by_username") if isinstance(config, dict) else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result_summary": task.result_summary,
            "error": config.get("error") if isinstance(config, dict) else None,
            "status_reason": config.get("status_reason") if isinstance(config, dict) else None,
            "status_history": config.get("status_history", []) if isinstance(config, dict) else [],
            "approval": config.get("approval") if isinstance(config, dict) else None,
            "approval_history": config.get("approval_history", []) if isinstance(config, dict) else [],
            "adoption": config.get("adoption") if isinstance(config, dict) else None,
            "rejection": config.get("rejection") if isinstance(config, dict) else None,
            "rejection_history": config.get("rejection_history", []) if isinstance(config, dict) else [],
            "model_feedback": config.get("model_feedback") if isinstance(config, dict) else None,
            "retry_count": config.get("retry_count", 0) if isinstance(config, dict) else 0,
            "max_retries": config.get("max_retries") if isinstance(config, dict) else None,
            "timed_out": config.get("timed_out", False) if isinstance(config, dict) else False,
            "dead_letter": config.get("dead_letter", False) if isinstance(config, dict) else False,
            "dead_letter_reason": config.get("dead_letter_reason") if isinstance(config, dict) else None,
            "go_no_go": go_no_go,
            "go_no_go_decision": go_no_go_decision,
            "decision_output": decision_output,
            "signal_governance_status": (
                signal_governance_summary.get("signal_governance_status")
                if isinstance(signal_governance_summary, dict)
                else None
            ),
            "signal_governance_summary": signal_governance_summary,
            "data_source_governance": data_source_governance,
            "result": result_payload,
            "execution_feedback_snapshot": config.get("execution_feedback_snapshot") if isinstance(config, dict) else None,
        }
        return mask_sensitive_data(payload)

    async def create_task(
        self,
        payload: dict[str, Any],
        created_by: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        require_permission(
            self.actor,
            build_permission(RESOURCE_SELECTION, ACTION_EXECUTE),
            resource="selection_task",
        )
        created_by_uuid = None
        if created_by:
            try:
                created_by_uuid = UUID(created_by)
            except ValueError:
                created_by_uuid = None

        task = await self.repo.create_task(
            title=payload["query"],
            category=payload.get("category") or "electronics",
            target_market=payload.get("target_market") or "US",
            budget_min=payload.get("investment_budget"),
            budget_max=payload.get("investment_budget"),
            description=f"选品分析: {payload['query']}",
            priority=self._map_priority(payload.get("priority", "normal")),
            config={
                "query": payload["query"],
                "auto_approve": payload.get("auto_approve", False),
                "session_id": None,
                "execution_result": None,
                "error": None,
                "status_reason": "任务已创建",
                "status_history": [],
                "approval": {
                    "status": "pending",
                    "current_stage": "operator_review",
                    "current_stage_order": 1,
                    "flow": self._build_approval_flow(),
                    "approval_count": 0,
                    "submitted_at": _now_iso(),
                },
                "approval_history": [],
                "tenant_id": tenant_id or self.tenant_id,
                "created_by_username": self.actor.get("username") or None,
                "request_id": get_request_id(),
                "trace_id": get_trace_id(),
            },
            created_by=created_by_uuid,
            tenant_id=tenant_id,
        )
        await self.repo.update_task_status(task.id, TaskStatus.PENDING, result_summary="任务已创建")
        task.config = task.config or {}
        task.config["session_id"] = str(task.id)
        await self.session.commit()
        await self.session.refresh(task)
        record_selection_created(tenant_id or self.tenant_id)
        return self._serialize_task(task)

    async def list_tasks(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        status_enum = None
        if status:
            try:
                status_enum = TaskStatus(status)
            except ValueError:
                status_enum = None

        tasks, total = await self.repo.list_tasks(status=status_enum, limit=limit, offset=offset)
        return {
            "total": total,
            "tasks": [self._serialize_task(task) for task in tasks],
        }

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        try:
            task = await self.repo.get_task(UUID(task_id))
        except ValueError:
            return None
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_READ)
        return self._serialize_task(task)

    async def get_task_result(self, task_id: str) -> dict[str, Any] | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        similar_history_cases = await self._load_similar_history_cases(task)
        review_cases = await self._load_similar_review_cases(task)
        historical_performance = await self._load_historical_performance(task)
        return {
            "task_id": task["task_id"],
            "query": task["query"],
            "status": task["status"],
            "result": task["result"],
            "result_summary": task["result_summary"],
            "go_no_go": task["go_no_go"],
            "go_no_go_decision": task["go_no_go_decision"],
            "decision_output": task.get("decision_output"),
            "signal_governance_status": task.get("signal_governance_status"),
            "signal_governance_summary": task.get("signal_governance_summary"),
            "data_source_governance": task.get("data_source_governance"),
            "completed_at": task["completed_at"],
            "similar_history_cases": similar_history_cases,
            "review_cases": review_cases,
            "historical_performance": historical_performance,
        }

    async def cancel_task(self, task_id: str) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None

        self._require_task_access(task, action=ACTION_MANAGE)

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise ValueError(f"任务已结束，无法取消: {task.status.value}")

        await self.repo.update_task_status(
            task_uuid,
            TaskStatus.CANCELLED,
            result_summary="用户取消",
            phase="cancelled",
            reason="用户取消",
        )
        config = task.config or {}
        config["error"] = None
        config["status_reason"] = "用户取消"
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        return self._serialize_task(task)

    async def pause_task(self, task_id: str, *, reason: str = "人工暂停") -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)
        if task.status != TaskStatus.RUNNING:
            raise ValueError(f"仅运行中的任务可暂停，当前状态: {task.status.value}")
        await self.repo.update_task_status(
            task_uuid,
            TaskStatus.PAUSED,
            result_summary="任务已暂停",
            phase="paused",
            reason=reason,
        )
        config = task.config or {}
        config["status_reason"] = reason
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        add_audit_log(
            action="selection.task.pause",
            actor=self.actor,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"reason": reason},
        )
        return self._serialize_task(task)

    async def resume_task(self, task_id: str) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)
        if task.status != TaskStatus.PAUSED:
            raise ValueError(f"仅暂停的任务可恢复，当前状态: {task.status.value}")
        await self.repo.update_task_status(
            task_uuid,
            TaskStatus.RUNNING,
            result_summary="任务已恢复",
            phase="data_collection",
            reason="任务已恢复执行",
        )
        config = task.config or {}
        config["status_reason"] = "任务已恢复执行"
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        add_audit_log(
            action="selection.task.resume",
            actor=self.actor,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={},
        )
        return self._serialize_task(task)

    async def add_feedback(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)
        config = task.config or {}
        feedback_entry = self._normalize_feedback(payload)
        feedback_history = list(config.get("feedback_history", [])) if isinstance(config, dict) else []
        feedback_history.append(feedback_entry)
        config["feedback_history"] = feedback_history[-50:]
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        if isinstance(execution_result, dict):
            config["execution_result"] = self._apply_feedback_to_result(execution_result, feedback_entry)
        config["status_reason"] = "已录入客户反馈"
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        serialized = self._serialize_task(task)
        serialized["feedback_entry"] = feedback_entry
        return serialized

    async def rescore_task_from_execution_feedback(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None

        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        if not isinstance(execution_result, dict):
            return None

        decision_output = self._extract_decision_output(execution_result) or {}
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
        risks = list(decision_output.get("risks") or []) if isinstance(decision_output.get("risks"), list) else []
        recommendation_reasons = list(decision_output.get("recommendation_reasons") or []) if isinstance(decision_output.get("recommendation_reasons"), list) else []

        sales_7d = int(payload.get("sales_7d") or 0)
        review_rating = payload.get("review_rating")
        review_count = int(payload.get("review_count") or 0)
        gross_profit = float(payload.get("gross_profit") or 0.0)
        margin_rate = payload.get("margin_rate")
        available_inventory = int(payload.get("available_inventory") or 0)
        stockout_risk = bool(payload.get("stockout_risk", False))
        complaint_count = int(payload.get("complaint_count") or 0)
        complaint_reason_breakdown = payload.get("complaint_reason_breakdown") if isinstance(payload.get("complaint_reason_breakdown"), dict) else {}

        try:
            review_rating_value = float(review_rating) if review_rating is not None else None
        except (TypeError, ValueError):
            review_rating_value = None
        try:
            margin_rate_value = float(margin_rate) if margin_rate is not None else None
        except (TypeError, ValueError):
            margin_rate_value = None

        score = 50.0
        score += min(sales_7d, 200) / 10
        score += max(min(gross_profit / 20, 20), -20)
        if review_rating_value is not None:
            score += (review_rating_value - 3.0) * 12
        if margin_rate_value is not None:
            score += (margin_rate_value - 0.2) * 100
        if available_inventory < 10 or stockout_risk:
            score -= 18
        if complaint_count > 0:
            score -= min(20, complaint_count * 6)
        if review_count == 0:
            score -= 5
        score = round(max(0.0, min(100.0, score)), 1)

        decision = "GO" if score >= 70 else ("REVIEW" if score >= 45 else "NO_GO")
        rescore_summary = {
            "score": score,
            "decision": decision,
            "evaluated_at": _now_iso(),
            "inputs": {
                "sales_7d": sales_7d,
                "review_rating": review_rating_value,
                "review_count": review_count,
                "gross_profit": gross_profit,
                "margin_rate": margin_rate_value,
                "available_inventory": available_inventory,
                "stockout_risk": stockout_risk,
                "complaint_count": complaint_count,
                "complaint_reason_breakdown": complaint_reason_breakdown,
                "source": payload.get("source") or "close_loop",
                "notes": payload.get("notes"),
            },
        }

        downstream_feedback = {
            "sales": {"sales_7d": sales_7d},
            "reviews": {"rating": review_rating_value, "count": review_count},
            "profit": {"gross_profit": gross_profit, "margin_rate": margin_rate_value},
            "inventory": {"available_inventory": available_inventory, "stockout_risk": stockout_risk},
            "complaints": {"count": complaint_count, "reason_breakdown": complaint_reason_breakdown},
        }

        if pricing.get("recommended_price") is not None:
            try:
                base_price = float(pricing.get("recommended_price"))
            except (TypeError, ValueError):
                base_price = None
            if base_price is not None:
                if decision == "GO":
                    pricing["recommended_price"] = round(base_price * 1.01, 2)
                elif decision == "NO_GO":
                    pricing["recommended_price"] = round(base_price * 0.95, 2)
                pricing["rescore_adjustment_applied"] = True

        if margin_rate_value is not None:
            profitability["expected_margin"] = round(margin_rate_value * 100, 2)
        profitability["actual_gross_profit"] = round(gross_profit, 2)
        profitability["feedback_sales_7d"] = sales_7d

        risks = [risk for risk in risks if not (isinstance(risk, dict) and risk.get("category") == "execution_feedback")]
        if stockout_risk:
            risks.insert(0, {"name": "执行后库存预警", "category": "execution_feedback", "score": 82})
        if complaint_count > 0:
            risks.insert(0, {"name": "客诉风险上升", "category": "customer_complaint", "score": min(95, 60 + complaint_count * 8), "reason_breakdown": complaint_reason_breakdown})
        elif decision == "NO_GO":
            risks.insert(0, {"name": "执行后经营表现不佳", "category": "execution_feedback", "score": 76})

        recommendation_reasons = [reason for reason in recommendation_reasons if "执行后再评分" not in str(reason)]
        recommendation_reasons.append(f"执行后再评分: {decision} ({score})")

        decision_output["pricing"] = pricing
        decision_output["profitability"] = profitability
        decision_output["risks"] = risks[:8]
        decision_output["recommendation_reasons"] = recommendation_reasons[:8]
        decision_output["decision"] = {
            **(decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}),
            "decision": decision,
            "rescore_score": score,
            "rescore_source": payload.get("source") or "close_loop",
        }
        decision_output["execution_feedback"] = downstream_feedback
        decision_output["rescore_summary"] = rescore_summary
        execution_result["decision_output"] = decision_output
        config["execution_result"] = execution_result
        config["status_reason"] = "已根据执行后销售/评价/利润/库存完成再评分"
        config["feedback_loop_rescored"] = True
        config["feedback_loop_rescore"] = rescore_summary
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        serialized = self._serialize_task(task)
        serialized["rescore_summary"] = rescore_summary
        return serialized

    async def export_feedback_feature_asset(self, task_id: str) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None

        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        if not isinstance(execution_result, dict):
            return None
        decision_output = self._extract_decision_output(execution_result) or {}
        execution_feedback = decision_output.get("execution_feedback") if isinstance(decision_output.get("execution_feedback"), dict) else {}
        rescore_summary = decision_output.get("rescore_summary") if isinstance(decision_output.get("rescore_summary"), dict) else config.get("feedback_loop_rescore") or {}

        sales_7d = int((execution_feedback.get("sales") or {}).get("sales_7d") or 0)
        review_rating = ((execution_feedback.get("reviews") or {}).get("rating"))
        available_inventory = int((execution_feedback.get("inventory") or {}).get("available_inventory") or 0)
        event_payload = {
            "product_id": str(task.id),
            "event_type": "sales",
            "sales": sales_7d,
            "price": (decision_output.get("pricing") or {}).get("recommended_price") or 0,
        }
        engine = FeatureEngine()
        await engine.process_event(event_payload)
        features = await engine.get_features(str(task.id))
        if features is None:
            return None

        result = {
            "task_id": task_id,
            "feature_asset": {
                "asset_type": "feedback_feature_asset",
                "product_id": str(task.id),
                "features": features,
                "evaluation_sample": {
                    "review_rating": review_rating,
                    "available_inventory": available_inventory,
                    "rescore_score": rescore_summary.get("score"),
                    "decision": rescore_summary.get("decision"),
                },
            },
        }
        config["feedback_feature_asset"] = result["feature_asset"]
        config["feedback_feature_asset_ready"] = True
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)
        return result

    async def approve_task(
        self,
        task_id: str,
        action: str,
        reviewer: str | None,
        comment: str | None,
        *,
        stage: str | None = None,
        stage_order: int | None = None,
        notify_channels: list[str] | None = None,
        webhook_url: str | None = None,
    ) -> dict[str, Any] | None:
        require_permission(
            self.actor,
            build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
            resource="selection_task",
        )
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_APPROVE)

        normalized_action = str(action or "approve").strip().lower()
        if normalized_action not in {"submit", "approve", "reject"}:
            raise ValueError(f"无效的审批动作: {action}")

        config = task.config or {}
        approval = config.get("approval") if isinstance(config.get("approval"), dict) else {}
        flow = approval.get("flow") if isinstance(approval.get("flow"), list) else self._build_approval_flow()
        actor_roles = [str(role) for role in (self.actor.get("roles") or [])]
        resolved_index = self._resolve_stage_index(
            flow,
            requested_stage=stage,
            requested_order=stage_order,
            actor_roles=actor_roles,
        )
        stage_item = dict(flow[resolved_index]) if flow else {
            "stage": stage or "operator_review",
            "stage_order": stage_order or 1,
            "display_name": stage or "审批",
            "roles": actor_roles,
            "status": "pending",
        }

        reviewer_name = reviewer or self.actor.get("username") or self.actor.get("user_id") or "api_user"
        now_iso = _now_iso()
        history_item = {
            "action": normalized_action,
            "stage": stage_item.get("stage"),
            "stage_order": stage_item.get("stage_order"),
            "display_name": stage_item.get("display_name"),
            "reviewer": reviewer_name,
            "comment": comment,
            "acted_at": now_iso,
        }
        notification: dict[str, Any] | None = None

        if normalized_action == "submit":
            stage_item["status"] = "pending"
            flow[resolved_index] = stage_item
            approval_status = "pending"
            config["status_reason"] = f"等待{stage_item.get('display_name') or stage_item.get('stage')}"
            if webhook_url and notify_channels:
                deliveries = []
                for channel in notify_channels:
                    deliveries.append(
                        await self._send_approval_notification(
                            channel=str(channel),
                            webhook_url=webhook_url,
                            title=f"选品任务待审批: {task.title}",
                            content=f"任务 {task.title} 已提交至 {stage_item.get('display_name') or stage_item.get('stage')}，请尽快处理。",
                        )
                    )
                notification = {
                    "channels": list(notify_channels),
                    "delivery_count": len(deliveries),
                    "deliveries": deliveries,
                    "webhook_url": webhook_url,
                }
                history_item["notification"] = {
                    "channels": list(notify_channels),
                    "delivery_count": len(deliveries),
                }
        elif normalized_action == "reject":
            stage_item.update(
                {
                    "status": "rejected",
                    "reviewer": reviewer_name,
                    "comment": comment,
                    "reviewed_at": now_iso,
                }
            )
            flow[resolved_index] = stage_item
            approval_status = "rejected"
            config["status_reason"] = f"{stage_item.get('display_name') or stage_item.get('stage')}已拒绝"
        else:
            stage_item.update(
                {
                    "status": "approved",
                    "reviewer": reviewer_name,
                    "comment": comment,
                    "reviewed_at": now_iso,
                }
            )
            flow[resolved_index] = stage_item
            next_stage = None
            for candidate in flow[resolved_index + 1 :]:
                if str(candidate.get("status") or "pending") == "pending":
                    next_stage = candidate
                    break
            if next_stage is None:
                approval_status = "approved"
                config["status_reason"] = "审批链已全部通过"
            else:
                approval_status = "pending"
                config["status_reason"] = f"等待{next_stage.get('display_name') or next_stage.get('stage')}"

        self._append_approval_history(config, history_item)
        approved_count = sum(1 for item in flow if str(item.get("status") or "pending") == "approved")
        current_pending = next((item for item in flow if str(item.get("status") or "pending") == "pending"), None)
        approval.update(
            {
                "action": normalized_action,
                "status": approval_status,
                "reviewer": reviewer_name,
                "comment": comment,
                "reviewed_at": now_iso if normalized_action != "submit" else approval.get("reviewed_at"),
                "flow": flow,
                "approval_count": approved_count,
                "current_stage": current_pending.get("stage") if isinstance(current_pending, dict) else None,
                "current_stage_order": current_pending.get("stage_order") if isinstance(current_pending, dict) else None,
                "final_decision": approval_status if approval_status in {"approved", "rejected"} else None,
            }
        )
        if notification is not None:
            approval["latest_notification"] = notification
        config["approval"] = approval
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)

        response = {
            "task_id": task_id,
            "action": normalized_action,
            "reviewer": reviewer_name,
            "comment": comment,
            "status": approval_status,
            "current_stage": approval.get("current_stage"),
            "current_stage_order": approval.get("current_stage_order"),
            "approval": approval,
            "approval_history": config.get("approval_history", []),
            "message": (
                f"已提交至{stage_item.get('display_name') or stage_item.get('stage')}审批"
                if normalized_action == "submit"
                else ("审批链已全部通过" if approval_status == "approved" else (f"{stage_item.get('display_name') or stage_item.get('stage')}审批通过" if normalized_action == "approve" else f"{stage_item.get('display_name') or stage_item.get('stage')}审批拒绝"))
            ),
        }
        if notification is not None:
            response["notification"] = notification
        return response

    async def adopt_recommendation(
        self,
        task_id: str,
        *,
        quantity: int,
        scm_name: str = "default",
        supplier_code: str | None = None,
        notes: str | None = None,
        submit_to_erp: bool = True,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)

        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        decision_output = self._extract_decision_output(execution_result) or {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        if str(decision_meta.get("decision") or "").upper() not in {"GO", "REVIEW"}:
            raise ValueError("当前任务不满足采纳推荐条件")

        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        recommended_price = pricing.get("recommended_price")
        try:
            recommended_price_value = float(recommended_price) if recommended_price is not None else None
        except (TypeError, ValueError):
            recommended_price_value = None

        supply_chain = decision_output.get("supply_chain") if isinstance(decision_output.get("supply_chain"), dict) else {}
        supplier_hint = supply_chain.get("primary_supplier") or supplier_code

        adoption = {
            "status": "adopted",
            "scm_name": scm_name,
            "supplier_code": supplier_hint,
            "quantity": int(quantity),
            "recommended_price": recommended_price_value,
            "notes": notes,
            "adopted_at": _now_iso(),
            "adopted_by": self.actor.get("username") or self.actor.get("user_id") or "api_user",
        }
        config["adoption"] = adoption
        config["status_reason"] = "已采纳推荐，等待采购执行"
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)

        erp_submission_result: dict[str, Any] | None = None
        if submit_to_erp:
            erp_submission_result = await self._submit_adoption_to_erp(
                task_id=task_id,
                adoption=adoption,
                decision_output=decision_output,
            )
            if erp_submission_result:
                adoption["erp_submission"] = erp_submission_result
                config["adoption"] = adoption
                task.config = config
                await self.session.commit()

        result = self._serialize_task(task)
        result["adoption"] = adoption
        result["message"] = "采纳推荐成功"
        if erp_submission_result:
            result["erp_submission"] = erp_submission_result
        return result

    async def _submit_adoption_to_erp(
        self,
        *,
        task_id: str,
        adoption: dict[str, Any],
        decision_output: dict[str, Any],
    ) -> dict[str, Any] | None:
        from src.core.pms_governance import AuditContext
        from src.models.enums import RecommendationCategory, RecommendationPriority
        from src.services.suggestion_service import SuggestionService

        try:
            audit_ctx = AuditContext.from_actor(
                self.actor,
                tenant_id=str(self.tenant_id) if self.tenant_id else None,
                purpose="adopt_recommendation",
                trace_id=get_trace_id() or f"adopt-{task_id}",
                idempotency_key=f"adopt:{task_id}",
            )

            suggestion_service = SuggestionService(
                self.session,
                tenant_id=str(self.tenant_id) if self.tenant_id else None,
                actor=self.actor,
            )

            suggestion = await suggestion_service.create_suggestion(
                category=RecommendationCategory.SELECTION,
                target_domain="scm",
                title=f"选品采纳-采购建议 (任务{task_id[:8]})",
                description=adoption.get("notes") or f"选品任务{task_id}采纳推荐，建议提交采购",
                priority=RecommendationPriority.HIGH,
                score=adoption.get("recommended_price"),
                payload={
                    "task_id": task_id,
                    "adoption": adoption,
                    "decision_output": decision_output,
                    "quantity": adoption.get("quantity"),
                    "supplier_code": adoption.get("supplier_code"),
                    "recommended_price": adoption.get("recommended_price"),
                    "suggestion_type": "purchase_suggestion",
                },
                audit_context=audit_ctx,
            )

            await suggestion_service.score_suggestion(
                suggestion["id"],
                score=adoption.get("recommended_price") or 50.0,
                audit_context=audit_ctx,
            )

            submit_result = await suggestion_service.submit_suggestion(
                suggestion["id"],
                audit_context=audit_ctx,
            )

            return {
                "suggestion_id": suggestion["id"],
                "suggestion_status": submit_result.get("suggestion_status"),
                "target_domain": "scm",
                "submitted_at": _now_iso(),
            }
        except Exception:
            logger.exception("采纳推荐提交ERP建议池失败: task_id=%s", task_id)
            return {"error": "erp_submission_failed", "task_id": task_id}

    async def reject_recommendation(
        self,
        task_id: str,
        *,
        reason: str,
        feedback_tags: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None

        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)

        normalized_reason = str(reason or "").strip()
        if len(normalized_reason) < 2:
            raise ValueError("拒绝原因不能为空")

        config = task.config or {}
        execution_result = config.get("execution_result") if isinstance(config, dict) else None
        decision_output = self._extract_decision_output(execution_result) or {}
        decision_meta = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}
        if str(decision_meta.get("decision") or "").upper() not in {"GO", "REVIEW"}:
            raise ValueError("当前任务不满足拒绝推荐条件")

        adoption = config.get("adoption") if isinstance(config.get("adoption"), dict) else {}
        if adoption and adoption.get("status") in {"adopted", "executed", "submitted"}:
            raise ValueError("当前任务已采纳推荐，不能再拒绝")

        resolved_tags = [str(tag).strip() for tag in (feedback_tags or []) if str(tag).strip()]
        if not resolved_tags:
            resolved_tags = self._infer_rejection_feedback_tags(normalized_reason)
        resolved_tags = list(dict.fromkeys(resolved_tags))[:8]

        actor_id = self.actor.get("username") or self.actor.get("user_id") or "api_user"
        rejected_at = _now_iso()
        rejection_entry = {
            "status": "rejected",
            "reason": normalized_reason,
            "notes": notes,
            "feedback_tags": resolved_tags,
            "rejected_at": rejected_at,
            "rejected_by": actor_id,
            "source": "user_rejection",
        }
        rejection_history = list(config.get("rejection_history", [])) if isinstance(config, dict) else []
        rejection_history.append(rejection_entry)

        recommendation_reasons = (
            list(decision_output.get("recommendation_reasons") or [])
            if isinstance(decision_output.get("recommendation_reasons"), list)
            else []
        )
        recommendation_reasons = [
            reason_item for reason_item in recommendation_reasons if "用户拒绝原因:" not in str(reason_item)
        ]
        recommendation_reasons.append(f"用户拒绝原因: {normalized_reason}")

        risks = list(decision_output.get("risks") or []) if isinstance(decision_output.get("risks"), list) else []
        risks.insert(0, {"name": "用户拒绝信号", "category": "user_rejection", "score": 100, "reason": normalized_reason})

        decision_output["recommendation_reasons"] = recommendation_reasons[:8]
        decision_output["risks"] = risks[:8]
        decision_output["rejection_feedback"] = {
            "label": "rejected",
            "reason": normalized_reason,
            "notes": notes,
            "tags": resolved_tags,
            "source": "user_rejection",
            "updated_at": rejected_at,
        }
        if isinstance(execution_result, dict):
            execution_result["decision_output"] = decision_output
            config["execution_result"] = execution_result

        config["rejection"] = rejection_entry
        config["rejection_history"] = rejection_history[-20:]
        config["model_feedback"] = {
            "latest_action": "reject",
            "source": "selection_recommendation_rejected",
            "rejection_reason": normalized_reason,
            "feedback_tags": resolved_tags,
            "notes": notes,
            "actor_id": actor_id,
            "updated_at": rejected_at,
        }
        config["status_reason"] = f"已拒绝推荐: {normalized_reason}"
        task.config = config
        await self.session.commit()
        await self.session.refresh(task)

        result = self._serialize_task(task)
        result["rejection"] = rejection_entry
        result["message"] = "已拒绝推荐并记录模型反馈"
        return result

    async def list_dead_letter_tasks(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        tasks, total = await self.repo.list_dead_letter_tasks(limit=limit, offset=offset)
        return {
            "total": total,
            "tasks": [self._serialize_task(task) for task in tasks],
        }

    async def requeue_dead_letter_task(self, task_id: str, reason: str = "人工重试") -> dict[str, Any] | None:
        require_permission(
            self.actor,
            build_permission(RESOURCE_SELECTION, ACTION_MANAGE),
            resource="selection_task",
        )
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        ok = await self.repo.requeue_task(task_uuid, reason, reset_dead_letter=True)
        if not ok:
            return None
        await self.session.commit()
        task = await self.repo.get_task(task_uuid)
        return self._serialize_task(task) if task is not None else None

    async def manual_intervene(self, task_id: str, action: str, comment: str | None = None) -> dict[str, Any] | None:
        require_permission(
            self.actor,
            build_permission(RESOURCE_SELECTION, ACTION_MANAGE),
            resource="selection_task",
        )
        try:
            task_uuid = UUID(task_id)
        except ValueError:
            return None
        task = await self.repo.get_task(task_uuid)
        if task is None:
            return None
        self._require_task_access(task, action=ACTION_MANAGE)

        normalized_action = str(action or "pause_and_review").strip() or "pause_and_review"
        config = task.config or {}
        interventions = list(config.get("manual_interventions", [])) if isinstance(config, dict) else []
        interventions.append(
            {
                "action": normalized_action,
                "comment": comment,
                "operator": self.actor.get("username") or self.actor.get("user_id") or "api_user",
                "tenant_id": self.tenant_id,
                "recorded_at": _now_iso(),
            }
        )
        config["manual_interventions"] = interventions[-20:]
        config["human_in_the_loop"] = {
            "active": True,
            "last_action": normalized_action,
            "last_comment": comment,
            "updated_at": _now_iso(),
        }
        config["status_reason"] = f"人工介入: {normalized_action}"
        task.config = config

        add_audit_log(
            action="selection.task.manual_intervention",
            actor=self.actor,
            target_type="selection_task",
            target_id=str(task.id),
            result="success",
            detail={
                "action": normalized_action,
                "comment": comment,
                "tenant_id": self.tenant_id,
                "task_status": task.status,
            },
        )
        await self.session.commit()
        await self.session.refresh(task)
        serialized = self._serialize_task(task)
        serialized["manual_intervention"] = interventions[-1]
        return serialized

    async def submit_task_for_execution(self, context: SelectionTaskExecutionContext) -> None:
        await self.executor.submit(self.execute_task, context)

    async def execute_task(self, context: SelectionTaskExecutionContext) -> None:
        logger.info(f"开始执行选品工作流: {context.task_id}")

        task_uuid = UUID(context.task_id)
        owns_session = self.session is None
        session = get_async_session_factory()() if owns_session else self.session
        service = (
            SelectionTaskService(
                session,
                executor=self.executor,
                tenant_id=context.tenant_id,
                actor={"tenant_id": context.tenant_id} if context.tenant_id else self.actor,
            )
            if owns_session
            else self
        )

        try:
            task = await service.repo.get_task(task_uuid)
            if task is None:
                logger.warning(f"任务不存在，无法执行: {context.task_id}")
                return
            if task.status in (TaskStatus.CANCELLED, TaskStatus.PAUSED):
                logger.info(f"任务已取消或暂停，跳过执行: {context.task_id}")
                return

            current_config = task.config or {}
            await service.repo.update_task_status(
                task_uuid,
                TaskStatus.RUNNING,
                result_summary="任务执行中",
                phase="data_collection",
                reason="任务执行中",
            )
            running_now = await _safe_count_running_tasks_for_repo(service.repo, context.tenant_id)
            backlog_now = await _safe_count_backlog_tasks_for_repo(service.repo, context.tenant_id)
            update_selection_running_metrics(context.tenant_id, running_now, backlog_now)
            current_config.update({
                "session_id": context.task_id,
                "execution_result": None,
                "error": None,
                "status_reason": "任务执行中",
                "phase": "data_collection",
            })
            task.config = current_config
            await session.commit()

            settings = get_settings().selection_execution
            max_retries = settings.max_retries
            timeout_seconds = settings.task_timeout_seconds
            current_config["max_retries"] = max_retries
            current_config.setdefault("retry_count", 0)
            commercial_rules = None
            if context.tenant_id:
                config_service = ConfigCenterService(session, tenant_id=context.tenant_id)
                commercial_rule_config = await config_service.get_config("selection.commercial.decision_rules")
                if isinstance(commercial_rule_config, dict):
                    commercial_rules = commercial_rule_config.get("value") if isinstance(commercial_rule_config.get("value"), dict) else None
            if commercial_rules:
                current_config["commercial_rules"] = commercial_rules
            task.config = current_config
            await session.commit()

            master = SelectionMaster(
                config={
                    "session_id": context.task_id,
                    "investment_budget": context.investment_budget,
                    "auto_approve_threshold": 85.0 if context.auto_approve else 70.0,
                    "use_langgraph": True,
                    "commercial_rules": commercial_rules,
                }
            )

            workflow_started_at = datetime.now(UTC)
            result = await asyncio.wait_for(
                master.run(
                    {
                        "session_id": context.task_id,
                        "query": context.query,
                        "category": context.category,
                        "target_market": context.target_market,
                        "investment_budget": context.investment_budget,
                        "commercial_rules": commercial_rules,
                    }
                ),
                timeout=timeout_seconds,
            )
            result_payload = service._extract_payload(result)
            go_no_go, go_no_go_decision = service._extract_go_no_go(result_payload)
            summary = result.get("summary") if isinstance(result, dict) else None
            task = await service.repo.get_task(task_uuid)
            if task is None:
                return
            if task.status == TaskStatus.CANCELLED:
                logger.info(f"任务已取消，跳过完成态写回: {context.task_id}")
                return
            config = task.config or {}
            config.update(
                {
                    "session_id": context.task_id,
                    "execution_result": result_payload,
                    "error": None,
                    "status_reason": "执行完成",
                    "phase": "completed",
                    "go_no_go": go_no_go,
                    "go_no_go_decision": go_no_go_decision,
                    "workflow_state": result.get("state_summary") if isinstance(result, dict) else None,
                }
            )
            task.config = config
            await service.repo.update_task_status(
                task_uuid,
                TaskStatus.COMPLETED,
                result_summary=summary or "执行完成",
                phase="completed",
                reason="执行完成",
            )
            AGENT_EXECUTION_DURATION.labels(agent="selection_master").observe(
                max((datetime.now(UTC) - workflow_started_at).total_seconds(), 0.0)
            )
            AGENT_EXECUTIONS_TOTAL.labels(agent="selection_master", status="completed").inc()
            running_now = await _safe_count_running_tasks_for_repo(service.repo, context.tenant_id)
            backlog_now = await _safe_count_backlog_tasks_for_repo(service.repo, context.tenant_id)
            update_selection_running_metrics(context.tenant_id, running_now, backlog_now)
            record_selection_terminal_status(context.tenant_id, "completed")
            await session.commit()
            logger.info(f"选品工作流完成: {context.task_id} | 决策: {go_no_go_decision or go_no_go}")
        except Exception as e:
            task = await service.repo.get_task(task_uuid)
            if task is not None:
                settings = get_settings().selection_execution
                config = task.config or {}
                retry_count = int(config.get("retry_count", 0)) + 1
                timed_out = isinstance(e, (TimeoutError, asyncio.TimeoutError))
                config.update(
                    {
                        "session_id": context.task_id,
                        "error": str(e),
                        "last_error": str(e),
                        "retry_count": retry_count,
                        "max_retries": settings.max_retries,
                        "timed_out": timed_out,
                        "status_reason": "执行超时" if timed_out else "执行失败",
                        "phase": "failed",
                    }
                )
                task.config = config
                AGENT_EXECUTIONS_TOTAL.labels(agent="selection_master", status="failed").inc()
                if retry_count <= settings.max_retries:
                    await service.repo.requeue_task(
                        task_uuid,
                        f"自动重试 {retry_count}/{settings.max_retries}: {str(e)[:200]}",
                    )
                    running_now = await _safe_count_running_tasks_for_repo(service.repo, context.tenant_id)
                    backlog_now = await _safe_count_backlog_tasks_for_repo(service.repo, context.tenant_id)
                    update_selection_running_metrics(context.tenant_id, running_now, backlog_now)
                else:
                    config.update(
                        {
                            "dead_letter": True,
                            "dead_letter_reason": "timeout" if timed_out else "max_retries_exceeded",
                            "dead_lettered_at": _now_iso(),
                        }
                    )
                    task.config = config
                    await service.repo.update_task_status(
                        task_uuid,
                        TaskStatus.FAILED,
                        result_summary=f"进入死信队列: {str(e)[:500]}",
                        phase="failed",
                        reason="进入死信队列",
                    )
                    running_now = await _safe_count_running_tasks_for_repo(service.repo, context.tenant_id)
                    backlog_now = await _safe_count_backlog_tasks_for_repo(service.repo, context.tenant_id)
                    update_selection_running_metrics(context.tenant_id, running_now, backlog_now)
                    record_selection_terminal_status(context.tenant_id, "failed")
                await session.commit()
            logger.error(f"选品工作流失败: {context.task_id} | 错误: {e}")
        finally:
            if owns_session:
                await session.close()
