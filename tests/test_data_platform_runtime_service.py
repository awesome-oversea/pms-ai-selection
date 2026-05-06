from __future__ import annotations

import json
from pathlib import Path

from src.services.data_platform_runtime_service import DataPlatformRuntimeService


def test_data_platform_runtime_service_reads_manifests_and_jobs():
    status = DataPlatformRuntimeService().build_status()
    assert status["scheduler"]["scheduler"] == "airflow-prefect-compatible"
    assert status["kettle"]["etl_engine"] == "kettle-compatible"
    assert status["kettle"]["latest_run"]["job_type"] == "kettle_etl"
    assert status["kettle"]["latest_run"]["quality_summary"]["all_required_fields_ready"] is True
    assert status["kettle"]["business_consumable"] is True
    assert status["kettle"]["latest_run_quality_score"] >= 0.8
    assert {item["runner"] for item in status["kettle"]["supported_runners"]} == {"python-local", "ray-compatible"}
    assert status["flink"]["feature_processing"]["job_type"] == "flink_feature_processing"
    assert status["flink"]["trend_wide_table"]["job_type"] == "flink_trend_wide_table"
    assert status["flink"]["forum_topic_modeling"]["job_type"] == "flink_forum_topic_modeling"
    assert status["jobs"]["kettle_etl"]["runner"] in {"python-local", "ray-compatible"}
    assert status["jobs"]["batch"]["status"] == "completed"
    assert status["jobs"]["stream"]["status"] == "completed"
    assert status["jobs"]["spark_backfill"]["job_type"] == "spark_historical_backfill"
    assert status["processing_engines"]["etl_engine"]["mode"] == "pandas-dask-compatible"
    assert status["processing_engines"]["etl_engine"]["runner"] in {"python-local", "ray-compatible"}
    assert status["ray_embedding"]["engine"] == "ray-compatible"
    assert status["platform_ready"] is True


def test_data_platform_runtime_service_reads_flink_checkpoint_acceptance_artifact(tmp_path: Path):
    artifact_root = tmp_path / "artifacts" / "data_platform"
    artifact_root.mkdir(parents=True, exist_ok=True)

    payloads = {
        "scheduler_manifest.json": {"scheduler": "airflow-prefect-compatible"},
        "kettle_etl_manifest.json": {
            "etl_engine": "kettle-compatible",
            "supported_runners": [{"runner": "python-local"}],
        },
        "kettle_etl_job_latest.json": {
            "job_type": "kettle_etl",
            "etl_engine": "pandas-dask-compatible",
            "runner": "python-local",
            "quality_summary": {"all_required_fields_ready": True, "quality_score": 0.91, "business_consumable": True, "failure_summary": []},
            "latest_run_quality_score": 0.91,
            "business_consumable": True,
            "failure_summary": [],
        },
        "flink_feature_job_manifest.json": {"job_type": "flink_feature_processing"},
        "flink_trendwide_manifest.json": {"job_type": "flink_trend_wide_table"},
        "flink_forum_topic_manifest.json": {"job_type": "flink_forum_topic_modeling"},
        "flink_checkpoint_acceptance_latest.json": {
            "accepted": True,
            "job_id": "job-flink-checkpoint-001",
            "input_topic": "pms-flink-checkpoint-test",
        },
        "batch_job_latest.json": {"status": "completed", "engine": "spark-compatible"},
        "stream_job_latest.json": {"status": "completed", "engine": "flink-compatible"},
        "spark_backfill_job_latest.json": {"job_type": "spark_historical_backfill"},
    }
    for filename, payload in payloads.items():
        (artifact_root / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    status = DataPlatformRuntimeService(root=tmp_path).build_status()

    assert status["flink"]["checkpoint_acceptance"]["accepted"] is True
    assert status["jobs"]["flink_checkpoint_acceptance"]["job_id"] == "job-flink-checkpoint-001"
    assert status["processing_engines"]["stream_engine"]["checkpoint_acceptance"]["input_topic"] == "pms-flink-checkpoint-test"
