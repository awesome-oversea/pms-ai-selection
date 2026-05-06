from __future__ import annotations

from typing import Any


class DataProcessingEngineCatalog:
    def build_status(self) -> dict[str, Any]:
        return {
            "batch_engine": {
                "mode": "spark-compatible",
                "status": "local-smoke-ready",
                "use_cases": ["daily_aggregation", "feature_computation", "offline_export"],
                "runner": "python-batch-job",
                "script": "scripts/run_batch_feature_job.py",
                "artifact": "artifacts/data_platform/batch_job_latest.json",
            },
            "stream_engine": {
                "mode": "flink-compatible",
                "status": "local-smoke-ready",
                "use_cases": ["event_enrichment", "realtime_metrics", "dlq_monitoring"],
                "runner": "python-stream-job",
                "script": "scripts/run_stream_feature_job.py",
                "artifact": "artifacts/data_platform/stream_job_latest.json",
            },
            "orchestration": {
                "batch": "airflow-compatible",
                "event_driven": "prefect-compatible",
            },
        }
