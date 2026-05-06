from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "data_platform" / "scheduler_manifest.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scheduler": "airflow-prefect-compatible",
        "runner": "python-local",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": [
            {
                "job_key": "daily_bi_kpi_sync",
                "schedule": "0 2 * * *",
                "engine": "airflow-compatible",
                "entrypoint": "python -m src.workers.bi_kpi_worker",
                "outputs": ["selection_daily_kpis"],
            },
            {
                "job_key": "batch_feature_job",
                "schedule": "0 1 * * *",
                "engine": "prefect-compatible",
                "entrypoint": "python scripts/run_batch_feature_job.py",
                "outputs": ["selection_task_metrics", "feedback_feature_asset"],
            },
            {
                "job_key": "stream_feature_job",
                "schedule": "*/15 * * * *",
                "engine": "prefect-compatible",
                "entrypoint": "python scripts/run_stream_feature_job.py",
                "outputs": ["data_sync_events_stream", "realtime_feature_projection"],
            },
            {
                "job_key": "data_quality_check",
                "schedule": "30 1 * * *",
                "engine": "airflow-compatible",
                "entrypoint": "python scripts/observability_smoke_check.py",
                "outputs": ["metrics_dashboard", "observability_smoke"],
            },
            {
                "job_key": "model_registry_review",
                "schedule": "0 3 * * 1",
                "engine": "airflow-compatible",
                "entrypoint": "POST /api/v1/llm/model-registry/default",
                "outputs": ["llm_model_registry_review"],
            },
        ],
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
