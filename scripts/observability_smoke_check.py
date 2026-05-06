from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.config.settings import OpsProbeSettings
except Exception:  # pragma: no cover - defensive import for standalone script
    OpsProbeSettings = None


def _get_probe_url(env_name: str, fallback_env_names: tuple[str, ...] = ()) -> str | None:
    for name in (env_name, *fallback_env_names):
        value = os.getenv(name)
        if value:
            return value
    if OpsProbeSettings is None:
        return None
    settings = OpsProbeSettings()
    mapping = {
        "OPS_PROBE_PROMETHEUS_URL": settings.prometheus_url,
        "OPS_PROBE_GRAFANA_URL": settings.grafana_url,
        "OPS_PROBE_ALERTMANAGER_URL": settings.alertmanager_url,
    }
    for name in (env_name, *fallback_env_names):
        value = mapping.get(name)
        if value:
            return value
    return None


DEFAULT_LOCAL_TARGETS = {
    "prometheus": "http://127.0.0.1:9090/-/ready",
    "grafana": "http://127.0.0.1:3300/api/health",
    "alertmanager": "http://127.0.0.1:9093/-/ready",
}


def _probe_url(url: str) -> tuple[bool, int | None, str | None]:
    connected = False
    status_code = None
    error = None
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            status_code = resp.status
            connected = 200 <= resp.status < 500
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        connected = 200 <= exc.code < 500
    except Exception as exc:  # pragma: no cover - network dependent
        error = str(exc)
    return connected, status_code, error


def _probe_remote_observability() -> dict:
    configured_targets = {
        "prometheus": _get_probe_url("OPS_PROBE_PROMETHEUS_URL", ("PROMETHEUS_URL",)),
        "grafana": _get_probe_url("OPS_PROBE_GRAFANA_URL", ("GRAFANA_URL",)),
        "alertmanager": _get_probe_url("OPS_PROBE_ALERTMANAGER_URL", ("ALERTMANAGER_URL",)),
    }
    results: dict[str, dict[str, object]] = {}
    any_connected = False
    any_configured = False
    all_required_connected = True
    for name, configured_url in configured_targets.items():
        url = configured_url
        auto_detected = False
        if not url:
            fallback_url = DEFAULT_LOCAL_TARGETS[name]
            fallback_connected, fallback_status_code, fallback_error = _probe_url(fallback_url)
            if fallback_connected:
                url = fallback_url
                auto_detected = True
                connected = fallback_connected
                status_code = fallback_status_code
                error = fallback_error
            else:
                connected = False
                status_code = None
                error = None
        else:
            connected, status_code, error = _probe_url(url)

        if url:
            any_configured = True
        any_connected = any_connected or connected
        all_required_connected = all_required_connected and connected
        results[name] = {
            "url": url,
            "reachable": connected,
            "status_code": status_code,
            "error": error,
            "auto_detected": auto_detected,
        }
    results["any_connected"] = any_connected
    results["any_configured"] = any_configured
    results["all_required_connected"] = all_required_connected
    return results


def build_payload() -> dict:
    docker_available = shutil.which("docker") is not None
    kubectl_available = shutil.which("kubectl") is not None
    prometheus_config_exists = (ROOT / "tests" / "test_prometheus_metrics.py").exists()
    perf_artifact_exists = (ROOT / "artifacts" / "perf" / "latest.json").exists()
    remote_targets = _probe_remote_observability()
    environment_connected = bool(remote_targets.get("all_required_connected", False))
    return {
        "observability_smoke": True,
        "required_endpoints": [
            "/health",
            "/metrics",
            "/api/v1/metrics-dashboard",
            "/api/v1/audit/logs",
            "/api/v1/audit-operations",
        ],
        "required_signals": {
            "metrics": ["selection_tasks_total", "http_request_duration", "llm_requests_total"],
            "audit": ["request_id", "trace_id"],
            "dashboard_layers": ["technical", "business", "commercial"],
        },
        "local_tooling": {
            "docker_available": docker_available,
            "kubectl_available": kubectl_available,
        },
        "remote_targets": remote_targets,
        "supporting_artifacts": {
            "prometheus_test_exists": prometheus_config_exists,
            "perf_artifact_exists": perf_artifact_exists,
        },
        "ready_for_manual_smoke": True,
        "environment_connected": environment_connected,
        "smoke_test_passed": environment_connected and prometheus_config_exists and perf_artifact_exists,
        "blocking_reason": None
        if environment_connected
        else (
            "remote_probe_unreachable"
            if remote_targets.get("any_configured", False)
            else "docker_or_kubectl_missing_and_no_remote_probe"
        ),
    }


def main() -> int:
    print(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
