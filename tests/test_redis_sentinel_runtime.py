from __future__ import annotations

import asyncio


def test_redis_settings_support_sentinel_nodes_csv(monkeypatch):
    monkeypatch.setenv("REDIS_SENTINEL_ENABLED", "true")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")
    monkeypatch.setenv("REDIS_SENTINEL_NODES", "localhost:26379,localhost:26380,localhost:26381")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.redis.sentinel_enabled is True
    assert settings.redis.sentinel_master_name == "mymaster"
    assert settings.redis.sentinel_nodes == [
        "localhost:26379",
        "localhost:26380",
        "localhost:26381",
    ]

    monkeypatch.delenv("REDIS_SENTINEL_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_MASTER_NAME", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_NODES", raising=False)
    get_settings.cache_clear()


def test_get_redis_connection_uses_sentinel_master(monkeypatch):
    import src.infrastructure.redis as redis_module
    from src.config.settings import get_settings

    monkeypatch.setenv("REDIS_SENTINEL_ENABLED", "true")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")
    monkeypatch.setenv("REDIS_SENTINEL_NODES", "redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/2")
    get_settings.cache_clear()

    calls: dict[str, object] = {}
    fake_client = object()

    class _FakeSentinel:
        def __init__(self, sentinels, min_other_sentinels=0, sentinel_kwargs=None, **connection_kwargs):
            calls["sentinels"] = sentinels
            calls["min_other_sentinels"] = min_other_sentinels
            calls["sentinel_kwargs"] = sentinel_kwargs
            calls["connection_kwargs"] = connection_kwargs

        def master_for(self, service_name, redis_class=None, **kwargs):
            calls["master_for"] = {
                "service_name": service_name,
                "redis_class": redis_class,
                "kwargs": kwargs,
            }
            return fake_client

    monkeypatch.setattr(redis_module, "RedisSentinel", _FakeSentinel)
    redis_module._redis_client = None
    redis_module._redis_sentinel = None

    client = redis_module.get_redis_connection()

    assert client is fake_client
    assert calls["sentinels"] == [
        ("redis-sentinel-1", 26379),
        ("redis-sentinel-2", 26379),
        ("redis-sentinel-3", 26379),
    ]
    assert calls["min_other_sentinels"] == 1
    assert calls["connection_kwargs"]["db"] == 2
    assert calls["master_for"]["service_name"] == "mymaster"

    redis_module._redis_client = None
    redis_module._redis_sentinel = None
    monkeypatch.delenv("REDIS_SENTINEL_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_MASTER_NAME", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()


def test_check_redis_health_reports_sentinel_metadata(monkeypatch):
    import src.infrastructure.redis as redis_module
    from src.config.settings import get_settings

    monkeypatch.setenv("REDIS_SENTINEL_ENABLED", "true")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")
    monkeypatch.setenv("REDIS_SENTINEL_NODES", "localhost:26379,localhost:26380,localhost:26381")
    get_settings.cache_clear()

    class _FakeRedis:
        async def ping(self):
            return True

        async def info(self):
            return {
                "connected_clients": 3,
                "used_memory_human": "1M",
                "uptime_in_seconds": 12,
                "redis_version": "7.4.0",
            }

    class _FakeSentinelManager:
        async def discover_master(self, service_name):
            assert service_name == "mymaster"
            return ("redis-master", 6379)

    monkeypatch.setattr(redis_module, "get_redis_connection", lambda: _FakeRedis())
    redis_module._redis_sentinel = _FakeSentinelManager()

    result = asyncio.run(redis_module.check_redis_health())

    assert result["status"] == "healthy"
    assert result["topology_mode"] == "sentinel"
    assert result["sentinel_master_name"] == "mymaster"
    assert result["sentinel_node_count"] == 3
    assert result["master_address"] == "redis-master:6379"

    redis_module._redis_sentinel = None
    monkeypatch.delenv("REDIS_SENTINEL_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_MASTER_NAME", raising=False)
    monkeypatch.delenv("REDIS_SENTINEL_NODES", raising=False)
    get_settings.cache_clear()
