from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.infrastructure.database import get_async_session_factory
from src.services.channel_delivery_service import ChannelCallbackVerificationError, ChannelDeliveryService
from src.services.selection_service import SelectionTaskService

router = APIRouter(prefix="/channels", tags=["多端接入"])


class DingtalkWebhookRequest(BaseModel):
    webhook_url: str = Field(..., min_length=1)


class DingtalkReportRequest(BaseModel):
    webhook_url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    report_url: str | None = None


class InteractiveCardRequest(BaseModel):
    channel: str = Field(..., pattern="^(dingtalk|wechat)$")
    webhook_url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str = Field(default="")
    task_id: str | None = None
    callback_base_url: str = Field(default="http://127.0.0.1:8000", min_length=1)


class ChannelApprovalCallbackRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|reject|submit)$")
    comment: str | None = None


class ChannelTaskCreateRequest(BaseModel):
    query: str = Field(..., min_length=2)
    category: str = Field(default="electronics")
    target_market: str = Field(default="US")
    investment_budget: float = Field(default=50000, ge=0)


@router.get("/callback/verify", response_model=dict)
async def verify_channel_callback(
    channel: str = Query(..., pattern="^(dingtalk|wechat)$"),
    timestamp: str = Query(..., min_length=1),
    nonce: str = Query(..., min_length=1),
    signature: str = Query(..., min_length=1),
    challenge: str | None = Query(default=None),
):
    service = ChannelDeliveryService()
    try:
        result = service.verify_callback_url(
            channel=channel,
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            challenge=challenge,
        )
    except ChannelCallbackVerificationError as exc:
        add_audit_log(
            "channel.callback.verify",
            actor={"username": f"{channel}_bot", "tenant_id": None},
            target_type="channel",
            target_id=channel,
            result="denied",
            detail={"reason": str(exc), "channel": channel},
        )
        raise HTTPException(status_code=exc.http_status, detail=str(exc))

    if not result.get("verified"):
        add_audit_log(
            "channel.callback.verify",
            actor={"username": f"{channel}_bot", "tenant_id": None},
            target_type="channel",
            target_id=channel,
            result="denied",
            detail={"reason": "signature_mismatch", "channel": channel, "timestamp": timestamp},
        )
        raise HTTPException(status_code=403, detail="回调签名校验失败")

    add_audit_log(
        "channel.callback.verify",
        actor={"username": f"{channel}_bot", "tenant_id": None},
        target_type="channel",
        target_id=channel,
        result="success",
        detail={"verification_mode": result.get("verification_mode"), "timestamp": timestamp},
    )
    return result


@router.post("/dingtalk/test", response_model=dict)
async def test_dingtalk_channel(request: DingtalkWebhookRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ChannelDeliveryService()
        result = await service.test_dingtalk(request.webhook_url)
        add_audit_log("channel.dingtalk.test", actor=current_user, target_type="channel", result="success")
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"钉钉通道测试失败: {e}")


@router.post("/dingtalk/send-report", response_model=dict)
async def send_report_to_dingtalk(request: DingtalkReportRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ChannelDeliveryService()
        result = await service.send_report(
            channel="dingtalk",
            webhook_url=request.webhook_url,
            title=request.title,
            content=request.content,
            report_url=request.report_url,
        )
        add_audit_log("channel.dingtalk.send_report", actor=current_user, target_type="channel", result="success", detail={"title": request.title})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"钉钉报告发送失败: {e}")


@router.post("/interactive-card", response_model=dict)
async def send_interactive_card(request: InteractiveCardRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ChannelDeliveryService()
        result = await service.send_interactive_card(
            channel=request.channel,
            webhook_url=request.webhook_url,
            title=request.title,
            task_id=request.task_id,
            summary=request.summary,
            callback_base_url=request.callback_base_url,
        )
        add_audit_log("channel.interactive_card.send", actor=current_user, target_type="channel", result="success", detail={"channel": request.channel, "task_id": request.task_id, "title": request.title})
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"交互式卡片发送失败: {e}")


@router.post("/callback/approval", response_model=dict)
async def channel_callback_approval(request: ChannelApprovalCallbackRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.approve_task(task_id=request.task_id, action=request.action, reviewer=current_user.get("username"), comment=request.comment or "渠道交互回调")
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {request.task_id}")
        add_audit_log("channel.callback.approval", actor=current_user, target_type="selection_task", target_id=request.task_id, result="success", detail={"action": request.action, "source": "interactive_card"})
        return result
    finally:
        await session.close()


@router.post("/callback/tasks", response_model=dict)
async def channel_callback_create_task(request: ChannelTaskCreateRequest, current_user: dict = Depends(get_current_user)):
    session = get_async_session_factory()()
    try:
        service = SelectionTaskService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
        result = await service.create_task(request.model_dump(), created_by=current_user.get("user_id"), tenant_id=current_user.get("tenant_id"))
        add_audit_log("channel.callback.task_create", actor=current_user, target_type="selection_task", target_id=result["task_id"], result="success", detail={"source": "interactive_card", "query": request.query})
        return result
    finally:
        await session.close()
