from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.services.ha_topology_service import HATopologyService

ROOT = Path(__file__).resolve().parents[1]


def test_ha_topology_service_exposes_multi_env_and_redundancy():
    status = HATopologyService().build_status()
    assert status["environments"]["test"]["configured"] is True
    assert status["environments"]["preprod"]["configured"] is True
    assert status["environments"]["prod"]["configured"] is True
    assert status["postgres_ha"]["replica_count"] >= 2
    assert status["redis_ha"]["sentinel_count"] >= 3
    assert status["gateway_ha"]["split_config"] is True
    assert status["ai_services"]["rag"]["replica_count"] >= 2
    assert status["ai_services"]["llm"]["replica_count"] >= 2
    assert status["overall_status"] == "ready"


def test_check_ha_topology_script_returns_expected_json():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_ha_topology.py")], capture_output=True, text=True)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["checks"]["test_overlay"] is True
    assert payload["checks"]["redis_sentinel"] is True
    assert payload["status"]["validation_script"] == "scripts/check_ha_topology.py"



def test_ha_topology_exposes_backup_and_recovery_readiness():
    service = HATopologyService()
    backup_result = subprocess.run([sys.executable, str(ROOT / "scripts" / "ha_backup_recovery_check.py")], capture_output=True, text=True)
    assert backup_result.returncode == 0
    backup_payload = json.loads(backup_result.stdout)
    assert backup_payload["ok"] is True

    status = service.build_status()
    assert status["backup_recovery"]["backup_ready"] is True
    assert status["backup_recovery"]["recovery_ready"] is True
    assert status["backup_recovery"]["status"] == "ready"
    assert status["backup_recovery"]["backup_snapshot"].endswith("artifacts/backup/latest_backup_status.json")
    assert status["backup_recovery"]["recovery_snapshot"].endswith("artifacts/backup/latest_recovery_status.json")
    assert status["disaster_recovery"]["overlay_ready"] is True
    assert status["disaster_recovery"]["rollback_script_ready"] is True
    assert "artifacts/release/latest_release.json" in status["disaster_recovery"]["evidence_paths"]
