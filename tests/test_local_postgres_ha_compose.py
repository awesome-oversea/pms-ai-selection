from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_compose() -> dict:
    with open(ROOT / "docker-compose.wsl-postgres-ha.yml", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_wsl_postgres_ha_compose_includes_primary_standbys_and_pgpool():
    compose = _load_compose()
    services = compose["services"]

    expected = {"pg-primary", "pg-standby-1", "pg-standby-2", "pgpool"}
    assert expected.issubset(services.keys())


def test_wsl_postgres_ha_compose_uses_repmgr_for_replication_and_failover():
    compose = _load_compose()
    primary = compose["services"]["pg-primary"]
    standby = compose["services"]["pg-standby-1"]

    assert primary["image"].startswith("bitnamilegacy/postgresql-repmgr:")
    assert primary["environment"]["REPMGR_PARTNER_NODES"] == "pg-primary-0,pg-standby-1,pg-standby-2"
    assert primary["environment"]["REPMGR_NODE_ID"] == "1"
    assert primary["hostname"] == "pg-primary-0"
    assert standby["environment"]["REPMGR_PRIMARY_HOST"] == "pg-primary-0"
    assert standby["environment"]["REPMGR_NODE_NAME"] == "pg-standby-1"


def test_wsl_postgres_ha_compose_exposes_pgpool_write_endpoint_on_15432():
    compose = _load_compose()
    pgpool = compose["services"]["pgpool"]
    primary = compose["services"]["pg-primary"]
    standby_1 = compose["services"]["pg-standby-1"]
    standby_2 = compose["services"]["pg-standby-2"]

    assert pgpool["image"].startswith("bitnamilegacy/pgpool:")
    assert "15432:5432" in pgpool["ports"]
    assert "15435:5432" in primary["ports"]
    assert "15436:5432" in standby_1["ports"]
    assert "15437:5432" in standby_2["ports"]
    assert "0:pg-primary:5432" in pgpool["environment"]["PGPOOL_BACKEND_NODES"]
    assert "1:pg-standby-1:5432" in pgpool["environment"]["PGPOOL_BACKEND_NODES"]
    assert pgpool["environment"]["PGPOOL_BACKEND_APPLICATION_NAMES"] == "pg-primary-0,pg-standby-1,pg-standby-2"
    assert pgpool["environment"]["PGPOOL_FAILOVER_ON_BACKEND_ERROR"] == "on"
    assert pgpool["environment"]["PGPOOL_AUTO_FAILBACK"] == "yes"
    assert pgpool["environment"]["PGPOOL_POSTGRES_CUSTOM_USERS"] == "pms"
    assert "psql -h 127.0.0.1 -p 5432 -U postgres -d pms_db" in pgpool["healthcheck"]["test"][1]
    assert 'PGPASSWORD="$$PGPOOL_POSTGRES_PASSWORD"' in pgpool["healthcheck"]["test"][1]


def test_wsl_postgres_ha_start_script_mentions_repmgr_pgpool_and_local_db_url():
    script = (ROOT / "scripts" / "wsl_postgres_ha_stack_start.sh").read_text(encoding="utf-8")

    assert 'docker compose -f "$COMPOSE_FILE" up -d' in script
    assert "repmgr cluster show" in script
    assert 'show pool_nodes;' in script
    assert "localhost:15432/pms_db" in script
