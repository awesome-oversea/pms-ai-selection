from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_compose() -> dict:
    with open(ROOT / "docker-compose.wsl-qdrant-cluster.yml", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_wsl_qdrant_cluster_compose_includes_three_nodes():
    compose = _load_compose()
    services = compose["services"]

    assert {"qdrant-node-1", "qdrant-node-2", "qdrant-node-3"}.issubset(services.keys())


def test_wsl_qdrant_cluster_enables_distributed_mode_and_bootstrap():
    compose = _load_compose()
    node_1 = compose["services"]["qdrant-node-1"]
    node_2 = compose["services"]["qdrant-node-2"]
    node_3 = compose["services"]["qdrant-node-3"]

    assert node_1["environment"]["QDRANT__CLUSTER__ENABLED"] == "true"
    assert "--uri" in node_1["command"]
    assert "http://qdrant-node-1:6335" in node_1["command"]
    assert "--bootstrap" in node_2["command"]
    assert "http://qdrant-node-1:6335" in node_2["command"]
    assert "--bootstrap" in node_3["command"]
    assert "http://qdrant-node-1:6335" in node_3["command"]


def test_wsl_qdrant_cluster_exposes_distinct_ports():
    compose = _load_compose()
    node_1 = compose["services"]["qdrant-node-1"]
    node_2 = compose["services"]["qdrant-node-2"]
    node_3 = compose["services"]["qdrant-node-3"]

    assert "16333:6333" in node_1["ports"]
    assert "16433:6333" in node_2["ports"]
    assert "16533:6333" in node_3["ports"]
    assert "16335:6335" in node_1["ports"]
    assert "16435:6335" in node_2["ports"]
    assert "16535:6335" in node_3["ports"]


def test_wsl_qdrant_cluster_start_script_mentions_cluster_envs():
    script = (ROOT / "scripts" / "wsl_qdrant_cluster_start.sh").read_text(encoding="utf-8")

    assert 'docker compose -f "$COMPOSE_FILE" up -d' in script
    assert "QDRANT_CLUSTER_ENABLED=true" in script
    assert "QDRANT_WRITE_URL=http://localhost:16333" in script
    assert "QDRANT_READ_URLS=http://localhost:16433,http://localhost:16533" in script
