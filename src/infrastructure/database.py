"""
PostgreSQL异步数据库连接管理
============================

提供:
    - SQLAlchemy 2.0 异步引擎创建
    - Session工厂(同步/异步)
    - FastAPI依赖注入(get_db/get_async_session)
    - 连接池配置与生命周期管理
    - 数据库初始化(init_db)

D5-T014: PostgreSQL主从集群连接支持
    - 主节点: 读写操作
    - 从节点: 只读查询(负载均衡)
    - 会话级透明读写分流

使用方式:
    from src.infrastructure.database import get_async_session_factory, get_async_session

    factory = get_async_session_factory()
    async with factory() as session:
        ...

    @router.get("/items")
    async def list_items(db: AsyncSession = Depends(get_async_session)):
        result = await db.execute(select(Item))
        return result.scalars().all()
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.elements import TextClause

from src.core.tenant import get_default_tenant_id
from src.models.base import Base

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None  # type: ignore[assignment]

_engine: AsyncEngine | None = None
_read_engines: list[AsyncEngine] = []
_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_write_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_read_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_session_factory: sessionmaker | None = None
_resolved_database_url: str | None = None
_resolved_read_database_urls: list[str] = []
_database_backend_mode: str | None = None
_database_topology: dict[str, Any] | None = None
_sqlite_schema_ready = False
_read_engine_index = 0
_read_engine_lock = Lock()


def _build_sqlite_fallback_url() -> str:
    fallback_name = "fallback_postgres.sqlite3"
    if os.getenv("PYTEST_CURRENT_TEST"):
        fallback_name = f"fallback_postgres_pytest_{os.getpid()}.sqlite3"
    fallback_path = (Path("artifacts") / "runtime" / fallback_name).resolve()
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{fallback_path.as_posix()}"


def _unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _probe_asyncpg_url(database_url: str, timeout_seconds: float = 3.0) -> bool:
    if asyncpg is None:
        return False

    parsed = make_url(database_url)

    def _worker() -> bool:
        async def _connect() -> None:
            connection = await asyncpg.connect(
                user=parsed.username or "",
                password=parsed.password or "",
                database=(parsed.database or "").lstrip("/"),
                host=parsed.host or "localhost",
                port=int(parsed.port or 5432),
                timeout=timeout_seconds,
                ssl=False,
            )
            try:
                await connection.execute("SELECT 1")
            finally:
                await connection.close()

        try:
            asyncio.run(_connect())
            return True
        except Exception:
            return False

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_worker)
        return future.result(timeout=timeout_seconds + 2)
    except FuturesTimeoutError:
        return False
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _cache_database_topology(
    *,
    writer_url: str,
    reader_urls: list[str],
    backend_mode: str,
    read_write_split: bool,
) -> dict[str, Any]:
    global _resolved_database_url, _resolved_read_database_urls, _database_backend_mode, _database_topology

    _resolved_database_url = writer_url
    _resolved_read_database_urls = list(reader_urls)
    _database_backend_mode = backend_mode
    _database_topology = {
        "writer_url": writer_url,
        "reader_urls": list(reader_urls),
        "backend_mode": backend_mode,
        "read_write_split": read_write_split,
    }
    return dict(_database_topology)


def _resolve_database_topology() -> dict[str, Any]:
    global _database_topology
    if _database_topology is not None:
        return dict(_database_topology)

    from src.config.settings import get_settings
    from src.core.logging import get_logger

    settings = get_settings()
    logger = get_logger(__name__)

    writer_url = settings.database.write_url or settings.database.url
    configured_reader_urls = _unique_urls(settings.database.read_urls)
    split_requested = settings.database.read_write_split and bool(configured_reader_urls)
    probe_timeout = settings.database.probe_timeout_seconds

    if settings.app.environment == "production" or not writer_url.startswith("postgresql+asyncpg://"):
        reader_urls = configured_reader_urls if split_requested else [writer_url]
        backend_mode = "configured-rw-split" if split_requested else "configured"
        return _cache_database_topology(
            writer_url=writer_url,
            reader_urls=reader_urls or [writer_url],
            backend_mode=backend_mode,
            read_write_split=split_requested and bool(reader_urls),
        )

    if _probe_asyncpg_url(writer_url, probe_timeout):
        healthy_reader_urls: list[str] = []
        if split_requested:
            for read_url in configured_reader_urls:
                if _probe_asyncpg_url(read_url, probe_timeout):
                    healthy_reader_urls.append(read_url)
                else:
                    logger.warning("PostgreSQL read replica probe failed for %s; skipping it", read_url)

        if healthy_reader_urls:
            return _cache_database_topology(
                writer_url=writer_url,
                reader_urls=healthy_reader_urls,
                backend_mode="postgresql-rw-split",
                read_write_split=True,
            )

        if split_requested and settings.database.fallback_to_write_for_reads:
            logger.warning(
                "PostgreSQL read replicas are unavailable; falling back to writer endpoint %s for reads",
                writer_url,
            )
            return _cache_database_topology(
                writer_url=writer_url,
                reader_urls=[writer_url],
                backend_mode="postgresql-read-fallback",
                read_write_split=False,
            )

        return _cache_database_topology(
            writer_url=writer_url,
            reader_urls=[writer_url],
            backend_mode="postgresql",
            read_write_split=False,
        )

    sqlite_fallback_url = _build_sqlite_fallback_url()
    logger.warning(
        "PostgreSQL asyncpg probe failed for %s; falling back to %s",
        writer_url,
        sqlite_fallback_url,
    )
    return _cache_database_topology(
        writer_url=sqlite_fallback_url,
        reader_urls=[sqlite_fallback_url],
        backend_mode="sqlite-fallback",
        read_write_split=False,
    )


def _ensure_sqlite_fallback_schema() -> None:
    global _sqlite_schema_ready
    if _sqlite_schema_ready:
        return

    topology = _resolve_database_topology()
    if topology["backend_mode"] != "sqlite-fallback":
        return

    import src.models.models  # noqa: F401

    sync_url = topology["writer_url"].replace("+aiosqlite", "")
    engine = create_engine(sync_url)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()
    _sqlite_schema_ready = True


def _create_engine_for_url(database_url: str) -> AsyncEngine:
    from src.config.settings import get_settings

    settings = get_settings()
    if database_url.startswith("sqlite+aiosqlite://"):
        return create_async_engine(
            database_url,
            echo=settings.database.echo_sql,
        )

    if os.getenv("PYTEST_CURRENT_TEST"):
        return create_async_engine(
            database_url,
            poolclass=NullPool,
            echo=settings.database.echo_sql,
        )

    return create_async_engine(
        database_url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=settings.database.echo_sql,
    )


def _create_sync_engine():
    """创建同步引擎(用于Alembic迁移等同步场景)。"""
    from src.config.settings import get_settings

    settings = get_settings()
    topology = _resolve_database_topology()
    sync_url = topology["writer_url"].replace("+asyncpg", "").replace("+aiosqlite", "")

    if sync_url.startswith("sqlite:///"):
        return create_engine(sync_url, echo=settings.database.echo_sql)

    return create_engine(
        sync_url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        echo=settings.database.echo_sql,
    )


def _is_write_clause(clause: Any) -> bool:
    if clause is None:
        return False
    if isinstance(clause, (Insert, Update, Delete)):
        return True
    if isinstance(clause, TextClause):
        statement = clause.text.strip().lower()
        read_prefixes = ("select", "show", "with", "explain", "pragma")
        return not statement.startswith(read_prefixes)
    return False


class RoutingSession(Session):
    """基于语句类型自动路由到主库/从库的同步会话。"""

    def get_bind(self, mapper: Any = None, clause: Any = None, **kwargs: Any) -> Any:
        forced_role = self.info.get("route_role")
        if forced_role == "write":
            return get_engine().sync_engine
        if forced_role == "read":
            return get_read_engine().sync_engine

        if self.info.get("pinned_to_writer"):
            return get_engine().sync_engine

        if self._flushing or _is_write_clause(clause):
            self.info["pinned_to_writer"] = True
            return get_engine().sync_engine

        return get_read_engine().sync_engine


def get_database_topology() -> dict[str, Any]:
    """返回数据库拓扑信息（脱敏前）。"""
    return _resolve_database_topology()


def get_engine() -> AsyncEngine:
    """
    获取全局写库异步引擎单例。

    Returns:
        AsyncEngine: 全局写库异步引擎
    """
    global _engine
    if _engine is None:
        topology = _resolve_database_topology()
        _engine = _create_engine_for_url(topology["writer_url"])
        from src.config.settings import get_settings
        from src.core.logging import get_logger

        logger = get_logger(__name__)
        settings = get_settings()
        logger.info(
            "✅ PostgreSQL写库引擎已创建 (pool=%s, mode=%s)",
            settings.database.pool_size,
            topology["backend_mode"],
        )
    return _engine


def get_read_engines() -> list[AsyncEngine]:
    """获取只读查询引擎列表。"""
    global _read_engines
    if _read_engines:
        return _read_engines

    topology = _resolve_database_topology()
    writer_engine = get_engine()
    writer_url = topology["writer_url"]
    read_engines: list[AsyncEngine] = []
    for read_url in topology["reader_urls"]:
        if read_url == writer_url:
            read_engines.append(writer_engine)
        else:
            read_engines.append(_create_engine_for_url(read_url))

    _read_engines = read_engines or [writer_engine]
    return _read_engines


def get_read_engine() -> AsyncEngine:
    """按轮询策略返回一个读引擎。"""
    global _read_engine_index

    engines = get_read_engines()
    if len(engines) == 1:
        return engines[0]

    with _read_engine_lock:
        engine = engines[_read_engine_index % len(engines)]
        _read_engine_index += 1
    return engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    获取异步Session工厂。

    默认使用透明读写分离路由。
    """
    global _async_session_factory
    if _async_session_factory is None:
        _ensure_sqlite_fallback_schema()
        get_engine()
        get_read_engines()
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            sync_session_class=RoutingSession,
            expire_on_commit=False,
        )
    return _async_session_factory


def get_write_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取强制走写库的异步Session工厂。"""
    global _write_async_session_factory
    if _write_async_session_factory is None:
        _ensure_sqlite_fallback_schema()
        _write_async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            sync_session_class=RoutingSession,
            expire_on_commit=False,
            info={"route_role": "write"},
        )
    return _write_async_session_factory


def get_read_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取强制走读库的异步Session工厂。"""
    global _read_async_session_factory
    if _read_async_session_factory is None:
        _ensure_sqlite_fallback_schema()
        get_read_engines()
        _read_async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            sync_session_class=RoutingSession,
            expire_on_commit=False,
            info={"route_role": "read"},
        )
    return _read_async_session_factory


# 向后兼容别名
AsyncSessionLocal = get_async_session_factory


def get_sync_session_factory() -> sessionmaker:
    """获取同步Session工厂(Alembic迁移用)。"""
    global _sync_session_factory
    if _sync_session_factory is None:
        engine = _create_sync_engine()
        _sync_session_factory = sessionmaker(bind=engine)
    return _sync_session_factory


# 向后兼容别名（同步）
SessionLocal = get_sync_session_factory


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI异步数据库会话依赖注入。

    默认使用自动读写路由，会话一旦发生写操作就固定到主库。
    """
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_read_async_session() -> AsyncGenerator[AsyncSession, None]:
    """显式获取只读会话。"""
    factory = get_read_async_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_write_async_session() -> AsyncGenerator[AsyncSession, None]:
    """显式获取写会话。"""
    factory = get_write_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_db() -> Generator:
    """
    同步数据库会话依赖注入(用于非异步场景)。

    同步场景统一连接写库。
    """
    factory = get_sync_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _apply_non_production_schema_patches(engine: AsyncEngine) -> None:
    """非生产环境最小 schema patch：为遗留表补当前阶段所需列。"""
    if engine.dialect.name == "sqlite":
        return

    default_tenant_id = get_default_tenant_id()
    statements = [
        f"ALTER TABLE selection_tasks ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE selection_results ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        f"ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tenant_id UUID DEFAULT '{default_tenant_id}' NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_task_tenant_status_priority ON selection_tasks (tenant_id, status, priority)",
        "CREATE INDEX IF NOT EXISTS ix_task_tenant_status_created ON selection_tasks (tenant_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_agent_run_tenant_task_type ON agent_runs (tenant_id, task_id, agent_type)",
        "CREATE INDEX IF NOT EXISTS ix_agent_run_tenant_status_time ON agent_runs (tenant_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_base_tenant_name ON knowledge_bases (tenant_id, name)",
        "CREATE INDEX IF NOT EXISTS ix_document_tenant_status_created ON documents (tenant_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_chunk_tenant_document_index ON document_chunks (tenant_id, document_id, chunk_index)",
        "CREATE INDEX IF NOT EXISTS ix_audit_tenant_action_time ON audit_logs (tenant_id, action, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_audit_tenant_user_time ON audit_logs (tenant_id, username, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_audit_tenant_target_time ON audit_logs (tenant_id, target_type, target_id, occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_sync_event_tenant_status_created ON data_sync_events (tenant_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_sync_event_tenant_topic_created ON data_sync_events (tenant_id, topic, created_at)",
    ]

    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def init_db():
    """
    初始化数据库(创建表结构)。

    开发环境使用 create_all + schema patch；
    生产环境使用 Alembic 迁移。
    """
    from src.config.settings import get_settings
    from src.core.logging import get_logger

    logger = get_logger(__name__)
    settings = get_settings()

    engine = get_engine()

    import src.models.models  # noqa: F401

    if settings.app.environment != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _apply_non_production_schema_patches(engine)
        logger.info("📦 非生产环境数据库表结构已初始化(create_all + schema patch)")
    else:
        logger.info("⏭️ production 环境跳过自动建表，请使用 Alembic 迁移")


async def close_db():
    """关闭数据库连接池。"""
    global _engine
    global _read_engines
    global _async_session_factory
    global _write_async_session_factory
    global _read_async_session_factory
    global _sync_session_factory
    global _resolved_database_url
    global _resolved_read_database_urls
    global _database_backend_mode
    global _database_topology
    global _sqlite_schema_ready
    global _read_engine_index

    disposed: set[int] = set()
    for engine in [*(_read_engines or []), _engine]:
        if engine is not None and id(engine) not in disposed:
            await engine.dispose()
            disposed.add(id(engine))

    _engine = None
    _read_engines = []
    _async_session_factory = None
    _write_async_session_factory = None
    _read_async_session_factory = None
    _sync_session_factory = None
    _resolved_database_url = None
    _resolved_read_database_urls = []
    _database_backend_mode = None
    _database_topology = None
    _sqlite_schema_ready = False
    _read_engine_index = 0

    from src.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("🔌 数据库连接池已关闭")


def _pool_snapshot(engine: AsyncEngine) -> dict[str, Any]:
    pool = engine.pool
    snapshot: dict[str, Any] = {
        "url_masked": str(engine.url),
        "dialect": engine.dialect.name,
    }
    for attr_name, key in (
        ("size", "pool_size"),
        ("checkedin", "pool_checked_in"),
        ("checkedout", "pool_checked_out"),
        ("overflow", "pool_overflow"),
    ):
        attr = getattr(pool, attr_name, None)
        if callable(attr):
            try:
                snapshot[key] = attr()
            except Exception:
                snapshot[key] = None
    return snapshot


async def _check_engine_health(engine: AsyncEngine, role: str) -> dict[str, Any]:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
        return {
            "role": role,
            "status": "healthy",
            **_pool_snapshot(engine),
        }
    except Exception as exc:
        return {
            "role": role,
            "status": "unhealthy",
            "error": str(exc),
            **_pool_snapshot(engine),
        }


async def check_db_health() -> dict:
    """
    检查数据库健康状态(D4验收标准)。

    执行简单 SELECT 1 验证写库和读库连接可用性，
    并返回当前主从路由拓扑。
    """
    from src.core.logging import get_logger

    logger = get_logger(__name__)
    topology = _resolve_database_topology()

    writer_health = await _check_engine_health(get_engine(), "writer")

    reader_health: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, engine in enumerate(get_read_engines(), start=1):
        if id(engine) in seen:
            continue
        seen.add(id(engine))
        item = await _check_engine_health(engine, "reader")
        item["index"] = index
        reader_health.append(item)

    is_healthy = writer_health["status"] == "healthy" and all(
        item["status"] == "healthy" for item in reader_health
    )

    if not is_healthy:
        logger.error(
            "❌ 数据库健康检查失败: writer=%s readers=%s",
            writer_health.get("status"),
            [item.get("status") for item in reader_health],
        )

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "backend_mode": topology["backend_mode"],
        "read_write_split": topology["read_write_split"],
        "writer": writer_health,
        "readers": reader_health,
        "reader_count": len(reader_health),
        "url_masked": writer_health.get("url_masked"),
        "pool_size": writer_health.get("pool_size"),
        "pool_checked_in": writer_health.get("pool_checked_in"),
        "pool_checked_out": writer_health.get("pool_checked_out"),
        "pool_overflow": writer_health.get("pool_overflow"),
        "writer_url": writer_health.get("url_masked"),
        "reader_urls": [item.get("url_masked") for item in reader_health],
    }
