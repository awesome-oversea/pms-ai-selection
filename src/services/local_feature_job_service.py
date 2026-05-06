from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.metrics import DATA_PLATFORM_JOB_RECORDS
from src.infrastructure.tracing import bind_trace_tags, get_request_id, get_trace_id
from src.services.batch_ads_service import LocalBatchAdsStore
from src.services.local_feedback_loop_service import LocalFeedbackLoopService
from src.workers.data_sync_consumer import DataSyncConsumer


class LocalFeatureJobService:
    def __init__(self, root: Path | None = None, ads_store: LocalBatchAdsStore | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.erp_root = self.root / "artifacts" / "erp_local"
        self.data_platform_root = self.root / "artifacts" / "data_platform"
        self.data_lake_root = self.root / "data" / "lake"
        self.ads_store = ads_store or LocalBatchAdsStore(self.root / "data" / "local_batch_ads.db")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _items(cls, path: Path) -> list[dict[str, Any]]:
        payload = cls._read_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _latest_jsonl_rows(self, asset: str, filename: str) -> list[dict[str, Any]]:
        snapshots = self.data_lake_root / asset / "snapshots"
        if not snapshots.exists():
            return []
        candidates = sorted([path for path in snapshots.iterdir() if path.is_dir()], reverse=True)
        for candidate in candidates:
            rows = self._read_jsonl(candidate / filename)
            if rows:
                return rows
        return []

    def _load_local_erp(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "orders": self._items(self.erp_root / "oms" / "orders.json"),
            "reviews": self._items(self.erp_root / "crm" / "feedback.json"),
            "inventory": self._items(self.erp_root / "wms" / "inventory.json"),
            "quotes": self._items(self.erp_root / "scm" / "quotes.json"),
            "selection_tasks": self._latest_jsonl_rows("selection_tasks", "selection_tasks.jsonl"),
            "data_sync_events": self._latest_jsonl_rows("data_sync_events", "data_sync_events.jsonl"),
        }

    async def run_stream_feature_job(self) -> dict[str, Any]:
        data = self._load_local_erp()
        task_id = self._infer_task_id(data)
        bind_trace_tags(feature_job_type="stream", feature_job_task_id=task_id)
        order_events = [LocalFeedbackLoopService._normalize_order_event(item, task_id=task_id) for item in data["orders"]]
        review_events = [LocalFeedbackLoopService._normalize_review_event(item, task_id=task_id) for item in data["reviews"]]
        passthrough_events = [
            item
            for item in data["data_sync_events"]
            if item.get("event_type") in {"sales", "price", "rank", "review", "order.updated", "review.updated"}
        ]
        all_events = [*order_events, *review_events, *passthrough_events]

        consumer = DataSyncConsumer(topic="pms-agent-event", consumer_group="pms-local-flink-feature-job")
        feature_result = await consumer.consume_feature_events(all_events)
        product_ids = feature_result.get("product_ids") or []
        feature_samples = [
            item.get("features")
            for item in feature_result.get("updated_features", [])[:5]
            if isinstance(item, dict) and isinstance(item.get("features"), dict)
        ]
        payload = {
            "job_type": "stream",
            "engine": "flink-compatible",
            "runner": "python-local",
            "status": "completed",
            "trace_id": get_trace_id(),
            "request_id": get_request_id(),
            "source_assets": ["artifacts/erp_local/oms/orders.json", "artifacts/erp_local/crm/feedback.json", "data/lake/data_sync_events"],
            "events_processed": len(all_events),
            "invalid_events": feature_result.get("skipped", 0),
            "product_ids": product_ids,
            "feature_samples": feature_samples,
            "quality_summary": {
                "schema_valid_events": len(all_events) - int(feature_result.get("skipped", 0) or 0),
                "feature_store_updated": bool(feature_result.get("feature_store_updated")),
                "updated_count": feature_result.get("updated_count", 0),
            },
            "output_assets": ["data_sync_events_stream", "realtime_feature_projection", "selection_feature_store"],
            "executed_at": self._now_iso(),
        }
        self._write_artifact("stream_job_latest.json", payload)
        DATA_PLATFORM_JOB_RECORDS.labels(job_type="stream", asset="events_processed").set(float(len(all_events)))
        return payload

    @staticmethod
    def _infer_task_id(data: dict[str, list[dict[str, Any]]]) -> str:
        for group in ["orders", "reviews", "inventory", "quotes", "selection_tasks"]:
            for item in data.get(group, []):
                value = item.get("task_id") or item.get("product_id") or item.get("sku") or item.get("id")
                if value:
                    return str(value)
        return "local-feature-job"

    @staticmethod
    def _price(item: dict[str, Any]) -> float:
        for key in ["unit_price", "price", "quote_price", "procurement_price"]:
            try:
                value = item.get(key)
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        quantity = float(item.get("quantity") or item.get("units") or 0)
        revenue = float(item.get("revenue") or item.get("sales") or item.get("sales_7d") or 0)
        return round(revenue / quantity, 4) if quantity > 0 else 0.0

    @staticmethod
    def _sentiment(review: dict[str, Any]) -> float:
        rating = review.get("customer_score") or review.get("rating")
        try:
            if rating is not None:
                return max(-1.0, min(1.0, (float(rating) - 3.0) / 2.0))
        except (TypeError, ValueError):
            pass
        text = str(review.get("feedback") or review.get("comment") or review.get("review_text") or "").lower()
        negative = ["refund", "complaint", "broken", "bad", "退货", "投诉", "破损", "差评"]
        positive = ["good", "great", "excellent", "好评", "良好", "满意"]
        if any(word in text for word in negative):
            return -0.6
        if any(word in text for word in positive):
            return 0.6
        return 0.0

    def run_batch_feature_job(self) -> dict[str, Any]:
        data = self._load_local_erp()
        orders = data["orders"]
        reviews = data["reviews"]
        inventory = data["inventory"]
        quotes = data["quotes"]
        task_id = self._infer_task_id(data)
        bind_trace_tags(feature_job_type="batch", feature_job_task_id=task_id)

        units = sum(int(item.get("quantity") or item.get("units") or 0) for item in orders)
        revenue = sum(float(item.get("revenue") or item.get("sales") or item.get("sales_7d") or 0.0) for item in orders)
        order_prices = [self._price(item) for item in orders if self._price(item) > 0]
        quote_prices = [self._price(item) for item in quotes if self._price(item) > 0]
        all_prices = [*order_prices, *quote_prices]
        avg_price = round(statistics.mean(all_prices), 4) if all_prices else 0.0
        price_volatility = round(statistics.pstdev(all_prices), 4) if len(all_prices) > 1 else 0.0
        review_scores = [self._sentiment(item) for item in reviews]
        review_sentiment_score = round(statistics.mean(review_scores), 4) if review_scores else 0.0
        review_count = sum(int(item.get("review_count") or 1) for item in reviews)
        available_inventory = sum(int(item.get("available_quantity") or item.get("available") or 0) for item in inventory)
        safety_stock = sum(int(item.get("safety_stock") or 0) for item in inventory)
        demand_supply_ratio = round(units / max(available_inventory, 1), 4)
        inventory_turnover_days = round(available_inventory / max(units, 1) * 7, 2)
        procurement_cost = round(statistics.mean(quote_prices), 4) if quote_prices else 0.0
        gross_margin_estimate = round((avg_price - procurement_cost) / max(avg_price, 1), 4) if avg_price else 0.0
        supplier_reliability_score = round(min(1.0, len(quotes) / 3 + (0.2 if procurement_cost > 0 else 0)), 4)
        refund_rate = 0.0
        if reviews:
            complaint_reviews = sum(1 for item in reviews if self._sentiment(item) < 0 or "投诉" in str(item.get("feedback") or ""))
            refund_rate = round(complaint_reviews / max(review_count, 1), 4)
        sales_growth_rate_7d = round((units - max(units / 4, 1)) / max(units / 4, 1), 4) if units else 0.0
        stockout_risk_score = round(1.0 - min(1.0, available_inventory / max(safety_stock, 1)), 4) if safety_stock else 0.0
        hot_hit_label = units >= 10 and review_sentiment_score >= 0.4 and gross_margin_estimate >= 0.2

        feature_row = {
            "product_id": task_id,
            "sales_growth_rate_7d": sales_growth_rate_7d,
            "review_sentiment_score": review_sentiment_score,
            "price_volatility": price_volatility,
            "demand_supply_ratio": demand_supply_ratio,
            "gross_margin_estimate": gross_margin_estimate,
            "refund_rate": refund_rate,
            "inventory_turnover_days": inventory_turnover_days,
            "supplier_reliability_score": supplier_reliability_score,
            "stockout_risk_score": stockout_risk_score,
            "sales_7d": units,
            "revenue_7d": round(revenue, 4),
            "avg_price": avg_price,
            "review_count": review_count,
            "available_inventory": available_inventory,
            "hot_hit_label": hot_hit_label,
        }
        payload = {
            "job_type": "batch",
            "engine": "spark-compatible",
            "runner": "python-local",
            "status": "completed",
            "trace_id": get_trace_id(),
            "request_id": get_request_id(),
            "records_processed": len(orders) + len(reviews) + len(inventory) + len(quotes) + len(data["selection_tasks"]),
            "source_assets": ["artifacts/erp_local", "data/lake/selection_tasks"],
            "feature_schema_version": "selection-feature-v2",
            "feature_count": 10,
            "features": [feature_row],
            "aggregates": {
                "task_count": max(len(data["selection_tasks"]), 1),
                "total_units": units,
                "total_revenue": round(revenue, 4),
                "avg_review_sentiment_score": review_sentiment_score,
                "supplier_count": len(quotes),
                "inventory_units": available_inventory,
            },
            "output_assets": ["selection_task_metrics", "feedback_feature_asset", "selection_feature_store", "ads_selection_daily_features", "selection_overview_ads"],
            "executed_at": self._now_iso(),
        }
        self.ads_store.upsert_feature_row(task_id, feature_row, executed_at=payload["executed_at"])
        self.ads_store.upsert_overview(
            {
                "overview_key": "selection_overview_ads",
                "product_id": task_id,
                "task_count": payload["aggregates"]["task_count"],
                "total_units": units,
                "total_revenue": round(revenue, 4),
                "avg_review_sentiment_score": review_sentiment_score,
                "avg_price": avg_price,
                "gross_margin_estimate": gross_margin_estimate,
                "supplier_count": len(quotes),
                "inventory_units": available_inventory,
                "hot_hit_count": 1 if hot_hit_label else 0,
                "updated_at": payload["executed_at"],
            },
            updated_at=payload["executed_at"],
        )
        self._write_artifact("batch_job_latest.json", payload)
        DATA_PLATFORM_JOB_RECORDS.labels(job_type="batch", asset="records_processed").set(float(payload["records_processed"]))
        return payload

    def _write_artifact(self, filename: str, payload: dict[str, Any]) -> None:
        self.data_platform_root.mkdir(parents=True, exist_ok=True)
        (self.data_platform_root / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
