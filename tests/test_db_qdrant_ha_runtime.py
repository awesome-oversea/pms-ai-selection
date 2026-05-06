from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import text


def test_database_settings_parse_rw_split_envs(monkeypatch):
    from src.config.settings import get_settings

    monkeypatch.setenv("DB_WRITE_URL", "postgresql+asyncpg://pms:secret@localhost:15432/pms_db")
    monkeypatch.setenv(
        "DB_READ_URLS",
        "postgresql+asyncpg://pms:secret@localhost:15436/pms_db,postgresql+asyncpg://pms:secret@localhost:15437/pms_db",
    )
    monkeypatch.setenv("DB_READ_WRITE_SPLIT", "true")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.database.write_url == "postgresql+asyncpg://pms:secret@localhost:15432/pms_db"
    assert settings.database.read_urls == [
        "postgresql+asyncpg://pms:secret@localhost:15436/pms_db",
        "postgresql+asyncpg://pms:secret@localhost:15437/pms_db",
    ]
    assert settings.database.read_write_split is True

    get_settings.cache_clear()


def test_qdrant_settings_parse_cluster_envs(monkeypatch):
    from src.config.settings import get_settings

    monkeypatch.setenv("QDRANT_WRITE_URL", "http://localhost:16333")
    monkeypatch.setenv("QDRANT_READ_URLS", "http://localhost:16433,http://localhost:16533")
    monkeypatch.setenv("QDRANT_CLUSTER_ENABLED", "true")
    monkeypatch.setenv("QDRANT_REPLICATION_FACTOR", "2")
    monkeypatch.setenv("QDRANT_WRITE_CONSISTENCY_FACTOR", "2")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.qdrant.write_url == "http://localhost:16333"
    assert settings.qdrant.read_urls == ["http://localhost:16433", "http://localhost:16533"]
    assert settings.qdrant.cluster_enabled is True
    assert settings.qdrant.replication_factor == 2
    assert settings.qdrant.write_consistency_factor == 2

    get_settings.cache_clear()


def test_routing_session_pins_to_writer_after_write(monkeypatch):
    import src.infrastructure.database as database_module

    writer_engine = SimpleNamespace(sync_engine="writer-sync")
    reader_engine = SimpleNamespace(sync_engine="reader-sync")

    monkeypatch.setattr(database_module, "get_engine", lambda: writer_engine)
    monkeypatch.setattr(database_module, "get_read_engine", lambda: reader_engine)

    session = database_module.RoutingSession()

    assert session.get_bind(clause=text("SELECT 1")) == "reader-sync"
    assert session.get_bind(clause=text("UPDATE tasks SET status='done'")) == "writer-sync"
    assert session.get_bind(clause=text("SELECT 2")) == "writer-sync"


def test_resolve_database_topology_prefers_healthy_replicas(monkeypatch):
    import src.infrastructure.database as database_module

    database_module._database_topology = None
    database_module._resolved_database_url = None
    database_module._resolved_read_database_urls = []
    database_module._database_backend_mode = None

    settings = SimpleNamespace(
        app=SimpleNamespace(environment="development"),
        database=SimpleNamespace(
            url="postgresql+asyncpg://pms:secret@localhost:15432/pms_db",
            write_url="postgresql+asyncpg://pms:secret@localhost:15432/pms_db",
            read_urls=[
                "postgresql+asyncpg://pms:secret@localhost:15436/pms_db",
                "postgresql+asyncpg://pms:secret@localhost:15437/pms_db",
            ],
            read_write_split=True,
            fallback_to_write_for_reads=True,
            probe_timeout_seconds=0.1,
        ),
    )

    monkeypatch.setattr("src.config.settings.get_settings", lambda: settings)
    monkeypatch.setattr(
        database_module,
        "_probe_asyncpg_url",
        lambda url, timeout_seconds=3.0: url.endswith(":15432/pms_db") or url.endswith(":15436/pms_db"),
    )

    topology = database_module.get_database_topology()
    assert topology["backend_mode"] == "postgresql-rw-split"
    assert topology["writer_url"].endswith(":15432/pms_db")
    assert topology["reader_urls"] == ["postgresql+asyncpg://pms:secret@localhost:15436/pms_db"]
    assert topology["read_write_split"] is True


def test_qdrant_topology_promotes_available_node(monkeypatch):
    import src.infrastructure.qdrant as qdrant_module

    qdrant_module._qdrant_topology = None
    qdrant_module._qdrant_mode = None

    settings = SimpleNamespace(
        app=SimpleNamespace(environment="development"),
        qdrant=SimpleNamespace(
            host="localhost",
            port=6333,
            url="http://localhost:16333",
            write_url="http://localhost:16333",
            read_urls=["http://localhost:16433", "http://localhost:16533"],
            cluster_enabled=True,
            api_key=None,
            timeout_seconds=1.0,
            prefer_local_fallback=True,
        ),
    )

    monkeypatch.setattr(qdrant_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        qdrant_module,
        "_can_use_remote_qdrant",
        lambda endpoint, timeout_seconds: endpoint in {"http://localhost:16433", "http://localhost:16533"},
    )

    topology = qdrant_module.get_qdrant_topology()
    assert topology["writer_endpoint"] == "http://localhost:16433"
    assert topology["read_endpoints"] == ["http://localhost:16433", "http://localhost:16533"]
    assert topology["mode"] == "cluster-rw-split"


@pytest.mark.asyncio
async def test_qdrant_cluster_client_routes_reads_and_writes():
    import src.infrastructure.qdrant as qdrant_module

    events: list[tuple[str, str]] = []

    class _Client:
        def __init__(self, name: str):
            self.name = name

        async def get_collections(self):
            events.append((self.name, "get_collections"))
            return SimpleNamespace(collections=[])

        async def upsert(self, **kwargs):
            events.append((self.name, "upsert"))
            return SimpleNamespace(operation_id=1)

        async def close(self):
            events.append((self.name, "close"))

    writer = _Client("writer")
    reader_a = _Client("reader-a")
    reader_b = _Client("reader-b")

    client = qdrant_module.QdrantClusterClient(
        writer_client=writer,
        writer_endpoint="http://writer",
        read_clients=[reader_a, reader_b],
        read_endpoints=["http://reader-a", "http://reader-b"],
        mode="cluster-rw-split",
    )

    await client.get_collections()
    await client.get_collections()
    await client.upsert(collection_name="demo", points=[])
    await client.close()

    assert ("reader-a", "get_collections") in events
    assert ("reader-b", "get_collections") in events
    assert ("writer", "upsert") in events
