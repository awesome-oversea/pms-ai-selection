from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_REMOTE_MODES = {"in-process", "remote-service"}
LOCAL_ONLY_CONTAINER_HOSTS = {
    "app",
    "postgres",
    "redis",
    "qdrant",
    "opensearch",
    "neo4j",
    "ollama",
    "kafka",
    "kafka-connect",
    "zookeeper",
    "kong-gateway",
}


def _ensure_workspace_root_on_sys_path(root: Path = ROOT) -> None:
    root_text = str(root)
    sys.path[:] = [root_text, *[item for item in sys.path if item != root_text]]


_ensure_workspace_root_on_sys_path()


@dataclass
class RuntimeCheck:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evidence is None:
            payload.pop("evidence")
        return payload


def _format_command(parts: list[str], *, os_name: str) -> str:
    if os_name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _to_wsl_path(path: Path) -> str:
    raw = str(path.resolve())
    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        tail = raw[2:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{tail}"
    return raw.replace("\\", "/")


def _load_settings():
    from src.config.settings import get_settings

    get_settings.cache_clear()
    return get_settings()


def _build_summary(settings: Any) -> dict[str, Any]:
    runtime = settings.local_runtime
    service_mode = settings.service_mode
    return {
        "app": {
            "name": settings.app.name,
            "environment": settings.app.environment,
            "debug": settings.app.debug,
            "api_prefix": settings.app.api_prefix,
        },
        "runtime": {
            "profile": runtime.profile,
            "preferred_os": runtime.preferred_os,
            "scenario_mode": runtime.scenario_mode,
        },
        "dependencies": {
            "database_url": settings.database.url,
            "redis_url": settings.redis.url,
            "qdrant_endpoint": settings.qdrant.url or f"http://{settings.qdrant.host}:{settings.qdrant.port}",
            "search_backend": settings.search.backend,
            "search_enabled": settings.search.enabled,
            "search_endpoint": settings.search.endpoint,
            "ollama_endpoint": settings.llm.ollama_endpoint,
            "dify_enabled": settings.dify.enabled,
            "dify_base_url": settings.dify.base_url,
        },
        "service_modes": {
            "rag_mode": service_mode.rag_mode,
            "llm_mode": service_mode.llm_mode,
            "agent_mode": service_mode.agent_mode,
            "embedding_mode": service_mode.embedding_mode,
            "enable_fallback": service_mode.enable_fallback,
        },
    }


def _venv_python_candidates(root: Path = ROOT) -> list[Path]:
    return [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]


def _resolve_venv_python_path(root: Path = ROOT) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _venv_ready_marker_path(root: Path = ROOT) -> Path:
    return root / ".venv" / ".pms_python_ready"


def _build_compose_command(compose_file: str, *compose_args: str) -> list[str]:
    return ["docker", "compose", "-f", compose_file, *compose_args]


def _resolve_backend_port(settings: Any, *, requested_port: int | None = None, os_name: str = os.name) -> int:
    if requested_port is not None:
        return requested_port

    env_port = os.environ.get("APP_HOST_PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass

    return _default_backend_port(settings, os_name=os_name)


def _build_backend_host_command(
    settings: Any,
    *,
    python_executable: str | None = None,
    host: str = "0.0.0.0",
    port: int | None = None,
    reload: bool = False,
    os_name: str = os.name,
) -> list[str]:
    command = [
        python_executable or sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--host",
        host,
        "--port",
        str(_resolve_backend_port(settings, requested_port=port, os_name=os_name)),
    ]
    if reload:
        command.append("--reload")
    return command


def _build_dependency_startup_steps(
    settings: Any,
    *,
    workspace_root: Path = ROOT,
    os_name: str = os.name,
    python_executable: str | None = None,
    include_ollama: bool = False,
    include_platform: bool = False,
    include_postgres_ha: bool = False,
    include_qdrant_cluster: bool = False,
    include_kafka: bool = False,
) -> list[dict[str, Any]]:
    runtime = settings.local_runtime
    if runtime.scenario_mode != "local-real":
        return []

    steps: list[dict[str, Any]] = [
        {
            "name": "core-data",
            "description": "Start the default PostgreSQL, Redis, and Qdrant services from docker-compose.yml.",
            "command": _build_compose_command("docker-compose.yml", "up", "-d", "postgres", "redis", "qdrant"),
        }
    ]

    if include_kafka:
        steps.append(
            {
                "name": "kafka-cdc",
                "description": "Bootstrap the canonical local Kafka/Zookeeper/Kafka Connect/Debezium init stack using docker-compose.local-kafka.yml.",
                "command": [python_executable or sys.executable, "scripts/bootstrap_local_kafka_debezium.py", "--startup-only"],
            }
        )

    if include_ollama:
        steps.append(
            {
                "name": "llm-local",
                "description": "Bootstrap the optional local private AI stack: Ollama runtime, required Ollama models, and CPU rerank/Whisper caches.",
                "command": [python_executable or sys.executable, "scripts/bootstrap_local_model_stack.py", "--startup-only"],
            }
        )

    if runtime.preferred_os in {"auto", "linux", "linux-wsl"}:
        steps.append(
            {
                "name": "gateway-search",
                "description": "Start Kong, OpenSearch, and Neo4j from docker-compose.wsl-local.yml.",
                "command": _build_compose_command(
                    "docker-compose.wsl-local.yml",
                    "up",
                    "-d",
                    "opensearch",
                    "neo4j",
                    "kong-gateway",
                ),
            }
        )
        if include_platform:
            steps.append(
                {
                    "name": "platform",
                    "description": "Start Redis Sentinel, Keycloak, and Flink from docker-compose.wsl-platform.yml.",
                    "command": _build_compose_command("docker-compose.wsl-platform.yml", "up", "-d"),
                }
            )
        if include_postgres_ha:
            steps.append(
                {
                    "name": "postgres-ha",
                    "description": "Start the optional PostgreSQL HA stack from docker-compose.wsl-postgres-ha.yml.",
                    "command": _build_compose_command("docker-compose.wsl-postgres-ha.yml", "up", "-d"),
                }
            )
        if include_qdrant_cluster:
            steps.append(
                {
                    "name": "qdrant-cluster",
                    "description": "Start the optional Qdrant HA cluster from docker-compose.wsl-qdrant-cluster.yml.",
                    "command": _build_compose_command("docker-compose.wsl-qdrant-cluster.yml", "up", "-d"),
                }
            )

    return steps


def _uses_wsl_local_dependency_stack(settings: Any, *, os_name: str = os.name) -> bool:
    runtime = settings.local_runtime
    if runtime.scenario_mode != "local-real":
        return False
    if os_name == "nt":
        return runtime.preferred_os in {"auto", "linux-wsl"}
    return runtime.preferred_os in {"auto", "linux", "linux-wsl"}


def _default_backend_port(settings: Any, *, os_name: str = os.name) -> int:
    # The WSL local stack exposes Kong on host port 8000. Keep the app directly
    # reachable on host port 18000 so local operators and smoke checks can still
    # bypass Kong when needed.
    return 18000 if _uses_wsl_local_dependency_stack(settings, os_name=os_name) else 8000


def _build_runtime_plan(
    settings: Any,
    *,
    workspace_root: Path = ROOT,
    os_name: str = os.name,
    python_executable: str | None = None,
    include_ollama: bool = False,
    include_platform: bool = False,
    include_postgres_ha: bool = False,
    include_qdrant_cluster: bool = False,
    include_kafka: bool = False,
) -> dict[str, Any]:
    runtime = settings.local_runtime
    python_cmd = python_executable or sys.executable
    backend_parts = _build_backend_host_command(
        settings,
        python_executable=python_cmd,
        host="0.0.0.0",
        reload=False,
        os_name=os_name,
    )

    dependency_steps = _build_dependency_startup_steps(
        settings,
        workspace_root=workspace_root,
        os_name=os_name,
        python_executable=python_cmd,
        include_ollama=include_ollama,
        include_platform=include_platform,
        include_postgres_ha=include_postgres_ha,
        include_qdrant_cluster=include_qdrant_cluster,
        include_kafka=include_kafka,
    )
    mock_parts: list[str] | None = None
    notes: list[str] = []

    if runtime.scenario_mode == "mock":
        mock_parts = [python_cmd, "scripts/mock_services.py", "--all"]
        notes.append("mock mode starts mock_services.py before the backend.")
    elif runtime.scenario_mode == "local-real":
        if runtime.preferred_os not in {"auto", "linux", "linux-wsl"}:
            notes.append("No compose dependency stack is selected for the current LOCAL_RUNTIME_PREFERRED_OS.")
        else:
            notes.append("Dependency startup now uses an explicit Docker Compose sequence: core data first, then gateway/search, then optional platform and HA stacks.")
        notes.append(
            "Backend default startup now runs on the host Python process via scripts/start_local.ps1 or scripts/start_local.sh; Docker Compose only keeps the middleware stack running by default."
        )
        if _uses_wsl_local_dependency_stack(settings, os_name=os_name):
            notes.append(
                f"Kong local proxy binds host port 8000; the backend remains directly reachable on host port {_resolve_backend_port(settings, os_name=os_name)} for smoke checks and local acceptance."
            )
        if include_ollama:
            notes.append(
                f"The local AI stack now boots through scripts/bootstrap_local_model_stack.py: it starts docker-compose.local-llm.yml, ensures the required Ollama models are present, and preloads CPU caches for bge-reranker-base plus Whisper tiny while the host backend continues to use {settings.llm.ollama_endpoint}."
            )
        if include_platform:
            notes.append("docker-compose.wsl-platform.yml is included for Redis Sentinel / Keycloak / Flink.")
        if include_postgres_ha:
            notes.append("docker-compose.wsl-postgres-ha.yml is included; switch DB_URL/DB_READ_URLS to the 15432/15436/15437 endpoints.")
        if include_qdrant_cluster:
            notes.append("docker-compose.wsl-qdrant-cluster.yml is included; switch QDRANT_URL/QDRANT_READ_URLS to the 16333/16433/16533 endpoints.")
        if include_kafka:
            notes.append(
                "Kafka/Zookeeper/Kafka Connect/Debezium init startup is orchestrated by scripts/bootstrap_local_kafka_debezium.py on top of docker-compose.local-kafka.yml; it ensures shared networks first, then keeps existing app containers on kafka:29092 and kafka-connect:8083 through pms-network aliases."
            )
    else:
        notes.append("remote-service mode assumes remote RAG/LLM services are available and healthy.")

    formatted_dependency_steps = [
        {
            "name": step["name"],
            "description": step["description"],
            "command": _format_command(step["command"], os_name=os_name),
        }
        for step in dependency_steps
    ]

    python_setup_command = _format_command([python_cmd, "scripts/install_python_deps.py", "--run-check"], os_name=os_name)

    return {
        "scenario_mode": runtime.scenario_mode,
        "python_setup_command": python_setup_command,
        "bootstrap_command": python_setup_command,
        "dependency_command": formatted_dependency_steps[0]["command"] if formatted_dependency_steps else None,
        "dependency_steps": formatted_dependency_steps,
        "mock_services_command": _format_command(mock_parts, os_name=os_name) if mock_parts else None,
        "backend_command": _format_command(backend_parts, os_name=os_name),
        "frontend_commands": [
            "npm install --prefix frontend",
            "npm run dev --prefix frontend",
        ],
        "notes": notes,
    }


def _validate_runtime_configuration(settings: Any, *, env_path: Path) -> list[RuntimeCheck]:
    runtime = settings.local_runtime
    service_mode = settings.service_mode
    checks: list[RuntimeCheck] = []

    if env_path.exists():
        checks.append(RuntimeCheck("env.file", "pass", f"Using environment file: {env_path.name}"))
    else:
        checks.append(RuntimeCheck("env.file", "warn", "No .env file found; falling back to defaults and process env"))

    if runtime.scenario_mode == "remote-service":
        remote_targets = [
            name
            for name, mode in {
                "rag": service_mode.rag_mode,
                "llm": service_mode.llm_mode,
                "agent": service_mode.agent_mode,
                "embedding": service_mode.embedding_mode,
            }.items()
            if mode == "remote-service"
        ]
        if remote_targets or settings.dify.enabled:
            checks.append(RuntimeCheck("runtime.remote-service", "pass", f"Remote targets: {remote_targets or ['dify']}"))
        else:
            checks.append(
                RuntimeCheck(
                    "runtime.remote-service",
                    "warn",
                    "LOCAL_RUNTIME_SCENARIO_MODE=remote-service but no SERVICE_MODE_* or DIFY runtime is configured for remote use",
                )
            )

    if runtime.scenario_mode == "mock" and any(
        mode == "remote-service"
        for mode in (
            service_mode.rag_mode,
            service_mode.llm_mode,
            service_mode.agent_mode,
            service_mode.embedding_mode,
        )
    ):
        checks.append(
            RuntimeCheck(
                "runtime.mock-vs-remote",
                "warn",
                "mock scenario is enabled while one or more SERVICE_MODE_* values still point to remote-service",
            )
        )
    else:
        checks.append(RuntimeCheck("runtime.mode", "pass", f"Scenario mode: {runtime.scenario_mode}"))

    for name, mode, base_url in (
        ("rag", service_mode.rag_mode, service_mode.rag_base_url),
        ("llm", service_mode.llm_mode, service_mode.llm_base_url),
        ("agent", service_mode.agent_mode, service_mode.agent_base_url),
        ("embedding", service_mode.embedding_mode, service_mode.embedding_base_url),
    ):
        if mode not in ALLOWED_REMOTE_MODES:
            checks.append(RuntimeCheck(f"service_mode.{name}", "fail", f"Unsupported mode: {mode}"))
            continue
        if mode == "remote-service" and not base_url:
            checks.append(RuntimeCheck(f"service_mode.{name}", "fail", "Remote-service mode requires a base URL"))
        else:
            checks.append(RuntimeCheck(f"service_mode.{name}", "pass", f"{name} mode = {mode}"))

    if settings.search.enabled and settings.search.backend in {"opensearch", "elasticsearch"} and not settings.search.endpoint:
        checks.append(
            RuntimeCheck(
                "search.endpoint",
                "fail",
                "SEARCH_ENABLED=true with opensearch/elasticsearch backend requires SEARCH_ENDPOINT",
            )
        )
    elif runtime.scenario_mode == "local-real" and settings.search.backend == "memory":
        checks.append(
            RuntimeCheck(
                "search.backend",
                "warn",
                "local-real scenario still uses SEARCH_BACKEND=memory; OpenSearch is not yet active",
            )
        )
    else:
        checks.append(RuntimeCheck("search.backend", "pass", f"{settings.search.backend}"))

    if settings.dify.enabled and not settings.dify.api_key:
        checks.append(RuntimeCheck("dify.api_key", "warn", "DIFY_ENABLED=true but DIFY_API_KEY is empty"))
    else:
        checks.append(RuntimeCheck("dify.runtime", "pass", f"Dify enabled = {settings.dify.enabled}"))

    if settings.app.environment == "production" and settings.app.debug:
        checks.append(RuntimeCheck("app.debug", "fail", "APP_DEBUG must be false in production"))
    else:
        checks.append(RuntimeCheck("app.debug", "pass", f"debug={settings.app.debug}"))

    if runtime.scenario_mode == "local-real":
        for check in (
            _check_host_backend_endpoint("database.host_endpoint", settings.database.write_url or settings.database.url),
            _check_host_backend_endpoint("redis.host_endpoint", settings.redis.url),
            _check_host_backend_endpoint(
                "search.host_endpoint",
                settings.search.endpoint if settings.search.enabled and settings.search.endpoint else None,
            ),
            _check_host_backend_endpoint("ollama.host_endpoint", settings.llm.ollama_endpoint),
            _check_host_backend_endpoint("neo4j.host_endpoint", settings.neo4j.uri if settings.neo4j.enabled else None),
            _check_host_backend_endpoint(
                "qdrant.host_endpoint",
                settings.qdrant.write_url or settings.qdrant.url or f"http://{settings.qdrant.host}:{settings.qdrant.port}",
            ),
            _check_host_backend_endpoint("kafka.host_endpoint", settings.kafka.bootstrap_servers),
        ):
            if check is not None:
                checks.append(check)

    if settings.redis.sentinel_enabled and not settings.redis.sentinel_nodes:
        checks.append(
            RuntimeCheck(
                "redis.sentinel_nodes",
                "fail",
                "REDIS_SENTINEL_ENABLED=true but REDIS_SENTINEL_NODES is empty",
            )
        )
    else:
        checks.append(
            RuntimeCheck(
                "redis.topology",
                "pass",
                "sentinel" if settings.redis.sentinel_enabled else "single-or-cluster",
            )
        )

    if settings.qdrant.cluster_enabled:
        if not (settings.qdrant.url or settings.qdrant.write_url):
            checks.append(
                RuntimeCheck(
                    "qdrant.cluster_endpoint",
                    "fail",
                    "QDRANT_CLUSTER_ENABLED=true requires QDRANT_URL or QDRANT_WRITE_URL",
                )
            )
        else:
            checks.append(RuntimeCheck("qdrant.cluster_endpoint", "pass", "cluster write endpoint configured"))
        if not settings.qdrant.read_urls:
            checks.append(
                RuntimeCheck(
                    "qdrant.read_urls",
                    "fail",
                    "QDRANT_CLUSTER_ENABLED=true requires QDRANT_READ_URLS",
                )
            )
        else:
            checks.append(RuntimeCheck("qdrant.read_urls", "pass", f"read_urls={len(settings.qdrant.read_urls)}"))
    else:
        checks.append(RuntimeCheck("qdrant.mode", "pass", "single-node/local-fallback"))

    if settings.neo4j.enabled:
        missing_neo4j = [
            name
            for name, value in (
                ("NEO4J_URI", settings.neo4j.uri),
                ("NEO4J_USERNAME", settings.neo4j.username),
                ("NEO4J_PASSWORD", settings.neo4j.password),
            )
            if not value
        ]
        if missing_neo4j:
            checks.append(
                RuntimeCheck(
                    "neo4j.credentials",
                    "fail",
                    f"NEO4J_ENABLED=true but missing {', '.join(missing_neo4j)}",
                )
            )
        else:
            checks.append(RuntimeCheck("neo4j.credentials", "pass", settings.neo4j.uri))
    else:
        checks.append(RuntimeCheck("neo4j.runtime", "pass", "disabled"))

    if settings.security.oidc_enabled:
        missing_oidc = [
            name
            for name, value in (
                ("SEC_OIDC_ISSUER_URL", settings.security.oidc_issuer_url),
                ("SEC_OIDC_CLIENT_ID", settings.security.oidc_client_id),
            )
            if not value
        ]
        if missing_oidc:
            checks.append(
                RuntimeCheck(
                    "security.oidc_required",
                    "fail",
                    f"SEC_OIDC_ENABLED=true but missing {', '.join(missing_oidc)}",
                )
            )
        else:
            checks.append(RuntimeCheck("security.oidc_required", "pass", settings.security.oidc_issuer_url or ""))
        issuer_url = (settings.security.oidc_issuer_url or "").strip().lower()
        if runtime.scenario_mode == "local-real" and (":18080/" in issuer_url or issuer_url.endswith(":18080")):
            checks.append(
                RuntimeCheck(
                    "security.oidc_local_port",
                    "warn",
                    "Current WSL Keycloak compose uses host port 18082; SEC_OIDC_ISSUER_URL still points to legacy 18080",
                )
            )
    else:
        checks.append(RuntimeCheck("security.oidc", "pass", "disabled"))

    return checks


def _normalize_http_base_url(raw_url: str) -> str:
    stripped = raw_url.strip().rstrip("/")
    if "://" not in stripped:
        return f"http://{stripped}"
    return stripped


def _extract_hostname(raw_value: str | None) -> str:
    if not raw_value:
        return ""
    candidate = raw_value.strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"placeholder://{candidate}"

    from urllib.parse import urlparse

    return (urlparse(candidate).hostname or "").strip().lower()


def _check_host_backend_endpoint(name: str, raw_value: str | None) -> RuntimeCheck | None:
    hostname = _extract_hostname(raw_value)
    if hostname and hostname in LOCAL_ONLY_CONTAINER_HOSTS:
        return RuntimeCheck(
            name,
            "fail",
            f"Host backend cannot reach container-only hostname `{hostname}` directly; use 127.0.0.1/localhost mapped ports instead",
        )
    return None


async def _probe_http_endpoint(
    name: str,
    url: str,
    *,
    allow_404: bool = False,
    timeout_seconds: float = 10.0,
) -> RuntimeCheck:
    import httpx

    normalized = _normalize_http_base_url(url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, trust_env=False) as client:
            response = await client.get(normalized)
        if response.status_code == 404 and allow_404:
            return RuntimeCheck(name, "warn", f"{normalized} returned 404 but the endpoint is reachable")
        if response.status_code >= 500:
            return RuntimeCheck(name, "fail", f"{normalized} returned HTTP {response.status_code}")
        return RuntimeCheck(name, "pass", f"{normalized} returned HTTP {response.status_code}")
    except Exception as exc:
        return RuntimeCheck(name, "fail", f"{normalized} probe failed: {exc}")


async def _probe_runtime_dependencies(settings: Any) -> list[RuntimeCheck]:
    from src.infrastructure.database import check_db_health
    from src.infrastructure.qdrant import check_qdrant_health
    from src.infrastructure.redis import check_redis_health

    checks: list[RuntimeCheck] = []

    db_payload = await check_db_health()
    checks.append(
        RuntimeCheck(
            "probe.database",
            "pass" if db_payload.get("status") == "healthy" else "fail",
            f"backend_mode={db_payload.get('backend_mode', 'unknown')}",
            db_payload,
        )
    )

    redis_payload = await check_redis_health()
    checks.append(
        RuntimeCheck(
            "probe.redis",
            "pass" if redis_payload.get("status") == "healthy" else "fail",
            f"topology={redis_payload.get('topology_mode', 'unknown')}",
            redis_payload,
        )
    )

    qdrant_payload = await check_qdrant_health()
    checks.append(
        RuntimeCheck(
            "probe.qdrant",
            "pass" if qdrant_payload.get("status") == "healthy" else "fail",
            f"backend_mode={qdrant_payload.get('backend_mode', 'unknown')}",
            qdrant_payload,
        )
    )

    if settings.search.enabled and settings.search.endpoint:
        checks.append(
            await _probe_http_endpoint(
                "probe.search",
                settings.search.endpoint,
                timeout_seconds=max(10.0, settings.search.timeout_seconds),
            )
        )
    else:
        checks.append(RuntimeCheck("probe.search", "skip", "Search probe skipped for current backend configuration"))

    if settings.llm.ollama_endpoint:
        ollama_url = urljoin(f"{_normalize_http_base_url(settings.llm.ollama_endpoint)}/", "api/tags")
        checks.append(await _probe_http_endpoint("probe.ollama", ollama_url, timeout_seconds=10.0))

    if settings.dify.enabled:
        checks.append(await _probe_http_endpoint("probe.dify", settings.dify.base_url, allow_404=True))
    else:
        checks.append(RuntimeCheck("probe.dify", "skip", "Dify probe skipped because DIFY_ENABLED=false"))

    for name, mode, base_url in (
        ("rag", settings.service_mode.rag_mode, settings.service_mode.rag_base_url),
        ("llm", settings.service_mode.llm_mode, settings.service_mode.llm_base_url),
        ("agent", settings.service_mode.agent_mode, settings.service_mode.agent_base_url),
        ("embedding", settings.service_mode.embedding_mode, settings.service_mode.embedding_base_url),
    ):
        if mode != "remote-service":
            checks.append(RuntimeCheck(f"probe.remote_{name}", "skip", f"{name} is in-process"))
            continue
        health_url = urljoin(f"{_normalize_http_base_url(base_url)}/", "health")
        checks.append(await _probe_http_endpoint(f"probe.remote_{name}", health_url, allow_404=True))

    return checks


def _render_checks(checks: list[RuntimeCheck]) -> None:
    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    for check in checks:
        label = icons.get(check.status, check.status.upper())
        print(f"[{label}] {check.name}: {check.detail}")


def _render_summary(payload: dict[str, Any], plan: dict[str, Any]) -> None:
    runtime = payload["runtime"]
    app = payload["app"]
    dependencies = payload["dependencies"]
    service_modes = payload["service_modes"]

    print(f"App: {app['name']} ({app['environment']}, debug={app['debug']})")
    print(
        "Runtime: "
        f"profile={runtime['profile']} "
        f"preferred_os={runtime['preferred_os']} "
        f"scenario={runtime['scenario_mode']}"
    )
    print(
        "Service modes: "
        f"rag={service_modes['rag_mode']} "
        f"llm={service_modes['llm_mode']} "
        f"agent={service_modes['agent_mode']} "
        f"embedding={service_modes['embedding_mode']} "
        f"fallback={service_modes['enable_fallback']}"
    )
    print(
        "Dependencies: "
        f"search={dependencies['search_backend']} "
        f"dify={dependencies['dify_enabled']} "
        f"ollama={dependencies['ollama_endpoint']}"
    )
    print("Plan:")
    print(f"  python-setup: {plan.get('python_setup_command', plan['bootstrap_command'])}")
    for index, step in enumerate(plan.get("dependency_steps", []), start=1):
        print(f"  deps[{index}] {step['name']}: {step['command']}")
        print(f"    note: {step['description']}")
    if plan["mock_services_command"]:
        print(f"  mock: {plan['mock_services_command']}")
    print(f"  backend: {plan['backend_command']}")
    for command in plan["frontend_commands"]:
        print(f"  frontend: {command}")
    for note in plan["notes"]:
        print(f"  note: {note}")


def _collect_runtime_report(settings: Any, *, include_probes: bool) -> dict[str, Any]:
    env_path = ROOT / ".env"
    summary = _build_summary(settings)
    plan = _build_runtime_plan(settings)
    validation_checks = _validate_runtime_configuration(settings, env_path=env_path)
    payload: dict[str, Any] = {
        "summary": summary,
        "plan": plan,
        "validation_checks": [item.to_dict() for item in validation_checks],
    }
    if include_probes:
        probe_checks = asyncio.run(_probe_runtime_dependencies(settings))
        payload["probe_checks"] = [item.to_dict() for item in probe_checks]
    return payload


def _write_output_if_requested(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote runtime report to {target}")


def _exit_code_from_checks(checks: list[RuntimeCheck]) -> int:
    return 1 if any(item.status == "fail" for item in checks) else 0


def _resolve_python_command() -> str:
    if _venv_ready_marker_path().exists():
        candidates = _venv_python_candidates()
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return sys.executable


def _run_command(command: list[str], *, cwd: Path = ROOT) -> int:
    env = os.environ.copy()
    is_docker_compose = len(command) >= 2 and command[0] == "docker" and command[1] == "compose"
    if is_docker_compose and ("--build" in command or any(arg in {"build", "bake"} for arg in command[2:])):
        # Docker Desktop's Buildx/Bake path has been flaky in local Windows setups
        # (`no such job ...`). Force the classic compose build path for stability.
        env.setdefault("COMPOSE_BAKE", "false")
        env.setdefault("DOCKER_BUILDKIT", "0")
        env.setdefault("COMPOSE_DOCKER_CLI_BUILD", "0")
    try:
        completed = subprocess.run(command, cwd=cwd, check=False, env=env)
        return completed.returncode
    except FileNotFoundError as exc:
        print(f"Command not found: {command[0]} ({exc})")
        return 127


def _module_is_available(python_cmd: str, module_name: str) -> bool:
    probe = subprocess.run(
        [
            python_cmd,
            "-c",
            (
                "import importlib.util, sys; "
                f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
            ),
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0


def _run_python_dependency_setup(args: argparse.Namespace) -> int:
    venv_python = _resolve_venv_python_path()
    if not venv_python.exists():
        print(f"Creating virtual environment at {venv_python.parent.parent}")
        if _run_command([sys.executable, "-m", "venv", str(ROOT / ".venv")]) != 0:
            return 1

    python_cmd = str(_resolve_venv_python_path())

    if args.install_dev:
        print("Installing project, dev, and local AI dependencies into .venv")
        if _run_command([python_cmd, "-m", "pip", "install", "--upgrade", "pip"]) != 0:
            return 1
        if _run_command([python_cmd, "-m", "pip", "install", "-e", ".[dev,local-ai]"]) != 0:
            return 1

    env_path = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if args.copy_env and not env_path.exists():
        if not env_example.exists():
            print("Cannot create .env because .env.example is missing.")
            return 1
        env_path.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created {env_path} from .env.example")
    elif env_path.exists():
        print(f"Keeping existing environment file: {env_path}")

    if args.verify:
        required_modules = ["pytest", "pytest_asyncio", "sentence_transformers", "faster_whisper"] if args.install_dev else []
        missing = [name for name in required_modules if not _module_is_available(python_cmd, name)]
        if missing:
            print(f"Python dependency verification failed; missing modules in .venv: {', '.join(missing)}")
            return 1
        if required_modules:
            print(f"Verified .venv modules: {', '.join(required_modules)}")

    if args.run_check:
        print("Running runtime validation after Python dependency setup")
        if _run_command([python_cmd, "scripts/local_runtime_manager.py", "check"]) != 0:
            return 1

    marker_path = _venv_ready_marker_path()
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("ready\n", encoding="utf-8")
    print("Python dependency setup completed.")
    return 0


def _run_bootstrap_command(args: argparse.Namespace) -> int:
    # Keep the legacy subcommand working, but route it through the dedicated
    # Python dependency setup flow used by install_python_deps.py.
    return _run_python_dependency_setup(args)


def _start_mock_services(python_cmd: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [python_cmd, "scripts/mock_services.py", "--all"],
        cwd=ROOT,
        text=True,
    )


def _run_up_command(settings: Any, args: argparse.Namespace) -> int:
    report = _collect_runtime_report(settings, include_probes=args.preflight)
    report["plan"] = _build_runtime_plan(
        settings,
        workspace_root=ROOT,
        os_name=os.name,
        python_executable=_resolve_python_command(),
        include_ollama=args.with_ollama,
        include_platform=args.with_platform,
        include_postgres_ha=args.with_postgres_ha,
        include_qdrant_cluster=args.with_qdrant_cluster,
        include_kafka=args.with_kafka,
    )
    validation_checks = [RuntimeCheck(**item) for item in report["validation_checks"]]
    _render_summary(report["summary"], report["plan"])
    _render_checks(validation_checks)
    if args.preflight and "probe_checks" in report:
        probe_checks = [RuntimeCheck(**item) for item in report["probe_checks"]]
        _render_checks(probe_checks)
    else:
        probe_checks = []

    failures = [item for item in validation_checks if item.status == "fail"]
    if args.preflight:
        failures.extend(item for item in probe_checks if item.status == "fail")
    if failures:
        print("Aborting startup because configuration validation failed.")
        return 1

    plan = report["plan"]
    if args.print_plan:
        return 0

    if settings.local_runtime.scenario_mode == "local-real" and not args.skip_deps:
        dependency_steps = _build_dependency_startup_steps(
            settings,
            workspace_root=ROOT,
            os_name=os.name,
            python_executable=_resolve_python_command(),
            include_ollama=args.with_ollama,
            include_platform=args.with_platform,
            include_postgres_ha=args.with_postgres_ha,
            include_qdrant_cluster=args.with_qdrant_cluster,
            include_kafka=args.with_kafka,
        )
        for step in dependency_steps:
            print(f"Starting {step['name']}: {_format_command(step['command'], os_name=os.name)}")
            if _run_command(step["command"]) != 0:
                return 1

    mock_process: subprocess.Popen[str] | None = None
    try:
        if settings.local_runtime.scenario_mode == "mock" and not args.skip_mock_services:
            python_cmd = _resolve_python_command()
            mock_process = _start_mock_services(python_cmd)
            print(f"Started mock services with PID {mock_process.pid}")

        if args.skip_backend:
            return 0

        backend_command = _build_backend_host_command(
            settings,
            python_executable=_resolve_python_command(),
            host=args.host,
            port=args.port,
            reload=args.reload,
            os_name=os.name,
        )
        print(f"Starting backend: {_format_command(backend_command, os_name=os.name)}")
        return _run_command(backend_command)
    finally:
        if mock_process is not None and mock_process.poll() is None:
            mock_process.terminate()
            try:
                mock_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mock_process.kill()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified local runtime manager for PMS local scenarios")
    subparsers = parser.add_subparsers(dest="command")

    for command_name in ("summary", "check", "plan"):
        subparser = subparsers.add_parser(command_name)
        subparser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
        subparser.add_argument("--output", help="Optional path to write the JSON report")
        if command_name != "plan":
            subparser.add_argument("--probes", action="store_true", help="Run dependency probes")

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument(
        "--install-dev",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Install the project with dev extras into .venv (includes pytest and pytest-asyncio).",
    )
    bootstrap_parser.add_argument(
        "--copy-env",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy .env.example to .env when .env is missing.",
    )
    bootstrap_parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify key bootstrap modules after installation.",
    )
    bootstrap_parser.add_argument("--run-check", action="store_true", help="Run `check` after bootstrap succeeds.")

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--preflight", action="store_true", help="Run dependency probes before startup")
    up_parser.add_argument("--print-plan", action="store_true", help="Only print the startup plan")
    up_parser.add_argument("--skip-deps", action="store_true", help="Do not start local dependencies")
    up_parser.add_argument("--skip-mock-services", action="store_true", help="Do not auto-start mock services in mock mode")
    up_parser.add_argument("--skip-backend", action="store_true", help="Do not start the backend process")
    up_parser.add_argument("--with-ollama", action="store_true", help="Also start the optional Ollama local LLM stack.")
    up_parser.add_argument("--with-platform", action="store_true", help="Also start the platform stack from docker-compose.wsl-platform.yml.")
    up_parser.add_argument("--with-postgres-ha", action="store_true", help="Also start the PostgreSQL HA stack.")
    up_parser.add_argument("--with-qdrant-cluster", action="store_true", help="Also start the Qdrant cluster stack.")
    up_parser.add_argument(
        "--with-kafka",
        action="store_true",
        help="Also start the canonical local Kafka/Zookeeper/Kafka Connect/Debezium init stack from docker-compose.local-kafka.yml.",
    )
    up_parser.add_argument("--host", default="0.0.0.0", help="Bind host for the local backend process.")
    up_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for the local backend process. Defaults to APP_HOST_PORT or the scenario default port.",
    )
    up_parser.add_argument("--reload", action=argparse.BooleanOptionalAction, default=False, help="Run the local backend with uvicorn --reload.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "bootstrap":
        return _run_bootstrap_command(args)

    settings = _load_settings()

    if args.command == "up":
        return _run_up_command(settings, args)

    include_probes = getattr(args, "probes", False)
    report = _collect_runtime_report(settings, include_probes=include_probes)
    _write_output_if_requested(getattr(args, "output", None), report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        checks = report["validation_checks"]
        if include_probes:
            checks = [*checks, *report.get("probe_checks", [])]
        return _exit_code_from_checks([RuntimeCheck(**item) for item in checks])

    _render_summary(report["summary"], report["plan"])
    validation_checks = [RuntimeCheck(**item) for item in report["validation_checks"]]
    _render_checks(validation_checks)
    probe_checks: list[RuntimeCheck] = []
    if include_probes:
        probe_checks = [RuntimeCheck(**item) for item in report.get("probe_checks", [])]
        _render_checks(probe_checks)
    return _exit_code_from_checks([*validation_checks, *probe_checks])


if __name__ == "__main__":
    raise SystemExit(main())
