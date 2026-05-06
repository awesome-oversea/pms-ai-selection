from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config.settings import get_settings


class TritonStatusService:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[2]

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

    def build_status(self) -> dict[str, Any]:
        settings = get_settings().llm
        smoke = self._run_script_json("scripts/triton_smoke_check.py") or {}
        detected_mode = smoke.get("detected_mode") or smoke.get("mode")
        smoke_passed = bool(smoke.get("smoke_test_passed", False) or smoke.get("triton_smoke", False))
        health_ready = bool(smoke.get("healthcheck_ok", False) or smoke_passed)
        rerank_ready = bool(smoke.get("rerank_ok", False) or smoke_passed)
        environment_connected = bool(smoke.get("environment_connected", False))
        local_compatible = bool(smoke.get("local_compatible", False) or detected_mode == "local-compatible")
        deploy_ready = health_ready and rerank_ready
        validation_status = "ready" if deploy_ready else "blocked"
        return {
            "enabled": settings.triton_enabled,
            "endpoint": settings.triton_endpoint,
            "timeout_seconds": settings.triton_timeout_seconds,
            "rerank_model": settings.rerank_model,
            "health_url": f"{settings.triton_endpoint.rstrip('/')}/v2/health/ready",
            "fallback": "local-or-mock-rerank",
            "deployment": {
                "embedding_manifest": "k8s/triton-embedding.yml",
                "rerank_manifest": "k8s/triton-rerank.yml",
                "rollback": "set LLM_TRITON_ENABLED=false",
            },
            "governance": {
                "route_policy": "triton-first",
                "fallback_policy": "local-or-mock-rerank",
                "telemetry": ["latency", "error_rate", "fallback_count"],
            },
            "runtime_probe": smoke,
            "route_status": {
                "environment_connected": environment_connected,
                "health_ready": health_ready,
                "rerank_ready": rerank_ready,
                "blocking_reason": smoke.get("blocking_reason"),
                "mode": detected_mode,
                "local_compatible": local_compatible,
            },
            "validation": {
                "script": "scripts/triton_smoke_check.py",
                "status": validation_status,
                "mode": detected_mode,
            },
            "deploy_ready": deploy_ready,
        }
