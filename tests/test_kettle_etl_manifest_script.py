from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_kettle_etl_manifest_script_generates_artifact():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "export_kettle_etl_manifest.py"
    artifact = root / "artifacts" / "data_platform" / "kettle_etl_manifest.json"

    completed = subprocess.run([sys.executable, str(script)], cwd=root, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    assert payload["etl_engine"] == "kettle-compatible"
    assert payload["status"] == "ready"
    assert {item["runner"] for item in payload["supported_runners"]} == {"python-local", "ray-compatible"}
    assert any(item["pipeline_key"] == "scm_to_wms_replenishment" for item in payload["pipelines"])
    assert any(item["pipeline_key"] == "oms_to_fms_orders" for item in payload["pipelines"])
    assert artifact.exists()
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert artifact_payload["pipelines"][0]["source_system"] == "scm"
    assert artifact_payload["latest_run_artifact"] == "artifacts/data_platform/kettle_etl_job_latest.json"
