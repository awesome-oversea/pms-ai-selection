from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.models.enums import ERPDomainType, RecommendationExecutionState
from src.services.bi_domain_service import BIDomainService
from src.services.crm_domain_service import CRMDomainService
from src.services.erp_workflow_service import ERPWorkflowService
from src.services.feedback_evaluator import FeedbackEvaluator
from src.services.ms_service import MasterDataService
from src.services.oms_domain_service import OMSDomainService
from src.services.scm_domain_service import SCMDomainService
from src.services.wms_domain_service import WMSDomainService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/erp", tags=["ERP六域服务"])


class CreateProductFromSelectionRequest(BaseModel):
    pdm_name: str = Field(default="default")
    product_name: str | None = None
    category: str | None = None
    target_market: str | None = None
    notes: str | None = None


class UpdateProductLifecycleRequest(BaseModel):
    lifecycle_state: str = Field(..., min_length=1, description="draft|pending_review|approved|active|discontinued|archived")


class CreateProductDefinitionsRequest(BaseModel):
    definitions: list[dict[str, Any]] = Field(..., min_length=1)


class OrchestrateAdoptionRequest(BaseModel):
    scm_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    oms_name: str = Field(default="default")
    som_name: str = Field(default="default")
    pdm_name: str = Field(default="default")
    quantity: int = Field(default=200, ge=1, le=100000)
    supplier_code: str | None = None
    notes: str | None = None


class OrchestrateCloseLoopRequest(BaseModel):
    oms_name: str = Field(default="default")
    scm_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    crm_name: str = Field(default="default")
    fms_name: str = Field(default="default")
    paas_name: str = Field(default="default")
    limit: int = Field(default=20, ge=1, le=200)


class AdvanceStateRequest(BaseModel):
    target_state: str = Field(..., min_length=1, description="目标状态枚举值")
    detail: str | None = None


async def _get_ms_service(current_user: dict) -> tuple[MasterDataService, Any]:
    session = get_async_session_factory()()
    service = MasterDataService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


async def _get_workflow_service(current_user: dict) -> tuple[ERPWorkflowService, Any]:
    session = get_async_session_factory()()
    service = ERPWorkflowService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


@router.post("/ms/products/from-selection/{task_id}", response_model=dict)
async def create_product_from_selection(
    task_id: str,
    request: CreateProductFromSelectionRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_ms_service(current_user)
    try:
        result = await service.create_product_from_selection(
            task_id=task_id,
            pdm_name=request.pdm_name,
            product_name=request.product_name,
            category=request.category,
            target_market=request.target_market,
            notes=request.notes,
        )
        await session.commit()
        add_audit_log("erp.ms.product.create_from_selection", actor=current_user, target_type="ms_product", target_id=result.get("product_id"), result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("从选品创建商品草稿失败")
        raise HTTPException(status_code=503, detail=f"从选品创建商品草稿失败: {e}")
    finally:
        await session.close()


@router.get("/ms/products/{task_id}", response_model=dict)
async def get_product(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_ms_service(current_user)
    try:
        return await service.get_product(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询商品主数据失败")
        raise HTTPException(status_code=503, detail=f"查询商品主数据失败: {e}")
    finally:
        await session.close()


@router.put("/ms/products/{task_id}/lifecycle", response_model=dict)
async def update_product_lifecycle(
    task_id: str,
    request: UpdateProductLifecycleRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_ms_service(current_user)
    try:
        result = await service.update_product_lifecycle(task_id=task_id, lifecycle_state=request.lifecycle_state)
        await session.commit()
        add_audit_log("erp.ms.product.lifecycle.update", actor=current_user, target_type="ms_product", target_id=task_id, result="success", detail={"lifecycle_state": request.lifecycle_state})
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("更新商品生命周期失败")
        raise HTTPException(status_code=503, detail=f"更新商品生命周期失败: {e}")
    finally:
        await session.close()


@router.post("/ms/products/{task_id}/definitions", response_model=dict)
async def create_product_definitions(
    task_id: str,
    request: CreateProductDefinitionsRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_ms_service(current_user)
    try:
        result = await service.create_product_definitions(task_id=task_id, definitions=request.definitions)
        await session.commit()
        add_audit_log("erp.ms.product.definitions.create", actor=current_user, target_type="ms_product_definition", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("创建产品定义失败")
        raise HTTPException(status_code=503, detail=f"创建产品定义失败: {e}")
    finally:
        await session.close()


@router.post("/workflow/adoption/{task_id}", response_model=dict)
async def orchestrate_adoption(
    task_id: str,
    request: OrchestrateAdoptionRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_workflow_service(current_user)
    try:
        result = await service.orchestrate_adoption(
            task_id=task_id,
            scm_name=request.scm_name,
            wms_name=request.wms_name,
            oms_name=request.oms_name,
            som_name=request.som_name,
            pdm_name=request.pdm_name,
            quantity=request.quantity,
            supplier_code=request.supplier_code,
            notes=request.notes,
        )
        await session.commit()
        add_audit_log("erp.workflow.adoption", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("ERP采纳编排失败")
        raise HTTPException(status_code=503, detail=f"ERP采纳编排失败: {e}")
    finally:
        await session.close()


@router.post("/workflow/close-loop/{task_id}", response_model=dict)
async def orchestrate_close_loop(
    task_id: str,
    request: OrchestrateCloseLoopRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_workflow_service(current_user)
    try:
        result = await service.orchestrate_close_loop(
            task_id=task_id,
            oms_name=request.oms_name,
            scm_name=request.scm_name,
            wms_name=request.wms_name,
            crm_name=request.crm_name,
            fms_name=request.fms_name,
            paas_name=request.paas_name,
            limit=request.limit,
        )
        await session.commit()
        add_audit_log("erp.workflow.close_loop", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("ERP闭环回流编排失败")
        raise HTTPException(status_code=503, detail=f"ERP闭环回流编排失败: {e}")
    finally:
        await session.close()


@router.get("/workflow/status/{task_id}", response_model=dict)
async def get_workflow_status(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_workflow_service(current_user)
    try:
        return await service.get_workflow_status(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询ERP工作流状态失败")
        raise HTTPException(status_code=503, detail=f"查询ERP工作流状态失败: {e}")
    finally:
        await session.close()


@router.post("/workflow/state/{task_id}/advance", response_model=dict)
async def advance_workflow_state(
    task_id: str,
    request: AdvanceStateRequest,
    current_user: dict = Depends(get_current_user),
):
    service, session = await _get_workflow_service(current_user)
    try:
        target_state = RecommendationExecutionState(request.target_state)
    except ValueError:
        valid_states = [s.value for s in RecommendationExecutionState]
        raise HTTPException(status_code=400, detail=f"无效的目标状态: {request.target_state}，有效值: {valid_states}")
    try:
        result = await service.advance_state(task_id=task_id, target_state=target_state, detail=request.detail)
        await session.commit()
        add_audit_log("erp.workflow.state.advance", actor=current_user, target_type="selection_task", target_id=task_id, result="success", detail={"target_state": request.target_state})
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("推进工作流状态失败")
        raise HTTPException(status_code=503, detail=f"推进工作流状态失败: {e}")
    finally:
        await session.close()


@router.get("/domains/catalog", response_model=dict)
async def get_domains_catalog(current_user: dict = Depends(get_current_user)):
    domains = []
    for domain in ERPDomainType:
        domain_info = {
            "code": domain.value,
            "name": {
                "ms": "商品主数据服务",
                "scm": "供应链管理",
                "wms": "仓储管理",
                "oms": "订单管理",
                "crm": "客户关系管理",
                "bi": "商业智能",
            }.get(domain.value, domain.value),
            "endpoints": _get_domain_endpoints(domain.value),
        }
        domains.append(domain_info)
    return {
        "domains": domains,
        "total": len(domains),
    }


@router.get("/state-machine/catalog", response_model=dict)
async def get_state_machine_catalog(current_user: dict = Depends(get_current_user)):
    from src.models.enums import get_valid_transitions, is_terminal_state

    states = []
    for state in RecommendationExecutionState:
        valid_next = get_valid_transitions(state)
        states.append({
            "code": state.value,
            "is_terminal": is_terminal_state(state),
            "valid_transitions": [s.value for s in valid_next],
        })
    return {
        "total_states": len(states),
        "states": states,
    }


def _get_domain_endpoints(domain_code: str) -> list[str]:
    base = "/api/v1/erp"
    endpoint_map = {
        "ms": [
            f"{base}/ms/products/from-selection/{{task_id}}",
            f"{base}/ms/products/{{task_id}}",
            f"{base}/ms/products/{{task_id}}/lifecycle",
            f"{base}/ms/products/{{task_id}}/definitions",
        ],
        "scm": [
            f"{base}/scm/review/{{task_id}}",
            f"{base}/scm/approve/{{task_id}}",
            f"{base}/scm/reject/{{task_id}}",
            f"{base}/scm/purchase-order/{{task_id}}",
            f"{base}/scm/status/{{task_id}}",
        ],
        "wms": [
            f"{base}/wms/reserve/{{task_id}}",
            f"{base}/wms/confirm/{{task_id}}",
            f"{base}/wms/status/{{task_id}}",
            f"{base}/wms/inventory-snapshots/{{task_id}}",
        ],
        "oms": [
            f"{base}/oms/listing-draft/{{task_id}}",
            f"{base}/oms/publish/{{task_id}}",
            f"{base}/oms/activate/{{task_id}}",
            f"{base}/oms/status/{{task_id}}",
            f"{base}/oms/sales-metrics/{{task_id}}",
        ],
        "crm": [
            f"{base}/crm/feedbacks/{{task_id}}",
            f"{base}/crm/complaints/{{task_id}}",
            f"{base}/crm/followup/{{task_id}}",
            f"{base}/crm/summary/{{task_id}}",
        ],
        "bi": [
            f"{base}/bi/push-selection-result/{{task_id}}",
            f"{base}/bi/push-execution-feedback/{{task_id}}",
            f"{base}/bi/kpi-dataset/{{task_id}}",
            f"{base}/bi/summary/{{task_id}}",
        ],
    }
    return endpoint_map.get(domain_code, [])


class SCMReviewRequest(BaseModel):
    scm_name: str = Field(default="default")
    supplier_code: str | None = None
    quantity: int = Field(default=200, ge=1)


class SCMAproveRequest(BaseModel):
    approved_quantity: int | None = None
    approved_supplier: str | None = None
    notes: str | None = None


class SCMRejectRequest(BaseModel):
    reason: str | None = None


class SCMPurchaseOrderRequest(BaseModel):
    scm_name: str = Field(default="default")
    quantity: int = Field(default=200, ge=1)
    supplier_code: str | None = None


class WMSReserveRequest(BaseModel):
    wms_name: str = Field(default="default")
    sku_code: str | None = None
    quantity: int = Field(default=200, ge=1)
    warehouse_code: str | None = None


class WMSConfirmRequest(BaseModel):
    confirmed_quantity: int | None = None
    notes: str | None = None


class OMSListingDraftRequest(BaseModel):
    oms_name: str = Field(default="default")
    title: str | None = None
    price: float | None = None
    sku_code: str | None = None
    marketplace: str | None = None


class OMSPublishRequest(BaseModel):
    notes: str | None = None


class OMSActivateRequest(BaseModel):
    notes: str | None = None


class CRMFollowupRequest(BaseModel):
    crm_name: str = Field(default="default")
    followup_type: str = Field(default="general")
    content: str | None = None
    customer_id: str | None = None


class BIPushRequest(BaseModel):
    bi_name: str = Field(default="default")


async def _get_scm_service(current_user: dict) -> tuple[SCMDomainService, Any]:
    session = get_async_session_factory()()
    service = SCMDomainService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


async def _get_wms_service(current_user: dict) -> tuple[WMSDomainService, Any]:
    session = get_async_session_factory()()
    service = WMSDomainService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


async def _get_oms_service(current_user: dict) -> tuple[OMSDomainService, Any]:
    session = get_async_session_factory()()
    service = OMSDomainService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


async def _get_crm_service(current_user: dict) -> tuple[CRMDomainService, Any]:
    session = get_async_session_factory()()
    service = CRMDomainService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


async def _get_bi_service(current_user: dict) -> tuple[BIDomainService, Any]:
    session = get_async_session_factory()()
    service = BIDomainService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


@router.post("/scm/review/{task_id}", response_model=dict)
async def scm_review(task_id: str, request: SCMReviewRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_scm_service(current_user)
    try:
        result = await service.review_supply_chain(task_id=task_id, scm_name=request.scm_name, supplier_code=request.supplier_code, quantity=request.quantity)
        await session.commit()
        add_audit_log("erp.scm.review", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("SCM审核失败")
        raise HTTPException(status_code=503, detail=f"SCM审核失败: {e}")
    finally:
        await session.close()


@router.post("/scm/approve/{task_id}", response_model=dict)
async def scm_approve(task_id: str, request: SCMAproveRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_scm_service(current_user)
    try:
        result = await service.approve_supply_chain(task_id=task_id, approved_quantity=request.approved_quantity, approved_supplier=request.approved_supplier, notes=request.notes)
        await session.commit()
        add_audit_log("erp.scm.approve", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("SCM审批失败")
        raise HTTPException(status_code=503, detail=f"SCM审批失败: {e}")
    finally:
        await session.close()


@router.post("/scm/reject/{task_id}", response_model=dict)
async def scm_reject(task_id: str, request: SCMRejectRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_scm_service(current_user)
    try:
        result = await service.reject_supply_chain(task_id=task_id, reason=request.reason)
        await session.commit()
        add_audit_log("erp.scm.reject", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("SCM驳回失败")
        raise HTTPException(status_code=503, detail=f"SCM驳回失败: {e}")
    finally:
        await session.close()


@router.post("/scm/purchase-order/{task_id}", response_model=dict)
async def scm_create_purchase_order(task_id: str, request: SCMPurchaseOrderRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_scm_service(current_user)
    try:
        result = await service.create_purchase_order(task_id=task_id, scm_name=request.scm_name, quantity=request.quantity, supplier_code=request.supplier_code)
        await session.commit()
        add_audit_log("erp.scm.purchase_order.create", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("SCM创建采购单失败")
        raise HTTPException(status_code=503, detail=f"SCM创建采购单失败: {e}")
    finally:
        await session.close()


@router.get("/scm/status/{task_id}", response_model=dict)
async def scm_get_status(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_scm_service(current_user)
    try:
        return await service.get_supply_chain_status(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询SCM状态失败")
        raise HTTPException(status_code=503, detail=f"查询SCM状态失败: {e}")
    finally:
        await session.close()


@router.post("/wms/reserve/{task_id}", response_model=dict)
async def wms_reserve(task_id: str, request: WMSReserveRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_wms_service(current_user)
    try:
        result = await service.reserve_inventory(task_id=task_id, wms_name=request.wms_name, sku_code=request.sku_code, quantity=request.quantity, warehouse_code=request.warehouse_code)
        await session.commit()
        add_audit_log("erp.wms.reserve", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("WMS库存预留失败")
        raise HTTPException(status_code=503, detail=f"WMS库存预留失败: {e}")
    finally:
        await session.close()


@router.post("/wms/confirm/{task_id}", response_model=dict)
async def wms_confirm(task_id: str, request: WMSConfirmRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_wms_service(current_user)
    try:
        result = await service.confirm_inventory(task_id=task_id, confirmed_quantity=request.confirmed_quantity, notes=request.notes)
        await session.commit()
        add_audit_log("erp.wms.confirm", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("WMS库存确认失败")
        raise HTTPException(status_code=503, detail=f"WMS库存确认失败: {e}")
    finally:
        await session.close()


@router.get("/wms/status/{task_id}", response_model=dict)
async def wms_get_status(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_wms_service(current_user)
    try:
        return await service.get_inventory_status(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询WMS状态失败")
        raise HTTPException(status_code=503, detail=f"查询WMS状态失败: {e}")
    finally:
        await session.close()


@router.get("/wms/inventory-snapshots/{task_id}", response_model=dict)
async def wms_fetch_inventory_snapshots(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_wms_service(current_user)
    try:
        return await service.fetch_inventory_snapshots(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询WMS库存快照失败")
        raise HTTPException(status_code=503, detail=f"查询WMS库存快照失败: {e}")
    finally:
        await session.close()


@router.post("/oms/listing-draft/{task_id}", response_model=dict)
async def oms_create_listing_draft(task_id: str, request: OMSListingDraftRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_oms_service(current_user)
    try:
        result = await service.create_listing_draft(task_id=task_id, oms_name=request.oms_name, title=request.title, price=request.price, sku_code=request.sku_code, marketplace=request.marketplace)
        await session.commit()
        add_audit_log("erp.oms.listing_draft.create", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OMS创建Listing草稿失败")
        raise HTTPException(status_code=503, detail=f"OMS创建Listing草稿失败: {e}")
    finally:
        await session.close()


@router.post("/oms/publish/{task_id}", response_model=dict)
async def oms_publish(task_id: str, request: OMSPublishRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_oms_service(current_user)
    try:
        result = await service.publish_listing(task_id=task_id, notes=request.notes)
        await session.commit()
        add_audit_log("erp.oms.publish", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OMS发布Listing失败")
        raise HTTPException(status_code=503, detail=f"OMS发布Listing失败: {e}")
    finally:
        await session.close()


@router.post("/oms/activate/{task_id}", response_model=dict)
async def oms_activate(task_id: str, request: OMSActivateRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_oms_service(current_user)
    try:
        result = await service.activate_listing(task_id=task_id, notes=request.notes)
        await session.commit()
        add_audit_log("erp.oms.activate", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OMS激活Listing失败")
        raise HTTPException(status_code=503, detail=f"OMS激活Listing失败: {e}")
    finally:
        await session.close()


@router.get("/oms/status/{task_id}", response_model=dict)
async def oms_get_status(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_oms_service(current_user)
    try:
        return await service.get_order_status(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询OMS状态失败")
        raise HTTPException(status_code=503, detail=f"查询OMS状态失败: {e}")
    finally:
        await session.close()


@router.get("/oms/sales-metrics/{task_id}", response_model=dict)
async def oms_fetch_sales_metrics(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_oms_service(current_user)
    try:
        return await service.fetch_sales_metrics(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询OMS销售指标失败")
        raise HTTPException(status_code=503, detail=f"查询OMS销售指标失败: {e}")
    finally:
        await session.close()


@router.get("/crm/feedbacks/{task_id}", response_model=dict)
async def crm_fetch_feedbacks(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_crm_service(current_user)
    try:
        result = await service.fetch_customer_feedbacks(task_id=task_id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("CRM客户反馈查询失败")
        raise HTTPException(status_code=503, detail=f"CRM客户反馈查询失败: {e}")
    finally:
        await session.close()


@router.get("/crm/complaints/{task_id}", response_model=dict)
async def crm_fetch_complaints(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_crm_service(current_user)
    try:
        result = await service.fetch_complaints(task_id=task_id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("CRM投诉查询失败")
        raise HTTPException(status_code=503, detail=f"CRM投诉查询失败: {e}")
    finally:
        await session.close()


@router.post("/crm/followup/{task_id}", response_model=dict)
async def crm_push_followup(task_id: str, request: CRMFollowupRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_crm_service(current_user)
    try:
        result = await service.push_followup(task_id=task_id, crm_name=request.crm_name, followup_type=request.followup_type, content=request.content, customer_id=request.customer_id)
        await session.commit()
        add_audit_log("erp.crm.followup.push", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("CRM跟进记录推送失败")
        raise HTTPException(status_code=503, detail=f"CRM跟进记录推送失败: {e}")
    finally:
        await session.close()


@router.get("/crm/summary/{task_id}", response_model=dict)
async def crm_get_summary(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_crm_service(current_user)
    try:
        return await service.get_crm_summary(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询CRM摘要失败")
        raise HTTPException(status_code=503, detail=f"查询CRM摘要失败: {e}")
    finally:
        await session.close()


@router.post("/bi/push-selection-result/{task_id}", response_model=dict)
async def bi_push_selection_result(task_id: str, request: BIPushRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_bi_service(current_user)
    try:
        result = await service.push_selection_result(task_id=task_id, bi_name=request.bi_name)
        await session.commit()
        add_audit_log("erp.bi.push_selection_result", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("BI选品结果推送失败")
        raise HTTPException(status_code=503, detail=f"BI选品结果推送失败: {e}")
    finally:
        await session.close()


@router.post("/bi/push-execution-feedback/{task_id}", response_model=dict)
async def bi_push_execution_feedback(task_id: str, request: BIPushRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_bi_service(current_user)
    try:
        result = await service.push_execution_feedback(task_id=task_id, bi_name=request.bi_name)
        await session.commit()
        add_audit_log("erp.bi.push_execution_feedback", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("BI执行反馈推送失败")
        raise HTTPException(status_code=503, detail=f"BI执行反馈推送失败: {e}")
    finally:
        await session.close()


@router.get("/bi/kpi-dataset/{task_id}", response_model=dict)
async def bi_read_kpi_dataset(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_bi_service(current_user)
    try:
        return await service.read_kpi_dataset(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("BI KPI数据集读取失败")
        raise HTTPException(status_code=503, detail=f"BI KPI数据集读取失败: {e}")
    finally:
        await session.close()


@router.get("/bi/summary/{task_id}", response_model=dict)
async def bi_get_summary(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_bi_service(current_user)
    try:
        return await service.get_bi_summary(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询BI摘要失败")
        raise HTTPException(status_code=503, detail=f"查询BI摘要失败: {e}")
    finally:
        await session.close()


class FeedbackEvaluateRequest(BaseModel):
    oms_name: str = Field(default="default")
    wms_name: str = Field(default="default")
    crm_name: str = Field(default="default")
    fms_name: str = Field(default="default")
    bi_name: str = Field(default="default")


async def _get_feedback_evaluator(current_user: dict) -> tuple[FeedbackEvaluator, Any]:
    session = get_async_session_factory()()
    service = FeedbackEvaluator(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session


@router.post("/feedback/evaluate/{task_id}", response_model=dict)
async def feedback_evaluate(task_id: str, request: FeedbackEvaluateRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_feedback_evaluator(current_user)
    try:
        await service.collect_feedback_metrics(
            task_id=task_id,
            oms_name=request.oms_name,
            wms_name=request.wms_name,
            crm_name=request.crm_name,
            fms_name=request.fms_name,
            bi_name=request.bi_name,
        )
        result = await service.evaluate_suggestion(task_id=task_id)
        await session.commit()
        add_audit_log("erp.feedback.evaluate", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("反馈评估失败")
        raise HTTPException(status_code=503, detail=f"反馈评估失败: {e}")
    finally:
        await session.close()


@router.get("/feedback/evaluation/{task_id}", response_model=dict)
async def feedback_get_evaluation(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await _get_feedback_evaluator(current_user)
    try:
        return await service.get_evaluation(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("查询反馈评估失败")
        raise HTTPException(status_code=503, detail=f"查询反馈评估失败: {e}")
    finally:
        await session.close()


@router.post("/feedback/collect-metrics/{task_id}", response_model=dict)
async def feedback_collect_metrics(task_id: str, request: FeedbackEvaluateRequest, current_user: dict = Depends(get_current_user)):
    service, session = await _get_feedback_evaluator(current_user)
    try:
        result = await service.collect_feedback_metrics(
            task_id=task_id,
            oms_name=request.oms_name,
            wms_name=request.wms_name,
            crm_name=request.crm_name,
            fms_name=request.fms_name,
            bi_name=request.bi_name,
        )
        await session.commit()
        add_audit_log("erp.feedback.collect_metrics", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("指标采集失败")
        raise HTTPException(status_code=503, detail=f"指标采集失败: {e}")
    finally:
        await session.close()
