from __future__ import annotations

from pathlib import Path

import pytest
import scripts.local_runtime_manager as local_runtime_manager
from scripts.local_runtime_manager import (
    _build_dependency_startup_steps,
    _build_parser,
    _build_runtime_plan,
    _default_backend_port,
    _ensure_workspace_root_on_sys_path,
    _resolve_python_command,
    _to_wsl_path,
    _validate_runtime_configuration,
)
from src.config.settings import DatabaseSettings, Neo4jSettings, QdrantSettings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_local_runtime_settings_are_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_PROFILE", "linux-dev")
    monkeypatch.setenv("LOCAL_RUNTIME_PREFERRED_OS", "linux")
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "mock")

    settings = get_settings()

    assert settings.local_runtime.profile == "linux-dev"
    assert settings.local_runtime.preferred_os == "linux"
    assert settings.local_runtime.scenario_mode == "mock"


def test_to_wsl_path_converts_windows_workspace_path() -> None:
    path = Path(r"D:\Project\fms")

    assert _to_wsl_path(path) == "/mnt/d/Project/fms"


def test_ensure_workspace_root_on_sys_path_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sentinel = "already-present"
    monkeypatch.setattr("scripts.local_runtime_manager.sys.path", [sentinel, str(tmp_path)])

    _ensure_workspace_root_on_sys_path(tmp_path)
    _ensure_workspace_root_on_sys_path(tmp_path)

    assert local_runtime_manager.sys.path == [str(tmp_path), sentinel]


def test_build_runtime_plan_prefers_wsl_launcher_for_windows_local_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    monkeypatch.setenv("LOCAL_RUNTIME_PREFERRED_OS", "linux-wsl")

    settings = get_settings()
    plan = _build_runtime_plan(
        settings,
        workspace_root=Path(r"D:\Project\fms"),
        os_name="nt",
        python_executable="python",
    )

    assert plan["dependency_steps"]
    assert plan["dependency_steps"][0]["name"] == "core-data"
    assert "docker compose -f docker-compose.yml up -d postgres redis qdrant" in plan["dependency_steps"][0]["command"]
    assert plan["dependency_steps"][1]["name"] == "gateway-search"
    assert "docker compose -f docker-compose.wsl-local.yml up -d kong-database opensearch neo4j kong-migrations kong-gateway" in plan["dependency_steps"][1]["command"]
    assert "docker compose -f docker-compose.yml up -d --build --no-deps app" in plan["backend_command"]


def test_default_backend_port_switches_to_gateway_upstream_port_for_wsl_local_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    monkeypatch.setenv("LOCAL_RUNTIME_PREFERRED_OS", "linux-wsl")

    settings = get_settings()

    assert _default_backend_port(settings, os_name="nt") == 18000


def test_resolve_python_command_ignores_venv_without_ready_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(local_runtime_manager, "_venv_python_candidates", lambda root=local_runtime_manager.ROOT: [venv_python])
    monkeypatch.setattr(local_runtime_manager, "_venv_ready_marker_path", lambda root=local_runtime_manager.ROOT: tmp_path / ".venv" / ".pms_python_ready")

    assert _resolve_python_command() == local_runtime_manager.sys.executable


def test_dependency_startup_steps_include_optional_stacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    monkeypatch.setenv("LOCAL_RUNTIME_PREFERRED_OS", "linux-wsl")

    settings = get_settings()
    steps = _build_dependency_startup_steps(
        settings,
        workspace_root=Path(r"D:\Project\fms"),
        os_name="nt",
        python_executable="python",
        include_ollama=True,
        include_platform=True,
        include_postgres_ha=True,
        include_qdrant_cluster=True,
        include_kafka=True,
    )

    assert [step["name"] for step in steps] == [
        "core-data",
        "kafka-cdc",
        "llm-local",
        "gateway-search",
        "platform",
        "postgres-ha",
        "qdrant-cluster",
    ]
    assert steps[1]["command"] == ["python", "scripts/bootstrap_local_kafka_debezium.py", "--startup-only"]
    assert steps[2]["command"] == ["python", "scripts/bootstrap_local_model_stack.py", "--startup-only"]


def test_runtime_plan_documents_shared_network_ollama_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    monkeypatch.setenv("LOCAL_RUNTIME_PREFERRED_OS", "linux-wsl")

    settings = get_settings()
    plan = _build_runtime_plan(
        settings,
        workspace_root=Path(r"D:\Project\fms"),
        os_name="nt",
        python_executable="python",
        include_ollama=True,
    )

    assert any("http://ollama:11434" in note for note in plan["notes"])
    assert any("bge-reranker-base" in note for note in plan["notes"])


def test_parser_supports_bootstrap_subcommand() -> None:
    parser = _build_parser()

    args = parser.parse_args(["bootstrap", "--no-install-dev", "--run-check"])

    assert args.command == "bootstrap"
    assert args.install_dev is False
    assert args.run_check is True


def test_main_bootstrap_does_not_require_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_runtime_manager, "_load_settings", lambda: (_ for _ in ()).throw(AssertionError("should not load settings")))
    monkeypatch.setattr(local_runtime_manager, "_run_python_dependency_setup", lambda args: 0)

    assert local_runtime_manager.main(["bootstrap"]) == 0


def test_repo_local_runtime_defaults_align_with_documented_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DB_URL",
        "DATABASE_URL",
        "NEO4J_URI",
        "QDRANT_COLLECTION_PREFIX",
    ):
        monkeypatch.delenv(key, raising=False)

    database = DatabaseSettings(_env_file=None)
    neo4j = Neo4jSettings(_env_file=None)
    qdrant = QdrantSettings(_env_file=None)

    assert database.url == "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"
    assert neo4j.uri == "bolt://localhost:17687"
    assert qdrant.collection_prefix == "pms_"


def test_validate_runtime_configuration_fails_when_search_endpoint_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    monkeypatch.setenv("SEARCH_BACKEND", "opensearch")
    monkeypatch.setenv("SEARCH_ENDPOINT", "")

    settings = get_settings()
    checks = _validate_runtime_configuration(settings, env_path=tmp_path / ".env")

    failed_names = {check.name for check in checks if check.status == "fail"}
    assert "search.endpoint" in failed_names


def test_validate_runtime_configuration_fails_when_redis_sentinel_nodes_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("REDIS_SENTINEL_ENABLED", "true")
    monkeypatch.setenv("REDIS_SENTINEL_NODES", "")

    settings = get_settings()
    checks = _validate_runtime_configuration(settings, env_path=tmp_path / ".env")

    failed_names = {check.name for check in checks if check.status == "fail"}
    assert "redis.sentinel_nodes" in failed_names


def test_validate_runtime_configuration_fails_when_qdrant_cluster_missing_read_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QDRANT_CLUSTER_ENABLED", "true")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:16333")
    monkeypatch.setenv("QDRANT_READ_URLS", "")

    settings = get_settings()
    checks = _validate_runtime_configuration(settings, env_path=tmp_path / ".env")

    failed_names = {check.name for check in checks if check.status == "fail"}
    assert "qdrant.read_urls" in failed_names


def test_validate_runtime_configuration_warns_when_oidc_issuer_uses_legacy_local_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "http://localhost:18080/realms/pms-dev")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-web")

    settings = get_settings()
    checks = _validate_runtime_configuration(settings, env_path=tmp_path / ".env")

    warned_names = {check.name for check in checks if check.status == "warn"}
    assert "security.oidc_local_port" in warned_names
