from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.infrastructure.bi_client import BIClient
from src.infrastructure.crm_client import CRMClient
from src.infrastructure.object_store import is_local_artifact_endpoint
from src.infrastructure.oms_client import OMSClient
from src.infrastructure.tracing import get_request_id, get_trace_id
from src.workers.data_sync_consumer import DataSyncConsumer


class LocalFeedbackLoopService:
    def __init__(self, *, topic: str = "pms-agent-event") -> None:
        self.topic = topic

    @staticmethod
    def _default_artifact_root() -> str:
        return Path("artifacts/erp_local").resolve().as_posix()

    @classmethod
    def _build_oms_client(cls, root: str) -> OMSClient:
        return OMSClient(
            api_endpoint=f"file://{root}/oms",
            api_key=None,
            inbound_path="/orders.json",
            outbound_path="/outbound-products.json",
            timeout_seconds=5,
        )

    @classmethod
    def _build_crm_client(cls, root: str) -> CRMClient:
        return CRMClient(
            api_endpoint=f"file://{root}/crm",
            api_key=None,
            inbound_path="/feedback.json",
            outbound_path="/outbound-followups.json",
            timeout_seconds=5,
        )

    @classmethod
    def _build_bi_client(cls, root: str) -> BIClient:
        return BIClient(
            api_endpoint=f"file://{root}/bi",
            api_key=None,
            health_path="/health.json",
            dataset_path="/outbound-datasets.json",
            timeout_seconds=5,
        )

    @staticmethod
    def _normalize_order_event(order: dict[str, Any], *, task_id: str | None = None) -> dict[str, Any]:
        product_id = str(task_id or order.get("task_id") or order.get("product_id") or order.get("id") or order.get("order_id"))
        quantity = int(order.get("quantity") or order.get("units") or order.get("sales") or 0)
        revenue = float(order.get("revenue") or order.get("sales") or order.get("sales_7d") or 0.0)
        unit_price = round(revenue / quantity, 4) if quantity > 0 and revenue > 0 else float(order.get("unit_price") or 0.0)
        return {
            "event_id": f"oms-order-{order.get('order_id') or product_id}",
            "topic": "pms-agent-event",
            "entity_type": "order",
            "event_type": "order.updated",
            "aggregate_id": product_id,
            "payload": {
                "task_id": product_id,
                "product_id": product_id,
                "order_id": order.get("order_id"),
                "units": quantity,
                "unit_price": unit_price,
                "revenue": revenue,
                "asin": order.get("asin"),
            },
        }

    @staticmethod
    def _normalize_review_event(review: dict[str, Any], *, task_id: str | None = None) -> dict[str, Any]:
        product_id = str(task_id or review.get("task_id") or review.get("product_id") or review.get("asin") or review.get("id"))
        review_id = str(review.get("id") or review.get("review_id") or f"review-{product_id}")
        return {
            "event_id": f"crm-review-{review_id}",
            "topic": "pms-agent-event",
            "entity_type": "review",
            "event_type": "review.updated",
            "aggregate_id": review_id,
            "payload": {
                "review_id": review_id,
                "task_id": product_id,
                "product_id": product_id,
                "product_name": review.get("product_name"),
                "asin": review.get("asin"),
                "rating": float(review.get("customer_score") or review.get("rating") or 0.0),
                "review_count": int(review.get("review_count") or 1),
                "feedback": review.get("feedback") or review.get("comment") or review.get("review_text"),
            },
        }

    @staticmethod
    def _build_daily_kpi(*, task_id: str, orders: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> dict[str, Any]:
        units = sum(int(item.get("quantity") or item.get("units") or 0) for item in orders)
        revenue = sum(float(item.get("revenue") or item.get("sales") or item.get("sales_7d") or 0.0) for item in orders)
        ratings = [float(item.get("customer_score") or item.get("rating") or 0.0) for item in reviews if item.get("customer_score") or item.get("rating")]
        avg_rating = round(sum(ratings) / len(ratings), 4) if ratings else 0.0
        actual_roi_percent = round((revenue * 0.28 / max(revenue * 0.72, 1.0)) * 100, 4) if revenue else 0.0
        is_hot_hit = units >= 10 and avg_rating >= 4.2
        today = datetime.now(UTC).date().isoformat()
        row = {
            "task_id": task_id,
            "kpi_date": today,
            "oms_units": units,
            "revenue": round(revenue, 4),
            "crm_avg_rating": avg_rating,
            "crm_review_count": sum(int(item.get("review_count") or 1) for item in reviews),
            "actual_roi_percent": actual_roi_percent,
            "selection_cycle_days": 0.0,
            "is_hot_hit": is_hot_hit,
        }
        return {
            "kpi_date": today,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "local_feedback_loop",
            "summary": {
                "task_count": 1,
                "hit_task_count": 1 if is_hot_hit else 0,
                "爆款命中率": 1.0 if is_hot_hit else 0.0,
                "ROI": actual_roi_percent,
                "选品周期": 0.0,
                "avg_review_rating": avg_rating,
                "total_units": units,
            },
            "rows": [row],
        }

    @staticmethod
    def _build_accuracy_trend(kpi: dict[str, Any]) -> dict[str, Any]:
        row = (kpi.get("rows") or [{}])[0]
        matched = bool(row.get("is_hot_hit"))
        point = {
            "date": row.get("kpi_date") or kpi.get("kpi_date"),
            "task_id": row.get("task_id"),
            "predicted_decision": "GO",
            "actual_positive": matched,
            "matched": matched,
            "accuracy": 1.0 if matched else 0.0,
        }
        return {
            "total_tasks": 1,
            "correct_tasks": 1 if matched else 0,
            "accuracy": point["accuracy"],
            "trend": [{"date": point["date"], "total": 1, "correct": point.get("correct_tasks", 1 if matched else 0), "accuracy": point["accuracy"], "cumulative_accuracy": point["accuracy"]}],
            "points": [point],
        }

    async def run_local_loop(self, *, task_id: str, artifact_root: str | None = None) -> dict[str, Any]:
        root = artifact_root or self._default_artifact_root()
        oms_client = self._build_oms_client(root)
        crm_client = self._build_crm_client(root)
        bi_client = self._build_bi_client(root)
        if not is_local_artifact_endpoint(oms_client.api_endpoint) or not is_local_artifact_endpoint(crm_client.api_endpoint):
            raise ValueError("LocalFeedbackLoopService only supports file:// local artifacts")

        orders = await oms_client.fetch_orders()
        reviews = await crm_client.fetch_customer_feedbacks()
        order_events = [self._normalize_order_event(item, task_id=task_id) for item in orders]
        review_events = [self._normalize_review_event(item, task_id=task_id) for item in reviews]
        all_events = [*order_events, *review_events]

        feature_consumer = DataSyncConsumer(topic=self.topic, consumer_group="pms-local-feedback-feature-loop")
        feature_result = await feature_consumer.consume_feature_events(all_events)
        review_consumer = DataSyncConsumer(topic=self.topic, consumer_group="pms-local-feedback-review-loop")
        review_result = await review_consumer.consume_review_events(review_events, session=None)

        kpi = self._build_daily_kpi(task_id=task_id, orders=orders, reviews=reviews)
        await bi_client.push_dataset({"datasets": [{"dataset_name": "selection_daily_kpis", "source": "local_feedback_loop", "rows": [kpi]}]})
        accuracy = self._build_accuracy_trend(kpi)
        return {
            "task_id": task_id,
            "mode": "local-single-process",
            "trace_id": get_trace_id(),
            "request_id": get_request_id(),
            "event_count": len(all_events),
            "oms": {"orders": len(orders), "events": len(order_events)},
            "crm": {"reviews": len(reviews), "events": len(review_events)},
            "cdc": {"consumed": feature_result.get("consumed", 0) + review_result.get("consumed", 0), "topic": self.topic},
            "feature_update": feature_result,
            "knowledge_update": review_result,
            "bi_kpi": kpi,
            "accuracy_trend": accuracy,
            "closed_loop_ready": bool(feature_result.get("updated_count")) and bool(review_result.get("ingested_count")) and bool(kpi.get("rows")),
        }
