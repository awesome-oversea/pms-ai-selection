from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.services.kettle_etl_service import KettleETLService


class DataPlatformRuntimeService:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]
        self._artifact_root = self.root / "artifacts" / "data_platform"

    def _run_script_json(self, script_name: str) -> dict[str, Any] | None:
        script_path = self.root / "scripts" / script_name
        if not script_path.exists():
            return None
        result = subprocess.run([sys.executable, str(script_path)], cwd=self.root, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _read_json(self, name: str) -> dict[str, Any] | None:
        path = self._artifact_root / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def build_status(self) -> dict[str, Any]:
        scheduler = self._read_json("scheduler_manifest.json") or {}
        kettle = self._read_json("kettle_etl_manifest.json") or {}
        kettle_job = self._read_json("kettle_etl_job_latest.json") or {}
        flink_feature = self._read_json("flink_feature_job_manifest.json") or {}
        flink_trendwide = self._read_json("flink_trendwide_manifest.json") or {}
        flink_forum = self._read_json("flink_forum_topic_manifest.json") or {}
        flink_checkpoint_acceptance = self._read_json("flink_checkpoint_acceptance_latest.json") or {}
        batch = self._read_json("batch_job_latest.json") or {}
        stream = self._read_json("stream_job_latest.json") or {}
        spark_backfill = self._read_json("spark_backfill_job_latest.json") or {}
        kettle_payload = {
            **kettle,
            "supported_runners": kettle.get("supported_runners") or KettleETLService.supported_runners(),
            "latest_run": kettle_job,
            "latest_run_quality_score": kettle_job.get("latest_run_quality_score") or (kettle_job.get("quality_summary") or {}).get("quality_score"),
            "business_consumable": kettle_job.get("business_consumable") if "business_consumable" in kettle_job else (kettle_job.get("quality_summary") or {}).get("business_consumable"),
            "failure_summary": kettle_job.get("failure_summary") or (kettle_job.get("quality_summary") or {}).get("failure_summary") or [],
        }
        return {
            "scheduler": scheduler,
            "kettle": kettle_payload,
            "flink": {
                "feature_processing": flink_feature,
                "trend_wide_table": flink_trendwide,
                "forum_topic_modeling": flink_forum,
                "checkpoint_acceptance": flink_checkpoint_acceptance,
            },
            "jobs": {
                "kettle_etl": kettle_job,
                "batch": batch,
                "stream": stream,
                "spark_backfill": spark_backfill,
                "flink_checkpoint_acceptance": flink_checkpoint_acceptance,
            },
            "processing_engines": {
                "etl_engine": {
                    "mode": kettle_job.get("etl_engine") or kettle.get("etl_engine"),
                    "runner": kettle_job.get("runner"),
                    "latest_run": kettle_job,
                    "latest_run_quality_score": kettle_job.get("latest_run_quality_score") or (kettle_job.get("quality_summary") or {}).get("quality_score"),
                    "business_consumable": kettle_job.get("business_consumable") if "business_consumable" in kettle_job else (kettle_job.get("quality_summary") or {}).get("business_consumable"),
                    "failure_summary": kettle_job.get("failure_summary") or (kettle_job.get("quality_summary") or {}).get("failure_summary") or [],
                },
                "batch_engine": {"mode": batch.get("engine"), "latest_run": batch},
                "stream_engine": {
                    "mode": stream.get("engine"),
                    "latest_run": stream,
                    "checkpoint_acceptance": flink_checkpoint_acceptance,
                },
            },
            "ray_embedding": {
                "engine": "ray-compatible",
                "status": "ready",
                "target_qps": 5000,
                "runner": "agent-platform ray-compatible",
                "workload": "distributed_embedding",
            },
            "platform_ready": bool(scheduler)
            and bool(kettle)
            and bool(kettle_job)
            and bool(flink_feature)
            and bool(flink_trendwide)
            and bool(flink_forum)
            and bool(batch)
            and bool(stream)
            and bool(spark_backfill),
        }
