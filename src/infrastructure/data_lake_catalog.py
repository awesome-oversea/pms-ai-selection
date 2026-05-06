from __future__ import annotations

from typing import Any

from src.infrastructure.stream_processing import DataProcessingEngineCatalog
from src.infrastructure.table_format import TableFormatCatalog


class DataLakeCatalog:
    def __init__(self) -> None:
        self.table_formats = TableFormatCatalog()
        self.processing_engines = DataProcessingEngineCatalog()

    def build_catalog(self) -> dict[str, Any]:
        return {
            "offline_assets": {
                "selection_tasks_snapshot": {
                    "asset_type": "offline-snapshot",
                    "format": "jsonl",
                    "future_format": "parquet",
                    "storage": "local-object-store",
                    "primary_key": "task_id",
                    "event_time": "created_at",
                    "partition_field": "snapshot_date",
                    "path_pattern": "selection_tasks/snapshots/YYYYMMDD/selection_tasks.jsonl",
                    "source_mapping": ["selection_tasks"],
                    "consumer_paths": ["运营分析", "租户任务统计"],
                    "consumption_example": "按 snapshot_date 读取任务快照并统计租户任务量",
                },
                "data_sync_events_snapshot": {
                    "asset_type": "offline-snapshot",
                    "format": "jsonl",
                    "future_format": "parquet",
                    "storage": "local-object-store",
                    "primary_key": "event_id",
                    "event_time": "created_at",
                    "partition_field": "snapshot_date",
                    "path_pattern": "data_sync_events/snapshots/YYYYMMDD/data_sync_events.jsonl",
                    "source_mapping": ["data_sync_events"],
                    "consumer_paths": ["事件运营分析", "失败事件复盘"],
                    "consumption_example": "按 snapshot_date 读取事件快照并统计多实体事件分布",
                },
                "selection_task_metrics": {
                    "asset_type": "offline-metric-dataset",
                    "format": "jsonl",
                    "future_format": "iceberg-compatible",
                    "storage": "local-object-store",
                    "primary_key": "task_id",
                    "event_time": "completed_at",
                    "partition_field": "snapshot_date",
                    "path_pattern": "selection_tasks/snapshots/YYYYMMDD/selection_tasks.jsonl",
                    "source_mapping": ["selection_tasks", "decision_output"],
                    "consumer_paths": ["利润分析", "经营复盘", "趋势回流"],
                    "consumption_example": "按 task_id 读取选品任务指标数据，分析 ROI / margin / risk 分布",
                },
            },
            "realtime_assets": {
                "data_sync_events_stream": {
                    "asset_type": "realtime-stream",
                    "format": "event-stream-sample",
                    "future_format": "iceberg-compatible",
                    "storage": "stream-sample",
                    "primary_key": "event_id",
                    "event_time": "created_at",
                    "partition_field": "topic",
                    "source": "data_sync_events",
                    "source_mapping": ["product.updated", "document.indexed", "inventory.updated"],
                    "consumer_paths": ["实时事件吞吐", "DLQ运营"],
                    "consumption_example": "按 topic / event_type 统计实时事件吞吐与失败率",
                }
            },
            "field_dictionary": {
                "selection_tasks_snapshot": {
                    "task_id": "选品任务ID",
                    "tenant_id": "租户ID",
                    "title": "任务标题",
                    "status": "任务状态",
                    "priority": "优先级",
                    "target_market": "目标市场",
                    "created_at": "任务创建时间",
                },
                "data_sync_events_snapshot": {
                    "event_id": "事件ID",
                    "tenant_id": "租户ID",
                    "entity_type": "实体类型",
                    "event_type": "事件类型",
                    "topic": "事件主题",
                    "status": "事件状态",
                    "created_at": "事件创建时间",
                },
                "data_sync_events_stream": {
                    "event_id": "事件ID",
                    "tenant_id": "租户ID",
                    "entity_type": "实体类型",
                    "event_type": "事件类型",
                    "topic": "事件主题",
                    "status": "事件状态",
                    "created_at": "事件创建时间",
                },
            },
            "table_formats": self.table_formats.build_status(),
            "processing_engines": self.processing_engines.build_status(),
            "downstream_consumers": {
                "bi": ["selection_task_metrics", "selection_overview_ads"],
                "evaluation": ["data_sync_events_snapshot", "data_sync_events_stream", "selection_tasks_dwd"],
                "operations": ["selection_tasks_snapshot", "data_sync_events_stream"],
                "dashboard": ["selection_overview_ads"],
            },
        }
