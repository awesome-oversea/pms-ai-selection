from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.services.release_management_service import ReleaseManagementService

ROOT = Path(__file__).resolve().parents[1]


def test_release_management_service_exposes_release_artifacts():
    service = ReleaseManagementService()
    status = service.build_status()
    assert "environments" in status
    assert "rollback_strategy" in status
    assert status["artifacts"]["deploy_script"] == "scripts/release_deploy.py"
    assert status["artifacts"]["gate_record"] == "artifacts/release/latest_gate_check.json"
    assert "release_gate" in status["quality_gates"]
    assert "latest_gate_status" in status["delivery_readiness"]


def test_release_deploy_requires_passed_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    deploy = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'release_deploy.py'), '--target', 'test', '--version', 'v1'], capture_output=True, text=True)
    assert deploy.returncode == 1
    deploy_data = json.loads(deploy.stdout)
    assert deploy_data["status"] == "blocked"
    assert deploy_data["blocking_reason"] == "release_gate_record_missing"


def test_release_deploy_rejects_stale_gate_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gate_dir = tmp_path / 'artifacts' / 'release'
    gate_dir.mkdir(parents=True, exist_ok=True)
    stale_time = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    (gate_dir / 'latest_gate_check.json').write_text(json.dumps({"mode": "all", "status": "passed", "exit_code": 0, "steps": [], "checked_at": stale_time}, ensure_ascii=False), encoding='utf-8')

    deploy = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'release_deploy.py'), '--target', 'test', '--version', 'v1'], capture_output=True, text=True)
    assert deploy.returncode == 1
    deploy_data = json.loads(deploy.stdout)
    assert deploy_data["status"] == "blocked"
    assert deploy_data["blocking_reason"] == "release_gate_record_stale"


def test_release_deploy_and_rollback_scripts_write_release_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gate_dir = tmp_path / 'artifacts' / 'release'
    gate_dir.mkdir(parents=True, exist_ok=True)
    (gate_dir / 'latest_gate_check.json').write_text(json.dumps({"mode": "all", "status": "passed", "exit_code": 0, "steps": [], "checked_at": datetime.now(UTC).isoformat()}, ensure_ascii=False), encoding='utf-8')

    deploy = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'release_deploy.py'), '--target', 'test', '--version', 'v1'], capture_output=True, text=True)
    assert deploy.returncode == 0
    deploy_data = json.loads(deploy.stdout)
    assert deploy_data["status"] == "deployed"
    assert deploy_data["gate_check"]["status"] == "passed"

    rollback = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'release_rollback.py'), '--target', 'test', '--reason', 'smoke_failed'], capture_output=True, text=True)
    assert rollback.returncode == 0
    rollback_data = json.loads(rollback.stdout)
    assert rollback_data["status"] == "rolled_back"
