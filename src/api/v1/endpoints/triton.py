from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from src.core.auth import get_current_user
from src.infrastructure.triton_client import TritonClient, TritonClientError
from src.services.triton_status_service import TritonStatusService

router = APIRouter(prefix="/triton", tags=["Triton"])


@router.get("/status", response_model=dict)
async def get_triton_status(current_user: dict = Depends(get_current_user)):
    service = TritonStatusService()
    return service.build_status()


@router.get("/health", response_model=dict)
async def get_triton_health(current_user: dict = Depends(get_current_user)):
    service = TritonStatusService()
    status = service.build_status()
    client = TritonClient(base_url=status["endpoint"], timeout_seconds=float(status.get("timeout_seconds", 5.0)))
    try:
        if hasattr(client, "healthcheck"):
            health = await client.healthcheck()
        else:
            health = await client.health()
        return {**status, "health": health, "reachable": True, "fallback_ready": True}
    except TritonClientError as e:
        raise HTTPException(status_code=503, detail=f"Triton健康检查失败: {e.error_code}")
