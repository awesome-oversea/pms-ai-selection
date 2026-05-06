"""
系统信息API端点
================

提供系统元信息、版本、配置概览和K8s拓扑信息查询。
用于:
- 系统状态面板
- 运维监控数据源
- 前端V2数据看板基础接口
"""

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.config.k8s_config import K8sTopologyConfig
from src.config.settings import get_settings
from src.core.security import add_audit_log, require_superuser
from src.infrastructure.database import get_async_session_factory
from src.repositories.tenant_quota_repository import TenantQuotaRepository
from src.repositories.tenant_repository import TenantRepository


class TenantOperationsService:
    def __init__(self, session):
        self.session = session

    async def build_status(self) -> dict[str, Any]:
        tenant_repo = TenantRepository(self.session)
        quota_repo = TenantQuotaRepository(self.session)
        tenants = await tenant_repo.list_tenants(limit=50)
        items = []
        for tenant in tenants[:10]:
            quota_status = await quota_repo.list_quota_status(tenant_id=str(tenant.id))
            items.append(
                {
                    "tenant_id": str(tenant.id),
                    "tenant_key": tenant.tenant_key,
                    "name": tenant.name,
                    "status": tenant.status,
                    "is_active": tenant.is_active,
                    "quota_status": quota_status,
                    "isolation_summary": {
                        "tenant_scoped": True,
                        "quota_governed": len(quota_status) > 0,
                    },
                }
            )
        return {"total": len(items), "tenants": items}
from src.infrastructure.ws_gateway_status import get_realtime_gateway_status
from src.services.audit_operations_service import AuditOperationsService
from src.services.batch_ads_service import BatchAdsService
from src.services.business_config_governance_service import BusinessConfigGovernanceService
from src.services.captcha_ocr_service import CaptchaOCRService
from src.services.config_center_service import ConfigCenterService
from src.services.config_center_service import ConfigCenterService as ConfigOperationsService
from src.services.data_domain_service import DataDomainService
from src.services.data_lake_service import DataLakeService
from src.services.data_platform_runtime_service import DataPlatformRuntimeService
from src.services.delivery_conclusion_service import DeliveryConclusionService
from src.services.delivery_readiness_service import DeliveryReadinessService
from src.services.delivery_scope_boundary_service import DeliveryScopeBoundaryService
from src.services.event_driven_scheduler_service import EventDrivenSchedulerService
from src.services.feature_asset_service import FeatureAssetService
from src.services.gateway_governance_service import GatewayGovernanceService
from src.services.ha_topology_service import HATopologyService
from src.services.interface_governance_service import InterfaceGovernanceService
from src.services.kafka_cluster_status_service import KafkaClusterStatusService
from src.services.llm_governance_service import LLMGovernanceService
from src.services.local_external_collection_readiness_service import LocalExternalCollectionReadinessService
from src.services.metrics_dashboard_service import MetricsDashboardService
from src.services.migration_governance_service import MigrationGovernanceService
from src.services.operations_governance_overview_service import OperationsGovernanceOverviewService
from src.services.profit_flywheel_service import ProfitFlywheelService
from src.services.profit_optimization_service import ProfitOptimizationService
from src.services.release_management_service import ReleaseManagementService
from src.services.security_baseline_service import SecurityBaselineService
from src.services.service_split_status_service import ServiceSplitStatusService
from src.services.slo_status_service import SLOStatusService
from src.workers.celery_schedule_monitor import build_schedule_monitor_status
import contextlib

router = APIRouter()


class SupplierQuoteCacheRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    max_suppliers: int = Field(default=10, ge=1, le=50)


class SupplierRecommendationRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    monthly_demand: int = Field(default=300, ge=1, le=1000000)
    max_suppliers: int = Field(default=10, ge=1, le=50)
    target_price: float = Field(default=39.9, gt=0)


class RestockPlanRequest(BaseModel):
    product_keyword: str = Field(..., min_length=1)
    monthly_demand: int = Field(..., ge=1, le=1000000)
    current_inventory_units: int = Field(default=0, ge=0, le=1000000)
    target_price: float = Field(..., gt=0)
    max_suppliers: int = Field(default=10, ge=1, le=50)
    preferred_supplier_code: str | None = Field(default=None)
    oms_api_endpoint: str | None = Field(default=None)
    oms_api_key: str | None = Field(default=None)
    oms_inbound_path: str = Field(default="/orders")
    product_id: str | None = Field(default=None)


class CaptchaOCRRequest(BaseModel):
    image_base64: str | None = Field(default=None)
    image_text_hint: str | None = Field(default=None)


class FeatureEventRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    timestamp: float | None = Field(default=None)
    sales: float | None = Field(default=None)
    price: float | None = Field(default=None)
    rank: int | None = Field(default=None)
    rating: float | None = Field(default=None)
    review_count: int | None = Field(default=None)
    sentiment: float | None = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict)


class FeatureBatchRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1)


class EventSchedulerEvaluateRequest(BaseModel):
    source: str = Field(default="event_scheduler_api")
    kafka_backlog: int = Field(default=0, ge=0)
    kafka_backlog_threshold: int = Field(default=10000, ge=1)
    google_trends_growth_percent: float = Field(default=0.0)
    google_trends_threshold_percent: float = Field(default=200.0)
    negative_review_rate: float = Field(default=0.0, ge=0.0)
    negative_review_threshold: float = Field(default=0.2, ge=0.0)


_ARTIFACTS_ROOT = Path("artifacts")
_REPORT_CENTER_STATE_PATH = _ARTIFACTS_ROOT / "report_center" / "state.json"
_BATCH_JOB_ARTIFACT_PATH = _ARTIFACTS_ROOT / "data_platform" / "batch_job_latest.json"
_STREAM_JOB_ARTIFACT_PATH = _ARTIFACTS_ROOT / "data_platform" / "stream_job_latest.json"
_METRICS_DASHBOARD_ARTIFACT_PATH = _ARTIFACTS_ROOT / "ops" / "metrics_dashboard.json"
_EXTERNAL_COLLECTION_READINESS_LATEST_PATH = _ARTIFACTS_ROOT / "ops" / "local_external_collection_readiness_latest.json"


def _load_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_external_collection_readiness_latest() -> dict[str, Any]:
    payload = _load_json_artifact(_EXTERNAL_COLLECTION_READINESS_LATEST_PATH)
    if payload is not None:
        return payload
    try:
        return LocalExternalCollectionReadinessService().run()
    except Exception as exc:
        return {
            "status": "failed",
            "accepted": False,
            "generated_at": None,
            "error": str(exc),
            "source_probes": {},
            "business_readiness_overview": {
                "classification_breakdown": {},
                "formal_ready_sources": [],
                "local_validation_only_sources": [],
                "blocked_sources": [],
                "formal_api_ready_count": 0,
                "local_validation_only_count": 0,
                "blocked_source_count": 0,
                "next_actions": [],
            },
            "readiness_snapshot": {
                "formal_api_ready_count": 0,
                "local_validation_only_count": 0,
                "blocked_source_count": 0,
                "next_actions": [],
            },
        }


def _build_selection_dashboard_from_artifacts() -> dict[str, Any] | None:
    report_state = _load_json_artifact(_REPORT_CENTER_STATE_PATH)
    batch_job = _load_json_artifact(_BATCH_JOB_ARTIFACT_PATH)
    stream_job = _load_json_artifact(_STREAM_JOB_ARTIFACT_PATH)
    metrics_dashboard = _load_json_artifact(_METRICS_DASHBOARD_ARTIFACT_PATH)
    if report_state is None and batch_job is None and stream_job is None and metrics_dashboard is None:
        return None

    reports = report_state.get("reports", {}) if isinstance(report_state, dict) else {}
    report_items = [item for item in reports.values() if isinstance(item, dict)]
    latest_report = max(report_items, key=lambda item: item.get("generated_at") or item.get("created_at") or "", default={})
    latest_metrics = latest_report.get("metrics", {}) if isinstance(latest_report, dict) else {}
    top_categories = latest_metrics.get("top_categories", []) if isinstance(latest_metrics, dict) else []
    gmv = round(float(latest_metrics.get("gmv") or 0), 2)
    completion_rate = round(float(latest_metrics.get("completion_rate") or 0) * 100, 2)
    roi = round(float(latest_metrics.get("roi") or 0), 2)
    anomalies = int(latest_metrics.get("anomalies") or 0)
    opportunities = int(latest_metrics.get("opportunities") or 0)
    batch_assets = batch_job.get("output_assets", []) if isinstance(batch_job, dict) else []
    stream_assets = stream_job.get("output_assets", []) if isinstance(stream_job, dict) else []
    business = metrics_dashboard.get("business", {}) if isinstance(metrics_dashboard, dict) else {}
    commercial = metrics_dashboard.get("commercial", {}) if isinstance(metrics_dashboard, dict) else {}
    technical = metrics_dashboard.get("technical", {}) if isinstance(metrics_dashboard, dict) else {}
    dependencies = technical.get("dependencies", {}) if isinstance(technical, dict) else {}
    unhealthy_dependencies = sum(1 for value in dependencies.values() if value != "healthy")
    loop_closed = anomalies == 0
    overall_status = "artifact_mvp_ready" if latest_report else "artifact_partial_ready"
    updated_at = max(
        filter(
            None,
            [
                latest_report.get("generated_at") if isinstance(latest_report, dict) else None,
                batch_job.get("executed_at") if isinstance(batch_job, dict) else None,
                stream_job.get("executed_at") if isinstance(stream_job, dict) else None,
            ],
        ),
        default=None,
    )
    bi_assets = [*batch_assets, *stream_assets]

    return {
        "summary": {
            "overall_status": overall_status,
            "bi_asset_count": len(bi_assets),
            "loop_closed": loop_closed,
            "data_source": "artifacts",
            "updated_at": updated_at,
            "report_title": latest_report.get("title", "未生成报告") if isinstance(latest_report, dict) else "未生成报告",
            "report_count": len(report_items),
            "gmv": gmv,
            "completion_rate": completion_rate,
        },
        "filters": ["time_window", "task_dimension", "data_source"],
        "charts": {
            "trend_chart": {
                "type": "line",
                "title": "趋势机会",
                "xAxis": ["任务完成率", "转化率", "ROI"],
                "series": [
                    completion_rate,
                    round(float(latest_metrics.get("conversion_rate") or 0) * 100, 2),
                    roi,
                ],
            },
            "profit_chart": {
                "type": "bar",
                "title": "利润 / ROI",
                "xAxis": ["GMV", "完成率", "ROI"],
                "series": [gmv, completion_rate, roi],
            },
            "risk_chart": {
                "type": "pie",
                "title": "库存 / 供应风险",
                "items": [
                    {"name": "异常告警", "value": anomalies},
                    {"name": "依赖异常", "value": unhealthy_dependencies},
                    {"name": "回流缺口", "value": 0 if loop_closed else 1},
                ],
            },
            "competitor_chart": {
                "type": "ranking",
                "title": "重点品类 / 资产榜单",
                "items": [
                    *[
                        {"name": category, "value": max(100 - index * 12, 40)}
                        for index, category in enumerate(top_categories[:3])
                    ],
                    *[
                        {"name": asset, "value": 72}
                        for asset in bi_assets[:2]
                    ],
                ]
                or [{"name": "no_artifact", "value": 0}],
            },
            "execution_chart": {
                "type": "progress",
                "title": "执行闭环进度",
                "items": [
                    {"name": "报告产出", "value": 100 if latest_report else 0},
                    {"name": "离线资产", "value": min(len(batch_assets) * 40, 100)},
                    {"name": "实时资产", "value": min(len(stream_assets) * 40, 100)},
                ],
            },
        },
        "highlights": {
            "top_categories": top_categories,
            "batch_assets": batch_assets,
            "stream_assets": stream_assets,
            "business_sources": business,
            "commercial_sources": commercial,
        },
    }


@router.get("/info")
async def system_info():
    from src.core.logging import get_logger
    from src.infrastructure.database import get_engine

    try:
        import psutil
    except Exception:
        psutil = None

    logger = get_logger(__name__)
    settings = get_settings()

    # 检查数据库连接
    db_ready = False
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        db_ready = True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # 检查服务状态
    services = {}

    # 检查Kong服务
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000", timeout=1)
            services["kong"] = {"ready": response.status_code == 200, "status": response.status_code}
    except Exception as e:
        services["kong"] = {"ready": False, "error": str(e)}

    # 检查Triton服务
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/v2/health/ready", timeout=1)
            services["triton"] = {"ready": response.status_code == 200, "status": response.status_code}
    except Exception as e:
        services["triton"] = {"ready": False, "error": str(e)}

    # 系统资源使用情况
    if psutil is None:
        system_info = {
            "cpu_percent": None,
            "memory": {"total": None, "available": None, "used_percent": None},
            "disk": {"total": None, "used": None, "used_percent": None},
            "network": {"sent": None, "recv": None},
            "metrics_backend": "unavailable-psutil",
        }
    else:
        system_info = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total": psutil.virtual_memory().total // (1024 * 1024),
                "available": psutil.virtual_memory().available // (1024 * 1024),
                "used_percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total": psutil.disk_usage("C:").total // (1024 * 1024 * 1024),
                "used": psutil.disk_usage("C:").used // (1024 * 1024 * 1024),
                "used_percent": psutil.disk_usage("C:").percent
            },
            "network": {
                "sent": psutil.net_io_counters().bytes_sent // (1024 * 1024),
                "recv": psutil.net_io_counters().bytes_recv // (1024 * 1024)
            },
            "metrics_backend": "psutil",
        }

    # 应用状态
    api_ready = True  # 假设API服务正常运行

    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "environment": settings.app.environment,
        "api_prefix": settings.app.api_prefix,
        "debug": settings.app.debug,
        "status": "healthy" if db_ready and api_ready else "unhealthy",
        "api_ready": api_ready,
        "db_ready": db_ready,
        "services": services,
        "system": system_info,
        "started_at": settings.app.started_at.isoformat() if hasattr(settings.app, "started_at") else None
    }


@router.get("/k8s/topology")
async def k8s_topology(current_user: dict = Depends(require_superuser)):
    topo = K8sTopologyConfig.default_production()
    return {
        "cluster": {
            "name": topo.cluster.name,
            "kubernetes_version": topo.cluster.kubernetes_version,
            "master_count": topo.cluster.master_count,
            "etcd_count": topo.cluster.etcd_count,
            "ha_vip": topo.cluster.ha_vip,
            "az_count": topo.cluster.az_count,
        },
        "nodes": [
            {
                "role": n.role.value,
                "count": n.count,
                "cpu_cores": n.cpu_cores,
                "memory_gb": n.memory_gb,
                "gpu_type": n.gpu_type,
                "gpu_count": n.gpu_count,
                "storage_gb": n.storage_gb,
                "total_cpu": n.total_cpu_cores(),
                "total_memory_gb": n.total_memory_gb(),
                "total_gpu": n.total_gpu_count(),
            }
            for n in topo.nodes
        ],
        "network": {
            "cni_type": topo.network.cni_type.value,
            "pod_cidr": topo.network.pod_cidr,
            "service_cidr": topo.network.service_cidr,
            "node_cidr": topo.network.node_cidr,
            "vpc_cidr": topo.network.vpc_cidr,
        },
        "storage": {
            "local_ssd_per_node_gb": topo.storage.local_ssd_per_node_gb,
            "oss_bucket_name": topo.storage.oss_bucket_name,
            "oss_capacity_tb": topo.storage.oss_capacity_tb,
        },
        "summary": topo.get_resource_summary(),
    }


@router.get("/k8s/topology/markdown")
async def k8s_topology_markdown(current_user: dict = Depends(require_superuser)):
    topo = K8sTopologyConfig.default_production()
    return {"markdown": topo.to_markdown(), "format": "markdown"}


@router.get("/k8s/topology/validate")
async def k8s_topology_validate(current_user: dict = Depends(require_superuser)):
    topo = K8sTopologyConfig.default_production()
    is_valid, messages = topo.validate_topology()
    return {"is_valid": is_valid, "message_count": len(messages), "messages": messages}


@router.get("/data-domains")
async def list_data_domains(current_user: dict = Depends(require_superuser)):
    service = DataDomainService()
    result = service.list_domains()
    if isinstance(result, dict) and "domains" in result:
        return result
    if isinstance(result, dict) and "entities" in result:
        return {**result, "domains": result["entities"]}
    return {"domains": result}


@router.get("/data-domains/{entity}")
async def get_data_domain(entity: str, current_user: dict = Depends(require_superuser)):
    service = DataDomainService()
    result = service.get_domain(entity)
    if result is None:
        raise HTTPException(status_code=404, detail=f"数据域实体不存在: {entity}")
    return result


@router.post("/configs/{config_key}/publish")
async def publish_config(config_key: str, payload: dict, current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=current_user.get("tenant_id"))
        result = await service.publish_config(config_key, payload.get("value", {}), payload.get("description", ""))
        await session.commit()
        add_audit_log("system.config.publish", actor=current_user, target_type="config", target_id=config_key, result="success")
        return result
    finally:
        await session.close()


@router.post("/configs/{config_key}/rollback")
async def rollback_config(config_key: str, current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=current_user.get("tenant_id"))
        result = await service.rollback_config(config_key)
        if result is None:
            raise HTTPException(status_code=404, detail=f"配置不存在或无历史版本: {config_key}")
        try:
            await session.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await session.rollback()
        add_audit_log("system.config.rollback", actor=current_user, target_type="config", target_id=config_key, result="success")
        return result
    finally:
        await session.close()


@router.get("/configs/{config_key}")
async def get_config(config_key: str, current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=current_user.get("tenant_id"))
        result = await service.get_config(config_key)
        if result is None:
            raise HTTPException(status_code=404, detail=f"配置不存在: {config_key}")
        return result
    finally:
        await session.close()


@router.post("/feature-flags/{flag_key}/publish")
async def publish_feature_flag(flag_key: str, payload: dict, current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=current_user.get("tenant_id"))
        result = await service.publish_feature_flag(
            flag_key,
            enabled=bool(payload.get("enabled", False)),
            rollout_percent=int(payload.get("rollout_percent", 0)),
            tenant_whitelist=payload.get("tenant_whitelist", []),
            description=payload.get("description", ""),
        )
        try:
            await session.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await session.rollback()
        add_audit_log("system.feature_flag.publish", actor=current_user, target_type="feature_flag", target_id=flag_key, result="success")
        return result
    finally:
        await session.close()


@router.get("/feature-flags/{flag_key}")
async def get_feature_flag(flag_key: str, current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=current_user.get("tenant_id"))
        raw = await service.get_feature_flag(flag_key)
        if raw is None:
            raise HTTPException(status_code=404, detail=f"特性开关不存在: {flag_key}")
        return await service.resolve_feature_flag(flag_key)
    finally:
        await session.close()


@router.get("/metrics-dashboard")
async def get_metrics_dashboard(current_user: dict = Depends(require_superuser)):
    service = MetricsDashboardService()
    return await service.build_dashboard()


@router.get("/dashboard/selection-overview")
async def get_selection_dashboard(
    source: Literal["auto", "artifacts", "services"] = Query("auto"),
    current_user: dict = Depends(require_superuser),
):
    if source in {"auto", "artifacts"}:
        artifact_payload = _build_selection_dashboard_from_artifacts()
        if artifact_payload is not None:
            if source == "artifacts":
                return artifact_payload
            if source == "auto":
                return artifact_payload
        if source == "artifacts":
            raise HTTPException(status_code=404, detail="本地模拟数据工件不存在")

    if source == "services" and hasattr(MetricsDashboardService, "build_selection_overview"):
        return MetricsDashboardService().build_selection_overview(source=source)

    session = get_async_session_factory()()
    try:
        data_lake = DataLakeService(session)
        flywheel = ProfitFlywheelService(session, tenant_id=current_user.get("tenant_id"))
        data_lake_status = await data_lake.build_status()
        flywheel_status = await flywheel.build_status()
        bi_assets = data_lake_status.get("bi_ready_assets", [])
        profit_summary = flywheel_status.get("fms", {}).get("profit_summary", {}) if isinstance(flywheel_status.get("fms"), dict) else {}
        inventory_summary = flywheel_status.get("wms", {}).get("inventory_summary", {}) if isinstance(flywheel_status.get("wms"), dict) else {}
        charts = {
            "trend_chart": {
                "type": "line",
                "title": "趋势机会",
                "xAxis": ["7d", "14d", "30d"],
                "series": [82, 84, 79],
            },
            "profit_chart": {
                "type": "bar",
                "title": "利润 / ROI",
                "xAxis": ["毛利润", "毛利率", "ROI"],
                "series": [
                    round(float(profit_summary.get("gross_profit_total") or 0), 2),
                    round(float(profit_summary.get("avg_margin_rate") or 0) * 100, 2),
                    42,
                ],
            },
            "risk_chart": {
                "type": "pie",
                "title": "库存 / 供应风险",
                "items": [
                    {"name": "库存风险", "value": int(inventory_summary.get("low_stock_count") or 0)},
                    {"name": "供应风险", "value": 0 if flywheel_status.get("scm", {}).get("ready") else 1},
                    {"name": "回流缺口", "value": len(flywheel_status.get("loop_gaps", []))},
                ],
            },
            "competitor_chart": {
                "type": "ranking",
                "title": "BI资产可用性榜单",
                "items": [{"name": item, "value": 100} for item in bi_assets] or [{"name": "no_asset", "value": 0}],
            },
            "execution_chart": {
                "type": "progress",
                "title": "执行闭环进度",
                "items": [
                    {"name": "飞轮闭环", "value": 100 if flywheel_status.get("feedback_loop", {}).get("loop_closed", False) else 60},
                    {"name": "BI资产", "value": min(len(bi_assets) * 20, 100)},
                    {"name": "系统就绪", "value": sum(int(bool(flywheel_status.get(key, {}).get("ready"))) for key in ["scm", "wms", "crm", "fms", "bi"]) * 20},
                ],
            },
        }
        return {
            "summary": {
                "overall_status": flywheel_status.get("overall_status"),
                "bi_asset_count": len(bi_assets),
                "loop_closed": flywheel_status.get("feedback_loop", {}).get("loop_closed", False),
                "data_source": "services",
                "updated_at": None,
                "report_title": "服务聚合",
                "report_count": 0,
                "gmv": round(float(profit_summary.get("gross_profit_total") or 0), 2),
                "completion_rate": 100 if flywheel_status.get("feedback_loop", {}).get("loop_closed", False) else 60,
            },
            "filters": ["time_window", "task_dimension", "data_source"],
            "charts": charts,
            "highlights": {
                "top_categories": [],
                "batch_assets": bi_assets,
                "stream_assets": [],
                "business_sources": {},
                "commercial_sources": {},
            },
        }
    finally:
        await session.close()


@router.get("/interfaces/governance")
async def get_interfaces_governance(current_user: dict = Depends(require_superuser)):
    service = InterfaceGovernanceService()
    return service.build_governance()


@router.get("/interface-governance")
async def get_interface_governance(current_user: dict = Depends(require_superuser)):
    service = InterfaceGovernanceService()
    return service.build_governance()


@router.get("/migrations/status")
async def get_migration_status(current_user: dict = Depends(require_superuser)):
    service = MigrationGovernanceService()
    return service.build_status()


@router.get("/gateway-governance")
async def get_gateway_governance(current_user: dict = Depends(require_superuser)):
    service = GatewayGovernanceService()
    return service.get_status()


@router.get("/service-split-status")
async def get_service_split_status(current_user: dict = Depends(require_superuser)):
    service = ServiceSplitStatusService()
    return service.build_status()


@router.get("/slo-status")
async def get_slo_status(current_user: dict = Depends(require_superuser)):
    service = SLOStatusService()
    result = service.build_status()
    if "capacity" not in result:
        result["capacity"] = result.get("capacity_baseline", {})
    if "alerts" not in result:
        result["alerts"] = result.get("alert_linkage", [])
    return result


@router.get("/data-lake/status")
async def get_data_lake_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        return await result if hasattr(result, "__await__") else result
    finally:
        await session.close()


@router.get("/data-platform/status")
async def get_data_platform_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        return await result if hasattr(result, "__await__") else result
    finally:
        await session.close()


@router.get("/data-platform/runtime")
async def get_data_platform_runtime(current_user: dict = Depends(require_superuser)):
    return DataPlatformRuntimeService().build_status()


@router.get("/external-collection/readiness")
async def get_external_collection_readiness(current_user: dict = Depends(require_superuser)):
    summary = _load_external_collection_readiness_latest()
    return {
        "status": summary.get("status"),
        "accepted": summary.get("accepted"),
        "generated_at": summary.get("generated_at"),
        "business_context": summary.get("business_context"),
        "readiness_snapshot": summary.get("readiness_snapshot")
        or summary.get("business_readiness_overview")
        or {},
        "business_readiness_overview": summary.get("business_readiness_overview") or {},
        "source_probes": summary.get("source_probes") or {},
        "gdelt_probe": summary.get("gdelt_probe") or {},
        "checks": summary.get("checks") or [],
    }


@router.get("/data-platform/event-scheduler/status")
async def get_data_platform_event_scheduler_status(current_user: dict = Depends(require_superuser)):
    return EventDrivenSchedulerService().build_status()


@router.post("/data-platform/event-scheduler/evaluate")
async def evaluate_data_platform_event_scheduler(
    request: EventSchedulerEvaluateRequest,
    current_user: dict = Depends(require_superuser),
):
    result = EventDrivenSchedulerService().evaluate(request.model_dump())
    add_audit_log(
        action="system.data_platform.event_scheduler.evaluate",
        actor=current_user,
        target_type="event_scheduler",
        result="success",
        detail={"trigger_count": result.get("trigger_count", 0), "source": request.source},
    )
    return result


@router.get("/data-platform/flink/status")
async def get_data_platform_flink_status(current_user: dict = Depends(require_superuser)):
    runtime = DataPlatformRuntimeService().build_status()
    return runtime.get("flink", {})


@router.get("/data-platform/scheduler/status")
async def get_data_platform_scheduler_status(current_user: dict = Depends(require_superuser)):
    runtime = DataPlatformRuntimeService().build_status()
    return runtime.get("scheduler", {})


@router.get("/data-platform/kettle/status")
async def get_data_platform_kettle_status(current_user: dict = Depends(require_superuser)):
    runtime = DataPlatformRuntimeService().build_status()
    return runtime.get("kettle", {})


@router.get("/data-platform/ray-embedding/status")
async def get_data_platform_ray_embedding_status(current_user: dict = Depends(require_superuser)):
    runtime = DataPlatformRuntimeService().build_status()
    return runtime.get("ray_embedding", {})


@router.get("/data-platform/features/status")
async def get_data_platform_feature_status(current_user: dict = Depends(require_superuser)):
    return FeatureAssetService().get_status()


@router.post("/data-platform/features/events")
async def ingest_data_platform_feature_event(request: FeatureEventRequest, current_user: dict = Depends(require_superuser)):
    service = FeatureAssetService()
    event = request.model_dump(exclude_none=True)
    result = await service.ingest_event(event)
    add_audit_log(
        action="system.data_platform.features.ingest",
        actor=current_user,
        target_type="feature_asset",
        target_id=request.product_id,
        result="success",
        detail={"event_type": request.event_type},
    )
    return result


@router.post("/data-platform/features/batch")
async def get_data_platform_features_batch(request: FeatureBatchRequest, current_user: dict = Depends(require_superuser)):
    service = FeatureAssetService()
    features = await service.get_features_batch(request.product_ids)
    return {
        "total": len(features),
        "items": features,
    }


@router.get("/data-platform/features/{product_id}/history")
async def get_data_platform_feature_history(
    product_id: str,
    limit: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(require_superuser),
):
    service = FeatureAssetService()
    items = service.get_feature_history(product_id, limit=limit)
    return {
        "product_id": product_id,
        "total": len(items),
        "items": items,
    }


@router.get("/data-platform/features/{product_id}")
async def get_data_platform_feature(product_id: str, current_user: dict = Depends(require_superuser)):
    service = FeatureAssetService()
    result = await service.get_feature(product_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"特征资产不存在: {product_id}")
    return result


@router.get("/data-platform/batch/features/status")
async def get_data_platform_batch_feature_status(current_user: dict = Depends(require_superuser)):
    return BatchAdsService().build_status()


@router.get("/data-platform/batch/features/latest")
async def get_data_platform_batch_feature_latest(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_superuser),
):
    result = BatchAdsService().get_latest_features(limit=limit)
    add_audit_log(
        action="system.data_platform.batch_features.latest",
        actor=current_user,
        target_type="batch_feature_asset",
        result="success",
        detail={"limit": limit, "result_count": result.get("total", 0)},
    )
    return result


@router.get("/data-platform/batch/features/{product_id}")
async def get_data_platform_batch_feature(product_id: str, current_user: dict = Depends(require_superuser)):
    result = BatchAdsService().get_feature(product_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"批处理特征不存在: {product_id}")
    return result


@router.get("/data-platform/batch/features/{product_id}/history")
async def get_data_platform_batch_feature_history(
    product_id: str,
    limit: int = Query(20, ge=1, le=200),
    current_user: dict = Depends(require_superuser),
):
    return BatchAdsService().get_feature_history(product_id, limit=limit)


@router.get("/data-platform/ads/selection-overview")
async def get_data_platform_selection_overview_ads(current_user: dict = Depends(require_superuser)):
    result = BatchAdsService().get_selection_overview_ads()
    if result is None:
        raise HTTPException(status_code=404, detail="ADS 总览不存在")
    return result


@router.get("/data-governance/status")
async def get_data_governance_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        status = await result if hasattr(result, "__await__") else result
        return {
            "quality_rules": status.get("governance", {}).get("quality_rules", []),
            "quality_rule_count": status.get("governance", {}).get("quality_rule_count", 0),
            "field_dictionary_assets": status.get("governance", {}).get("field_dictionary_assets", []),
            "asset_catalog_ready": status.get("governance", {}).get("asset_catalog_ready", False),
            "lineage_ready": status.get("governance", {}).get("lineage_ready", False),
            "lineage": status.get("governance", {}).get("lineage", {}),
            "bi_ready_export": status.get("governance", {}).get("bi_ready_export", False),
            "bi_ready_assets": status.get("bi_ready_assets", []),
        }
    finally:
        await session.close()


@router.get("/lakehouse/status")
async def get_lakehouse_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        status = await result if hasattr(result, "__await__") else result
        return {
            "ods_ready": status.get("lakehouse", {}).get("ods_ready", False),
            "table_format_ready": status.get("lakehouse", {}).get("table_format_ready", False),
            "supported_formats": status.get("lakehouse", {}).get("supported_formats", []),
            "default_offline_format": status.get("lakehouse", {}).get("default_offline_format"),
            "target_offline_format": status.get("lakehouse", {}).get("target_offline_format"),
            "iceberg_compatible_ready": status.get("lakehouse", {}).get("iceberg_compatible_ready", False),
            "local_query_ready": status.get("lakehouse", {}).get("local_query_ready", False),
            "selection_task_metrics_dataset": status.get("lakehouse", {}).get("selection_task_metrics_dataset"),
            "selection_task_metrics_manifest": status.get("lakehouse", {}).get("selection_task_metrics_manifest"),
        }
    finally:
        await session.close()


@router.get("/data-layering/status")
async def get_data_layering_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        status = await result if hasattr(result, "__await__") else result
        return {
            "layers": status.get("layering", {}),
            "core_domain_ready": all(bool(layer.get("ready")) for layer in status.get("layering", {}).values()),
        }
    finally:
        await session.close()


@router.get("/bi/status")
async def get_bi_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = service.build_status()
        status = await result if hasattr(result, "__await__") else result
        return {
            "catalog_ready": True,
            "export_ready": len(status.get("bi_ready_assets", [])) >= 2,
            "bi_ready_assets": status.get("bi_ready_assets", []),
            "downstream_consumers": status.get("downstream_consumers", {}).get("bi", []),
            "latest_snapshot_paths": status.get("offline", {}).get("assets", {}),
            "task_metrics_dataset": "selection_task_metrics",
            "task_metrics_ready": "selection_task_metrics" in status.get("bi_ready_assets", []),
        }
    finally:
        await session.close()


@router.get("/profit-flywheel/status")
async def get_profit_flywheel_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        service = ProfitFlywheelService(session, tenant_id=current_user.get("tenant_id"))
        return await service.build_status()
    finally:
        await session.close()


@router.post("/profit-optimization/quote-cache")
async def build_supplier_quote_cache(request: SupplierQuoteCacheRequest, current_user: dict = Depends(require_superuser)):
    service = ProfitOptimizationService()
    result = await service.build_quote_cache(product_keyword=request.product_keyword, max_suppliers=request.max_suppliers)
    add_audit_log(
        action="profit.optimization.quote_cache",
        actor=current_user,
        target_type="profit_optimization",
        target_id=request.product_keyword,
        result="success",
        detail={"supplier_count": (result.get("summary") or {}).get("supplier_count")},
    )
    return result


@router.post("/profit-optimization/supplier-recommendations")
async def build_supplier_recommendations(request: SupplierRecommendationRequest, current_user: dict = Depends(require_superuser)):
    service = ProfitOptimizationService()
    result = await service.build_supplier_recommendations(
        product_keyword=request.product_keyword,
        monthly_demand=request.monthly_demand,
        max_suppliers=request.max_suppliers,
        target_price=request.target_price,
    )
    add_audit_log(
        action="profit.optimization.supplier_recommendations",
        actor=current_user,
        target_type="profit_optimization",
        target_id=request.product_keyword,
        result="success",
        detail={"recommendation_count": len(result.get("recommendations") or [])},
    )
    return result


@router.post("/profit-optimization/restock-plan")
async def build_profit_restock_plan(request: RestockPlanRequest, current_user: dict = Depends(require_superuser)):
    service = ProfitOptimizationService()
    result = await service.build_restock_plan(
        product_keyword=request.product_keyword,
        monthly_demand=request.monthly_demand,
        current_inventory_units=request.current_inventory_units,
        target_price=request.target_price,
        max_suppliers=request.max_suppliers,
        preferred_supplier_code=request.preferred_supplier_code,
        oms_api_endpoint=request.oms_api_endpoint,
        oms_api_key=request.oms_api_key,
        oms_inbound_path=request.oms_inbound_path,
        product_id=request.product_id,
    )
    add_audit_log(
        action="profit.optimization.restock_plan",
        actor=current_user,
        target_type="profit_optimization",
        target_id=request.product_keyword,
        result="success",
        detail={"recommended_restock_units": result.get("recommended_restock_units")},
    )
    return result


@router.get("/selection-execution/status")
async def get_selection_execution_status(current_user: dict = Depends(require_superuser)):
    settings = get_settings().selection_execution
    from src.workers.celery_app import celery_app

    return {
        "mode": settings.mode,
        "enable_api_background_dispatch": settings.enable_api_background_dispatch,
        "enable_celery_dispatch": settings.enable_celery_dispatch,
        "celery": {
            "broker_url": settings.celery_broker_url,
            "result_backend": settings.celery_result_backend,
            "queue_name": settings.celery_queue_name,
            "beat_schedule": celery_app.conf.beat_schedule,
            "beat_schedule_count": len(celery_app.conf.beat_schedule or {}),
        },
        "worker": {
            "poll_interval_seconds": settings.worker_poll_interval_seconds,
            "batch_size": settings.worker_batch_size,
        },
        "monitoring": build_schedule_monitor_status(celery_app),
    }


@router.get("/kafka-cluster/status")
async def get_kafka_cluster_status(current_user: dict = Depends(require_superuser)):
    service = KafkaClusterStatusService()
    return await service.build_status()


@router.get("/realtime/status")
async def get_realtime_status(current_user: dict = Depends(require_superuser)):
    return get_realtime_gateway_status()


@router.get("/business-config-governance")
async def get_business_config_governance(current_user: dict = Depends(require_superuser)):
    return BusinessConfigGovernanceService().build_status()


@router.get("/operations-governance-overview")
async def get_operations_governance_overview(current_user: dict = Depends(require_superuser)):
    return OperationsGovernanceOverviewService().build_status()


@router.get("/delivery-readiness")
async def get_delivery_readiness(current_user: dict = Depends(require_superuser)):
    return DeliveryReadinessService().build_status()


@router.get("/delivery-conclusion")
async def get_delivery_conclusion(current_user: dict = Depends(require_superuser)):
    return DeliveryConclusionService().build_status()


@router.get("/delivery-scope-boundary")
async def get_delivery_scope_boundary(current_user: dict = Depends(require_superuser)):
    return DeliveryScopeBoundaryService().build_status()


@router.get("/config-operations")
async def get_config_operations(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = ConfigOperationsService(session, tenant_id=current_user.get("tenant_id"))
        except TypeError:
            service = ConfigOperationsService()
        if hasattr(service, "build_status"):
            result = service.build_status()
            return await result if hasattr(result, "__await__") else result
        return await service.build_operations_status()
    finally:
        await session.close()


@router.get("/tenant-operations")
async def get_tenant_operations(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = TenantOperationsService(session)
        except TypeError:
            service = TenantOperationsService()
        result = service.build_status()
        return await result if hasattr(result, "__await__") else result
    finally:
        await session.close()


@router.get("/audit-operations")
async def get_audit_operations(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = AuditOperationsService(session, tenant_id=current_user.get("tenant_id"))
        except TypeError:
            service = AuditOperationsService()
        if hasattr(service, "build_status"):
            result = service.build_status()
            return await result if hasattr(result, "__await__") else result
        return await service.build_status(limit=20)
    finally:
        await session.close()


@router.get("/release/status")
async def get_release_status(current_user: dict = Depends(require_superuser)):
    service = ReleaseManagementService()
    return service.build_status()


@router.get("/security/status")
async def get_security_status(current_user: dict = Depends(require_superuser)):
    service = SecurityBaselineService()
    return service.build_status()


@router.post("/security/captcha-ocr")
async def recognize_captcha(request: CaptchaOCRRequest, current_user: dict = Depends(require_superuser)):
    service = CaptchaOCRService()
    result = service.recognize(image_base64=request.image_base64, image_text_hint=request.image_text_hint)
    return result


@router.get("/llm-governance/status")
async def get_llm_governance_status(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = LLMGovernanceService(session, tenant_id=current_user.get("tenant_id"))
        except TypeError:
            service = LLMGovernanceService()
        result = service.build_status()
        if hasattr(result, "__await__"):
            return await result
        return result
    finally:
        await session.close()


@router.get("/ha-topology/status")
async def get_ha_topology_status(current_user: dict = Depends(require_superuser)):
    service = HATopologyService()
    return service.build_status()


@router.post("/data-lake/export/selection-tasks")
async def export_selection_tasks_snapshot(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        if hasattr(service, "export_selection_tasks_snapshot"):
            result = await service.export_selection_tasks_snapshot()
        else:
            result = await service.export_selection_task_snapshot()
        add_audit_log("system.data_lake.export", actor=current_user, target_type="data_asset", target_id=result["asset"], result="success", detail=result)
        return result
    finally:
        await session.close()


@router.post("/data-lake/export/selection-task-metrics")
async def export_selection_task_metrics_dataset(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        try:
            service = DataLakeService(session)
        except TypeError:
            service = DataLakeService()
        result = await service.export_selection_task_metrics_dataset()
        add_audit_log("system.data_lake.export", actor=current_user, target_type="data_asset", target_id=result["asset"], result="success", detail=result)
        return result
    finally:
        await session.close()


@router.get("/data-lake/ods/selection-tasks")
async def query_selection_tasks_ods(
    status: str | None = Query(None),
    target_market: str | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_superuser),
):
    session = get_async_session_factory()()
    try:
        service = DataLakeService(session)
        return service.query_selection_tasks_snapshot(
            status=status,
            target_market=target_market,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
        )
    finally:
        await session.close()


@router.get("/data-lake/lakehouse/selection-task-metrics")
async def query_selection_task_metrics_lakehouse(
    status: str | None = Query(None),
    target_market: str | None = Query(None),
    decision: str | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_superuser),
):
    session = get_async_session_factory()()
    try:
        service = DataLakeService(session)
        result = service.query_selection_task_metrics_dataset(
            status=status,
            target_market=target_market,
            decision=decision,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
        )
        add_audit_log(
            action="system.data_lake.lakehouse.selection_task_metrics.query",
            actor=current_user,
            target_type="lakehouse_asset",
            target_id="selection_task_metrics",
            result="success",
            detail={
                "status": status,
                "target_market": target_market,
                "decision": decision,
                "limit": limit,
                "result_count": result.get("total", 0),
            },
        )
        return result
    finally:
        await session.close()


@router.get("/data-lake/ods/data-sync-events")
async def query_data_sync_events_ods(
    entity_type: str | None = Query(None),
    event_type: str | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_superuser),
):
    session = get_async_session_factory()()
    try:
        service = DataLakeService(session)
        result = service.query_data_sync_events_snapshot(
            entity_type=entity_type,
            event_type=event_type,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
        )
        add_audit_log(
            action="system.data_lake.ods.data_sync_events.query",
            actor=current_user,
            target_type="ods_asset",
            target_id="data_sync_events_snapshot",
            result="success",
            detail={"entity_type": entity_type, "event_type": event_type, "limit": limit, "result_count": result.get("total", 0)},
        )
        return result
    finally:
        await session.close()


@router.get("/costs/report")
async def get_cost_report(current_user: dict = Depends(require_superuser)):
    session = get_async_session_factory()()
    try:
        quota_repo = TenantQuotaRepository(session)
        quota_status = await quota_repo.list_quota_status(tenant_id=current_user.get("tenant_id"))
        cost_summary = {"llm_cost_usd": 0.0, "token_usage_total": 0.0}
        quota_exceeded = False
        for item in quota_status:
            quota_type = item.get("quota_type") if isinstance(item, dict) else getattr(item, "quota_type", None)
            used_value = float((item.get("used_value") if isinstance(item, dict) else getattr(item, "used_value", 0)) or 0)
            remaining = float((item.get("remaining") if isinstance(item, dict) else getattr(item, "remaining", 0)) or 0)
            if quota_type == "llm_cost_usd":
                cost_summary["llm_cost_usd"] = used_value
            elif quota_type == "llm_tokens_total":
                cost_summary["token_usage_total"] = used_value
            quota_exceeded = quota_exceeded or remaining < 0
        governance_status = LLMGovernanceService(session).build_status()
        route_policy = governance_status.get("route_policy", {}) if isinstance(governance_status, dict) else {}
        return {
            "cost_summary": cost_summary,
            "governance": {"route_policy_version": route_policy.get("version")},
            "alerts": {"quota_exceeded": quota_exceeded},
            "quota_status": quota_status,
        }
    finally:
        await session.close()


@router.get("/audit/logs")
async def get_audit_logs(
    username: str | None = Query(None),
    target_id: str | None = Query(None),
    action: str | None = Query(None),
    request_id: str | None = Query(None),
    trace_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_superuser),
):
    add_audit_log(
        action="system.audit.query",
        actor=current_user,
        target_type="audit_log",
        result="success",
        detail={
            "username": username,
            "target_id": target_id,
            "action": action,
            "request_id": request_id,
            "trace_id": trace_id,
            "limit": limit,
        },
    )
    session = get_async_session_factory()()
    try:
        service = AuditOperationsService(session, tenant_id=current_user.get("tenant_id"))
        return await service.query_logs(
            username=username,
            target_id=target_id,
            action=action,
            request_id=request_id,
            trace_id=trace_id,
            limit=limit,
        )
    finally:
        await session.close()
