from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from statistics import mean

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.config.settings import get_settings
from src.core.auth import decode_token, get_current_user
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.infrastructure.ws_gateway import WSMessageType
from src.infrastructure.ws_gateway_status import get_websocket_manager
from src.models.schemas import SelectionTaskRunCreate
from src.services.erp_integration_service import ErpIntegrationService
from src.services.knowledge_service import KnowledgeService
from src.services.local_knowledge_service import LocalKnowledgeService
from src.services.selection_service import (
    FastAPIBackgroundTaskDispatcher,
    SelectionTaskExecutionContext,
    SelectionTaskService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bff", tags=["BFF"])


async def _get_db_session() -> AsyncSession:
    factory = get_async_session_factory()
    return factory()


def _create_knowledge_service(session: AsyncSession | None, tenant_id: str | None = None, actor: dict | None = None):
    if session is None:
        return LocalKnowledgeService()
    return KnowledgeService(session, tenant_id=tenant_id, actor=actor)


def _decode_websocket_user(token: str) -> dict:
    payload = decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token 中缺少用户标识")
    return {
        "username": username,
        "user_id": payload.get("user_id"),
        "is_superuser": payload.get("is_superuser", False),
        "tenant_id": payload.get("tenant_id"),
        "tenant_key": payload.get("tenant_key"),
        "tenant_name": payload.get("tenant_name"),
        "roles": payload.get("roles", []),
        "authorization": f"Bearer {token}",
    }


def _extract_signal_governance_status(task: dict) -> str | None:
    status = task.get("signal_governance_status")
    if status:
        return str(status)
    decision_output = task.get("decision_output")
    if not isinstance(decision_output, dict):
        return None
    quality_summary = decision_output.get("quality_summary")
    if isinstance(quality_summary, dict) and quality_summary.get("signal_governance_status"):
        return str(quality_summary.get("signal_governance_status"))
    governance = decision_output.get("data_source_governance")
    if isinstance(governance, dict) and governance.get("governance_status"):
        return str(governance.get("governance_status"))
    return None


def _extract_signal_governance_summary(task: dict) -> dict | None:
    summary = task.get("signal_governance_summary")
    if isinstance(summary, dict):
        return summary
    governance = task.get("data_source_governance")
    if not isinstance(governance, dict):
        decision_output = task.get("decision_output")
        governance = (
            decision_output.get("data_source_governance")
            if isinstance(decision_output, dict) and isinstance(decision_output.get("data_source_governance"), dict)
            else {}
        )
    status = _extract_signal_governance_status(task)
    if status is None and not governance:
        return None
    summary_payload = {
        "signal_governance_status": status or "unknown",
        "local_validation_only_sources": list(governance.get("local_validation_only_sources") or []),
        "enterprise_ready_sources": list(governance.get("enterprise_ready_sources") or []),
        "mock_only_sources": list(governance.get("mock_only_sources") or []),
        "not_ready_sources": list(governance.get("not_ready_sources") or []),
        "requires_enterprise_connectors": str(status or "unknown") != "enterprise_ready",
    }
    if governance.get("next_action"):
        summary_payload["next_action"] = governance.get("next_action")
    return summary_payload


async def _build_selection_stream_payload(current_user: dict) -> dict:
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.list_tasks(status=None, limit=20, offset=0)
        tasks = result["tasks"]
        counts = Counter(task.get("status", "unknown") for task in tasks)
        recent_tasks = tasks[:5]
        governance_counter = Counter(
            status for task in tasks for status in [_extract_signal_governance_status(task)] if status
        )
        requires_enterprise_connectors_count = sum(
            1
            for task in tasks
            if ((_extract_signal_governance_summary(task) or {}).get("requires_enterprise_connectors"))
        )
        signals = [
            {
                "task_id": task.get("task_id"),
                "trend_direction": ((task.get("decision_output") or {}).get("market_summary") or {}).get("trend_direction"),
                "decision": ((task.get("decision_output") or {}).get("decision") or {}).get("decision"),
                "risk_count": len((task.get("decision_output") or {}).get("risks") or []),
                "signal_governance_status": _extract_signal_governance_status(task),
                "requires_enterprise_connectors": bool(
                    (_extract_signal_governance_summary(task) or {}).get("requires_enterprise_connectors")
                ),
            }
            for task in recent_tasks
            if isinstance(task.get("decision_output"), dict)
        ]
        agent_steps = [
            {
                "task_id": task.get("task_id"),
                "steps": (((task.get("decision_output") or {}).get("execution_summary") or {}).get("steps") or []),
            }
            for task in recent_tasks
            if isinstance(task.get("decision_output"), dict)
        ]
        return {
            "summary": {
                "tenant_id": current_user.get("tenant_id"),
                "username": current_user.get("username"),
                "total": result["total"],
                "by_status": dict(counts),
                "signal_governance_overview": dict(governance_counter),
                "requires_enterprise_connectors_count": requires_enterprise_connectors_count,
                "recent_tasks": recent_tasks,
            },
            "tasks": {
                "total": result["total"],
                "tasks": tasks,
            },
            "signals": signals,
            "agent_steps": agent_steps,
            "reconnect": {"retry_ms": 3000, "strategy": "client_reconnect"},
            "transport": {
                "protocol": "sse",
                "heartbeat_seconds": 1,
                "stream_type": "selection-workbench",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }
    finally:
        await session.close()


@router.get("/auth/me", response_model=dict)
async def get_bff_me(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": current_user.get("user_id"),
        "username": current_user.get("username"),
        "tenant_id": current_user.get("tenant_id"),
        "tenant_key": current_user.get("tenant_key"),
        "tenant_name": current_user.get("tenant_name"),
        "roles": current_user.get("roles", []),
        "auth_source": current_user.get("auth_source", "local_jwt"),
        "provider_issuer": current_user.get("provider_issuer"),
    }


@router.get("/workbench/selection/summary", response_model=dict)
async def get_selection_workbench_summary(current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.list_tasks(status=None, limit=100, offset=0)
        tasks = result["tasks"]
        counts = Counter(task.get("status", "unknown") for task in tasks)
        recent_tasks = tasks[:5]
        governance_counter = Counter(
            status for task in tasks for status in [_extract_signal_governance_status(task)] if status
        )
        requires_enterprise_connectors_count = sum(
            1
            for task in tasks
            if ((_extract_signal_governance_summary(task) or {}).get("requires_enterprise_connectors"))
        )
        decision_snapshot = [
            {
                "task_id": task.get("task_id"),
                "query": task.get("query"),
                "decision": (task.get("decision_output") or {}).get("decision"),
                "pricing": (task.get("decision_output") or {}).get("pricing"),
                "profitability": (task.get("decision_output") or {}).get("profitability"),
                "signal_governance_status": _extract_signal_governance_status(task),
                "signal_governance_summary": _extract_signal_governance_summary(task),
            }
            for task in recent_tasks
            if isinstance(task.get("decision_output"), dict)
        ]
        pending_approval_count = sum(
            1
            for task in tasks
            if isinstance(task.get("approval"), dict)
            and str(task.get("approval", {}).get("status") or task.get("approval", {}).get("action") or "").lower() == "pending"
        )
        high_risk_count = sum(
            1
            for task in tasks
            if isinstance(task.get("decision_output"), dict)
            and len((task.get("decision_output") or {}).get("risks") or []) > 0
        )
        roi_values = [
            float(roi)
            for task in tasks
            for roi in [(((task.get("decision_output") or {}).get("profitability") or {}).get("roi_year1_percent") or ((task.get("decision_output") or {}).get("profitability") or {}).get("expected_roi"))]
            if roi is not None
        ]
        updated_candidates = [task.get("updated_at") or task.get("created_at") for task in tasks if task.get("updated_at") or task.get("created_at")]
        try:
            accuracy_payload = await service.get_accuracy_trend(limit=100)
            accuracy_trend = accuracy_payload.get("trend", [])
        except Exception:
            accuracy_trend = []
        return {
            "tenant_id": current_user.get("tenant_id"),
            "username": current_user.get("username"),
            "total": result["total"],
            "by_status": dict(counts),
            "recent_tasks": recent_tasks,
            "decision_snapshot": decision_snapshot,
            "pending_approval_count": pending_approval_count,
            "high_risk_count": high_risk_count,
            "avg_roi_year1_percent": round(sum(roi_values) / len(roi_values), 2) if roi_values else None,
            "go_decision_count": sum(
                1
                for task in tasks
                if str(((task.get("decision_output") or {}).get("decision") or {}).get("decision") or "").upper() == "GO"
            ),
            "signal_governance_overview": dict(governance_counter),
            "requires_enterprise_connectors_count": requires_enterprise_connectors_count,
            "data_source": "selection_task_service",
            "updated_at": max(updated_candidates) if updated_candidates else None,
            "accuracy_trend": accuracy_trend,
        }
    except Exception as e:
        logger.exception("BFF 查询工作台汇总失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台汇总失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/manager/overview", response_model=dict)
async def get_manager_workbench_overview(current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.list_tasks(status=None, limit=200, offset=0)
        tasks = result["tasks"]

        counts = Counter(task.get("status", "unknown") for task in tasks)
        pending_approval_tasks = [
            task for task in tasks
            if isinstance(task.get("approval"), dict)
            and str(task.get("approval", {}).get("status") or "").lower() == "pending"
        ]
        approval_queue = [
            {
                "task_id": task.get("task_id"),
                "query": task.get("query"),
                "current_stage": (task.get("approval") or {}).get("current_stage"),
                "current_stage_order": (task.get("approval") or {}).get("current_stage_order"),
                "approval_count": (task.get("approval") or {}).get("approval_count"),
                "target_market": task.get("target_market"),
                "priority": task.get("priority"),
                "created_at": task.get("created_at"),
                "updated_at": task.get("updated_at"),
                "created_by_username": task.get("created_by_username") or task.get("created_by") or "未标记",
            }
            for task in pending_approval_tasks[:12]
        ]

        performance_map: dict[str, dict[str, float | int | str]] = {}
        for task in tasks:
            owner = str(task.get("created_by_username") or task.get("created_by") or "未标记")
            item = performance_map.setdefault(owner, {
                "owner": owner,
                "task_count": 0,
                "completed_count": 0,
                "go_count": 0,
                "pending_count": 0,
                "avg_roi_year1_percent": 0.0,
                "roi_sample_count": 0,
            })
            item["task_count"] = int(item["task_count"]) + 1
            status = str(task.get("status") or "")
            if status == "completed":
                item["completed_count"] = int(item["completed_count"]) + 1
            if status == "pending":
                item["pending_count"] = int(item["pending_count"]) + 1
            decision = str(((task.get("decision_output") or {}).get("decision") or {}).get("decision") or "").upper()
            if decision == "GO":
                item["go_count"] = int(item["go_count"]) + 1
            roi = (((task.get("decision_output") or {}).get("profitability") or {}).get("roi_year1_percent") or ((task.get("decision_output") or {}).get("profitability") or {}).get("expected_roi"))
            if roi is not None:
                item["avg_roi_year1_percent"] = float(item["avg_roi_year1_percent"]) + float(roi)
                item["roi_sample_count"] = int(item["roi_sample_count"]) + 1

        team_performance = []
        for raw in performance_map.values():
            roi_sample_count = int(raw["roi_sample_count"])
            avg_roi = round(float(raw["avg_roi_year1_percent"]) / roi_sample_count, 2) if roi_sample_count else None
            task_count = int(raw["task_count"])
            completed_count = int(raw["completed_count"])
            go_count = int(raw["go_count"])
            completion_rate = round((completed_count / task_count) * 100, 2) if task_count else 0.0
            go_rate = round((go_count / task_count) * 100, 2) if task_count else 0.0
            score = round((completion_rate * 0.45) + (go_rate * 0.35) + ((avg_roi or 0.0) * 0.2), 2)
            team_performance.append({
                "owner": raw["owner"],
                "task_count": task_count,
                "completed_count": completed_count,
                "pending_count": int(raw["pending_count"]),
                "go_count": go_count,
                "completion_rate": completion_rate,
                "go_rate": go_rate,
                "avg_roi_year1_percent": avg_roi,
                "performance_score": score,
            })
        team_performance.sort(key=lambda item: (item.get("performance_score") or 0, item.get("task_count") or 0), reverse=True)

        accuracy_payload = await service.get_accuracy_trend(limit=200)
        accuracy_trend = accuracy_payload.get("trend", [])
        completion_rate = round((counts.get("completed", 0) / result["total"]) * 100, 2) if result["total"] else 0.0
        roi_values = [
            float(roi)
            for task in tasks
            for roi in [(((task.get("decision_output") or {}).get("profitability") or {}).get("roi_year1_percent") or ((task.get("decision_output") or {}).get("profitability") or {}).get("expected_roi"))]
            if roi is not None
        ]
        governance_counter = Counter(
            status for task in tasks for status in [_extract_signal_governance_status(task)] if status
        )
        requires_enterprise_connectors_count = sum(
            1
            for task in tasks
            if ((_extract_signal_governance_summary(task) or {}).get("requires_enterprise_connectors"))
        )
        summary = {
            "overall_status": "审批待处理" if pending_approval_tasks else ("运行中" if counts.get("running", 0) else "稳定"),
            "gmv": 0,
            "completion_rate": completion_rate,
            "loop_closed": any(bool(task.get("execution_feedback_snapshot")) for task in tasks),
            "bi_asset_count": len([task for task in tasks if task.get("decision_output")]),
            "data_source": "bff_manager_overview",
            "updated_at": max([task.get("updated_at") or task.get("created_at") for task in tasks if task.get("updated_at") or task.get("created_at")], default=None),
            "report_title": approval_queue[0]["query"] if approval_queue else (tasks[0].get("query") if tasks else None),
            "report_count": result["total"],
            "pending_approval_count": len(pending_approval_tasks),
            "avg_roi_year1_percent": round(mean(roi_values), 2) if roi_values else None,
            "accuracy": accuracy_payload.get("accuracy"),
            "correct_tasks": accuracy_payload.get("correct_tasks"),
            "total_accuracy_tasks": accuracy_payload.get("total_tasks"),
            "signal_governance_overview": dict(governance_counter),
            "requires_enterprise_connectors_count": requires_enterprise_connectors_count,
        }
        charts = {
            "trend_chart": {
                "type": "line",
                "title": "准确率趋势",
                "xAxis": [item.get("date") for item in accuracy_trend[-12:]],
                "series": [round(float(item.get("cumulative_accuracy") or item.get("accuracy") or 0) * 100, 2) for item in accuracy_trend[-12:]],
            },
            "profit_chart": {
                "type": "ranking",
                "title": "团队绩效排名",
                "items": [{"name": str(item.get("owner")), "value": float(item.get("performance_score") or 0)} for item in team_performance[:8]],
            },
            "risk_chart": {
                "type": "pie",
                "title": "任务状态分布",
                "items": [{"name": str(status), "value": int(count)} for status, count in counts.items()],
            },
            "execution_chart": {
                "type": "progress",
                "title": "成员完成率",
                "items": [{"name": str(item.get("owner")), "value": float(item.get("completion_rate") or 0)} for item in team_performance[:6]],
            },
        }
        return {
            "summary": summary,
            "charts": charts,
            "team_performance": team_performance,
            "approval_queue": approval_queue,
            "accuracy_trend": accuracy_trend,
            "recent_tasks": tasks[:8],
            "status_distribution": dict(counts),
        }
    except Exception as e:
        logger.exception("BFF 查询管理者工作台失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询管理者工作台失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks", response_model=dict)
async def list_selection_workbench_tasks(
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        return await service.list_tasks(status=status, limit=limit, offset=offset)
    except Exception as e:
        logger.exception("BFF 查询工作台任务失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台任务失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/accuracy-trend", response_model=dict)
async def get_selection_workbench_accuracy_trend(
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        trend = await service.get_accuracy_trend(limit=limit)
        return {
            "tenant_id": current_user.get("tenant_id"),
            "accuracy": trend.get("accuracy"),
            "total_tasks": trend.get("total_tasks"),
            "correct_tasks": trend.get("correct_tasks"),
            "trend": trend.get("trend", []),
        }
    except Exception as e:
        logger.exception("BFF 查询选品准确率趋势失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询选品准确率趋势失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/stream")
async def stream_selection_workbench(current_user: dict = Depends(get_current_user)):
    retry_ms = 3000

    async def event_generator():
        yield ": selection-workbench-stream-start\n\n"
        for _ in range(3):
            payload = await _build_selection_stream_payload(current_user)
            payload["reconnect"] = {"retry_ms": retry_ms, "strategy": "client_reconnect"}
            payload["transport"] = {
                "protocol": "sse",
                "heartbeat_seconds": 1,
                "stream_type": "selection-workbench",
            }
            yield f"retry: {retry_ms}\n"
            yield f"event: selection-workbench\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/workbench/selection/ws")
async def selection_workbench_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="missing token")
        return

    try:
        current_user = _decode_websocket_user(token)
    except Exception:
        await websocket.close(code=4401, reason="invalid token")
        return

    ws_manager = get_websocket_manager()
    conn_id = f"selection-ws-{uuid.uuid4()}"
    task_id = websocket.query_params.get("task_id") or ""
    await websocket.accept()
    await ws_manager.connect(conn_id=conn_id, task_id=task_id, client_type="selection-workbench")

    try:
        initial_payload = await _build_selection_stream_payload(current_user)
        initial_payload["transport"] = {
            "protocol": "websocket",
            "heartbeat_seconds": 30,
            "stream_type": "selection-workbench",
        }
        await websocket.send_json(initial_payload)

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=2.0)
            except TimeoutError:
                payload = await _build_selection_stream_payload(current_user)
                payload["transport"] = {
                    "protocol": "websocket",
                    "heartbeat_seconds": 30,
                    "stream_type": "selection-workbench",
                }
                await websocket.send_json(payload)
                continue

            action = str(message.get("action") or "heartbeat").strip().lower()
            if action == "heartbeat":
                await ws_manager.heartbeat(conn_id)
                await websocket.send_json({
                    "type": WSMessageType.HEARTBEAT.value,
                    "status": "ack",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                continue

            if action == "refresh":
                payload = await _build_selection_stream_payload(current_user)
                payload["transport"] = {
                    "protocol": "websocket",
                    "heartbeat_seconds": 30,
                    "stream_type": "selection-workbench",
                }
                await ws_manager.send_task_progress(task_id=task_id or "selection-workbench", phase="refresh", progress_pct=100, message="workbench refresh")
                await websocket.send_json(payload)
                continue

            if action == "intervene":
                target_task_id = str(message.get("task_id") or "").strip()
                if not target_task_id:
                    await websocket.send_json({"type": "error", "detail": "task_id is required for intervene"})
                    continue
                session = await _get_db_session()
                try:
                    service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
                    result = await service.manual_intervene(
                        task_id=target_task_id,
                        action=str(message.get("intervention_action") or message.get("decision") or "pause_and_review"),
                        comment=message.get("comment"),
                    )
                    if result is None:
                        await websocket.send_json({"type": "error", "detail": f"任务不存在: {target_task_id}"})
                        continue
                    add_audit_log(
                        action="bff.selection.task.intervene.ws",
                        actor=current_user,
                        target_type="selection_task",
                        target_id=target_task_id,
                        result="success",
                        detail={"action": message.get("intervention_action") or message.get("decision") or "pause_and_review"},
                    )
                    payload = await _build_selection_stream_payload(current_user)
                    payload["transport"] = {
                        "protocol": "websocket",
                        "heartbeat_seconds": 30,
                        "stream_type": "selection-workbench",
                    }
                    await ws_manager.send_agent_status(
                        task_id=target_task_id,
                        agent_name="human_in_loop",
                        status="intervened",
                        progress=100.0,
                        step_name=str(message.get("intervention_action") or message.get("decision") or "pause_and_review"),
                        output_preview=str(message.get("comment") or ""),
                    )
                    await websocket.send_json(payload)
                finally:
                    await session.close()
                continue

            await websocket.send_json({"type": "error", "detail": f"unsupported action: {action}"})
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(conn_id)


@router.get("/workbench/selection/tasks/{task_id}", response_model=dict)
async def get_selection_workbench_task(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task = await service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台任务详情失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台任务详情失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/result", response_model=dict)
async def get_selection_workbench_task_result(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task = await service.get_task_result(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台任务结果失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台任务结果失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/approve", response_model=dict)
async def approve_selection_workbench_task(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        approve_kwargs = {
            "task_id": task_id,
            "action": str(payload.get("action") or "approve"),
            "reviewer": payload.get("reviewer") or current_user.get("username"),
            "comment": payload.get("comment"),
        }
        signature = inspect.signature(service.approve_task)
        if "stage" in signature.parameters:
            approve_kwargs["stage"] = payload.get("stage")
        if "stage_order" in signature.parameters:
            approve_kwargs["stage_order"] = payload.get("stage_order")
        if "notify_channels" in signature.parameters:
            approve_kwargs["notify_channels"] = list(payload.get("notify_channels") or [])
        if "webhook_url" in signature.parameters:
            approve_kwargs["webhook_url"] = payload.get("webhook_url")
        result = await service.approve_task(**approve_kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="bff.selection.task.approve",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"approval_action": payload.get("action") or "approve"},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 审批工作台任务失败")
        raise HTTPException(status_code=503, detail=f"BFF 审批工作台任务失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/approval-history", response_model=dict)
async def get_selection_workbench_task_approval_history(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task = await service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return {
            "task_id": task_id,
            "approval": task.get("approval"),
            "approval_history": task.get("approval_history", []),
            "total": len(task.get("approval_history", [])),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询审批历史失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询审批历史失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/intervene", response_model=dict)
async def intervene_selection_workbench_task(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.manual_intervene(
            task_id=task_id,
            action=str(payload.get("action") or "pause_and_review"),
            comment=payload.get("comment"),
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="bff.selection.task.intervene",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"action": payload.get("action") or "pause_and_review"},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 人工介入工作台任务失败")
        raise HTTPException(status_code=503, detail=f"BFF 人工介入工作台任务失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/feedback", response_model=dict)
async def add_selection_workbench_task_feedback(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.add_feedback(task_id, payload)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="bff.selection.task.feedback",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"source": payload.get("source"), "sentiment": payload.get("sentiment")},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 录入工作台任务反馈失败")
        raise HTTPException(status_code=503, detail=f"BFF 录入工作台任务反馈失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/adopt", response_model=dict)
async def adopt_selection_workbench_task(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        selection_service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        integration_service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        adopted = await selection_service.adopt_recommendation(
            task_id,
            quantity=int(payload.get("quantity") or 200),
            scm_name=str(payload.get("scm_name") or "default"),
            supplier_code=payload.get("supplier_code"),
            notes=payload.get("notes"),
        )
        if adopted is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        result = await integration_service.execute_selection_adoption(
            task_id=task_id,
            scm_name=str(payload.get("scm_name") or "default"),
            wms_name=str(payload.get("wms_name") or "default"),
            oms_name=str(payload.get("oms_name") or "default"),
            som_name=str(payload.get("som_name") or "default"),
            quantity=int(payload.get("quantity") or 200),
            supplier_code=payload.get("supplier_code"),
            notes=payload.get("notes"),
        )
        await session.commit()
        add_audit_log(
            action="bff.selection.task.adopt",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={
                "quantity": payload.get("quantity") or 200,
                "scm_name": payload.get("scm_name") or "default",
                "wms_name": payload.get("wms_name") or "default",
                "oms_name": payload.get("oms_name") or "default",
                "som_name": payload.get("som_name") or "default",
                "supplier_code": payload.get("supplier_code"),
                "purchase_order_id": result.get("scm_receipt", {}).get("purchase_order_id"),
            },
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("BFF 采纳推荐失败")
        raise HTTPException(status_code=503, detail=f"BFF 采纳推荐失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/rescore", response_model=dict)
async def rescore_selection_workbench_task(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.rescore_task_from_execution_feedback(task_id, payload)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或尚无可再评分结果: {task_id}")
        add_audit_log(
            action="bff.selection.task.rescore",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={
                "sales_7d": payload.get("sales_7d"),
                "gross_profit": payload.get("gross_profit"),
                "available_inventory": payload.get("available_inventory"),
            },
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 工作台任务再评分失败")
        raise HTTPException(status_code=503, detail=f"BFF 工作台任务再评分失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/feedback-loop-status", response_model=dict)
async def get_selection_workbench_feedback_loop_status(
    task_id: str,
    crm_name: str = Query("default"),
    paas_name: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        return await service.get_selection_feedback_loop_status(task_id=task_id, crm_name=crm_name, paas_name=paas_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台反馈闭环状态失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台反馈闭环状态失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/profit-trace", response_model=dict)
async def get_selection_workbench_profit_trace(
    task_id: str,
    crm_name: str = Query("default"),
    fms_name: str = Query("default"),
    wms_name: str = Query("default"),
    paas_name: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        return await service.get_selection_profit_trace(task_id=task_id, crm_name=crm_name, fms_name=fms_name, wms_name=wms_name, paas_name=paas_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台利润追踪失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台利润追踪失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/execution-feedback-sync", response_model=dict)
async def sync_selection_workbench_execution_feedback(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.sync_selection_execution_feedback(
            task_id=task_id,
            oms_name=str(payload.get("oms_name") or "default"),
            crm_name=str(payload.get("crm_name") or "default"),
            fms_name=str(payload.get("fms_name") or "default"),
            wms_name=str(payload.get("wms_name") or "default"),
            auto_rescore=bool(payload.get("auto_rescore", True)),
        )
        await session.commit()
        add_audit_log(
            action="bff.selection.task.execution_feedback_sync",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"auto_rescore": bool(payload.get("auto_rescore", True))},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("BFF 同步执行反馈失败")
        raise HTTPException(status_code=503, detail=f"BFF 同步执行反馈失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/feedback-feature-asset", response_model=dict)
async def get_selection_workbench_feedback_feature_asset(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.export_feedback_feature_asset(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或尚无反馈特征资产: {task_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台反馈特征资产失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台反馈特征资产失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/history-case-ingest", response_model=dict)
async def ingest_selection_workbench_history_case(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        selection_service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task_detail = await selection_service.get_task(task_id)
        if task_detail is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        knowledge_service = _create_knowledge_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await knowledge_service.ingest_selection_case(task_detail)
        await session.commit()
        add_audit_log(
            action="bff.selection.task.history_case_ingest",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"doc_id": result.get("doc_id")},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 历史选品案例入库失败")
        raise HTTPException(status_code=503, detail=f"BFF 历史选品案例入库失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/history-cases/query", response_model=dict)
async def query_selection_workbench_history_cases(payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        knowledge_service = _create_knowledge_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await knowledge_service.query_selection_cases(
            query=str(payload.get("query") or "").strip(),
            top_k=int(payload.get("top_k") or 5),
            threshold=float(payload.get("threshold") or 0.1),
        )
        return result
    except Exception as e:
        logger.exception("BFF 历史选品案例检索失败")
        raise HTTPException(status_code=503, detail=f"BFF 历史选品案例检索失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/review-case-ingest", response_model=dict)
async def ingest_selection_workbench_review_case(task_id: str, payload: dict | None = None, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        integration_service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        request_payload = payload or {}
        result = await integration_service.ingest_selection_review_cases(
            task_id=task_id,
            crm_name=str(request_payload.get("crm_name") or "default"),
            publish_events=bool(request_payload.get("publish_events", True)),
        )
        await session.commit()
        add_audit_log(
            action="bff.selection.task.review_case_ingest",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"matched_review_count": result.get("matched_review_count")},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF CRM评价案例入库失败")
        raise HTTPException(status_code=503, detail=f"BFF CRM评价案例入库失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/review-cases/query", response_model=dict)
async def query_selection_workbench_review_cases(payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        knowledge_service = _create_knowledge_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await knowledge_service.query_review_cases(
            query=str(payload.get("query") or "").strip(),
            top_k=int(payload.get("top_k") or 5),
            threshold=float(payload.get("threshold") or 0.1),
        )
        return result
    except Exception as e:
        logger.exception("BFF CRM评价案例检索失败")
        raise HTTPException(status_code=503, detail=f"BFF CRM评价案例检索失败: {e}")
    finally:
        await session.close()


@router.get("/workbench/selection/tasks/{task_id}/close-loop-overview", response_model=dict)
async def get_selection_workbench_close_loop_overview(
    task_id: str,
    crm_name: str = Query("default"),
    fms_name: str = Query("default"),
    wms_name: str = Query("default"),
    paas_name: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        integration_service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        selection_service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        feedback_loop_status = await integration_service.get_selection_feedback_loop_status(task_id=task_id, crm_name=crm_name, paas_name=paas_name)
        profit_trace = await integration_service.get_selection_profit_trace(task_id=task_id, crm_name=crm_name, fms_name=fms_name, wms_name=wms_name, paas_name=paas_name)
        feature_asset = await selection_service.export_feedback_feature_asset(task_id)
        task_detail = await selection_service.get_task(task_id)
        task_result = await selection_service.get_task_result(task_id)
        adoption_status = (task_detail or {}).get("adoption") if isinstance(task_detail, dict) else None
        execution_feedback_snapshot = None
        similar_history_cases = None
        review_cases = None
        historical_performance = None
        if isinstance(task_detail, dict):
            result_payload = task_detail.get("result") or {}
            decision_output = (result_payload.get("decision_output") or {}) if isinstance(result_payload, dict) else {}
            execution_feedback_snapshot = decision_output.get("execution_feedback")
        if isinstance(task_result, dict):
            similar_history_cases = task_result.get("similar_history_cases")
            historical_performance = task_result.get("historical_performance")
            product = ((task_result.get("decision_output") or {}).get("product") or {}) if isinstance(task_result.get("decision_output"), dict) else {}
            review_query_parts = [
                str(task_result.get("query") or "").strip(),
                str(product.get("name") or product.get("product_name") or "").strip(),
                str(product.get("asin") or product.get("external_product_id") or "").strip(),
                "评价",
                "投诉",
            ]
            review_query = " ".join([part for part in review_query_parts if part])
            try:
                knowledge_service = _create_knowledge_service(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
                review_cases = await knowledge_service.query_review_cases(query=review_query, top_k=3, threshold=0.1)
            except Exception:
                review_cases = None
        return {
            "task_id": task_id,
            "feedback_loop_status": feedback_loop_status,
            "profit_trace": profit_trace,
            "feature_asset": feature_asset.get("feature_asset") if isinstance(feature_asset, dict) else None,
            "adoption_status": adoption_status,
            "execution_feedback_snapshot": execution_feedback_snapshot,
            "similar_history_cases": similar_history_cases,
            "review_cases": review_cases,
            "historical_performance": historical_performance,
            "overview_ready": bool(
                feedback_loop_status.get("selection_feedback_loop", {}).get("auto_rescore_completed")
                and feedback_loop_status.get("selection_feedback_loop", {}).get("feature_asset_ready")
                and profit_trace.get("ready")
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 查询工作台闭环总览失败")
        raise HTTPException(status_code=503, detail=f"BFF 查询工作台闭环总览失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks/{task_id}/close-loop", response_model=dict)
async def close_loop_selection_workbench_task(task_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = ErpIntegrationService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.close_selection_loop(
            task_id=task_id,
            oms_name=str(payload.get("oms_name") or "default"),
            scm_name=str(payload.get("scm_name") or "default"),
            wms_name=str(payload.get("wms_name") or "default"),
            crm_name=str(payload.get("crm_name") or "default"),
            fms_name=str(payload.get("fms_name") or "default"),
            paas_name=str(payload.get("paas_name") or "default"),
            limit=int(payload.get("limit") or 20),
        )
        await session.commit()
        add_audit_log(
            action="bff.selection.task.close_loop",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
            detail={"trace_id": result.get("trace_id")},
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("BFF 执行选品闭环失败")
        raise HTTPException(status_code=503, detail=f"BFF 执行选品闭环失败: {e}")
    finally:
        await session.close()


@router.delete("/workbench/selection/tasks/{task_id}", response_model=dict)
async def cancel_selection_workbench_task(task_id: str, current_user: dict = Depends(get_current_user)):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        task = await service.cancel_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log(
            action="bff.selection.task.cancel",
            actor=current_user,
            target_type="selection_task",
            target_id=task_id,
            result="success",
        )
        return {
            "task_id": task_id,
            "status": task.get("status", "cancelled"),
            "message": "工作台任务已取消",
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("BFF 取消工作台任务失败")
        raise HTTPException(status_code=503, detail=f"BFF 取消工作台任务失败: {e}")
    finally:
        await session.close()


@router.post("/workbench/selection/tasks", response_model=dict)
async def create_selection_workbench_task(
    task_data: SelectionTaskRunCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_db_session()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        try:
            created = await service.create_task(
                task_data.model_dump(),
                created_by=current_user.get("user_id"),
                tenant_id=current_user.get("tenant_id"),
            )
        except TypeError as e:
            if "unexpected keyword" not in str(e):
                raise
            created = await service.create_task(task_data.model_dump())
        context = SelectionTaskExecutionContext(
            task_id=created["task_id"],
            tenant_id=created.get("tenant_id") or current_user.get("tenant_id"),
            query=created.get("query") or task_data.query,
            category=task_data.category or "electronics",
            investment_budget=task_data.investment_budget or 50000.0,
            target_market=task_data.target_market or "US",
            auto_approve=task_data.auto_approve,
            priority=task_data.priority,
        )
        dispatch_message = "工作台任务已创建，等待后台执行"
        if get_settings().selection_execution.enable_api_background_dispatch:
            dispatcher = FastAPIBackgroundTaskDispatcher(background_tasks)
            await dispatcher.dispatch(service, context)
            dispatch_message = "工作台任务已创建，已由 API 后台任务启动执行"
        add_audit_log(
            action="bff.selection.task.create",
            actor=current_user,
            target_type="selection_task",
            target_id=created["task_id"],
            result="success",
            detail={"query": created.get("query") or task_data.query},
        )
        return {
            "task_id": created["task_id"],
            "query": created.get("query") or task_data.query,
            "status": "pending",
            "created_at": created.get("created_at"),
            "message": dispatch_message,
        }
    except Exception as e:
        logger.exception("BFF 创建工作台任务失败")
        raise HTTPException(status_code=503, detail=f"BFF 创建工作台任务失败: {e}")
    finally:
        await session.close()
