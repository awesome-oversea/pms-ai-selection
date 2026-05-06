from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_scheduler_manifest_script_generates_artifact(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "export_scheduler_manifest.py"
    artifact = root / "artifacts" / "data_platform" / "scheduler_manifest.json"

    completed = subprocess.run([sys.executable, str(script)], cwd=root, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    assert payload["scheduler"] == "airflow-prefect-compatible"
    assert payload["status"] == "ready"
    assert any(job["job_key"] == "daily_bi_kpi_sync" for job in payload["jobs"])
    assert any(job["job_key"] == "batch_feature_job" for job in payload["jobs"])
    assert any(job["job_key"] == "stream_feature_job" for job in payload["jobs"])
    assert artifact.exists()
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["jobs"][0]["job_key"] == "daily_bi_kpi_sync"
