"""
FastAPI应用主入口
=================

AI选品系统后端服务启动入口。
负责初始化日志、依赖连接、追踪和路由。
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.config.settings import get_settings
from src.core.api_contract import ApiContractMiddleware, build_error_envelope, install_openapi_envelope
from src.core.exceptions import PMSBaseException
from src.core.logging import get_logger, setup_logger
from src.core.waf import RequestWAFMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    setup_logger(
        log_level=settings.app.log_level,
        log_dir=None if settings.app.debug else Path("./logs"),
    )

    logger = get_logger(__name__)
    logger.info(f"{settings.app.name} v{settings.app.version} 正在启动")
    logger.info(f"环境: {settings.app.environment}")
    logger.info(f"调试模式: {settings.app.debug}")

    dependency_status: dict[str, str] = {
        "database": "not_initialized",
        "redis": "not_initialized",
        "qdrant": "not_initialized",
        "tracing": "not_initialized",
    }

    try:
        from src.infrastructure.database import get_engine, init_db

        get_engine()
        await init_db()
        dependency_status["database"] = "ready"
        logger.info("数据库初始化完成")
    except Exception as e:
        dependency_status["database"] = f"failed: {e}"
        logger.warning(f"数据库初始化失败，降级以内存/本地兼容路径继续启动: {e}")

    try:
        from src.infrastructure.redis import get_redis_connection

        get_redis_connection()
        dependency_status["redis"] = "ready"
        logger.info("Redis客户端已创建")
    except Exception as e:
        dependency_status["redis"] = f"failed: {e}"
        logger.warning(f"Redis初始化失败: {e}")

    try:
        from src.infrastructure.qdrant import get_qdrant_client

        await asyncio.wait_for(asyncio.to_thread(get_qdrant_client), timeout=8)
        dependency_status["qdrant"] = "ready"
        logger.info("Qdrant客户端已创建")
    except Exception as e:
        dependency_status["qdrant"] = f"failed: {e}"
        logger.warning(f"Qdrant初始化失败: {e}")

    try:
        from src.core.tracing import setup_tracing

        setup_tracing(
            app,
            service_name=settings.app.name,
            environment=settings.app.environment,
        )
        dependency_status["tracing"] = "ready"
    except Exception as e:
        dependency_status["tracing"] = f"failed: {e}"
        logger.warning(f"OpenTelemetry 初始化失败: {e}")

    logger.info(f"依赖状态摘要: {dependency_status}")

    bi_kpi_worker_task = None
    try:
        if settings.selection_execution.enable_bi_daily_kpi_scheduler:
            from src.workers.bi_kpi_worker import BIDailyKpiWorker

            bi_kpi_worker = BIDailyKpiWorker()
            bi_kpi_worker_task = asyncio.create_task(bi_kpi_worker.run_forever())
            logger.info("BI每日KPI调度器已启动")
    except Exception as e:
        logger.warning(f"BI每日KPI调度器启动失败: {e}")

    yield

    logger.info("应用正在关闭，释放资源")

    if bi_kpi_worker_task is not None:
        bi_kpi_worker_task.cancel()
        with suppress(Exception):
            await bi_kpi_worker_task

    try:
        from src.infrastructure.database import close_db

        await close_db()
    except Exception as e:
        logger.warning(f"数据库关闭异常: {e}")

    try:
        from src.infrastructure.redis import close_redis

        await close_redis()
    except Exception as e:
        logger.warning(f"Redis关闭异常: {e}")

    try:
        from src.infrastructure.qdrant import close_qdrant

        await close_qdrant()
    except Exception as e:
        logger.warning(f"Qdrant关闭异常: {e}")

    try:
        from src.infrastructure.kafka import close_kafka

        await close_kafka()
    except Exception:
        pass

    logger.info("所有资源已释放，应用已停止")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        description=(
            "跨境电商 AI 选品系统当前开发基线。\n\n"
            "说明：当前仓库为单体原型收敛阶段，README 与阶段验收文档优先于目标态方案。"
        ),
        version=settings.app.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.security.secret_key,
        same_site="lax",
        https_only=settings.app.environment == "production",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Trace-ID"],
    )

    try:
        from src.infrastructure.tracing import TraceMiddleware

        app.add_middleware(TraceMiddleware)
    except Exception:
        pass

    try:
        from src.core.rate_limit import RateLimitMiddleware

        app.add_middleware(RateLimitMiddleware)
    except Exception:
        pass

    app.add_middleware(RequestWAFMiddleware)
    app.add_middleware(ApiContractMiddleware, api_prefix=settings.app.api_prefix)

    @app.exception_handler(PMSBaseException)
    async def pms_exception_handler(request, exc: PMSBaseException):
        return JSONResponse(
            status_code=exc.http_status,
            content=build_error_envelope(
                request=request,
                message=exc.message,
                error_code=exc.error_code,
                detail=exc.detail or exc.message,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        if exc.status_code == 401:
            error_code = "AUTH_FAILED"
        elif exc.status_code == 403:
            error_code = "FORBIDDEN"
        elif exc.status_code == 404:
            error_code = "NOT_FOUND"
        elif exc.status_code == 422:
            error_code = "VALIDATION_ERROR"
        elif exc.status_code == 429:
            error_code = "QUOTA_EXCEEDED"
        elif exc.status_code >= 500:
            error_code = "DEPENDENCY_UNAVAILABLE"
        else:
            error_code = "HTTP_ERROR"
        detail = exc.detail
        message = detail if isinstance(detail, str) else "请求处理失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_envelope(
                request=request,
                message=message,
                error_code=error_code,
                detail=detail,
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=build_error_envelope(
                request=request,
                message="系统内部错误",
                error_code="INTERNAL_ERROR",
                detail=str(exc),
            ),
        )

    @app.get("/health", tags=["系统"])
    async def root_health_check():
        from src.infrastructure.database import check_db_health
        from src.infrastructure.qdrant import check_qdrant_health
        from src.infrastructure.redis import check_redis_health

        db = await check_db_health()
        redis = await check_redis_health()
        qdrant = await check_qdrant_health()
        return {
            "status": "healthy",
            "service": settings.app.name,
            "version": settings.app.version,
            "checks": {
                "database": db.get("status", "unknown"),
                "redis": redis.get("status", "unknown"),
                "qdrant": qdrant.get("status", "unknown"),
            },
        }

    @app.get("/ready", tags=["系统"])
    async def root_ready_check(response: Response):
        from src.infrastructure.database import check_db_health
        from src.infrastructure.qdrant import check_qdrant_health
        from src.infrastructure.redis import check_redis_health

        db = await check_db_health()
        redis = await check_redis_health()
        qdrant = await check_qdrant_health()
        checks = {
            "database": db.get("status") == "healthy",
            "redis": redis.get("status") == "healthy",
            "qdrant": qdrant.get("status") == "healthy",
        }
        critical_checks = {
            "database": checks["database"],
            "redis": checks["redis"],
        }
        ready = all(critical_checks.values())
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ready" if ready else "not_ready", "checks": checks}

    @app.get("/live", tags=["系统"])
    async def root_live_check():
        return {"status": "alive", "service": settings.app.name}

    @app.get("/v2/health/ready", tags=["Triton兼容"])
    async def triton_compatible_ready_check():
        return {
            "ready": True,
            "mode": "local-compatible",
            "service": settings.app.name,
            "capabilities": ["rerank"],
        }

    @app.post("/v1/rerank", tags=["Triton兼容"])
    async def triton_compatible_rerank(payload: dict):
        from src.services.rerank import RerankService

        query = str(payload.get("query") or "")
        documents = payload.get("documents") or []
        if not isinstance(documents, list) or any(not isinstance(item, str) for item in documents):
            raise HTTPException(status_code=422, detail="documents 必须为字符串数组")
        top_k = int(payload.get("top_k") or 5)
        service = RerankService(prefer_triton=False)
        results = service.score_documents_locally(query, documents, min(top_k, len(documents)) if documents else 0)
        return {
            "mode": "local-compatible",
            "model": service.model_name,
            "results": results,
        }

    @app.get("/", tags=["系统"])
    async def root():
        return {
            "service": settings.app.name,
            "frontend": "Next.js 14 App Router",
            "workbench_url": "http://localhost:3000/workbench/selection",
            "legacy_jinja_routes": "redirected",
        }

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["监控"])
    except ImportError:
        pass

    try:
        from src.core.metrics import init_app_info

        init_app_info(
            name=settings.app.name,
            version=settings.app.version,
            environment=settings.app.environment,
        )
    except Exception:
        pass

    from src.api.v1.router import api_router

    app.include_router(api_router, prefix=settings.app.api_prefix)

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    legacy_static_dir = Path(__file__).resolve().parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    elif legacy_static_dir.exists():
        app.mount("/static", StaticFiles(directory=legacy_static_dir), name="static")

    try:
        from src.web.routes import router as web_router

        app.include_router(web_router)
    except Exception:
        pass

    install_openapi_envelope(app, api_prefix=settings.app.api_prefix)

    return app


app = create_app()
