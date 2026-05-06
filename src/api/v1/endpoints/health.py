"""
健康检查API端点
================

提供应用级健康、就绪、存活检查接口。
用于:
- 本地自检
- Docker HEALTHCHECK
- Kubernetes liveness/readiness probe
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from src.infrastructure.database import check_db_health
from src.infrastructure.qdrant import check_qdrant_health
from src.infrastructure.redis import check_redis_health

router = APIRouter()


@router.get("/health")
async def health_check():
    """综合健康信息，用于人工查看当前服务与依赖状态。"""
    db = await check_db_health()
    redis = await check_redis_health()
    qdrant = await check_qdrant_health()

    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "pms-ai-selection",
        "checks": {
            "database": db.get("status", "unknown"),
            "redis": redis.get("status", "unknown"),
            "qdrant": qdrant.get("status", "unknown"),
        },
    }


@router.get("/ready")
async def readiness_check(response: Response):
    """就绪检查，仅当关键依赖可用时返回 200。"""
    db = await check_db_health()
    redis = await check_redis_health()
    qdrant = await check_qdrant_health()

    readiness_status = {
        "database": db.get("status") == "healthy",
        "redis": redis.get("status") == "healthy",
        "qdrant": qdrant.get("status") == "healthy",
    }
    critical_dependencies = {
        "database": readiness_status["database"],
        "redis": readiness_status["redis"],
    }

    all_ready = all(critical_dependencies.values())
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": readiness_status,
    }


@router.get("/live")
async def liveness_check():
    """存活检查，仅表示应用进程存活。"""
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat(),
    }
