from __future__ import annotations

from pathlib import Path

from src.infrastructure.graph_rag import Neo4jMock


def test_wsl_local_compose_includes_neo4j_service() -> None:
    compose_text = Path("docker-compose.wsl-local.yml").read_text(encoding="utf-8")

    assert "neo4j:" in compose_text
    assert "neo4j:5.26-community" in compose_text
    assert 'container_name: pms-neo4j-local' in compose_text
    assert "NEO4J_AUTH: neo4j/pms_graph_dev" in compose_text
    assert '"17474:7474"' in compose_text
    assert '"17687:7687"' in compose_text
    assert "/var/lib/neo4j/bin/cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p pms_graph_dev" in compose_text
    assert "neo4j_data:/data" in compose_text
    assert "./artifacts/runtime/neo4j/logs:/logs" in compose_text


def test_env_example_exposes_neo4j_runtime_settings() -> None:
    env_text = Path(".env.example").read_text(encoding="utf-8")

    assert "NEO4J_ENABLED=false" in env_text
    assert "NEO4J_URI=bolt://localhost:17687" in env_text
    assert "NEO4J_USERNAME=neo4j" in env_text
    assert "NEO4J_PASSWORD=pms_graph_dev" in env_text
    assert "NEO4J_DATABASE=neo4j" in env_text
    assert "NEO4J_PREFER_LOCAL_FALLBACK=true" in env_text


def test_wsl_local_stack_script_starts_neo4j() -> None:
    script_text = Path("scripts/wsl_local_stack_start.sh").read_text(encoding="utf-8")

    assert "up -d kong-database opensearch neo4j" in script_text
    assert "pms-neo4j-local" in script_text
    assert "/var/lib/neo4j/bin/cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p pms_graph_dev" in script_text


def test_neo4j_mock_default_uri_matches_local_runtime_baseline() -> None:
    store = Neo4jMock()

    assert store._uri == "bolt://localhost:17687"
