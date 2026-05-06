from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.feature_engine import FeatureEngine
from src.infrastructure.kafka import drain_memory_messages
from src.models.enums import ERPSystemType
from src.services.crawl_platform_service import CrawlPlatformService
from src.services.data_sync_service import DataSyncService
from src.services.erp_integration_service import ErpIntegrationService
from src.services.local_feedback_loop_service import LocalFeedbackLoopService
from src.workers.data_sync_consumer import DataSyncConsumer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integration", tags=["ERP集成"])


class OmsConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/products")
    outbound_path: str = Field(default="/products/bulk-upsert")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class OmsSyncRequest(BaseModel):
    name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class OmsConfigActionRequest(BaseModel):
    name: str = Field(default="default")


class ScmConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/supplier-products")
    outbound_path: str = Field(default="/product-plans/bulk-upsert")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class ScmSyncRequest(BaseModel):
    name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class SomConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/listings")
    outbound_path: str = Field(default="/listing-drafts")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class SomSyncRequest(BaseModel):
    name: str = Field(default="default")


class WmsConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/inventory-snapshots")
    outbound_path: str = Field(default="/replenishment-plans/bulk-upsert")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class WmsSyncRequest(BaseModel):
    name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class CrmConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/customer-feedbacks")
    outbound_path: str = Field(default="/followups/bulk-upsert")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class CrmSyncRequest(BaseModel):
    name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class FmsConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    inbound_path: str = Field(default="/finance-metrics")
    outbound_path: str = Field(default="/profit-plans/bulk-upsert")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class FmsSyncRequest(BaseModel):
    name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class BiConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    health_path: str = Field(default="/health")
    dataset_path: str = Field(default="/datasets/push")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class BiSyncRequest(BaseModel):
    name: str = Field(default="default")


class BiDailyKpiSyncRequest(BaseModel):
    name: str = Field(default="default")
    day: str | None = Field(default=None, description="KPI日期，格式 YYYY-MM-DD；为空时按最新完成任务日期聚合")
    limit: int = Field(default=200, ge=1, le=1000)


class PaaSConfigRequest(BaseModel):
    name: str = Field(default="default")
    api_endpoint: str = Field(..., min_length=1)
    api_key: str | None = None
    secret_key: str | None = None
    health_path: str = Field(default="/health")
    trigger_path: str = Field(default="/workflows/trigger")
    status_path: str = Field(default="/workflows/{run_id}")
    callback_token: str | None = None
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class PaaSTestRequest(BaseModel):
    name: str = Field(default="default")


class PaaSTriggerRequest(BaseModel):
    name: str = Field(default="default")
    workflow_key: str = Field(default="selection_workflow", min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    callback_url: str = Field(..., min_length=1)


class CrawlRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="real", pattern="^(mock|auto|real)$")
    topic: str = Field(default="pms-data-collection", min_length=1)
    engine: str = Field(default="all", pattern="^(all|scrapy-compatible|playwright-compatible)$")


class CrawlSchedulerRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="real", pattern="^(mock|auto|real)$")
    topic: str = Field(default="pms-data-collection", min_length=1)
    job_key: str | None = Field(default=None)


class PaaSCallbackRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    result: dict[str, Any] = Field(default_factory=dict)


class ProductEventRequest(BaseModel):
    aggregate_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    event_type: str = Field(default="product.updated")


class DomainEventRequest(BaseModel):
    aggregate_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class CdcConnectorConfigRequest(BaseModel):
    system_name: str = Field(..., min_length=1, description="支持 oms/crm")
    connector_name: str | None = Field(default=None)


class CdcPublishRequest(BaseModel):
    system_name: str = Field(..., min_length=1, description="支持 oms/crm")
    aggregate_id: str = Field(..., min_length=1)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    op: str = Field(..., min_length=1, description="Debezium操作类型: c/u/d/r")
    ts_ms: int | None = Field(default=None, ge=0)
    source: dict[str, Any] = Field(default_factory=dict)


class EventConsumeRequest(BaseModel):
    topic: str = Field(default="pms-agent-event")
    event_type: str | None = Field(default=None)


class FeatureEventConsumeRequest(BaseModel):
    topic: str = Field(default="pms-agent-event")
    event_types: list[str] = Field(default_factory=lambda: ["order.updated", "review.updated"])


class LocalFeedbackLoopRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    artifact_root: str | None = None


class SelectionAdoptionRequest(BaseModel):
    scm_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    oms_name: str = Field(default="default")
    som_name: str = Field(default="default")
    quantity: int = Field(default=200, ge=1, le=100000)
    supplier_code: str | None = None
    notes: str | None = None


class SelectionCloseLoopRequest(BaseModel):
    oms_name: str = Field(default="default")
    scm_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    crm_name: str = Field(default="default")
    fms_name: str = Field(default="default")
    paas_name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class SelectionExecutionFeedbackSyncRequest(BaseModel):
    oms_name: str = Field(default="default")
    crm_name: str = Field(default="default")
    fms_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    auto_rescore: bool = Field(default=True)


class SelectionReviewCaseIngestRequest(BaseModel):
    crm_name: str = Field(default="default")
    publish_events: bool = Field(default=True)


async def _get_service(current_user: dict) -> tuple[ErpIntegrationService, Any]:
    session = get_async_session_factory()()
    service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


@router.post("/oms/config", response_model=dict)
async def save_oms_config(request: OmsConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_oms_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.oms.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存OMS配置失败")
        raise HTTPException(status_code=503, detail=f"保存OMS配置失败: {e}")
    finally:
        await session.close()


@router.post("/oms/test-connection", response_model=dict)
async def test_oms_connection(request: OmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_oms_connection(name=request.name)
        add_audit_log("integration.oms.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("OMS连接测试失败")
        raise HTTPException(status_code=503, detail=f"OMS连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/oms/sync/inbound", response_model=dict)
async def sync_oms_inbound(request: OmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_inbound_products(name=request.name)
        await session.commit()
        add_audit_log("integration.oms.sync.inbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("OMS入站同步失败")
        raise HTTPException(status_code=503, detail=f"OMS入站同步失败: {e}")
    finally:
        await session.close()


@router.post("/oms/sync/outbound", response_model=dict)
async def sync_oms_outbound(request: OmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_products(name=request.name, limit=request.limit)
        await session.commit()
        add_audit_log("integration.oms.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("OMS出站同步失败")
        raise HTTPException(status_code=503, detail=f"OMS出站同步失败: {e}")
    finally:
        await session.close()


@router.post("/oms/sync/{log_id}/retry", response_model=dict)
async def retry_oms_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.oms.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("OMS同步重试失败")
        raise HTTPException(status_code=503, detail=f"OMS同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/oms/logs", response_model=dict)
async def list_oms_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_oms_logs(limit=limit)
    except Exception as e:
        logger.exception("查询OMS同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询OMS同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/oms/status", response_model=dict)
async def get_oms_status(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_oms_operational_status(name=name)
    except Exception as e:
        logger.exception("查询OMS运营状态失败")
        raise HTTPException(status_code=503, detail=f"查询OMS运营状态失败: {e}")
    finally:
        await session.close()


@router.post("/oms/config/disable", response_model=dict)
async def disable_oms_config(request: OmsConfigActionRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.disable_oms_config(name=request.name)
        await session.commit()
        add_audit_log("integration.oms.config.disable", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("禁用OMS配置失败")
        raise HTTPException(status_code=503, detail=f"禁用OMS配置失败: {e}")
    finally:
        await session.close()


@router.post("/oms/cursor/reset", response_model=dict)
async def reset_oms_cursor(request: OmsConfigActionRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.reset_oms_cursor(name=request.name)
        await session.commit()
        add_audit_log("integration.oms.cursor.reset", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("重置OMS同步游标失败")
        raise HTTPException(status_code=503, detail=f"重置OMS同步游标失败: {e}")
    finally:
        await session.close()


@router.post("/scm/config", response_model=dict)
async def save_scm_config(request: ScmConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_scm_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.scm.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存SCM配置失败")
        raise HTTPException(status_code=503, detail=f"保存SCM配置失败: {e}")
    finally:
        await session.close()


@router.post("/scm/test-connection", response_model=dict)
async def test_scm_connection(request: ScmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_scm_connection(name=request.name)
        add_audit_log("integration.scm.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("SCM连接测试失败")
        raise HTTPException(status_code=503, detail=f"SCM连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/scm/sync/inbound", response_model=dict)
async def sync_scm_inbound(request: ScmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_inbound_supplier_products(name=request.name)
        await session.commit()
        add_audit_log("integration.scm.sync.inbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("SCM入站同步失败")
        raise HTTPException(status_code=503, detail=f"SCM入站同步失败: {e}")
    finally:
        await session.close()


@router.post("/scm/sync/outbound", response_model=dict)
async def sync_scm_outbound(request: ScmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_product_plan(name=request.name, limit=request.limit)
        await session.commit()
        add_audit_log("integration.scm.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("SCM出站同步失败")
        raise HTTPException(status_code=503, detail=f"SCM出站同步失败: {e}")
    finally:
        await session.close()


@router.post("/scm/sync/{log_id}/retry", response_model=dict)
async def retry_scm_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.scm.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("SCM同步重试失败")
        raise HTTPException(status_code=503, detail=f"SCM同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/scm/logs", response_model=dict)
async def list_scm_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_scm_logs(limit=limit)
    except Exception as e:
        logger.exception("查询SCM同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询SCM同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/scm/status", response_model=dict)
async def get_scm_status(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_scm_operational_status(name=name)
    except Exception as e:
        logger.exception("查询SCM运营状态失败")
        raise HTTPException(status_code=503, detail=f"查询SCM运营状态失败: {e}")
    finally:
        await session.close()


@router.post("/som/config", response_model=dict)
async def save_som_config(request: SomConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_som_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.som.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存SOM配置失败")
        raise HTTPException(status_code=503, detail=f"保存SOM配置失败: {e}")
    finally:
        await session.close()


@router.post("/som/test-connection", response_model=dict)
async def test_som_connection(request: SomSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_som_connection(name=request.name)
        add_audit_log("integration.som.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("SOM连接测试失败")
        raise HTTPException(status_code=503, detail=f"SOM连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/wms/config", response_model=dict)
async def save_wms_config(request: WmsConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_wms_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.wms.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存WMS配置失败")
        raise HTTPException(status_code=503, detail=f"保存WMS配置失败: {e}")
    finally:
        await session.close()


@router.post("/wms/test-connection", response_model=dict)
async def test_wms_connection(request: WmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_wms_connection(name=request.name)
        add_audit_log("integration.wms.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("WMS连接测试失败")
        raise HTTPException(status_code=503, detail=f"WMS连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/wms/sync/inbound", response_model=dict)
async def sync_wms_inbound(request: WmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_inbound_inventory(name=request.name)
        await session.commit()
        add_audit_log("integration.wms.sync.inbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("WMS入站同步失败")
        raise HTTPException(status_code=503, detail=f"WMS入站同步失败: {e}")
    finally:
        await session.close()


@router.post("/wms/sync/outbound", response_model=dict)
async def sync_wms_outbound(request: WmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_replenishment_plan(name=request.name, limit=request.limit)
        await session.commit()
        add_audit_log("integration.wms.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("WMS出站同步失败")
        raise HTTPException(status_code=503, detail=f"WMS出站同步失败: {e}")
    finally:
        await session.close()


@router.post("/wms/sync/{log_id}/retry", response_model=dict)
async def retry_wms_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.wms.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("WMS同步重试失败")
        raise HTTPException(status_code=503, detail=f"WMS同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/wms/logs", response_model=dict)
async def list_wms_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_wms_logs(limit=limit)
    except Exception as e:
        logger.exception("查询WMS同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询WMS同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/wms/status", response_model=dict)
async def get_wms_status(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_wms_operational_status(name=name)
    except Exception as e:
        logger.exception("查询WMS运营状态失败")
        raise HTTPException(status_code=503, detail=f"查询WMS运营状态失败: {e}")
    finally:
        await session.close()


@router.post("/crm/config", response_model=dict)
async def save_crm_config(request: CrmConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_crm_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.crm.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存CRM配置失败")
        raise HTTPException(status_code=503, detail=f"保存CRM配置失败: {e}")
    finally:
        await session.close()


@router.post("/crm/test-connection", response_model=dict)
async def test_crm_connection(request: CrmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_crm_connection(name=request.name)
        add_audit_log("integration.crm.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("CRM连接测试失败")
        raise HTTPException(status_code=503, detail=f"CRM连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/crm/sync/inbound", response_model=dict)
async def sync_crm_inbound(request: CrmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_inbound_customer_feedback(name=request.name)
        await session.commit()
        add_audit_log("integration.crm.sync.inbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("CRM入站同步失败")
        raise HTTPException(status_code=503, detail=f"CRM入站同步失败: {e}")
    finally:
        await session.close()


@router.post("/crm/sync/outbound", response_model=dict)
async def sync_crm_outbound(request: CrmSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_customer_followup(name=request.name, limit=request.limit)
        await session.commit()
        add_audit_log("integration.crm.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("CRM出站同步失败")
        raise HTTPException(status_code=503, detail=f"CRM出站同步失败: {e}")
    finally:
        await session.close()


@router.post("/crm/sync/{log_id}/retry", response_model=dict)
async def retry_crm_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.crm.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("CRM同步重试失败")
        raise HTTPException(status_code=503, detail=f"CRM同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/crm/logs", response_model=dict)
async def list_crm_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_crm_logs(limit=limit)
    except Exception as e:
        logger.exception("查询CRM同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询CRM同步日志失败: {e}")
    finally:
        await session.close()


@router.post("/fms/config", response_model=dict)
async def save_fms_config(request: FmsConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_fms_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.fms.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存FMS配置失败")
        raise HTTPException(status_code=503, detail=f"保存FMS配置失败: {e}")
    finally:
        await session.close()


@router.post("/fms/test-connection", response_model=dict)
async def test_fms_connection(request: FmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_fms_connection(name=request.name)
        add_audit_log("integration.fms.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("FMS连接测试失败")
        raise HTTPException(status_code=503, detail=f"FMS连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/fms/sync/inbound", response_model=dict)
async def sync_fms_inbound(request: FmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_inbound_finance_metrics(name=request.name)
        await session.commit()
        add_audit_log("integration.fms.sync.inbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("FMS入站同步失败")
        raise HTTPException(status_code=503, detail=f"FMS入站同步失败: {e}")
    finally:
        await session.close()


@router.post("/fms/sync/outbound", response_model=dict)
async def sync_fms_outbound(request: FmsSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_profit_plan(name=request.name, limit=request.limit)
        await session.commit()
        add_audit_log("integration.fms.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("FMS出站同步失败")
        raise HTTPException(status_code=503, detail=f"FMS出站同步失败: {e}")
    finally:
        await session.close()


@router.get("/profit/trend", response_model=dict)
async def get_profit_trend(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_profit_trend(name=name)
    except Exception as e:
        logger.exception("查询利润趋势失败")
        raise HTTPException(status_code=503, detail=f"查询利润趋势失败: {e}")
    finally:
        await session.close()


@router.post("/fms/sync/{log_id}/retry", response_model=dict)
async def retry_fms_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.fms.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("FMS同步重试失败")
        raise HTTPException(status_code=503, detail=f"FMS同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/fms/logs", response_model=dict)
async def list_fms_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_fms_logs(limit=limit)
    except Exception as e:
        logger.exception("查询FMS同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询FMS同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/fms/status", response_model=dict)
async def get_fms_status(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_fms_operational_status(name=name)
    except Exception as e:
        logger.exception("查询FMS运营状态失败")
        raise HTTPException(status_code=503, detail=f"查询FMS运营状态失败: {e}")
    finally:
        await session.close()


@router.post("/bi/config", response_model=dict)
async def save_bi_config(request: BiConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_bi_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.bi.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存BI配置失败")
        raise HTTPException(status_code=503, detail=f"保存BI配置失败: {e}")
    finally:
        await session.close()


@router.post("/bi/test-connection", response_model=dict)
async def test_bi_connection(request: BiSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_bi_connection(name=request.name)
        add_audit_log("integration.bi.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("BI连接测试失败")
        raise HTTPException(status_code=503, detail=f"BI连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/bi/sync/outbound", response_model=dict)
async def sync_bi_outbound(request: BiSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_outbound_bi_assets(name=request.name)
        await session.commit()
        add_audit_log("integration.bi.sync.outbound", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success")
        return result
    except Exception as e:
        logger.exception("BI出站同步失败")
        raise HTTPException(status_code=503, detail=f"BI出站同步失败: {e}")
    finally:
        await session.close()


@router.post("/bi/sync/{log_id}/retry", response_model=dict)
async def retry_bi_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.bi.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("BI同步重试失败")
        raise HTTPException(status_code=503, detail=f"BI同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/bi/logs", response_model=dict)
async def list_bi_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_bi_logs(limit=limit)
    except Exception as e:
        logger.exception("查询BI同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询BI同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/bi/tasks/{task_id}/metrics", response_model=dict)
async def get_bi_task_metrics(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.get_bi_task_metrics(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"BI任务指标不存在: {task_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询BI任务指标失败")
        raise HTTPException(status_code=503, detail=f"查询BI任务指标失败: {e}")
    finally:
        await session.close()


@router.post("/bi/kpis/daily/sync", response_model=dict)
async def sync_bi_daily_kpis(request: BiDailyKpiSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_daily_bi_kpis(name=request.name, day=request.day, limit=request.limit)
        await session.commit()
        add_audit_log("integration.bi.kpi.daily.sync", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success", detail={"kpi_date": result.get("kpi_date")})
        return result
    except Exception as e:
        logger.exception("同步BI每日KPI失败")
        raise HTTPException(status_code=503, detail=f"同步BI每日KPI失败: {e}")
    finally:
        await session.close()


@router.get("/bi/kpis/daily/latest", response_model=dict)
async def get_latest_bi_daily_kpis(name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.get_latest_daily_selection_kpis(name=name)
        if result is None:
            raise HTTPException(status_code=404, detail="BI每日KPI不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询BI每日KPI失败")
        raise HTTPException(status_code=503, detail=f"查询BI每日KPI失败: {e}")
    finally:
        await session.close()


@router.get("/bi/kpis/daily/compute", response_model=dict)
async def compute_bi_daily_kpis(
    name: str = Query("default"),
    day: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_service(current_user)
    try:
        await service._get_required_config(ERPSystemType.BI, name, "BI 配置不存在")
        result = await service.compute_daily_selection_kpis(day=day, limit=limit)
        add_audit_log("integration.bi.kpi.daily.compute", actor=current_user, target_type="erp_config", result="success", detail={"kpi_date": result.get("kpi_date")})
        return result
    except Exception as e:
        logger.exception("计算BI每日KPI失败")
        raise HTTPException(status_code=503, detail=f"计算BI每日KPI失败: {e}")
    finally:
        await session.close()


@router.post("/paas/config", response_model=dict)
async def save_paas_config(request: PaaSConfigRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.save_paas_config(**request.model_dump())
        await session.commit()
        add_audit_log("integration.paas.config.save", actor=current_user, target_type="erp_config", target_id=result["config_id"], result="success")
        return result
    except Exception as e:
        logger.exception("保存PaaS配置失败")
        raise HTTPException(status_code=503, detail=f"保存PaaS配置失败: {e}")
    finally:
        await session.close()


@router.post("/paas/test-connection", response_model=dict)
async def test_paas_connection(request: PaaSTestRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.test_paas_connection(name=request.name)
        add_audit_log("integration.paas.connection.test", actor=current_user, target_type="erp_config", result="success", detail=result)
        return result
    except Exception as e:
        logger.exception("PaaS连接测试失败")
        raise HTTPException(status_code=503, detail=f"PaaS连接测试失败: {e}")
    finally:
        await session.close()


@router.post("/paas/trigger", response_model=dict)
async def trigger_paas_workflow(request: PaaSTriggerRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.trigger_paas_workflow(
            name=request.name,
            workflow_key=request.workflow_key,
            trigger_payload=request.payload,
            callback_url=request.callback_url,
        )
        await session.commit()
        add_audit_log("integration.paas.trigger", actor=current_user, target_type="erp_sync_log", target_id=result["log_id"], result="success", detail={"workflow_key": request.workflow_key})
        return result
    except Exception as e:
        logger.exception("PaaS流程触发失败")
        raise HTTPException(status_code=503, detail=f"PaaS流程触发失败: {e}")
    finally:
        await session.close()


@router.post("/paas/callback", response_model=dict)
async def handle_paas_callback(request: PaaSCallbackRequest, x_callback_token: str | None = Header(default=None, alias="X-Callback-Token")):
    session = get_async_session_factory()()
    service = ErpIntegrationService(session)
    try:
        log, config = await service.repo.get_sync_log_with_config(request.run_id)
        if log is None or config is None:
            raise HTTPException(status_code=404, detail=f"PaaS运行日志不存在: {request.run_id}")
        expected_token = (config.extra_config or {}).get("callback_token")
        if expected_token and expected_token != x_callback_token:
            raise HTTPException(status_code=401, detail="PaaS回调令牌无效")
        result = await service.update_paas_callback(run_id=request.run_id, status=request.status, result=request.result)
        await session.commit()
        add_audit_log("integration.paas.callback", actor={"sub": "paas-callback"}, target_type="erp_sync_log", target_id=request.run_id, result="success", detail={"status": request.status})
        return result
    finally:
        await session.close()


@router.get("/paas/runs/{run_id}", response_model=dict)
async def get_paas_run_status(run_id: str, name: str = Query("default"), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_paas_run_status(name=name, run_id=run_id)
    except Exception as e:
        logger.exception("查询PaaS运行状态失败")
        raise HTTPException(status_code=503, detail=f"查询PaaS运行状态失败: {e}")
    finally:
        await session.close()


@router.post("/paas/sync/{log_id}/retry", response_model=dict)
async def retry_paas_sync(log_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.retry_sync_log(log_id)
        await session.commit()
        add_audit_log("integration.paas.sync.retry", actor=current_user, target_type="erp_sync_log", target_id=log_id, result="success")
        return result
    except Exception as e:
        logger.exception("PaaS同步重试失败")
        raise HTTPException(status_code=503, detail=f"PaaS同步重试失败: {e}")
    finally:
        await session.close()


@router.get("/paas/logs", response_model=dict)
async def list_paas_logs(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_paas_logs(limit=limit)
    except Exception as e:
        logger.exception("查询PaaS同步日志失败")
        raise HTTPException(status_code=503, detail=f"查询PaaS同步日志失败: {e}")
    finally:
        await session.close()


@router.get("/events/catalog", response_model=dict)
async def get_event_catalog(current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        return {"events": service.get_event_catalog()}
    finally:
        await session.close()


@router.get("/cdc/catalog", response_model=dict)
async def get_cdc_catalog(current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        return {"connectors": service.get_cdc_catalog()}
    finally:
        await session.close()


@router.post("/cdc/connectors/config", response_model=dict)
async def build_cdc_connector_config(request: CdcConnectorConfigRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = service.build_cdc_connector_config(system_name=request.system_name, connector_name=request.connector_name)
        add_audit_log("integration.cdc.connector.config", actor=current_user, target_type="cdc_connector", target_id=result["name"], result="success", detail={"system_name": request.system_name})
        return result
    except Exception as e:
        logger.exception("生成CDC连接器配置失败")
        raise HTTPException(status_code=503, detail=f"生成CDC连接器配置失败: {e}")
    finally:
        await session.close()


@router.post("/cdc/publish", response_model=dict)
async def publish_cdc_event(request: CdcPublishRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.publish_cdc_event(
            system_name=request.system_name,
            aggregate_id=request.aggregate_id,
            before=request.before,
            after=request.after,
            op=request.op,
            ts_ms=request.ts_ms,
            source=request.source,
        )
        await session.commit()
        add_audit_log("integration.cdc.publish", actor=current_user, target_type="data_sync_event", target_id=result["event_id"], result="success", detail={"system_name": request.system_name, "op": request.op})
        return result
    except Exception as e:
        logger.exception("发布CDC事件失败")
        raise HTTPException(status_code=503, detail=f"发布CDC事件失败: {e}")
    finally:
        await session.close()


@router.get("/cdc/platform-governance", response_model=dict)
async def get_cdc_platform_governance(current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.build_platform_governance()
        add_audit_log("integration.cdc.platform_governance", actor=current_user, target_type="data_sync_event", result="success")
        return result
    finally:
        await session.close()


@router.get("/crawl/platforms", response_model=dict)
async def get_crawl_platforms(current_user: dict = Depends(get_current_user)):
    service = CrawlPlatformService()
    add_audit_log("integration.crawl.platforms", actor=current_user, target_type="crawl_platform", result="success")
    return service.build_status()


@router.post("/crawl/platforms/run-local", response_model=dict)
async def run_local_crawl_platform(request: CrawlRunRequest, current_user: dict = Depends(get_current_user)):
    service = CrawlPlatformService()
    result = await service.run_local_crawl(query=request.query, mode=request.mode, topic=request.topic, engine=request.engine)
    add_audit_log(
        "integration.crawl.platforms.run_local",
        actor=current_user,
        target_type="crawl_platform",
        result="success",
        detail={"query": request.query, "mode": request.mode, "engine": request.engine},
    )
    return result


@router.post("/crawl/platforms/run-scheduler", response_model=dict)
async def run_crawl_scheduler(request: CrawlSchedulerRequest, current_user: dict = Depends(get_current_user)):
    service = CrawlPlatformService()
    result = await service.run_scheduled_jobs_once(query=request.query, mode=request.mode, topic=request.topic, job_key=request.job_key)
    add_audit_log(
        "integration.crawl.platforms.run_scheduler",
        actor=current_user,
        target_type="crawl_platform",
        result="success",
        detail={"query": request.query, "mode": request.mode, "job_key": request.job_key},
    )
    return result


@router.get("/selection/{task_id}/feedback-loop-status", response_model=dict)
async def get_selection_feedback_loop_status(
    task_id: str,
    crm_name: str = Query("default"),
    paas_name: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_service(current_user)
    try:
        result = await service.get_selection_feedback_loop_status(task_id=task_id, crm_name=crm_name, paas_name=paas_name)
        add_audit_log("integration.selection.feedback_loop_status", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询选品反馈闭环状态失败")
        raise HTTPException(status_code=503, detail=f"查询选品反馈闭环状态失败: {e}")
    finally:
        await session.close()


@router.get("/selection/{task_id}/profit-trace", response_model=dict)
async def get_selection_profit_trace(
    task_id: str,
    crm_name: str = Query("default"),
    fms_name: str = Query("default"),
    wms_name: str = Query("default"),
    paas_name: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_service(current_user)
    try:
        result = await service.get_selection_profit_trace(task_id=task_id, crm_name=crm_name, fms_name=fms_name, wms_name=wms_name, paas_name=paas_name)
        add_audit_log("integration.selection.profit_trace", actor=current_user, target_type="selection_task", target_id=task_id, result="success", detail={"trace_id": result.get("trace_id")})
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询选品利润 Trace 失败")
        raise HTTPException(status_code=503, detail=f"查询选品利润 Trace 失败: {e}")
    finally:
        await session.close()


@router.post("/selection/{task_id}/adopt", response_model=dict)
async def adopt_selection_recommendation(task_id: str, request: SelectionAdoptionRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.execute_selection_adoption(
            task_id=task_id,
            scm_name=request.scm_name,
            wms_name=request.wms_name,
            oms_name=request.oms_name,
            som_name=request.som_name,
            quantity=request.quantity,
            supplier_code=request.supplier_code,
            notes=request.notes,
        )
        await session.commit()
        add_audit_log(
            "integration.selection.adopt",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"trace_id": result.get("trace_id"), "supplier_code": result.get("purchase_suggestion", {}).get("supplier_code"), "som_name": request.som_name},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("选品采纳推荐执行失败")
        raise HTTPException(status_code=503, detail=f"选品采纳推荐执行失败: {e}")
    finally:
        await session.close()


@router.post("/selection/{task_id}/close-loop", response_model=dict)
async def close_selection_loop(task_id: str, request: SelectionCloseLoopRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.close_selection_loop(
            task_id=task_id,
            oms_name=request.oms_name,
            scm_name=request.scm_name,
            wms_name=request.wms_name,
            crm_name=request.crm_name,
            fms_name=request.fms_name,
            limit=request.limit,
        )
        await session.commit()
        add_audit_log("integration.selection.close_loop", actor=current_user, target_type="selection_task", target_id=task_id, result="success", detail={"trace_id": result.get("trace_id")})
        return result
    except Exception as e:
        logger.exception("选品跨系统闭环执行失败")
        raise HTTPException(status_code=503, detail=f"选品跨系统闭环执行失败: {e}")
    finally:
        await session.close()


@router.post("/selection/{task_id}/execution-feedback-sync", response_model=dict)
async def sync_selection_execution_feedback(task_id: str, request: SelectionExecutionFeedbackSyncRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.sync_selection_execution_feedback(
            task_id=task_id,
            oms_name=request.oms_name,
            crm_name=request.crm_name,
            fms_name=request.fms_name,
            wms_name=request.wms_name,
            auto_rescore=request.auto_rescore,
        )
        await session.commit()
        add_audit_log(
            "integration.selection.execution_feedback_sync",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"auto_rescore": request.auto_rescore},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("同步选品执行反馈失败")
        raise HTTPException(status_code=503, detail=f"同步选品执行反馈失败: {e}")
    finally:
        await session.close()


@router.post("/selection/{task_id}/review-cases/ingest", response_model=dict)
async def ingest_selection_review_cases(task_id: str, request: SelectionReviewCaseIngestRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        result = await service.ingest_selection_review_cases(
            task_id=task_id,
            crm_name=request.crm_name,
            publish_events=request.publish_events,
        )
        await session.commit()
        add_audit_log(
            "integration.selection.review_case_ingest",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"matched_review_count": result.get("matched_review_count"), "published_event_count": len(result.get("published_events") or [])},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("同步选品评价案例入库失败")
        raise HTTPException(status_code=503, detail=f"同步选品评价案例入库失败: {e}")
    finally:
        await session.close()


@router.get("/selection/{task_id}/adoption-status", response_model=dict)
async def get_adoption_status(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.get_adoption_status(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询采纳状态失败")
        raise HTTPException(status_code=503, detail=f"查询采纳状态失败: {e}")
    finally:
        await session.close()


@router.get("/selection/{task_id}/adopt-logs", response_model=dict)
async def list_adoption_logs(task_id: str, limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    service, session = await _get_service(current_user)
    try:
        return await service.list_adoption_logs(task_id=task_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询采纳日志失败")
        raise HTTPException(status_code=503, detail=f"查询采纳日志失败: {e}")
    finally:
        await session.close()


class CeleryTaskSubmitRequest(BaseModel):
    task_type: str = Field(description="任务类型: selection|adoption|feedback|report|feature|vector|knowledge")
    task_id: str = Field(description="选品任务ID")
    params: dict[str, Any] = Field(default_factory=dict, description="任务参数")


@router.post("/celery/submit", response_model=dict)
async def submit_celery_task(request: CeleryTaskSubmitRequest, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user.get("tenant_id", "default")
    try:
        from src.workers.celery_tasks import (
            execute_adoption_task,
            execute_selection_task,
            generate_report_task,
            process_feedback_data,
            update_feature_store,
            update_knowledge_base,
            update_vector_store,
        )

        task_map = {
            "selection": execute_selection_task,
            "adoption": execute_adoption_task,
            "feedback": process_feedback_data,
            "report": generate_report_task,
            "feature": update_feature_store,
            "vector": update_vector_store,
            "knowledge": update_knowledge_base,
        }

        task_func = task_map.get(request.task_type)
        if not task_func:
            raise HTTPException(status_code=400, detail=f"不支持的任务类型: {request.task_type}")

        params = request.params
        if request.task_type == "selection":
            celery_result = task_func.delay(
                task_id=request.task_id,
                tenant_id=tenant_id,
                query=params.get("query", ""),
                category=params.get("category", "electronics"),
                target_market=params.get("target_market", "US"),
                investment_budget=float(params.get("investment_budget", 0.0)),
                priority=params.get("priority", "normal"),
            )
        elif request.task_type == "adoption":
            celery_result = task_func.delay(
                task_id=request.task_id,
                tenant_id=tenant_id,
                scm_name=params.get("scm_name", "default"),
                wms_name=params.get("wms_name", "default"),
                oms_name=params.get("oms_name", "default"),
                quantity=int(params.get("quantity", 200)),
                supplier_code=params.get("supplier_code", ""),
                notes=params.get("notes", ""),
            )
        elif request.task_type == "feedback":
            celery_result = task_func.delay(
                task_id=request.task_id,
                tenant_id=tenant_id,
                feedback_type=params.get("feedback_type", "all"),
                limit=int(params.get("limit", 100)),
            )
        elif request.task_type == "report":
            celery_result = task_func.delay(
                task_id=request.task_id,
                tenant_id=tenant_id,
                query=params.get("query", ""),
                category=params.get("category", ""),
                target_market=params.get("target_market", "US"),
                report_format=params.get("format", "json"),
            )
        elif request.task_type in {"feature", "vector", "knowledge"}:
            celery_result = task_func.delay(
                task_id=request.task_id,
                tenant_id=tenant_id,
                **params,
            )
        else:
            raise HTTPException(status_code=400, detail=f"任务类型参数缺失: {request.task_type}")

        add_audit_log(
            "integration.celery.submit",
            actor=current_user,
            target_type="celery_task",
            target_id=celery_result.id,
            result="submitted",
            detail={"task_type": request.task_type, "task_id": request.task_id},
        )

        return {
            "celery_task_id": celery_result.id,
            "task_type": request.task_type,
            "selection_task_id": request.task_id,
            "status": "submitted",
            "submitted_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Celery任务提交失败")
        raise HTTPException(status_code=503, detail=f"Celery任务提交失败: {e}")


@router.get("/celery/status/{celery_task_id}", response_model=dict)
async def get_celery_task_status(celery_task_id: str, current_user: dict = Depends(get_current_user)):
    try:
        from src.workers.celery_app import celery_app
        result = celery_app.AsyncResult(celery_task_id)
        return {
            "celery_task_id": celery_task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
            "traceback": str(result.traceback) if result.failed() else None,
        }
    except Exception as e:
        logger.exception("查询Celery任务状态失败")
        raise HTTPException(status_code=503, detail=f"查询Celery任务状态失败: {e}")


@router.post("/events/products/publish", response_model=dict)
async def publish_product_event(request: ProductEventRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.publish_product_event(
            aggregate_id=request.aggregate_id,
            payload=request.payload,
            event_type=request.event_type,
        )
        await session.commit()
        add_audit_log("integration.event.publish", actor=current_user, target_type="data_sync_event", target_id=result["event_id"], result="success")
        return result
    finally:
        await session.close()


@router.post("/events/documents/publish", response_model=dict)
async def publish_document_event(request: DomainEventRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.publish_domain_event(
            aggregate_id=request.aggregate_id,
            payload=request.payload,
            event_type="document.indexed",
        )
        await session.commit()
        add_audit_log("integration.event.publish", actor=current_user, target_type="data_sync_event", target_id=result["event_id"], result="success")
        return result
    finally:
        await session.close()


@router.post("/events/inventory/publish", response_model=dict)
async def publish_inventory_event(request: DomainEventRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.publish_domain_event(
            aggregate_id=request.aggregate_id,
            payload=request.payload,
            event_type="inventory.updated",
        )
        await session.commit()
        add_audit_log("integration.event.publish", actor=current_user, target_type="data_sync_event", target_id=result["event_id"], result="success")
        return result
    finally:
        await session.close()


@router.post("/events/dispatch", response_model=dict)
async def dispatch_events(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.dispatch_pending_events(limit=limit)
        await session.commit()
        add_audit_log("integration.event.dispatch", actor=current_user, target_type="data_sync_event", result="success", detail=result)
        return result
    finally:
        await session.close()


@router.post("/events/consume", response_model=dict)
async def consume_events(request: EventConsumeRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        consumer = DataSyncConsumer(topic=request.topic, consumer_group="pms-review-consumer-group")
        messages = drain_memory_messages(request.topic)
        normalized_messages = [item.get("message") or item for item in messages]
        if request.event_type:
            normalized_messages = [item for item in normalized_messages if item.get("event_type") == request.event_type]
        result = await consumer.consume_review_events(
            normalized_messages,
            session=session,
            tenant_id=current_user.get("tenant_id"),
            actor=current_user,
        )
        await session.commit()
        add_audit_log("integration.event.consume", actor=current_user, target_type="data_sync_event", result="success", detail={"consumed": result.get("consumed"), "ingested_count": result.get("ingested_count")})
        return result
    finally:
        await session.close()


@router.post("/events/features/consume", response_model=dict)
async def consume_feature_events(request: FeatureEventConsumeRequest, current_user: dict = Depends(get_current_user)):
    consumer = DataSyncConsumer(topic=request.topic, consumer_group="pms-feature-consumer-group")
    messages = drain_memory_messages(request.topic)
    normalized_messages = [item.get("message") or item for item in messages]
    allowed_types = set(request.event_types)
    normalized_messages = [item for item in normalized_messages if item.get("event_type") in allowed_types]
    result = await consumer.consume_feature_events(normalized_messages)
    add_audit_log("integration.feature.consume", actor=current_user, target_type="feature_event", result="success", detail={"consumed": result.get("consumed"), "updated_count": result.get("updated_count")})
    return result


@router.post("/feedback-loop/local-run", response_model=dict)
async def run_local_feedback_loop(request: LocalFeedbackLoopRequest, current_user: dict = Depends(get_current_user)):
    service = LocalFeedbackLoopService(topic="pms-agent-event")
    result = await service.run_local_loop(task_id=request.task_id, artifact_root=request.artifact_root)
    add_audit_log("integration.feedback_loop.local_run", actor=current_user, target_type="selection_task", target_id=request.task_id, result="success", detail={"closed_loop_ready": result.get("closed_loop_ready")})
    return result


@router.get("/features/{product_id}", response_model=dict)
async def get_product_features(product_id: str, limit: int = Query(20, ge=1, le=100), current_user: dict = Depends(get_current_user)):
    engine = FeatureEngine()
    features = await engine.get_features(product_id)
    history = engine.get_feature_history(product_id, limit=limit)
    if features is None:
        raise HTTPException(status_code=404, detail=f"特征不存在: {product_id}")
    return {
        "product_id": product_id,
        "features": features,
        "history": history,
        "feature_store": engine.get_stats(),
    }


@router.get("/events/dlq", response_model=dict)
async def list_dead_letter_events(limit: int = Query(20, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        return await service.list_dead_letter(limit=limit)
    finally:
        await session.close()


@router.post("/events/{event_id}/replay", response_model=dict)
async def replay_dead_letter_event(event_id: str, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        result = await service.replay_dead_letter(event_id)
        await session.commit()
        add_audit_log("integration.event.replay", actor=current_user, target_type="data_sync_event", target_id=event_id, result="success")
        return result
    finally:
        await session.close()


@router.get("/events/platform-governance", response_model=dict)
async def get_event_platform_governance(current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    service = DataSyncService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    try:
        return await service.build_platform_governance()
    finally:
        await session.close()
