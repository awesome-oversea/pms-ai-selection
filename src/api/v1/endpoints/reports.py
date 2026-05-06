"""
报告管理API
==========

提供报告生成与管理能力(D41):
    - GET  /api/v1/reports/templates          - 报告模板与指标目录
    - POST /api/v1/reports/generate           - 生成报告
    - GET  /api/v1/reports                    - 报告列表
    - GET  /api/v1/reports/share/{token}      - 访问分享链接
    - GET  /api/v1/reports/{id}               - 报告详情
    - GET  /api/v1/reports/{id}/download      - 下载报告
    - POST /api/v1/reports/{id}/share         - 创建分享链接
    - DELETE /api/v1/reports/{id}             - 删除报告
"""

from typing import Any

_SHARE_REPORT_OVERRIDES: dict[str, str] = {}

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.report_center_service import ReportCenterService

router = APIRouter(prefix="/reports", tags=["报告管理"])
service = ReportCenterService()


class ReportShareRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=720)


class ReportCompareRequest(BaseModel):
    baseline_report_id: str = Field(..., min_length=1)
    target_report_id: str = Field(..., min_length=1)


class ReportChannelShareRequest(BaseModel):
    channel: str = Field(..., pattern="^(dingtalk|wechat)$")
    webhook_url: str = Field(..., min_length=1)
    expires_in_hours: int = Field(default=24, ge=1, le=720)


class CustomReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    template_name: str | None = Field(default=None)
    title: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    sections: list[str] = Field(default_factory=list)
    metrics_filter: list[str] = Field(default_factory=list)
    chart_keys: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)

    def build_params(self) -> dict[str, Any]:
        merged = dict(self.params)
        for key, value in (self.model_extra or {}).items():
            if value is not None:
                merged[key] = value
        return merged

    def has_customization(self) -> bool:
        return any(
            [
                self.template_name,
                self.title,
                self.summary,
                self.sections,
                self.metrics_filter,
                self.chart_keys,
                self.build_params(),
            ]
        )


@router.get("/templates")
async def list_report_templates(current_user: dict = Depends(get_current_user)) -> dict:
    return service.list_report_templates()


@router.post("/generate")
async def generate_report(
    report_type: str = Query(..., description="报告类型: daily/weekly/monthly"),
    format: str = Query("html", description="输出格式: html/pdf/excel/xlsx/ppt"),
    task_id: str | None = Query(None, description="关联任务ID"),
    request: CustomReportGenerateRequest = Body(default_factory=CustomReportGenerateRequest),
    current_user: dict = Depends(get_current_user),
) -> dict:
    try:
        effective_params = request.build_params()
        is_customized = request.has_customization()
        if is_customized:
            report = await service.generate_custom_report(
                report_type=report_type,
                format=format,
                task_id=task_id,
                template_name=request.template_name,
                title=request.title,
                summary=request.summary,
                sections=request.sections,
                metrics_filter=request.metrics_filter,
                chart_keys=request.chart_keys,
                params=effective_params,
            )
        else:
            report = await service.generate(
                report_type=report_type,
                format=format,
                task_id=task_id,
                params=effective_params or None,
            )
        add_audit_log(
            "report.generate",
            actor=current_user,
            target_type="report",
            target_id=report["report_id"],
            result="success",
            detail={
                "format": format,
                "report_type": report_type,
                "template_name": request.template_name,
                "metrics_filter": request.metrics_filter,
                "chart_keys": request.chart_keys,
                "customized": is_customized,
            },
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"报告生成失败: {e}")


@router.get("")
async def list_reports(
    report_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    created_after: str | None = Query(None, description="筛选生成时间 >= 指定ISO时间"),
    created_before: str | None = Query(None, description="筛选生成时间 <= 指定ISO时间"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    items = await service.list_reports(
        report_type=report_type,
        limit=limit + offset,
        created_after=created_after,
        created_before=created_before,
    )
    total = len(items)
    paginated = items[offset : offset + limit]
    completion_rates = [float(item.get("metrics", {}).get("completion_rate") or 0) for item in paginated]
    gmvs = [float(item.get("metrics", {}).get("gmv") or 0) for item in paginated]
    generated_ats = [item.get("generated_at") or item.get("created_at") for item in paginated if item.get("generated_at") or item.get("created_at")]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "report_type": report_type,
            "created_after": created_after,
            "created_before": created_before,
        },
        "summary": {
            "report_count": len(paginated),
            "total_gmv": round(sum(gmvs), 2),
            "avg_completion_rate": round(sum(completion_rates) / len(completion_rates), 4) if completion_rates else 0,
            "latest_generated_at": max(generated_ats) if generated_ats else None,
            "data_source": "report_center_state",
        },
        "items": paginated,
    }


@router.get("/share/{share_token}")
async def get_shared_report(share_token: str) -> dict:
    shared = await service.resolve_share_link(share_token)
    if shared is None:
        raise HTTPException(status_code=404, detail=f"分享链接不存在或已过期: {share_token}")
    if share_token in _SHARE_REPORT_OVERRIDES:
        shared = {**shared, "report_id": _SHARE_REPORT_OVERRIDES[share_token]}
    add_audit_log(
        "report.share.access",
        actor={"username": "anonymous"},
        target_type="report_share",
        target_id=share_token,
        result="success",
        detail={"report_id": shared["report_id"]},
    )
    return shared


@router.post("/compare")
async def compare_reports(request: ReportCompareRequest, current_user: dict = Depends(get_current_user)) -> dict:
    result = await service.compare_reports(request.baseline_report_id, request.target_report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="报告不存在，无法对比")
    add_audit_log(
        "report.compare",
        actor=current_user,
        target_type="report_compare",
        result="success",
        detail={"baseline_report_id": request.baseline_report_id, "target_report_id": request.target_report_id},
    )
    return result


@router.get("/archive", response_model=dict)
async def list_archived_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return await service.list_archived_reports(limit=limit, offset=offset)


@router.get("/archive/{report_id}", response_model=dict)
async def get_archived_report(report_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    archived = await service.get_archive_record(report_id)
    if archived is None:
        raise HTTPException(status_code=404, detail=f"归档报告不存在: {report_id}")
    return archived


@router.get("/{report_id}")
async def get_report(report_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    return report


@router.get("/{report_id}/download")
async def download_report(report_id: str, current_user: dict = Depends(get_current_user)):
    downloaded = await service.build_download(report_id)
    if downloaded is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    content, media_type, filename = downloaded
    add_audit_log(
        "report.download",
        actor=current_user,
        target_type="report",
        target_id=report_id,
        result="success",
        detail={"filename": filename},
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{report_id}/share")
async def create_report_share(
    report_id: str,
    request: ReportShareRequest = Body(default_factory=ReportShareRequest),
    current_user: dict = Depends(get_current_user),
) -> dict:
    shared = await service.create_share_link(
        report_id,
        created_by=current_user.get("username", "unknown"),
        expires_in_hours=request.expires_in_hours,
    )
    if shared is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    _SHARE_REPORT_OVERRIDES[shared["share_token"]] = report_id
    add_audit_log(
        "report.share.create",
        actor=current_user,
        target_type="report",
        target_id=report_id,
        result="success",
        detail={"share_token": shared["share_token"], "expires_in_hours": request.expires_in_hours},
    )
    return shared


@router.post("/{report_id}/share/deliver")
async def deliver_report_share(
    report_id: str,
    request: ReportChannelShareRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    result = await service.share_report_to_channel(
        report_id,
        channel=request.channel,
        webhook_url=request.webhook_url,
        created_by=current_user.get("username", "unknown"),
        expires_in_hours=request.expires_in_hours,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    _SHARE_REPORT_OVERRIDES[result["share"]["share_token"]] = report_id
    add_audit_log(
        "report.share.deliver",
        actor=current_user,
        target_type="report",
        target_id=report_id,
        result="success",
        detail={"channel": request.channel, "share_token": result["share"]["share_token"]},
    )
    return result


@router.delete("/{report_id}")
async def delete_report(report_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    archived = await service.archive_report(report_id)
    if not archived:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    add_audit_log(
        "report.delete",
        actor=current_user,
        target_type="report",
        target_id=report_id,
        result="success",
    )
    return archived
