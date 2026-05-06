from __future__ import annotations

from pathlib import Path


def test_install_python_deps_script_covers_pytest_asyncio() -> None:
    script_text = Path("scripts/install_python_deps.py").read_text(encoding="utf-8")
    runtime_manager_text = Path("scripts/local_runtime_manager.py").read_text(encoding="utf-8")
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "local_runtime_manager._run_python_dependency_setup" in script_text
    assert "--install-dev" in script_text
    assert "pytest-asyncio" in script_text
    assert "sentence-transformers" in script_text
    assert '".[dev,local-ai]"' in runtime_manager_text
    assert "faster-whisper" in pyproject_text


def test_ollama_warmup_script_uses_configurable_endpoint_and_current_baseline() -> None:
    script_text = Path("scripts/tmp_ollama_warmup.py").read_text(encoding="utf-8")

    assert 'LLM_OLLAMA_ENDPOINT' in script_text
    assert 'httpx.post' in script_text
    assert 'qwen2.5:1.5b-instruct' in script_text


def test_bootstrap_local_model_stack_script_covers_required_local_model_matrix() -> None:
    script_text = Path("scripts/bootstrap_local_model_stack.py").read_text(encoding="utf-8")
    module_text = Path("src/bootstrap_local_model_assets.py").read_text(encoding="utf-8")

    assert "--startup-only" in script_text
    assert "target_ollama_models" in script_text
    assert "cpu-model-cache-init" in script_text
    assert "_pull_ollama_model" in script_text
    assert '"ollama", "pull"' in script_text
    assert "sentence_transformers" in module_text
    assert "faster_whisper" in module_text


def test_install_local_software_script_covers_required_and_optional_tools() -> None:
    script_text = Path("scripts/install_local_software.py").read_text(encoding="utf-8")

    assert "Python 3.11+" in script_text
    assert "PostgreSQL 16" in script_text
    assert "MariaDB" in script_text
    assert "Redis 7" in script_text
    assert "MinIO" in script_text
    assert "Kafka 3.6" in script_text
    assert "Elasticsearch 8" in script_text
    assert "OpenSearch 2" in script_text
    assert "Qdrant 1.9+" in script_text
    assert "MongoDB 7" in script_text
    assert "Neo4j 5" in script_text
    assert "Ollama" in script_text
    assert "D:\\aitools\\shared" in script_text
    assert "Node.js LTS" in script_text
    assert "--apply" in script_text


def test_install_local_software_script_recognizes_current_aitools_layout() -> None:
    script_text = Path("scripts/install_local_software.py").read_text(encoding="utf-8")

    assert "SOFTWARE_ROOT = Path(r\"D:\\aitools\\software\")" in script_text
    assert "Redis-7.2.9-Windows-x64-msys2" in script_text
    assert "kafka_2.13-3.6.1" in script_text
    assert "opensearch-2.15.0" in script_text
    assert "neo4j-community-5.23.0" in script_text
    assert "ollama-new" in script_text
    assert "mongodb-win32-x86_64-windows-7.0.11" in script_text
    assert "postgres*/bin/psql.exe" in script_text
    assert "mysql*/bin/mysql.exe" in script_text
    assert "_glob_software_candidate" in script_text
    assert "_probe_existing_path" in script_text


def test_local_env_example_matches_first_environment_shared_windows_plan() -> None:
    env_text = Path(".env.local.example").read_text(encoding="utf-8")

    assert "DB_URL=postgresql+asyncpg://fms:fms@localhost:5432/fms" in env_text
    assert "REDIS_URL=redis://localhost:6379/4" in env_text
    assert "KAFKA_BOOTSTRAP_SERVERS=localhost:9092" in env_text
    assert "SEARCH_ENDPOINT=http://localhost:9201" in env_text
    assert "QDRANT_PORT=6333" in env_text
    assert "NEO4J_URI=bolt://localhost:7687" in env_text
    assert "LLM_OLLAMA_ENDPOINT=http://localhost:11434" in env_text


def test_bootstrap_local_kafka_script_supports_startup_only_mode() -> None:
    script_text = Path("scripts/bootstrap_local_kafka_debezium.py").read_text(encoding="utf-8")

    assert "--startup-only" in script_text
    assert '"pms-network"' in script_text
    assert '"debezium-init"' in script_text


def test_cleanup_local_runtime_script_targets_obsolete_legacy_kafka_stack() -> None:
    script_text = Path("scripts/cleanup_local_runtime.py").read_text(encoding="utf-8")

    assert "pms-kafka" in script_text
    assert "pms-zookeeper" in script_text
    assert "pms-kafka-connect" in script_text
    assert "pms-debezium-init" in script_text
    assert "fms_kafka_data" in script_text
    assert "--apply" in script_text


def test_start_local_services_script_exposes_optional_stack_flags() -> None:
    script_text = Path("scripts/start_local_services.py").read_text(encoding="utf-8")

    assert "--with-ollama" in script_text
    assert "--with-platform" in script_text
    assert "--with-postgres-ha" in script_text
    assert "--with-qdrant-cluster" in script_text
    assert "--with-kafka" in script_text
    assert "docker-compose.local-kafka.yml" in script_text
    assert "_venv_ready_marker_path" in script_text


def test_start_local_wrappers_default_to_backend_only_mode() -> None:
    powershell_wrapper = Path("scripts/start_local.ps1").read_text(encoding="utf-8")
    shell_wrapper = Path("scripts/start_local.sh").read_text(encoding="utf-8")

    assert ".pms_python_ready" in powershell_wrapper
    assert ".pms_python_ready" in shell_wrapper
    assert '@("up", "--skip-deps") + $args' in powershell_wrapper
    assert 'up --skip-deps "$@"' in shell_wrapper


def test_core_compose_maps_backend_to_gateway_safe_host_port() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert '${APP_HOST_PORT:-18000}:8000' in compose_text


def test_core_compose_app_uses_shared_network_ollama_alias_by_default() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "LLM_OLLAMA_ENDPOINT: ${DOCKER_APP_LLM_OLLAMA_ENDPOINT:-http://ollama:11434}" in compose_text


def test_local_kafka_compose_persists_kafka_and_zookeeper_state() -> None:
    compose_text = Path("docker-compose.local-kafka.yml").read_text(encoding="utf-8")

    assert "local_zookeeper_data:/var/lib/zookeeper/data" in compose_text
    assert "local_zookeeper_log:/var/lib/zookeeper/log" in compose_text
    assert "local_kafka_data:/var/lib/kafka/data" in compose_text


def test_core_compose_no_longer_embeds_kafka_stack() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "container_name: pms-local-kafka" not in compose_text
    assert "container_name: pms-kafka" not in compose_text
    assert "container_name: pms-zookeeper" not in compose_text


def test_optional_llm_compose_uses_official_ollama_image() -> None:
    compose_text = Path("docker-compose.local-llm.yml").read_text(encoding="utf-8")
    dockerfile_text = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ollama/ollama" in compose_text
    assert "11434:11434" in compose_text
    assert "cpu-model-cache-init" in compose_text
    assert "src.bootstrap_local_model_assets" in compose_text
    assert "local_ai_model_cache:/app/.cache" in compose_text
    assert "ollama_data:/root/.ollama" in compose_text
    assert "name: pms-network" in compose_text
    assert "- ollama" in compose_text
    assert "- pms-ollama-local" in compose_text
    assert "ffmpeg" in dockerfile_text
