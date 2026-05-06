from __future__ import annotations

from typing import Any


class TableFormatCatalog:
    def build_status(self) -> dict[str, Any]:
        return {
            "supported_formats": ["jsonl", "parquet-compatible", "iceberg-compatible"],
            "default_offline_format": "parquet-compatible",
            "default_realtime_format": "iceberg-compatible",
            "asset_mapping": {
                "selection_tasks_snapshot": {
                    "current_format": "jsonl",
                    "target_format": "parquet-compatible",
                    "table_name": "selection_tasks_snapshot",
                },
                "data_sync_events_snapshot": {
                    "current_format": "jsonl",
                    "target_format": "parquet-compatible",
                    "table_name": "data_sync_events_snapshot",
                },
                "data_sync_events_stream": {
                    "current_format": "event-stream-sample",
                    "target_format": "iceberg-compatible",
                    "table_name": "data_sync_events_stream",
                },
            },
        }
