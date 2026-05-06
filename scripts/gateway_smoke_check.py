from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPECTED_SERVICE_HOST = "host.docker.internal"
DEFAULT_EXPECTED_SERVICE_PORT = 18000
HTTP_TIMEOUT_SECONDS = float(os.getenv("OPS_PROBE_HTTP_TIMEOUT_SECONDS", "3"))
LOCAL_ADMIN_STATUS_URL = os.getenv("OPS_PROBE_KONG_LOCAL_ADMIN_STATUS_URL", "http://127.0.0.1:8001/status")
LOCAL_ADMIN_SERVICES_URL = os.getenv("OPS_PROBE_KONG_LOCAL_ADMIN_SERVICES_URL", "http://127.0.0.1:8001/services")
LOCAL_PROXY_ROOT_URL = os.getenv("OPS_PROBE_KONG_LOCAL_PROXY_URL", "http://127.0.0.1:8000/docs")
LOCAL_PROXY_ROUTE_PROBES = [
    ("internal_llm_inference_health", "http://127.0.0.1:8000/api/v1/llm/inference/health"),
    ("bff_auth", "http://127.0.0.1:8000/api/v1/bff/auth/me"),
    ("openapi_docs", "http://127.0.0.1:8000/docs"),
]


def _load_expected_service_target() -> tuple[str, int]:
    services_path = ROOT / "k8s" / "gateway" / "kong-services.yml"
    if services_path.exists():
        try:
            for raw in services_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line.startswith("url:"):
                    continue
                parsed = urlparse(line.split(":", 1)[1].strip())
                if parsed.hostname:
                    return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        except OSError:
            pass

    return DEFAULT_EXPECTED_SERVICE_HOST, DEFAULT_EXPECTED_SERVICE_PORT


EXPECTED_SERVICE_HOST, EXPECTED_SERVICE_PORT = _load_expected_service_target()
EXPECTED_SERVICE_HOST = os.getenv("OPS_PROBE_KONG_EXPECTED_SERVICE_HOST", EXPECTED_SERVICE_HOST)
EXPECTED_SERVICE_PORT = int(os.getenv("OPS_PROBE_KONG_EXPECTED_SERVICE_PORT", str(EXPECTED_SERVICE_PORT)))


def _http_probe(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {
                "url": url,
                "reachable": True,
                "status_code": response.status,
                "body": body,
                "body_excerpt": body[:300],
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return {
            "url": url,
            "reachable": True,
            "status_code": exc.code,
            "body": body,
            "body_excerpt": body[:300],
        }
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "url": url,
            "reachable": False,
            "status_code": None,
            "body": "",
            "body_excerpt": "",
            "error": str(exc),
        }


def _compact_probe(result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in result.items() if key != "body"}


def _build_unreachable_probe(url: str, error: str) -> dict[str, object]:
    return {
        "url": url,
        "reachable": False,
        "status_code": None,
        "body_excerpt": "",
        "error": error,
    }


def _probe_local_gateway_runtime() -> dict[str, object]:
    admin_status = _http_probe(LOCAL_ADMIN_STATUS_URL)
    proxy_status = _http_probe(LOCAL_PROXY_ROOT_URL)
    admin_services = (
        _http_probe(LOCAL_ADMIN_SERVICES_URL)
        if admin_status.get("reachable")
        else _build_unreachable_probe(LOCAL_ADMIN_SERVICES_URL, "local_kong_admin_unreachable")
    )
    runtime_services: list[dict[str, object]] = []
    runtime_config_matches_files = False

    if admin_services.get("reachable") and isinstance(admin_services.get("body"), str):
        try:
            payload = json.loads(str(admin_services.get("body") or ""))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            data = payload.get("data") or []
            runtime_services = [
                {
                    "service_name": str(item.get("name") or ""),
                    "host": str(item.get("host") or ""),
                    "port": int(item.get("port") or 0),
                }
                for item in data
                if isinstance(item, dict)
            ]
            runtime_config_matches_files = bool(runtime_services) and all(
                item["host"] == EXPECTED_SERVICE_HOST and item["port"] == EXPECTED_SERVICE_PORT
                for item in runtime_services
            )

    route_probes: list[dict[str, object]] = []
    route_ready_statuses = {200, 401, 403, 405, 422}
    route_probe_passed = False
    wrong_upstream_detected = False
    if proxy_status.get("reachable"):
        for route_key, url in LOCAL_PROXY_ROUTE_PROBES:
            result = _http_probe(url)
            body_excerpt = str(result.get("body_excerpt") or "")
            route_ready = bool(result.get("reachable")) and int(result.get("status_code") or 0) in route_ready_statuses and "no handler found for uri" not in body_excerpt
            wrong_upstream = "no handler found for uri" in body_excerpt
            route_probe_passed = route_probe_passed or route_ready
            wrong_upstream_detected = wrong_upstream_detected or wrong_upstream
            route_probes.append(
                {
                    "route_key": route_key,
                    **_compact_probe(result),
                    "route_ready": route_ready,
                    "wrong_upstream_detected": wrong_upstream,
                }
            )
    else:
        proxy_error = str(proxy_status.get("error") or "local_kong_proxy_unreachable")
        route_probes = [
            {
                "route_key": route_key,
                **_build_unreachable_probe(url, proxy_error),
                "route_ready": False,
                "wrong_upstream_detected": False,
            }
            for route_key, url in LOCAL_PROXY_ROUTE_PROBES
        ]

    route_probe_reachable = any(bool(item.get("reachable")) for item in route_probes)
    connected = bool(admin_status.get("reachable")) and (bool(proxy_status.get("reachable")) or route_probe_reachable)
    if not bool(admin_status.get("reachable")):
        blocking_reason = "local_kong_runtime_unreachable"
    elif not runtime_config_matches_files:
        blocking_reason = "runtime_service_drift"
    elif wrong_upstream_detected:
        blocking_reason = "business_route_points_to_wrong_upstream"
    elif not route_probe_passed:
        blocking_reason = "business_route_not_ready"
    else:
        blocking_reason = None

    return {
        "connected": connected,
        "expected_service_host": EXPECTED_SERVICE_HOST,
        "expected_service_port": EXPECTED_SERVICE_PORT,
        "admin_status": _compact_probe(admin_status),
        "admin_services": runtime_services,
        "runtime_config_matches_files": runtime_config_matches_files,
        "proxy_status": _compact_probe(proxy_status),
        "route_probes": route_probes,
        "business_proxy_ready": route_probe_passed and runtime_config_matches_files,
        "blocking_reason": blocking_reason,
    }


def main() -> int:
    validate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_gateway_config.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    checklist = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gateway_environment_checklist.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    local_app_data = os.getenv("LOCALAPPDATA")
    kubectl_winget = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "kubectl.exe" if local_app_data else None
    docker_path_candidates = [
        Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"),
        Path(r"C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe"),
    ]
    docker_available = shutil.which("docker") is not None or any(path.exists() for path in docker_path_candidates)
    kubectl_available = shutil.which("kubectl") is not None or (kubectl_winget.exists() if kubectl_winget is not None else False)

    payload = {
        "gateway_validation_exit_code": validate.returncode,
        "gateway_validation_ok": validate.returncode == 0 and "gateway_config_validation=ok" in validate.stdout,
        "checklist_exit_code": checklist.returncode,
        "checklist_ready": checklist.returncode == 0,
        "local_tooling": {
            "docker_available": docker_available,
            "kubectl_available": kubectl_available,
        },
        "environment_connected": False,
        "smoke_test_passed": False,
        "artifacts": {
            "validation_script": "scripts/validate_gateway_config.py",
            "checklist_script": "scripts/gateway_environment_checklist.py",
            "gateway_dir": "k8s/gateway",
        },
        "local_runtime": _probe_local_gateway_runtime(),
    }

    if checklist.returncode == 0:
        payload["checklist"] = json.loads(checklist.stdout)
        remote_targets = payload["checklist"].get("remote_targets", {})
        remote_connected = bool(remote_targets.get("any_connected", False))
        payload["environment_connected"] = payload["environment_connected"] or remote_connected
        payload["remote_targets"] = remote_targets

    payload["smoke_test_passed"] = (
        payload["gateway_validation_ok"]
        and payload["checklist_ready"]
        and payload["environment_connected"]
    )
    if not payload["environment_connected"]:
        remote_targets = payload.get("remote_targets", {})
        checklist_tooling = (payload.get("checklist") or {}).get("local_tooling", {})
        environment_blocking = (((payload.get("checklist") or {}).get("environments") or {}).get("test") or {}).get("blocking_reason")
        if remote_targets.get("any_configured", False):
            payload["blocking_reason"] = "remote_probe_unreachable"
        else:
            payload["blocking_reason"] = environment_blocking or (
            "docker_or_kubectl_missing_and_no_remote_probe"
            if (not checklist_tooling.get("docker_available", False) or not checklist_tooling.get("kubectl_available", False))
            else None
            if checklist_tooling.get("docker_windows_engine_ready", False) or checklist_tooling.get("docker_linux_engine_ready", False)
            else "docker_engine_unavailable"
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["gateway_validation_ok"] and payload["checklist_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
