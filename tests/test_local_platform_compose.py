from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_compose() -> dict:
    with open(ROOT / "docker-compose.wsl-platform.yml", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_wsl_platform_compose_includes_redis_sentinel_keycloak_and_flink():
    compose = _load_compose()
    services = compose["services"]

    expected = {
        "redis-master",
        "redis-replica-1",
        "redis-replica-2",
        "redis-sentinel-1",
        "redis-sentinel-2",
        "redis-sentinel-3",
        "keycloak-db",
        "keycloak",
        "flink-jobmanager",
        "flink-taskmanager",
    }
    assert expected.issubset(services.keys())


def test_wsl_platform_compose_keycloak_imports_local_realm():
    compose = _load_compose()
    keycloak = compose["services"]["keycloak"]

    assert keycloak["image"].startswith("quay.io/keycloak/keycloak:")
    assert "start-dev" in keycloak["command"]
    assert any("pms-dev-realm.json" in volume for volume in keycloak["volumes"])


def test_wsl_platform_compose_redis_sentinel_uses_quorum_topology():
    compose = _load_compose()
    sentinel = compose["services"]["redis-sentinel-1"]

    command = "\n".join(sentinel["command"])
    assert 'MASTER_IP="$(ping -c 1 redis-master' in command
    assert "sentinel monitor mymaster $${MASTER_IP} 6379 2" in command
    assert "sentinel down-after-milliseconds mymaster 5000" in command
    assert "SENTINEL" in " ".join(sentinel["healthcheck"]["test"])


def test_wsl_platform_compose_flink_matches_official_standalone_pattern():
    compose = _load_compose()
    jobmanager = compose["services"]["flink-jobmanager"]
    taskmanager = compose["services"]["flink-taskmanager"]

    assert jobmanager["image"] == "flink:2.2.0-scala_2.12"
    assert jobmanager["command"] == "jobmanager"
    assert taskmanager["image"] == "flink:2.2.0-scala_2.12"
    assert taskmanager["command"] == "taskmanager"
    assert "18081:8081" in jobmanager["ports"]


def test_wsl_platform_start_script_mentions_current_keycloak_ports():
    script = (ROOT / "scripts" / "wsl_platform_stack_start.sh").read_text(encoding="utf-8")

    assert "http://localhost:19000/health/ready" in script
    assert "http://localhost:18082/realms/pms-dev/.well-known/openid-configuration" in script
    assert "SEC_OIDC_ISSUER_URL=http://localhost:18082/realms/pms-dev" in script
