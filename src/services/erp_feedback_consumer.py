from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.logging import get_logger
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.kafka import send_message
from src.models.enums import RecommendationExecutionState
from src.services.recommendation_pool_service import RecommendationPoolService
from src.services.suggestion_service import SuggestionService

logger = get_logger(__name__)

ERP_FEEDBACK_TOPICS = [
    "erp.suggestion.approved",
    "erp.suggestion.rejected",
    "erp.suggestion.executing",
    "erp.suggestion.executed",
    "erp.suggestion.execution_failed",
    "erp.suggestion.partially_executed",
    "erp.suggestion.measured",
    "erp.suggestion.closed",
]

STATE_MAPPING: dict[str, RecommendationExecutionState] = {
    "approved": RecommendationExecutionState.ERP_APPROVED,
    "rejected": RecommendationExecutionState.ERP_REJECTED,
    "executing": RecommendationExecutionState.SCM_REVIEWING,
    "executed": RecommendationExecutionState.EXECUTED,
    "execution_failed": RecommendationExecutionState.EXECUTION_FAILED,
    "partially_executed": RecommendationExecutionState.PARTIALLY_EXECUTED,
    "measured": RecommendationExecutionState.CLOSED,
    "closed": RecommendationExecutionState.CLOSED,
    "draft_created": RecommendationExecutionState.ERP_DRAFT_CREATED,
    "pending_review": RecommendationExecutionState.ERP_PENDING_REVIEW,
}


async def handle_erp_feedback_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    处理ERP执行反馈事件。

    事件来源: ERP各域(ADS/FBA/TMS/OMS/SCM/SOM/WMS/CRM等)
    事件格式: {
        "event_type": "erp.suggestion.approved" | "erp.suggestion.rejected" | ...,
        "aggregate_id": "recommendation-uuid",
        "tenant_id": "tenant-uuid",
        "payload": {
            "recommendation_id": "uuid",
            "erp_ref_id": "erp-side-id",
            "execution_state": "approved" | "rejected" | ...,
            "feedback": {...},
            "detail": "optional detail"
        },
        "occurred_at": "ISO8601",
        "source": "erp"
    }
    """
    event_type = event.get("event_type", "")
    payload = event.get("payload", {})
    recommendation_id = payload.get("recommendation_id")
    tenant_id = event.get("tenant_id")

    if not recommendation_id:
        logger.warning("ERP反馈事件缺少recommendation_id: event_type=%s", event_type)
        return {"status": "skipped", "reason": "missing_recommendation_id"}

    execution_state_str = payload.get("execution_state")
    target_state = STATE_MAPPING.get(execution_state_str or "") if execution_state_str else None

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            pool_service = RecommendationPoolService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "source": "erp_feedback"},
            )

            if target_state:
                result = await pool_service.advance_state(
                    recommendation_id,
                    target_state,
                    detail=payload.get("detail"),
                    erp_ref_id=payload.get("erp_ref_id"),
                )
            else:
                result = await pool_service.receive_erp_feedback(
                    recommendation_id,
                    execution_state=execution_state_str,
                    feedback=payload.get("feedback"),
                    erp_ref_id=payload.get("erp_ref_id"),
                )

            suggestion_service = SuggestionService(
                session,
                tenant_id=tenant_id,
                actor={"tenant_id": tenant_id, "source": "erp_feedback"},
            )
            if target_state:
                try:
                    await suggestion_service.sync_from_execution_state(
                        recommendation_id,
                        target_state,
                        detail=payload.get("detail"),
                    )
                except (ValueError, KeyError) as sync_err:
                    logger.warning(
                        "建议状态同步跳过: recommendation_id=%s error=%s",
                        recommendation_id,
                        sync_err,
                    )

            source_domain = payload.get("source_domain") or _infer_domain_from_event(event_type)
            if source_domain:
                try:
                    from src.services.execution_tracking_service import ExecutionTrackingService
                    tracking_service = ExecutionTrackingService(
                        session,
                        tenant_id=tenant_id,
                        actor={"tenant_id": tenant_id, "source": "erp_feedback"},
                    )
                    await tracking_service.track_suggestion_status(
                        recommendation_id,
                        target_domain=source_domain,
                        domain_reference_id=payload.get("erp_ref_id"),
                    )
                except Exception as track_err:
                    logger.warning(
                        "反馈事件触发状态追踪失败: recommendation_id=%s error=%s",
                        recommendation_id,
                        track_err,
                    )

            await session.commit()

            await _publish_acknowledgement(event, result)

            logger.info(
                "ERP反馈已处理: recommendation_id=%s event_type=%s new_state=%s",
                recommendation_id,
                event_type,
                result.get("execution_state"),
            )

            return {"status": "processed", "recommendation_id": recommendation_id, "new_state": result.get("execution_state")}

        except ValueError as e:
            logger.warning("ERP反馈处理失败(建议不存在): recommendation_id=%s error=%s", recommendation_id, e)
            return {"status": "not_found", "recommendation_id": recommendation_id, "error": str(e)}
        except Exception:
            logger.exception("ERP反馈处理异常: recommendation_id=%s", recommendation_id)
            return {"status": "error", "recommendation_id": recommendation_id, "error": "internal_error"}


async def handle_erp_domain_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    处理ERP域事件(数据变更通知)。

    用于触发PMS重新评估/更新建议:
    - 库存变更 → 触发补货建议重新评估
    - 订单变更 → 触发风控重新评估
    - 价格变更 → 触发定价建议重新评估
    """
    event_type = event.get("event_type", "")
    domain = event.get("domain", "")
    tenant_id = event.get("tenant_id")
    payload = event.get("payload", {})

    logger.info(
        "收到ERP域事件: domain=%s event_type=%s tenant_id=%s",
        domain,
        event_type,
        tenant_id,
    )

    trigger_result = await _evaluate_trigger_rules(domain, event_type, payload, tenant_id)

    return {
        "status": "processed",
        "domain": domain,
        "event_type": event_type,
        "triggers": trigger_result,
    }


async def _evaluate_trigger_rules(
    domain: str,
    event_type: str,
    payload: dict[str, Any],
    tenant_id: str | None,
) -> list[dict[str, Any]]:
    triggers = []

    if domain in {"wms", "fba"} and "inventory" in event_type:
        triggers.append({
            "rule": "inventory_change_restock_reval",
            "action": "schedule_restock_revaluation",
            "product_id": payload.get("product_id"),
        })

    if domain == "oms" and "order" in event_type:
        triggers.append({
            "rule": "order_change_risk_reval",
            "action": "schedule_risk_reassessment",
            "order_id": payload.get("order_id"),
        })

    if domain in {"som", "pdm"} and "price" in event_type:
        triggers.append({
            "rule": "price_change_pricing_reval",
            "action": "schedule_pricing_revaluation",
            "product_id": payload.get("product_id"),
        })

    if domain == "ads" and "campaign" in event_type:
        triggers.append({
            "rule": "campaign_change_ad_reval",
            "action": "schedule_ad_optimization_revaluation",
            "campaign_id": payload.get("campaign_id"),
        })

    return triggers


async def _publish_acknowledgement(original_event: dict[str, Any], result: dict[str, Any]) -> None:
    try:
        await send_message(
            topic="pms.recommendation.feedback_ack",
            message={
                "event_type": "pms.feedback_acknowledged",
                "original_event_type": original_event.get("event_type"),
                "recommendation_id": result.get("id"),
                "new_state": result.get("execution_state"),
                "acknowledged_at": datetime.now(UTC).isoformat(),
                "source": "pms",
            },
        )
    except Exception:
        logger.exception("发布反馈确认事件失败")


def _infer_domain_from_event(event_type: str) -> str | None:
    prefix_map = {
        "erp.scm": "scm",
        "erp.wms": "wms",
        "erp.ads": "ads",
        "erp.oms": "oms",
        "erp.som": "som",
        "erp.fba": "fba",
        "erp.crm": "crm",
        "erp.fms": "fms",
        "erp.pdm": "pdm",
    }
    for prefix, domain in prefix_map.items():
        if event_type.startswith(prefix):
            return domain
    if "suggestion" in event_type:
        return "scm"
    return None
