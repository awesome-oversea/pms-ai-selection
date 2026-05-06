from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.perf_report_parser import parse_report

ROOT = Path(__file__).resolve().parents[2]
LATEST_ARTIFACT = ROOT / "artifacts" / "perf" / "latest.json"


class SLOStatusService:
    def _run_observability_smoke(self) -> dict[str, Any] | None:
        script_path = ROOT / "scripts" / "observability_smoke_check.py"
        if not script_path.exists():
            return None
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def build_status(self) -> dict[str, Any]:
        latest_run = None
        if LATEST_ARTIFACT.exists():
            latest_run = parse_report(LATEST_ARTIFACT)
        smoke = self._run_observability_smoke() or {}
        return {
            "perf_baseline": {
                "script": "scripts/perf_baseline.py",
                "runner": "scripts/perf_run_sample.py",
                "parser": "scripts/perf_report_parser.py",
                "artifact": str(LATEST_ARTIFACT).replace("\\", "/"),
                "report_format": "json",
                "repeatable": True,
            },
            "sli": {
                "availability": "successful_requests / total_requests",
                "latency_p95": "95th percentile latency in milliseconds",
                "latency_p99": "99th percentile latency in milliseconds",
                "error_rate": "5xx_and_contract_failures / total_requests",
                "recovery_time": "time to recover from dependency failure",
            },
            "slo": {
                "availability": {"target": ">= 99.0%", "window": "30d"},
                "latency_p95": {"target": "<= 800ms", "window": "7d"},
                "latency_p99": {"target": "<= 1500ms", "window": "7d"},
                "error_rate": {"target": "<= 1.0%", "window": "7d"},
                "recovery_time": {"target": "<= 15m", "window": "incident"},
            },
            "capacity_baseline": {
                "single_instance": {
                    "api_rps_recommended": 30,
                    "worker_parallelism_recommended": 4,
                    "llm_route_rps_recommended": 10,
                },
                "scale_out_thresholds": {
                    "api_latency_p95_ms": 800,
                    "error_rate_percent": 1.0,
                    "worker_backlog": 50,
                },
                "recommended_replicas": {"api": 2, "worker": 2},
            },
            "observability_runtime": {
                "local_tooling": smoke.get("local_tooling", {
                    "docker_available": shutil.which("docker") is not None,
                    "kubectl_available": shutil.which("kubectl") is not None,
                }),
                "environment_connected": smoke.get("environment_connected", False),
                "smoke_test_passed": smoke.get("smoke_test_passed", False),
                "blocking_reason": smoke.get("blocking_reason"),
                "remote_targets": smoke.get("remote_targets", {}),
            },
            "recent_run": latest_run,
            "alert_linkage": [
                {"name": "api_latency_p95_high", "condition": "p95 > 800ms", "severity": "warning"},
                {"name": "api_error_rate_high", "condition": "error_rate > 1%", "severity": "critical"},
                {"name": "worker_backlog_high", "condition": "backlog > 50", "severity": "warning"},
            ],
            "incident_response": {
                "notification_channels": ["dingtalk", "email"],
                "recovery_target": "<= 15m",
                "runbook": "docs/runbook_oncall_sla_change.md",
            },
        }
