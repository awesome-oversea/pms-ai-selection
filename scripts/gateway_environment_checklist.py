from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.config.settings import OpsProbeSettings
except Exception:  # pragma: no cover - defensive import for standalone script
    OpsProbeSettings = None

ENVIRONMENTS = ["test", "preprod", "prod"]
REQUIRED_STEPS = [
    "apply_gateway_manifest",
    "verify_internal_bff_openapi_routes",
    "verify_key_auth_and_consumer",
    "verify_rate_limit_policy",
    "verify_checksum_and_validation_script",
    "record_rollback_rehearsal",
]
REQUIRED_EVIDENCE = [
    "deploy_log",
    "route_check",
    "rate_limit_check",
    "rollback_record",
    "screenshot_or_recording",
]
DOCKER_PROBE_TIMEOUT_SECONDS = float(os.getenv("OPS_PROBE_DOCKER_TIMEOUT_SECONDS", "5"))


def _get_probe_url(env_name: str, fallback_env_names: tuple[str, ...] = ()) -> str | None:
    for name in (env_name, *fallback_env_names):
        value = os.getenv(name)
        if value:
            return value
    if OpsProbeSettings is None:
        return None
    settings = OpsProbeSettings()
    mapping = {
        "OPS_PROBE_KONG_TEST_URL": settings.kong_test_url,
        "OPS_PROBE_KONG_PREPROD_URL": settings.kong_preprod_url,
        "OPS_PROBE_KONG_PROD_URL": settings.kong_prod_url,
    }
    for name in (env_name, *fallback_env_names):
        value = mapping.get(name)
        if value:
            return value
    return None


def _tool_path(command: str, windows_fallbacks: tuple[str, ...] = ()) -> Path | None:
    resolved = shutil.which(command)
    if resolved is not None:
        return Path(resolved)
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        candidates: list[Path] = []
        if local_app_data:
            candidates.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / f"{command}.exe")
        candidates.extend(Path(path) for path in windows_fallbacks)
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def _tool_exists(command: str, windows_fallbacks: tuple[str, ...] = ()) -> bool:
    return _tool_path(command, windows_fallbacks) is not None


def _windows_reboot_pending() -> bool:
    if os.name != "nt" or winreg is None:
        return False
    pending_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"),
    ]
    for hive, subkey in pending_keys:
        try:
            with winreg.OpenKey(hive, subkey):
                return True
        except FileNotFoundError:
            continue
    return False


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        with contextlib.suppress(Exception):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
    else:
        with contextlib.suppress(Exception):
            os.killpg(process.pid, signal.SIGKILL)

    if process.poll() is None:
        with contextlib.suppress(Exception):
            process.kill()
    with contextlib.suppress(Exception):
        process.wait(timeout=2)


def _run_probe_command(command: list[str], timeout_seconds: float) -> tuple[int, str, str, bool]:
    if os.name == "nt":
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    else:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return process.returncode or 0, stdout or "", stderr or "", False
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=1)
        except Exception:
            stdout, stderr = "", ""
        return process.returncode if process.returncode is not None else 124, stdout or "", stderr or "", True


def _probe_docker_engine(docker_path: Path | None, *, context: str | None = None) -> tuple[bool, str | None]:
    if docker_path is None:
        return False, None
    command = [str(docker_path)]
    if context:
        command.extend(["--context", context])
    command.extend(["info", "--format", "{{json .ServerVersion}}"])
    try:
        returncode, stdout, stderr, timed_out = _run_probe_command(command, DOCKER_PROBE_TIMEOUT_SECONDS)
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, str(exc)
    if timed_out:
        return False, f"docker probe timed out after {DOCKER_PROBE_TIMEOUT_SECONDS:g}s"
    if returncode == 0 and stdout.strip():
        return True, None
    combined = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
    return False, combined or None


def _probe_local_tooling() -> dict:
    docker_path = _tool_path(
        "docker",
        (
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            r"C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe",
        ),
    )
    kubectl_path = _tool_path("kubectl")
    docker_linux_engine_ready, docker_linux_engine_error = _probe_docker_engine(docker_path, context="desktop-linux")
    docker_windows_engine_ready, docker_windows_engine_error = _probe_docker_engine(docker_path, context="desktop-windows")
    docker_engine_ready = docker_linux_engine_ready or docker_windows_engine_ready
    docker_engine_error = docker_linux_engine_error if docker_linux_engine_error else docker_windows_engine_error
    reboot_pending = _windows_reboot_pending()
    preferred_context = "desktop-linux" if docker_linux_engine_ready else ("desktop-windows" if docker_windows_engine_ready else None)
    environment_connected = bool(docker_engine_ready and kubectl_path is not None)
    return {
        "docker_available": docker_path is not None,
        "docker_engine_ready": docker_engine_ready,
        "docker_engine_error": docker_engine_error,
        "docker_linux_engine_ready": docker_linux_engine_ready,
        "docker_linux_engine_error": docker_linux_engine_error,
        "docker_windows_engine_ready": docker_windows_engine_ready,
        "docker_windows_engine_error": docker_windows_engine_error,
        "preferred_context": preferred_context,
        "kubectl_available": kubectl_path is not None,
        "reboot_pending": reboot_pending,
        "environment_connected": environment_connected,
    }


def _probe_remote_urls() -> dict:
    targets = {
        "test": _get_probe_url("OPS_PROBE_KONG_TEST_URL", ("KONG_TEST_URL",)),
        "preprod": _get_probe_url("OPS_PROBE_KONG_PREPROD_URL", ("KONG_PREPROD_URL", "KONG_STAGING_URL")),
        "prod": _get_probe_url("OPS_PROBE_KONG_PROD_URL", ("KONG_PROD_URL",)),
    }
    results: dict[str, dict[str, object]] = {}
    any_connected = False
    any_configured = False
    for env, url in targets.items():
        connected = False
        status_code = None
        error = None
        if url:
            any_configured = True
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
        any_connected = any_connected or connected
        results[env] = {
            "url": url,
            "reachable": connected,
            "status_code": status_code,
            "error": error,
        }
    results["any_connected"] = any_connected
    results["any_configured"] = any_configured
    return results


def _resolve_blocking_reason(local_tooling: dict[str, object], remote_target: dict[str, object]) -> str | None:
    if bool(local_tooling.get("environment_connected", False)) or bool(remote_target.get("reachable", False)):
        return None
    if remote_target.get("url"):
        return "remote_probe_unreachable"
    if not bool(local_tooling.get("docker_available", False)) or not bool(local_tooling.get("kubectl_available", False)):
        return "docker_or_kubectl_missing_and_no_remote_probe"
    if bool(local_tooling.get("reboot_pending", False)):
        return "local_reboot_required_after_feature_enable"
    if bool(local_tooling.get("docker_windows_engine_ready", False)) and not bool(local_tooling.get("docker_linux_engine_ready", False)):
        return "docker_linux_backend_unavailable"
    return "docker_engine_unavailable"


def build_checklist() -> dict:
    tooling = _probe_local_tooling()
    remote = _probe_remote_urls()
    return {
        "gateway_delivery_pack": True,
        "local_tooling": tooling,
        "remote_targets": remote,
        "environments": {
            env: {
                "required_steps": REQUIRED_STEPS,
                "required_evidence": REQUIRED_EVIDENCE,
                "ready_for_handoff": True,
                "environment_connected": bool(remote.get(env, {}).get("reachable", False)),
                "blocking_reason": _resolve_blocking_reason(tooling, remote.get(env, {})),
            }
            for env in ENVIRONMENTS
        },
        "source_files": [
            "k8s/gateway/kong.yml",
            "k8s/gateway/kong-services.yml",
            "k8s/gateway/kong-routes.yml",
            "k8s/gateway/kong-plugins.yml",
            "k8s/gateway/kong-consumers.yml",
            "scripts/validate_gateway_config.py",
        ],
    }


def main() -> int:
    payload = build_checklist()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
