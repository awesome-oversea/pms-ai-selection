"""
Redis connection management.

Supports standalone Redis, Redis Cluster, and Redis Sentinel.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import redis.asyncio as aioredis
from redis.asyncio.sentinel import Sentinel as RedisSentinel

from src.config.settings import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: aioredis.Redis | None = None
_redis_sentinel: RedisSentinel | None = None


def _parse_host_ports(nodes: list[str], default_port: int) -> list[tuple[str, int]]:
    parsed_nodes: list[tuple[str, int]] = []
    for node in nodes:
        host, separator, raw_port = node.strip().partition(":")
        if not host:
            continue
        port = default_port
        if separator and raw_port:
            try:
                port = int(raw_port)
            except ValueError:
                logger.warning("Ignoring invalid Redis node port: %s", node)
                continue
        parsed_nodes.append((host, port))
    return parsed_nodes


def _build_redis_connection_kwargs() -> dict[str, object]:
    settings = get_settings().redis
    parsed = urlparse(settings.url)
    query = parse_qs(parsed.query)

    db = settings.sentinel_db
    if parsed.path and parsed.path != "/":
        try:
            db = int(parsed.path.strip("/"))
        except ValueError:
            logger.warning("Unable to parse Redis DB index from REDIS_URL=%s", settings.url)

    kwargs: dict[str, object] = {
        "db": db,
        "decode_responses": True,
        "max_connections": settings.max_connections,
        "health_check_interval": 30,
    }
    if parsed.username:
        kwargs["username"] = parsed.username
    if parsed.password:
        kwargs["password"] = parsed.password
    if parsed.scheme == "rediss":
        kwargs["ssl"] = True
    if query.get("socket_timeout"):
        try:
            kwargs["socket_timeout"] = float(query["socket_timeout"][0])
        except ValueError:
            logger.warning("Ignoring invalid Redis socket_timeout in REDIS_URL=%s", settings.url)
    return kwargs


def _create_sentinel_client() -> aioredis.Redis:
    settings = get_settings().redis
    sentinel_nodes = _parse_host_ports(settings.sentinel_nodes, default_port=26379)
    if not sentinel_nodes:
        raise ValueError("REDIS_SENTINEL_ENABLED=true but REDIS_SENTINEL_NODES is empty")

    connection_kwargs = _build_redis_connection_kwargs()
    sentinel_kwargs: dict[str, object] = {
        "socket_timeout": connection_kwargs.get("socket_timeout", 1.0),
    }
    if settings.sentinel_username:
        sentinel_kwargs["username"] = settings.sentinel_username
    if settings.sentinel_password:
        sentinel_kwargs["password"] = settings.sentinel_password

    global _redis_sentinel
    _redis_sentinel = RedisSentinel(
        sentinel_nodes,
        min_other_sentinels=1 if len(sentinel_nodes) > 1 else 0,
        sentinel_kwargs=sentinel_kwargs,
        **connection_kwargs,
    )
    logger.info(
        "Using Redis Sentinel mode (master=%s, sentinels=%s)",
        settings.sentinel_master_name,
        settings.sentinel_nodes,
    )
    return _redis_sentinel.master_for(
        settings.sentinel_master_name,
        redis_class=aioredis.Redis,
    )


def _create_redis_client() -> aioredis.Redis:
    settings = get_settings()

    if settings.redis.sentinel_enabled:
        return _create_sentinel_client()

    if settings.redis.cluster_mode and settings.redis.cluster_nodes:
        logger.info("Using Redis Cluster mode")
        from redis.asyncio.cluster import RedisCluster

        return RedisCluster(
            startup_nodes=settings.redis.cluster_nodes,
            decode_responses=True,
            max_connections=settings.redis.max_connections,
        )

    logger.info("Using standalone Redis mode: %s", settings.redis.url)
    return aioredis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=True,
        health_check_interval=30,
    )


def get_redis_connection() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = _create_redis_client()
        settings = get_settings().redis
        logger.info(
            "Redis client created (max_conn=%s, cluster=%s, sentinel=%s)",
            settings.max_connections,
            settings.cluster_mode,
            settings.sentinel_enabled,
        )
    return _redis_client


redis_client = property(lambda self: get_redis_connection())


@asynccontextmanager
async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis_connection()
    try:
        yield client
    except aioredis.ConnectionError as exc:
        logger.error("Redis connection error: %s", exc)
        raise


class CacheService:
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        if ttl_seconds is not None:
            return await self._redis.setex(key, ttl_seconds, value)
        return await self._redis.set(key, value)

    async def delete(self, key: str) -> int:
        return await self._redis.delete(key)

    async def exists(self, *keys: str) -> int:
        return await self._redis.exists(*keys)

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        return await self._redis.expire(key, ttl_seconds)

    async def ttl(self, key: str) -> int:
        return await self._redis.ttl(key)

    async def increment(self, key: str, amount: int = 1) -> int:
        return await self._redis.incrby(key, amount)

    async def hget(self, name: str, key: str) -> str | None:
        return await self._redis.hget(name, key)

    async def hset(self, name: str, key: str, value: str) -> bool:
        return await self._redis.hset(name, key, value)

    async def hgetall(self, name: str) -> dict:
        return await self._redis.hgetall(name)

    async def lpush(self, key: str, *values: str) -> int:
        return await self._redis.lpush(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list:
        return await self._redis.lrange(key, start, end)

    async def close(self) -> None:
        await self._redis.aclose()


async def check_redis_health() -> dict:
    settings = get_settings().redis
    client = get_redis_connection()

    try:
        pong = await client.ping()
        info = await client.info()
        payload = {
            "status": "healthy" if pong else "unhealthy",
            "ping": "pong" if pong else "failed",
            "connected_clients": info.get("connected_clients", "N/A"),
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "redis_version": info.get("redis_version", "N/A"),
            "topology_mode": "single",
        }
        if settings.cluster_mode:
            payload["topology_mode"] = "cluster"
        if settings.sentinel_enabled:
            payload["topology_mode"] = "sentinel"
            payload["sentinel_master_name"] = settings.sentinel_master_name
            payload["sentinel_node_count"] = len(settings.sentinel_nodes)
            if _redis_sentinel is not None:
                host, port = await _redis_sentinel.discover_master(settings.sentinel_master_name)
                payload["master_address"] = f"{host}:{port}"
        return payload
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "error": str(exc),
            "topology_mode": "sentinel" if settings.sentinel_enabled else "cluster" if settings.cluster_mode else "single",
        }


async def close_redis() -> None:
    global _redis_client, _redis_sentinel

    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except RuntimeError as exc:
            if "Event loop is closed" not in str(exc):
                raise
            logger.warning("Skipping Redis pool cleanup on closed event loop: %s", exc)
        finally:
            _redis_client = None
            _redis_sentinel = None
        logger.info("Redis connection closed")
