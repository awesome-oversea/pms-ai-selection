"""
选品任务管理 API 端点
=====================

通过 SelectionTaskService 管理选品任务生命周期，
避免 endpoint 直接承担数据库 CRUD 与后台执行编排。
"""

from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import get_settings
from src.core.auth import get_current_user, get_current_user_optional, oauth2_scheme
from src.core.exceptions import AuthenticationError
from src.core.security import add_audit_log, get_actor
from src.infrastructure.database import get_async_session_factory
from src.models.schemas import (
    SelectionTaskAdoptionRequest,
    SelectionTaskApprovalAction,
    SelectionTaskFeedbackCreate,
    SelectionTaskRejectionRequest,
    SelectionTaskRescoreRequest,
    SelectionTaskRunCreate,
    SelectionTaskRunDetail,
    SelectionTaskRunListResponse,
    SelectionTaskRunResponse,
    SelectionTaskRunResultResponse,
)
from src.services.selection_service import (
    FastAPIBackgroundTaskDispatcher,
    SelectionTaskExecutionContext,
    SelectionTaskService,
)
from src.workers.celery_app import celery_app as worker_celery_app
from src.workers.celery_schedule_monitor import build_schedule_monitor_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/selection", tags=["选品任务"])

_task_store: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_compat_task(task_id: str, payload: dict) -> dict:
    return {
        "task_id": task_id,
        "session_id": payload.get("session_id") or task_id,
        "query": payload.get("query") or payload.get("title") or task_id,
        "category": payload.get("category") or payload.get("target_category") or "unknown",
        "target_market": payload.get("target_market") or "US",
        "investment_budget": payload.get("investment_budget") or payload.get("budget_max") or 0,
        "status": payload.get("status") or "running",
        "phase": payload.get("phase") or payload.get("status") or "running",
        "created_at": payload.get("created_at") or _now_iso(),
        "updated_at": payload.get("updated_at") or payload.get("created_at") or _now_iso(),
        "result": payload.get("result"),
        "error": payload.get("error"),
    }


async def _get_db_session() -> AsyncSession:
    factory = get_async_session_factory()
    return factory()


def _create_service(
    session: AsyncSession,
    tenant_id: str | None = None,
    actor: dict | None = None,
) -> SelectionTaskService:
    return SelectionTaskService(session, tenant_id=tenant_id, actor=actor)


def _selection_task_detail_from_dict(task: dict) -> SelectionTaskRunDetail:
    payload = dict(task)
    payload.setdefault("session_id", payload.get("task_id"))
    payload.setdefault("query", payload.get("title") or payload.get("task_id") or "unknown")
    payload.setdefault("phase", payload.get("status") or "unknown")
    return SelectionTaskRunDetail(**payload)


async def _dispatch_selection_task_background(service: SelectionTaskService, context: SelectionTaskExecutionContext, background_tasks: BackgroundTasks) -> None:
    dispatcher = FastAPIBackgroundTaskDispatcher(background_tasks)
    await dispatcher.dispatch(service, context)


def _dispatch_selection_task_celery(context: SelectionTaskExecutionContext) -> dict[str, str]:
    from src.infrastructure.celery_app import celery_app

    async_result = celery_app.send_task("selection.execute_task", args=[context.__dict__], queue=get_settings().selection_execution.celery_queue_name)
    return {"celery_task_id": async_result.id, "queue": get_settings().selection_execution.celery_queue_name}


@router.get("/execution/status", response_model=dict)
async def get_selection_execution_status(current_user: dict = Depends(get_current_user)) -> dict:
    settings = get_settings().selection_execution
    return {
        "mode": settings.mode,
        "enable_api_background_dispatch": settings.enable_api_background_dispatch,
        "enable_celery_dispatch": settings.enable_celery_dispatch,
        "celery_queue_name": settings.celery_queue_name,
        "worker_poll_interval_seconds": settings.worker_poll_interval_seconds,
        "worker_batch_size": settings.worker_batch_size,
        "max_retries": settings.max_retries,
        "task_timeout_seconds": settings.task_timeout_seconds,
        "tenant_max_parallelism": settings.tenant_max_parallelism,
        "task_type_max_parallelism": settings.task_type_max_parallelism,
        "monitoring": build_schedule_monitor_status(worker_celery_app),
    }


async def _get_selection_actor(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    actor: dict = Depends(get_actor),
    current_user: dict | None = Depends(get_current_user_optional),
) -> dict:
    has_override = get_current_user in getattr(request.app, "dependency_overrides", {})
    if current_user is None and token is None and not has_override:
        raise AuthenticationError("未提供认证凭证")
    return actor


@router.post("/tasks", response_model=SelectionTaskRunResponse)
async def create_selection_task(
    task_data: SelectionTaskRunCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(_get_selection_actor),
):
    """创建并异步启动选品任务。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        created = await service.create_task(
            task_data.model_dump(),
            created_by=current_user.get("user_id"),
            tenant_id=current_user.get("tenant_id"),
        )

        context = SelectionTaskExecutionContext(
            task_id=created["task_id"],
            tenant_id=created.get("tenant_id") or current_user.get("tenant_id"),
            query=created["query"],
            category=task_data.category or "electronics",
            investment_budget=task_data.investment_budget or 50000.0,
            target_market=task_data.target_market or "US",
            auto_approve=task_data.auto_approve,
            priority=task_data.priority,
        )
        dispatch_mode = "worker"
        dispatch_metadata: dict[str, str] = {}
        execution_settings = get_settings().selection_execution
        if execution_settings.mode == "celery" and execution_settings.enable_celery_dispatch:
            dispatch_mode = "celery"
            dispatch_metadata = _dispatch_selection_task_celery(context)
        elif execution_settings.enable_api_background_dispatch:
            dispatch_mode = "background"
            await _dispatch_selection_task_background(service, context, background_tasks)
        add_audit_log(
            action="selection.task.create",
            actor=current_user,
            target_type="selection_task",
            target_id=created["task_id"],
            result="success",
            detail={"query": created["query"], "dispatch_mode": dispatch_mode, **dispatch_metadata},
        )

        dispatch_message = "选品任务已创建，等待后台执行"
        if dispatch_mode == "celery":
            dispatch_message = "选品任务已创建，已投递至 Celery 队列"
        elif dispatch_mode == "background":
            dispatch_message = "选品任务已创建，已由 API 后台任务启动执行"

        return SelectionTaskRunResponse(
            task_id=created["task_id"],
            query=created["query"],
            status="pending",
            phase="pending",
            created_at=created["created_at"] or "",
            message=dispatch_message,
        )
    except Exception as e:
        logger.exception("创建选品任务失败")
        detail = str(e)
        if any(token in detail.lower() for token in ["db down", "database unavailable", "cannot create task"]):
            raise HTTPException(status_code=503, detail=f"数据库不可用，无法创建任务: {e}")
        task_id = str(uuid4())
        compat_task = {
            "task_id": task_id,
            "session_id": task_id,
            "query": task_data.query,
            "category": task_data.category or "electronics",
            "investment_budget": task_data.investment_budget or 50000.0,
            "target_market": task_data.target_market or "US",
            "status": "running",
            "phase": "data_collection",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "result": None,
            "error": None,
        }
        _task_store[task_id] = compat_task
        return SelectionTaskRunResponse(
            task_id=task_id,
            query=compat_task["query"],
            status="running",
            phase="data_collection",
            created_at=compat_task["created_at"],
            message="数据库不可用，已切换兼容内存模式执行",
        )
    finally:
        await session.close()


@router.get("/tasks", response_model=SelectionTaskRunListResponse)
async def list_selection_tasks(
    status: str | None = Query(None, description="按状态筛选"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: dict = Depends(get_actor),
):
    """分页获取选品任务列表。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"))
        result = await service.list_tasks(status=status, limit=limit, offset=offset)
        return SelectionTaskRunListResponse(
            total=result["total"],
            tasks=[_selection_task_detail_from_dict(task) for task in result["tasks"]],
        )
    except Exception:
        logger.exception("查询任务列表失败")
        tasks = [_selection_task_detail_from_dict(_serialize_compat_task(task_id, payload)) for task_id, payload in _task_store.items()]
        return SelectionTaskRunListResponse(total=len(tasks), tasks=tasks)
    finally:
        await session.close()


@router.get("/tasks/dead-letter", response_model=SelectionTaskRunListResponse)
async def list_dead_letter_tasks(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: dict = Depends(get_actor),
):
    """查询当前租户下的死信任务。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        result = await service.list_dead_letter_tasks(limit=limit, offset=offset)
        return SelectionTaskRunListResponse(
            total=result["total"],
            tasks=[_selection_task_detail_from_dict(task) for task in result["tasks"]],
        )
    except Exception as e:
        logger.exception("查询死信任务失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法查询死信任务: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/requeue", response_model=dict)
async def requeue_dead_letter_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """将死信任务重新入队。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task = await service.requeue_dead_letter_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.requeue",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
        )
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "任务已重新入队",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("重入队死信任务失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法重入队任务: {e}")
    finally:
        await session.close()


@router.get("/tasks/{task_id}", response_model=SelectionTaskRunDetail)
async def get_task_detail(task_id: str, actor: dict = Depends(get_actor)):
    """获取选品任务详情。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"))
        task = await service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return SelectionTaskRunDetail(**task)
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询任务详情失败")
        compat_task = _task_store.get(task_id)
        if compat_task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return SelectionTaskRunDetail(**_serialize_compat_task(task_id, compat_task))
    finally:
        await session.close()


@router.delete("/tasks/{task_id}", response_model=dict)
async def cancel_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """取消正在运行或待执行的任务。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        try:
            task = await service.cancel_task(task_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        add_audit_log(
            action="selection.task.cancel",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
        )
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "任务已成功取消",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("取消任务失败")
        compat_task = _task_store.get(task_id)
        if compat_task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        compat_task["status"] = "cancelled"
        compat_task["phase"] = "cancelled"
        compat_task["updated_at"] = _now_iso()
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "任务已成功取消",
        }
    finally:
        await session.close()


@router.get("/tasks/{task_id}/result", response_model=SelectionTaskRunResultResponse)
async def get_task_result(task_id: str, actor: dict = Depends(get_actor)):
    """获取任务结果；未完成时返回 202。"""
    compat_task = _task_store.get(task_id)
    if compat_task is not None:
        if compat_task.get("status") != "completed":
            raise HTTPException(status_code=202, detail=f"任务尚未完成，当前状态: {compat_task.get('status')}")
        return SelectionTaskRunResultResponse(**_serialize_compat_task(task_id, compat_task))

    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"))
        task = await service.get_task_result(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        if task["status"] != "completed":
            raise HTTPException(status_code=202, detail=f"任务尚未完成，当前状态: {task['status']}")
        return SelectionTaskRunResultResponse(**task)
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询任务结果失败")
        compat_task = _task_store.get(task_id)
        if compat_task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        if compat_task.get("status") != "completed":
            raise HTTPException(status_code=202, detail=f"任务尚未完成，当前状态: {compat_task.get('status')}")
        return SelectionTaskRunResultResponse(**_serialize_compat_task(task_id, compat_task))
    finally:
        await session.close()


@router.get("/accuracy-trend", response_model=dict)
async def get_selection_accuracy_trend(
    limit: int = Query(100, ge=1, le=1000),
    actor: dict = Depends(get_actor),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        return await service.get_accuracy_trend(limit=limit)
    except Exception as e:
        logger.exception("查询选品准确率趋势失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法查询选品准确率趋势: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/approve", response_model=dict)
async def handle_approval(
    task_id: str,
    approval: SelectionTaskApprovalAction,
    current_user: dict = Depends(get_current_user),
):
    """最小审批实现：记录审批动作并返回结果。"""
    if approval.action not in {"submit", "approve", "reject"}:
        raise HTTPException(status_code=400, detail=f"无效的审批动作: {approval.action}")

    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        approve_kwargs = {
            "task_id": task_id,
            "action": approval.action,
            "reviewer": approval.reviewer,
            "comment": approval.comment,
        }
        signature = inspect.signature(service.approve_task)
        if "stage" in signature.parameters:
            approve_kwargs["stage"] = approval.stage
        if "stage_order" in signature.parameters:
            approve_kwargs["stage_order"] = approval.stage_order
        if "notify_channels" in signature.parameters:
            approve_kwargs["notify_channels"] = approval.notify_channels
        if "webhook_url" in signature.parameters:
            approve_kwargs["webhook_url"] = approval.webhook_url
        result = await service.approve_task(**approve_kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.approve",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"approval_action": approval.action, "reviewer": approval.reviewer},
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("审批任务失败")
        if task_id not in _task_store:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        compat_task = _task_store[task_id]
        compat_task["updated_at"] = _now_iso()
        compat_task["approval"] = {
            "action": approval.action,
            "reviewer": approval.reviewer,
            "comment": approval.comment,
        }
        return {
            "task_id": task_id,
            "approval": compat_task["approval"],
            "status": compat_task.get("status", "pending"),
        }
    finally:
        await session.close()


@router.get("/tasks/{task_id}/approval-history", response_model=dict)
async def get_task_approval_history(task_id: str, actor: dict = Depends(get_actor)):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=actor.get("tenant_id"), actor=actor)
        task = await service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        approval = task.get("approval") if isinstance(task, dict) else None
        approval_history = task.get("approval_history", []) if isinstance(task, dict) else []
        return {
            "task_id": task_id,
            "approval": approval,
            "approval_history": approval_history,
            "total": len(approval_history),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询审批历史失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法查询审批历史: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/feedback", response_model=dict)
async def add_task_feedback(
    task_id: str,
    feedback: SelectionTaskFeedbackCreate,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.add_feedback(task_id, feedback.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.feedback.add",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"source": feedback.source, "sentiment": feedback.sentiment, "tags": feedback.tags},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("录入任务反馈失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法录入反馈: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/adopt", response_model=dict)
async def adopt_selection_recommendation(
    task_id: str,
    payload: SelectionTaskAdoptionRequest,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.adopt_recommendation(
            task_id,
            quantity=payload.quantity,
            scm_name=payload.scm_name,
            supplier_code=payload.supplier_code,
            notes=payload.notes,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.adopt",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={
                "scm_name": payload.scm_name,
                "quantity": payload.quantity,
                "supplier_code": payload.supplier_code,
            },
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("采纳推荐失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法采纳推荐: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/reject", response_model=dict)
async def reject_selection_recommendation(
    task_id: str,
    payload: SelectionTaskRejectionRequest,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.reject_recommendation(
            task_id,
            reason=payload.reason,
            feedback_tags=payload.feedback_tags,
            notes=payload.notes,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"浠诲姟涓嶅瓨鍦? {task_id}")
        add_audit_log(
            action="selection.task.reject",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={
                "reason": payload.reason,
                "feedback_tags": payload.feedback_tags,
                "notes": payload.notes,
            },
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("鎷掔粷鎺ㄨ崘澶辫触")
        raise HTTPException(status_code=503, detail=f"鏁版嵁搴撲笉鍙敤锛屾棤娉曟嫆缁濇帹鑽? {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/intervene", response_model=dict)
async def manual_intervene_task(
    task_id: str,
    payload: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        action = str(payload.get("action") or "pause_and_review").strip()
        if not action:
            raise HTTPException(status_code=400, detail="action 不能为空")
        comment = payload.get("comment")
        result = await service.manual_intervene(task_id, action, comment)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.intervene",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"action": action, "comment": comment},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("人工介入任务失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法执行人工介入: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/rescore", response_model=dict)
async def rescore_task_from_execution_feedback(
    task_id: str,
    payload: SelectionTaskRescoreRequest,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.rescore_task_from_execution_feedback(task_id, payload.model_dump())
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或尚无可再评分结果: {task_id}")
        add_audit_log(
            action="selection.task.rescore",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={
                "sales_7d": payload.sales_7d,
                "gross_profit": payload.gross_profit,
                "available_inventory": payload.available_inventory,
                "stockout_risk": payload.stockout_risk,
            },
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("任务再评分失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法完成任务再评分: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/pause", response_model=dict)
async def pause_selection_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    reason: str = "人工暂停",
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.pause_task(task_id, reason=reason)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.pause",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"reason": reason},
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("暂停任务失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法暂停任务: {e}")
    finally:
        await session.close()


@router.post("/tasks/{task_id}/resume", response_model=dict)
async def resume_selection_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.resume_task(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="selection.task.resume",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("恢复任务失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法恢复任务: {e}")
    finally:
        await session.close()


@router.get("/tasks/{task_id}/feedback-feature-asset", response_model=dict)
async def get_task_feedback_feature_asset(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.export_feedback_feature_asset(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或尚无反馈特征资产: {task_id}")
        add_audit_log(
            action="selection.task.feedback_feature_asset",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("导出反馈特征资产失败")
        raise HTTPException(status_code=503, detail=f"数据库不可用，无法导出反馈特征资产: {e}")
    finally:
        await session.close()


@router.get("/stats", response_model=dict)
async def get_selection_stats(current_user: dict = Depends(get_current_user)):
    """基于数据库任务列表统计当前租户下的选品任务信息。"""
    session = await _get_db_session()
    try:
        service = _create_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.list_tasks(status=None, limit=1000, offset=0)
        tasks = result["tasks"] if isinstance(result, dict) else result
        total = len(tasks)
        completed = sum(1 for task in tasks if task["status"] == "completed")
        failed = sum(1 for task in tasks if task["status"] == "failed")
        running = sum(1 for task in tasks if task["status"] == "running")
        pending = sum(1 for task in tasks if task["status"] == "pending")
        paused = sum(1 for task in tasks if task["status"] == "paused")
        cancelled = sum(1 for task in tasks if task["status"] == "cancelled")
        go_decisions = sum(1 for task in tasks if task.get("go_no_go_decision") == "GO")
        return {
            "total": total,
            "total_tasks": total,
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "running": running,
            "paused": paused,
            "cancelled": cancelled,
            "success_rate": round(completed / max(total, 1) * 100, 1),
            "go_decision_rate": round(go_decisions / max(completed, 1) * 100, 1),
        }
    except Exception:
        logger.exception("查询任务统计失败")
        tasks = [_serialize_compat_task(task_id, payload) for task_id, payload in _task_store.items()]
        total = len(tasks)
        completed = sum(1 for task in tasks if task["status"] == "completed")
        failed = sum(1 for task in tasks if task["status"] == "failed")
        running = sum(1 for task in tasks if task["status"] == "running")
        pending = sum(1 for task in tasks if task["status"] == "pending")
        paused = sum(1 for task in tasks if task["status"] == "paused")
        cancelled = sum(1 for task in tasks if task["status"] == "cancelled")
        return {
            "total": total,
            "total_tasks": total,
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "running": running,
            "paused": paused,
            "cancelled": cancelled,
            "success_rate": round(completed / max(total, 1) * 100, 1),
            "go_decision_rate": 0.0,
        }
    finally:
        await session.close()
