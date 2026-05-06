from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class ReleaseManagementService:
    MAX_GATE_AGE_HOURS = 24

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.release_workflow = self.root / ".github" / "workflows" / "release.yml"
        self.ci_workflow = self.root / ".github" / "workflows" / "ci.yml"
        self.deploy_script = self.root / "scripts" / "release_deploy.py"
        self.rollback_script = self.root / "scripts" / "release_rollback.py"
        self.runbook = self.root / "docs" / "runbook_oncall_sla_change.md"
        self.release_record = self.root / "artifacts" / "release" / "latest_release.json"
        self.gate_record = self.root / "artifacts" / "release" / "latest_gate_check.json"
        self.perf_artifact = self.root / "artifacts" / "perf" / "latest.json"

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _run_script_json(self, relative_script_path: str) -> dict[str, Any] | None:
        script_path = self.root / relative_script_path
        if not script_path.exists():
            return None
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=self.root,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _required_gate_mode(self, env: str) -> str:
        return "smoke" if env == "test" else "all"

    def _gate_is_fresh(self, gate_record: dict[str, Any] | None) -> bool:
        if not gate_record:
            return False
        checked_at = gate_record.get("checked_at")
        if not checked_at:
            return False
        try:
            checked_time = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(UTC) - checked_time <= timedelta(hours=self.MAX_GATE_AGE_HOURS)

    def build_status(self) -> dict[str, Any]:
        release_record = self._read_json(self.release_record)
        gate_record = self._read_json(self.gate_record)
        gateway_smoke = self._read_json(self.root / "artifacts" / "ops" / "kong_deployment_manifest.json") or self._read_json(self.root / "artifacts" / "ops" / "kong_canary_manifest.json") or {}
        gateway_checklist = gateway_smoke.get("checklist", {})
        gateway_envs = gateway_checklist.get("environments", {})
        observability_smoke = self._read_json(self.root / "artifacts" / "ops" / "observability_smoke.json") or {}

        artifacts_ready = all(
            [
                self.release_workflow.exists(),
                self.ci_workflow.exists(),
                self.deploy_script.exists(),
                self.rollback_script.exists(),
                self.runbook.exists(),
            ]
        )
        gateway_gate_ready = bool(gateway_smoke.get("gateway_validation_ok", False)) and bool(gateway_smoke.get("checklist_ready", False))
        observability_gate_ready = bool(observability_smoke.get("observability_smoke", False))
        perf_artifact_ready = self.perf_artifact.exists()
        gateway_environment_connected = bool(gateway_smoke.get("environment_connected", False))
        observability_environment_connected = bool(observability_smoke.get("environment_connected", False))
        latest_release_status = release_record.get("status") if release_record else None
        gate_record_present = gate_record is not None
        gate_status = gate_record.get("status") if gate_record else None
        gate_mode = gate_record.get("mode") if gate_record else None
        gate_fresh = self._gate_is_fresh(gate_record)
        gate_passed = gate_status == "passed" and gate_fresh

        ready_for_deploy = artifacts_ready and gate_passed and gateway_gate_ready and observability_gate_ready and perf_artifact_ready
        ready_for_cutover = ready_for_deploy and gateway_environment_connected and observability_environment_connected
        overall_ready = ready_for_cutover and latest_release_status == "deployed"

        blocking_reasons: list[str] = []
        if not self.release_workflow.exists():
            blocking_reasons.append("release_workflow_missing")
        if not self.ci_workflow.exists():
            blocking_reasons.append("ci_workflow_missing")
        if not self.deploy_script.exists():
            blocking_reasons.append("deploy_script_missing")
        if not self.rollback_script.exists():
            blocking_reasons.append("rollback_script_missing")
        if not self.runbook.exists():
            blocking_reasons.append("runbook_missing")
        if not gate_record_present:
            blocking_reasons.append("release_gate_record_missing")
        elif gate_status != "passed":
            blocking_reasons.append(f"release_gate_status_{gate_status}")
        elif not gate_fresh:
            blocking_reasons.append("release_gate_record_stale")
        if not perf_artifact_ready:
            blocking_reasons.append("perf_artifact_missing")
        if not gateway_gate_ready:
            blocking_reasons.append("gateway_smoke_not_ready")
        if not gateway_environment_connected:
            blocking_reasons.append(f"gateway:{gateway_smoke.get('blocking_reason') or 'environment_not_connected'}")
        if not observability_gate_ready:
            blocking_reasons.append("observability_smoke_not_ready")
        if not observability_environment_connected:
            blocking_reasons.append(f"observability:{observability_smoke.get('blocking_reason') or 'environment_not_connected'}")
        if release_record is None:
            blocking_reasons.append("release_record_missing")
        elif latest_release_status != "deployed":
            blocking_reasons.append(f"latest_release_status_{latest_release_status}")

        environments = {}
        for env, required_gates in {
            "test": ["smoke", "migration-smoke"],
            "preprod": ["all"],
            "prod": ["all", "manual-approval"],
        }.items():
            env_gateway = gateway_envs.get(env, {})
            env_release_selected = bool(release_record and release_record.get("target") == env)
            env_release_status = release_record.get("status") if env_release_selected and release_record else None
            env_gateway_connected = bool(env_gateway.get("environment_connected", False))
            required_gate_mode = self._required_gate_mode(env)
            env_gate_mode_match = gate_mode in {required_gate_mode, "all"}
            env_gate_ready = gate_passed and env_gate_mode_match
            environments[env] = {
                "configured": self.release_workflow.exists(),
                "required_gates": required_gates,
                "required_gate_mode": required_gate_mode,
                "latest_gate_mode": gate_mode,
                "latest_gate_passed": gate_passed,
                "latest_gate_fresh": gate_fresh,
                "latest_gate_mode_match": env_gate_mode_match,
                "gateway_connected": env_gateway_connected,
                "observability_connected": observability_environment_connected,
                "release_applied": env_release_status == "deployed",
                "last_release_status": env_release_status,
                "ready_for_deploy": ready_for_deploy and env_gate_ready,
                "ready_for_cutover": ready_for_deploy and env_gate_ready and env_gateway_connected and observability_environment_connected,
                "blocking_reason": env_gateway.get("blocking_reason") if not env_gateway_connected else (None if env_gate_ready else ("release_gate_record_stale" if gate_status == "passed" and not gate_fresh else f"release_gate_status_{gate_status}" if gate_status != "passed" else f"release_gate_mode_mismatch_required_{required_gate_mode}")),
            }

        return {
            "environments": environments,
            "artifacts": {
                "release_workflow": self._display_path(self.release_workflow),
                "ci_workflow": self._display_path(self.ci_workflow),
                "deploy_script": self._display_path(self.deploy_script),
                "rollback_script": self._display_path(self.rollback_script),
                "runbook": self._display_path(self.runbook),
                "perf_artifact": self._display_path(self.perf_artifact),
                "gate_record": self._display_path(self.gate_record),
            },
            "quality_gates": {
                "gateway_smoke": {
                    "validated": bool(gateway_smoke.get("gateway_validation_ok", False)),
                    "checklist_ready": bool(gateway_smoke.get("checklist_ready", False)),
                    "environment_connected": gateway_environment_connected,
                    "blocking_reason": gateway_smoke.get("blocking_reason"),
                },
                "observability_smoke": {
                    "smoke_declared": bool(observability_smoke.get("observability_smoke", False)),
                    "environment_connected": observability_environment_connected,
                    "smoke_test_passed": bool(observability_smoke.get("smoke_test_passed", False)),
                    "blocking_reason": observability_smoke.get("blocking_reason"),
                },
                "perf_baseline": {
                    "artifact_exists": perf_artifact_ready,
                    "artifact": self._display_path(self.perf_artifact),
                },
                "release_gate": {
                    "record_present": gate_record_present,
                    "status": gate_status,
                    "mode": gate_mode,
                    "fresh": gate_fresh,
                    "passed": gate_passed,
                },
            },
            "delivery_readiness": {
                "ready_for_deploy": ready_for_deploy,
                "ready_for_cutover": ready_for_cutover,
                "overall_ready": overall_ready,
                "release_record_present": release_record is not None,
                "latest_release_status": latest_release_status,
                "gate_record_present": gate_record_present,
                "latest_gate_status": gate_status,
                "latest_gate_mode": gate_mode,
                "blocking_reasons": blocking_reasons,
            },
            "rollback_strategy": {
                "policy": "release-record + scripted rollback",
                "app": "run scripts/release_rollback.py --target <env>",
                "db": "rollback only within compatible alembic window",
                "gateway": "config-first rollback",
            },
            "auditable": {
                "release_record_exists": self.release_record.exists(),
                "record_path": self._display_path(self.release_record),
            },
            "latest_release": release_record,
        }
