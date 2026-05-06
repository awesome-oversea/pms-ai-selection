from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from shutil import which

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config.settings import get_settings

_COMPOSE_FILE = _PROJECT_ROOT / "docker-compose.local-llm.yml"
_ARTIFACT_PATH = _PROJECT_ROOT / "artifacts" / "ops" / "local_model_stack_acceptance.json"
_DOCKER_CANDIDATES = (
    which("docker"),
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
)
_REQUIRED_EXTERNAL_NETWORKS = ("pms-network",)
_OLLAMA_CONTAINER = "pms-ollama-local"


def _resolve_docker_cli() -> str:
    for candidate in _DOCKER_CANDIDATES:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("docker cli not found")


_DOCKER_CLI = _resolve_docker_cli()


def _docker_args(*args: str) -> list[str]:
    return [_DOCKER_CLI, *args]


def _compose_args(*args: str) -> list[str]:
    return _docker_args("compose", "-f", str(_COMPOSE_FILE), *args)


def _step(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def _run(args: list[str], *, timeout_seconds: float = 900.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    is_docker_compose = len(args) >= 2 and Path(args[0]).name.lower().startswith("docker") and args[1] == "compose"
    if is_docker_compose and ("--build" in args or any(arg in {"build", "bake"} for arg in args[2:])):
        # Keep local compose builds on the classic path; Docker Desktop Buildx/Bake
        # intermittently returns "no such job" in this workspace.
        env.setdefault("COMPOSE_BAKE", "false")
        env.setdefault("DOCKER_BUILDKIT", "0")
        env.setdefault("COMPOSE_DOCKER_CLI_BUILD", "0")
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout_seconds,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _docker_network_exists(name: str) -> bool:
    result = subprocess.run(
        _docker_args("network", "inspect", name),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=30.0,
        check=False,
    )
    return result.returncode == 0


def _ensure_external_networks() -> None:
    for network_name in _REQUIRED_EXTERNAL_NETWORKS:
        if _docker_network_exists(network_name):
            continue
        _step(f"creating missing docker network: {network_name}")
        _run(_docker_args("network", "create", network_name), timeout_seconds=30.0)


def _wait_for_ollama(endpoint: str, *, timeout_seconds: float = 180.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = "ollama not ready"
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{endpoint.rstrip('/')}/api/tags")
                response.raise_for_status()
                payload = response.json()
            if isinstance(payload, dict):
                return payload
            last_error = "unexpected ollama tags payload"
        except Exception as exc:  # pragma: no cover - environment-dependent runtime branch
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"ollama runtime not ready: {last_error}")


def _list_ollama_models(endpoint: str) -> list[str]:
    payload = _wait_for_ollama(endpoint, timeout_seconds=30.0)
    models = payload.get("models") or []
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _pull_ollama_model(model_name: str) -> None:
    _step(f"pulling ollama model: {model_name}")
    _run(_docker_args("exec", _OLLAMA_CONTAINER, "ollama", "pull", model_name), timeout_seconds=5400.0)


def _warmup_ollama(endpoint: str, model_name: str) -> dict:
    payload = {
        "model": model_name,
        "prompt": "请只输出“本地模型在线”六个字，不要添加任何其他内容。",
        "stream": False,
        "options": {"temperature": 0, "num_predict": 16},
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(f"{endpoint.rstrip('/')}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
    return {
        "model": str(data.get("model") or model_name),
        "response_preview": str(data.get("response") or "").strip()[:120],
        "load_duration": data.get("load_duration"),
        "eval_count": data.get("eval_count"),
    }


def _run_cpu_model_cache_init() -> dict:
    _step("preloading cpu rerank/whisper model assets")
    result = _run(_compose_args("run", "--rm", "--build", "cpu-model-cache-init"), timeout_seconds=5400.0)
    output = (result.stdout or "").strip()
    try:
        return json.loads(output or "{}")
    except json.JSONDecodeError as exc:
        start = output.find("{")
        end = output.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(output[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"cpu model cache init returned non-json output: {exc}\n{result.stdout}") from exc


def _write_artifact(payload: dict) -> None:
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the local private AI model stack for PMS.")
    parser.add_argument(
        "--startup-only",
        action="store_true",
        help="Ensure Ollama runtime, required local models, and CPU model caches. Skip extra acceptance warmup details.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = get_settings().llm
    target_ollama_models = [settings.primary_model, settings.multimodal_model]
    artifact = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "compose_file": str(_COMPOSE_FILE),
        "endpoint": settings.ollama_endpoint,
        "mode": "startup-only" if args.startup_only else "acceptance",
        "target_ollama_models": target_ollama_models,
        "cpu_models": {
            "rerank": settings.rerank_model,
            "speech": settings.speech_model,
        },
    }
    try:
        _ensure_external_networks()
        _step("ensuring ollama runtime")
        _run(_compose_args("up", "-d", "--force-recreate", "ollama"), timeout_seconds=900.0)
        _wait_for_ollama(settings.ollama_endpoint)

        current_models = _list_ollama_models(settings.ollama_endpoint)
        artifact["models_before"] = current_models
        for model_name in target_ollama_models:
            if model_name in current_models:
                continue
            _pull_ollama_model(model_name)
            current_models = _list_ollama_models(settings.ollama_endpoint)

        artifact["models_after"] = current_models
        missing_models = [model_name for model_name in target_ollama_models if model_name not in current_models]
        if missing_models:
            raise RuntimeError(f"missing required ollama models after bootstrap: {missing_models}")

        cpu_model_cache = _run_cpu_model_cache_init()
        artifact["cpu_model_cache"] = cpu_model_cache

        if args.startup_only:
            artifact["warmup"] = None
        else:
            artifact["warmup"] = {
                "text": _warmup_ollama(settings.ollama_endpoint, settings.primary_model),
                "multimodal": _warmup_ollama(settings.ollama_endpoint, settings.multimodal_model),
            }

        artifact["accepted"] = bool(cpu_model_cache.get("accepted"))
    except Exception as exc:
        artifact["accepted"] = False
        artifact["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        artifact["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_artifact(artifact)

    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if bool(artifact.get("accepted")) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
