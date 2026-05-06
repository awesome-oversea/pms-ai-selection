from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.data_lake_catalog import DataLakeCatalog
from src.infrastructure.object_store import LocalObjectStore
from src.models.models import DataSyncEvent, SelectionTask


class DataLakeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.object_store = LocalObjectStore("data/lake")
        self.catalog = DataLakeCatalog()

    def build_catalog(self) -> dict[str, Any]:
        return self.catalog.build_catalog()

    @staticmethod
    def _normalize_iso_prefix(value: str | None) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    def _latest_snapshot_rows(self, asset: str, filename: str) -> tuple[str | None, list[dict[str, Any]]]:
        snapshot_root = self.object_store.root / asset / "snapshots"
        if not snapshot_root.exists():
            return None, []
        snapshot_dirs = sorted([path for path in snapshot_root.iterdir() if path.is_dir()], reverse=True)
        for snapshot_dir in snapshot_dirs:
            rows = self._read_jsonl(snapshot_dir / filename)
            if rows:
                return snapshot_dir.name, rows
        return None, []

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

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace("%", "")
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    def _build_selection_task_metrics_row(self, task: Any, snapshot_date: str) -> dict[str, Any]:
        config = task.config if isinstance(getattr(task, "config", None), dict) else {}
        execution_result = config.get("execution_result") if isinstance(config.get("execution_result"), dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result.get("decision_output"), dict) else {}
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        profitability = decision_output.get("profitability") if isinstance(decision_output.get("profitability"), dict) else {}
        risks = decision_output.get("risks") if isinstance(decision_output.get("risks"), list) else []
        recommendation_reasons = decision_output.get("recommendation_reasons") if isinstance(decision_output.get("recommendation_reasons"), list) else []
        rescore_summary = decision_output.get("rescore_summary") if isinstance(decision_output.get("rescore_summary"), dict) else {}
        decision = decision_output.get("decision") if isinstance(decision_output.get("decision"), dict) else {}

        return {
            "task_id": str(task.id),
            "tenant_id": str(task.tenant_id),
            "query": getattr(task, "title", None),
            "status": self._enum_value(getattr(task, "status", None)),
            "priority": self._enum_value(getattr(task, "priority", None)),
            "category": getattr(task, "target_category", None),
            "target_market": getattr(task, "target_market", None),
            "snapshot_date": snapshot_date,
            "risk_count": len(risks),
            "risk_level": risks[0].get("category") if risks and isinstance(risks[0], dict) else None,
            "recommendation_count": len(recommendation_reasons),
            "recommended_price": self._coerce_number(pricing.get("recommended_price")),
            "roi_year1_percent": self._coerce_number(profitability.get("roi_year1_percent") or profitability.get("expected_roi")),
            "payback_period_months": self._coerce_number(profitability.get("payback_period_months")),
            "expected_margin": self._coerce_number(
                profitability.get("expected_margin") or profitability.get("gross_margin_pct") or getattr(task, "expected_margin", None)
            ),
            "decision": decision.get("decision") if isinstance(decision, dict) else None,
            "rescore_score": self._coerce_number(rescore_summary.get("score")),
            "feedback_feature_asset_ready": bool(config.get("feedback_feature_asset_ready", False)),
            "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
            "completed_at": task.completed_at.isoformat() if getattr(task, "completed_at", None) else None,
        }

    @staticmethod
    def _selection_task_metrics_schema() -> list[dict[str, str]]:
        return [
            {"name": "task_id", "type": "string"},
            {"name": "tenant_id", "type": "string"},
            {"name": "query", "type": "string"},
            {"name": "status", "type": "string"},
            {"name": "priority", "type": "string"},
            {"name": "category", "type": "string"},
            {"name": "target_market", "type": "string"},
            {"name": "snapshot_date", "type": "string"},
            {"name": "risk_count", "type": "integer"},
            {"name": "risk_level", "type": "string"},
            {"name": "recommendation_count", "type": "integer"},
            {"name": "recommended_price", "type": "number"},
            {"name": "roi_year1_percent", "type": "number"},
            {"name": "payback_period_months", "type": "number"},
            {"name": "expected_margin", "type": "number"},
            {"name": "decision", "type": "string"},
            {"name": "rescore_score", "type": "number"},
            {"name": "feedback_feature_asset_ready", "type": "boolean"},
            {"name": "created_at", "type": "datetime"},
            {"name": "completed_at", "type": "datetime"},
        ]

    def _latest_snapshot_artifact_path(self, asset: str, filename: str) -> str | None:
        snapshot_root = self.object_store.root / asset / "snapshots"
        if not snapshot_root.exists():
            return None
        snapshot_files = sorted(snapshot_root.glob(f"*/{filename}"), reverse=True)
        if not snapshot_files:
            return None
        return str(snapshot_files[0]).replace("\\", "/")

    async def export_selection_task_snapshot(self) -> dict[str, Any]:
        snapshot_date = datetime.now(UTC).strftime("%Y%m%d")
        relative_path = f"selection_tasks/snapshots/{snapshot_date}/selection_tasks.jsonl"

        result = await self.session.execute(select(SelectionTask).order_by(SelectionTask.created_at.desc()).limit(200))
        tasks = list(result.scalars().all())

        rows: list[dict[str, Any]] = []
        for task in tasks:
            rows.append(
                {
                    "task_id": str(task.id),
                    "tenant_id": str(task.tenant_id),
                    "title": task.title,
                    "status": task.status.value if task.status else None,
                    "priority": task.priority.value if task.priority else None,
                    "target_market": task.target_market,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "snapshot_date": snapshot_date,
                }
            )

        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        target_path = self.object_store.write_text(relative_path, content)

        return {
            "asset": "selection_tasks_snapshot",
            "asset_type": "offline-snapshot",
            "snapshot_date": snapshot_date,
            "path": target_path,
            "relative_path": relative_path,
            "record_count": len(rows),
            "format": "jsonl",
            "storage": self.object_store.kind(),
            "consumer_paths": ["运营分析", "租户任务统计"],
        }

    async def export_data_sync_events_snapshot(self) -> dict[str, Any]:
        snapshot_date = datetime.now(UTC).strftime("%Y%m%d")
        relative_path = f"data_sync_events/snapshots/{snapshot_date}/data_sync_events.jsonl"

        result = await self.session.execute(select(DataSyncEvent).order_by(DataSyncEvent.created_at.desc()).limit(200))
        events = list(result.scalars().all())

        rows: list[dict[str, Any]] = []
        for event in events:
            rows.append(
                {
                    "event_id": str(event.id),
                    "tenant_id": str(event.tenant_id),
                    "entity_type": event.entity_type,
                    "event_type": event.event_type,
                    "topic": event.topic,
                    "status": event.status,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                    "snapshot_date": snapshot_date,
                }
            )

        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        target_path = self.object_store.write_text(relative_path, content)

        return {
            "asset": "data_sync_events_snapshot",
            "asset_type": "offline-snapshot",
            "snapshot_date": snapshot_date,
            "path": target_path,
            "relative_path": relative_path,
            "record_count": len(rows),
            "format": "jsonl",
            "storage": self.object_store.kind(),
            "consumer_paths": ["事件运营分析", "失败事件复盘"],
        }

    async def export_selection_task_metrics_dataset(self) -> dict[str, Any]:
        snapshot_date = datetime.now(UTC).strftime("%Y%m%d")
        relative_path = f"selection_task_metrics/snapshots/{snapshot_date}/selection_task_metrics.jsonl"
        manifest_relative_path = f"selection_task_metrics/snapshots/{snapshot_date}/selection_task_metrics.manifest.json"

        result = await self.session.execute(select(SelectionTask).order_by(SelectionTask.created_at.desc()).limit(200))
        tasks = list(result.scalars().all())
        rows = [self._build_selection_task_metrics_row(task, snapshot_date) for task in tasks]

        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        target_path = self.object_store.write_text(relative_path, content)

        manifest = {
            "table_name": "selection_task_metrics",
            "table_format": "iceberg-compatible",
            "storage_format": "jsonl",
            "storage_mode": self.object_store.kind(),
            "query_mode": "local-file-scan",
            "snapshot_date": snapshot_date,
            "data_path": target_path,
            "record_count": len(rows),
            "partition_fields": ["snapshot_date", "target_market"],
            "primary_key": "task_id",
            "schema": self._selection_task_metrics_schema(),
            "generated_at": datetime.now(UTC).isoformat(),
            "query_endpoint": "/api/v1/data-lake/lakehouse/selection-task-metrics",
        }
        manifest_path = self.object_store.write_text(manifest_relative_path, json.dumps(manifest, ensure_ascii=False, indent=2))

        return {
            "asset": "selection_task_metrics",
            "asset_type": "offline-metric-dataset",
            "table_format": "iceberg-compatible",
            "snapshot_date": snapshot_date,
            "path": target_path,
            "relative_path": relative_path,
            "manifest_path": manifest_path,
            "manifest_relative_path": manifest_relative_path,
            "record_count": len(rows),
            "storage": self.object_store.kind(),
            "query_mode": "local-file-scan",
        }

    async def build_realtime_sample(self) -> dict[str, Any]:
        result = await self.session.execute(select(DataSyncEvent).order_by(DataSyncEvent.created_at.desc()).limit(20))
        events = list(result.scalars().all())
        return {
            "asset": "data_sync_events_stream",
            "record_count": len(events),
            "sample": [
                {
                    "event_id": str(event.id),
                    "tenant_id": str(event.tenant_id),
                    "entity_type": event.entity_type,
                    "event_type": event.event_type,
                    "topic": event.topic,
                    "status": event.status,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                for event in events[:5]
            ],
        }

    def query_selection_tasks_snapshot(
        self,
        *,
        status: str | None = None,
        target_market: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        snapshot_date, rows = self._latest_snapshot_rows("selection_tasks", "selection_tasks.jsonl")
        normalized_after = self._normalize_iso_prefix(created_after)
        normalized_before = self._normalize_iso_prefix(created_before)
        filtered = []
        for row in rows:
            if status and str(row.get("status") or "") != status:
                continue
            if target_market and str(row.get("target_market") or "") != target_market:
                continue
            created_at = str(row.get("created_at") or "")
            if normalized_after and created_at and created_at < normalized_after:
                continue
            if normalized_before and created_at and created_at > normalized_before:
                continue
            filtered.append(row)
        return {
            "asset": "selection_tasks_snapshot",
            "snapshot_date": snapshot_date,
            "filters": {
                "status": status,
                "target_market": target_market,
                "created_after": created_after,
                "created_before": created_before,
            },
            "total": len(filtered),
            "items": filtered[:limit],
        }

    def query_data_sync_events_snapshot(
        self,
        *,
        entity_type: str | None = None,
        event_type: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        snapshot_date, rows = self._latest_snapshot_rows("data_sync_events", "data_sync_events.jsonl")
        normalized_after = self._normalize_iso_prefix(created_after)
        normalized_before = self._normalize_iso_prefix(created_before)
        filtered = []
        for row in rows:
            if entity_type and str(row.get("entity_type") or "") != entity_type:
                continue
            if event_type and str(row.get("event_type") or "") != event_type:
                continue
            created_at = str(row.get("created_at") or "")
            if normalized_after and created_at and created_at < normalized_after:
                continue
            if normalized_before and created_at and created_at > normalized_before:
                continue
            filtered.append(row)
        return {
            "asset": "data_sync_events_snapshot",
            "snapshot_date": snapshot_date,
            "filters": {
                "entity_type": entity_type,
                "event_type": event_type,
                "created_after": created_after,
                "created_before": created_before,
            },
            "total": len(filtered),
            "items": filtered[:limit],
        }

    def query_selection_task_metrics_dataset(
        self,
        *,
        status: str | None = None,
        target_market: str | None = None,
        decision: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        snapshot_date, rows = self._latest_snapshot_rows("selection_task_metrics", "selection_task_metrics.jsonl")
        normalized_after = self._normalize_iso_prefix(created_after)
        normalized_before = self._normalize_iso_prefix(created_before)
        manifest = None
        if snapshot_date:
            manifest = self._read_json_artifact(
                self.object_store.root / "selection_task_metrics" / "snapshots" / snapshot_date / "selection_task_metrics.manifest.json"
            )

        filtered = []
        for row in rows:
            if status and str(row.get("status") or "") != status:
                continue
            if target_market and str(row.get("target_market") or "") != target_market:
                continue
            if decision and str(row.get("decision") or "") != decision:
                continue
            event_time = str(row.get("completed_at") or row.get("created_at") or "")
            if normalized_after and event_time and event_time < normalized_after:
                continue
            if normalized_before and event_time and event_time > normalized_before:
                continue
            filtered.append(row)

        return {
            "asset": "selection_task_metrics",
            "table_format": "iceberg-compatible",
            "snapshot_date": snapshot_date,
            "manifest": manifest,
            "filters": {
                "status": status,
                "target_market": target_market,
                "decision": decision,
                "created_after": created_after,
                "created_before": created_before,
            },
            "total": len(filtered),
            "items": filtered[:limit],
        }

    @staticmethod
    def _read_json_artifact(path: Path) -> dict[str, Any] | None:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    async def build_status(self) -> dict[str, Any]:
        catalog = self.build_catalog()
        realtime = await self.build_realtime_sample()

        latest_selection_snapshot = self._latest_snapshot_artifact_path("selection_tasks", "selection_tasks.jsonl")
        latest_event_snapshot = self._latest_snapshot_artifact_path("data_sync_events", "data_sync_events.jsonl")
        latest_task_metrics_snapshot = self._latest_snapshot_artifact_path("selection_task_metrics", "selection_task_metrics.jsonl")
        latest_task_metrics_manifest = self._latest_snapshot_artifact_path("selection_task_metrics", "selection_task_metrics.manifest.json")

        quality_rules = [rule.name for rule in __import__("src.services.etl", fromlist=["ETLPipeline"]).ETLPipeline().rules]
        lineage = {
            "selection_task_metrics": {
                "upstream": ["selection_tasks_snapshot", "decision_output"],
                "downstream": ["bi", "dashboard", "evaluation"],
            },
            "data_sync_events_snapshot": {
                "upstream": ["data_sync_events"],
                "downstream": ["operations", "evaluation"],
            },
        }

        layers = {
            "ods": {"assets": ["selection_tasks_snapshot", "data_sync_events_snapshot"], "ready": True},
            "dwd": {"assets": ["selection_task_metrics"], "ready": True},
            "dws": {"assets": ["selection_overview_ads"], "ready": True},
            "ads": {"assets": ["selection_overview_ads", "bi_ready_assets_view"], "ready": True},
        }

        batch_job = self._read_json_artifact(Path("artifacts/data_platform/batch_job_latest.json"))
        stream_job = self._read_json_artifact(Path("artifacts/data_platform/stream_job_latest.json"))
        scheduler_manifest = self._read_json_artifact(Path("artifacts/data_platform/scheduler_manifest.json"))
        kettle_etl_manifest = self._read_json_artifact(Path("artifacts/data_platform/kettle_etl_manifest.json"))
        flink_feature_manifest = self._read_json_artifact(Path("artifacts/data_platform/flink_feature_job_manifest.json"))
        flink_trendwide_manifest = self._read_json_artifact(Path("artifacts/data_platform/flink_trendwide_manifest.json"))
        flink_forum_topic_manifest = self._read_json_artifact(Path("artifacts/data_platform/flink_forum_topic_manifest.json"))
        flink_checkpoint_acceptance = self._read_json_artifact(Path("artifacts/data_platform/flink_checkpoint_acceptance_latest.json"))

        return {
            "offline": {
                "asset_count": len(catalog["offline_assets"]),
                "storage": self.object_store.kind(),
                "latest_snapshot": latest_selection_snapshot,
                "assets": {
                    "selection_tasks_snapshot": latest_selection_snapshot,
                    "data_sync_events_snapshot": latest_event_snapshot,
                    "selection_task_metrics": latest_task_metrics_snapshot,
                },
            },
            "realtime": realtime,
            "catalog": catalog,
            "table_formats": catalog["table_formats"],
            "processing_engines": {
                **catalog["processing_engines"],
                "batch_engine": {
                    **catalog["processing_engines"]["batch_engine"],
                    "latest_run": batch_job,
                    "scheduler_manifest": scheduler_manifest,
                    "kettle_etl_manifest": kettle_etl_manifest,
                },
                "stream_engine": {
                    **catalog["processing_engines"]["stream_engine"],
                    "latest_run": stream_job,
                    "flink_feature_manifest": flink_feature_manifest,
                    "flink_trendwide_manifest": flink_trendwide_manifest,
                    "flink_forum_topic_manifest": flink_forum_topic_manifest,
                    "checkpoint_acceptance": flink_checkpoint_acceptance,
                },
            },
            "downstream_consumers": catalog["downstream_consumers"],
            "pipeline_readiness": {
                "batch_ready": bool(batch_job),
                "stream_ready": bool(stream_job),
                "quality_checks_ready": True,
            },
            "lakehouse": {
                "ods_ready": True,
                "table_format_ready": True,
                "supported_formats": catalog["table_formats"].get("supported_formats", []),
                "default_offline_format": catalog["table_formats"].get("default_offline_format"),
                "target_offline_format": "iceberg-compatible",
                "iceberg_compatible_ready": bool(latest_task_metrics_snapshot and latest_task_metrics_manifest),
                "local_query_ready": bool(latest_task_metrics_snapshot),
                "selection_task_metrics_dataset": latest_task_metrics_snapshot,
                "selection_task_metrics_manifest": latest_task_metrics_manifest,
            },
            "layering": layers,
            "governance": {
                "quality_rules": quality_rules,
                "quality_rule_count": len(quality_rules),
                "field_dictionary_ready": True,
                "field_dictionary_assets": list(catalog.get("field_dictionary", {}).keys()),
                "asset_catalog_ready": True,
                "lineage_ready": True,
                "lineage": lineage,
                "bi_ready_export": True,
            },
            "bi_ready_assets": ["selection_tasks_snapshot", "data_sync_events_snapshot", "selection_task_metrics"],
        }
