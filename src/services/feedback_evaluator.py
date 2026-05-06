from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import ERPSystemType
from src.repositories.erp_repository import ErpIntegrationRepository
from src.repositories.selection_repository import SelectionTaskRepository

logger = get_logger(__name__)


class FeedbackEvaluator:
    """
    闭环反馈评估服务。

    职责:
    - 收集实际执行指标（销售/库存/广告/利润/KPI）
    - 对比预测值与实际值，计算偏差
    - 生成评估报告
    - 触发模型再训练信号
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = ErpIntegrationRepository(session, tenant_id=self.tenant_id) if session is not None else None
        self.selection_repo = SelectionTaskRepository(session, tenant_id=self.tenant_id) if session is not None else None

    async def evaluate_suggestion(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        execution_result = config.get("execution_result") if isinstance(config.get("execution_result"), dict) else {}
        decision_output = execution_result.get("decision_output") if isinstance(execution_result, dict) else {}

        predicted = self._extract_predictions(decision_output)
        actual = await self._collect_actual_metrics(task_id, config)

        evaluation = {
            "task_id": task_id,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "predicted": predicted,
            "actual": actual,
            "deviations": {
                "roi": self._calc_deviation(predicted.get("roi"), actual.get("roi")),
                "sales": self._calc_deviation(predicted.get("sales"), actual.get("sales")),
                "acos": self._calc_deviation(predicted.get("acos"), actual.get("acos")),
                "profit_margin": self._calc_deviation(predicted.get("profit_margin"), actual.get("profit_margin")),
                "inventory_turnover": self._calc_deviation(predicted.get("inventory_turnover"), actual.get("inventory_turnover")),
            },
            "overall_score": self._calc_overall_score(predicted, actual),
            "recommendation": self._generate_recommendation(predicted, actual),
        }

        config.setdefault("feedback", {})
        config["feedback"]["evaluation"] = evaluation
        config["feedback"]["evaluated_at"] = datetime.now(UTC).isoformat()
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return evaluation

    async def collect_feedback_metrics(
        self,
        task_id: str,
        *,
        oms_name: str = "default",
        wms_name: str = "default",
        crm_name: str = "default",
        fms_name: str = "default",
        bi_name: str = "default",
    ) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}

        metrics: dict[str, Any] = {
            "task_id": task_id,
            "collected_at": datetime.now(UTC).isoformat(),
            "sales": {},
            "inventory": {},
            "customer": {},
            "financial": {},
            "kpi": {},
        }

        if self.repo is not None:
            try:
                oms_config = await self.repo.get_config(ERPSystemType.OMS, name=oms_name)
                if oms_config is not None:
                    from src.infrastructure.oms_client import OMSClient
                    extra = oms_config.extra_config or {}
                    oms_client = OMSClient(
                        api_endpoint=oms_config.api_endpoint,
                        api_key=oms_config.api_key,
                        secret_key=oms_config.secret_key,
                        inbound_path=extra.get("inbound_path", "/products"),
                        outbound_path=extra.get("outbound_path", "/listings"),
                        timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
                    )
                    sales_metrics = await oms_client.fetch_sales_metrics()
                    metrics["sales"] = {"data": sales_metrics, "source": "oms"}
            except Exception as e:
                logger.warning("OMS销售指标采集失败: %s", e)
                metrics["sales"] = {"error": str(e), "source": "oms"}

            try:
                wms_config = await self.repo.get_config(ERPSystemType.WMS, name=wms_name)
                if wms_config is not None:
                    from src.infrastructure.base_erp_client import AuditContext
                    from src.infrastructure.wms_client import WMSClient
                    extra = wms_config.extra_config or {}
                    wms_client = WMSClient(
                        api_endpoint=wms_config.api_endpoint,
                        api_key=wms_config.api_key,
                        secret_key=wms_config.secret_key,
                        inbound_path=extra.get("inbound_path", "/inventory-snapshots"),
                        outbound_path=extra.get("outbound_path", "/replenishment-plans"),
                        timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
                    )
                    inventory_snapshots = await wms_client.fetch_inventory_snapshots(
                        audit_context=AuditContext(
                            tenant_id=self.tenant_id or "system",
                            actor_type="service",
                            actor_id="feedback-evaluator",
                            domain="wms",
                            purpose="collect_feedback_metrics",
                            trace_id=f"feedback-{task_id}",
                        ),
                    )
                    metrics["inventory"] = {"data": inventory_snapshots, "source": "wms"}
            except Exception as e:
                logger.warning("WMS库存指标采集失败: %s", e)
                metrics["inventory"] = {"error": str(e), "source": "wms"}

            try:
                crm_config = await self.repo.get_config(ERPSystemType.CRM, name=crm_name)
                if crm_config is not None:
                    from src.infrastructure.crm_client import CRMClient
                    extra = crm_config.extra_config or {}
                    crm_client = CRMClient(
                        api_endpoint=crm_config.api_endpoint,
                        api_key=crm_config.api_key,
                        secret_key=crm_config.secret_key,
                        inbound_path=extra.get("inbound_path", "/feedbacks"),
                        outbound_path=extra.get("outbound_path", "/followups"),
                        timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
                    )
                    feedbacks = await crm_client.fetch_customer_feedbacks()
                    complaints = await crm_client.fetch_complaints()
                    metrics["customer"] = {
                        "feedbacks_count": len(feedbacks) if isinstance(feedbacks, list) else 0,
                        "complaints_count": len(complaints) if isinstance(complaints, list) else 0,
                        "source": "crm",
                    }
            except Exception as e:
                logger.warning("CRM客户指标采集失败: %s", e)
                metrics["customer"] = {"error": str(e), "source": "crm"}

            try:
                bi_config = await self.repo.get_config(ERPSystemType.BI, name=bi_name)
                if bi_config is not None:
                    from src.infrastructure.bi_client import BIClient
                    extra = bi_config.extra_config or {}
                    bi_client = BIClient(
                        api_endpoint=bi_config.api_endpoint,
                        api_key=bi_config.api_key,
                        secret_key=bi_config.secret_key,
                        inbound_path=extra.get("inbound_path", "/datasets"),
                        outbound_path=extra.get("outbound_path", "/kpis"),
                        timeout_seconds=float(extra.get("timeout_seconds", 10.0)),
                    )
                    kpi_dataset = await bi_client.read_dataset()
                    metrics["kpi"] = {"data": kpi_dataset, "source": "bi"}
            except Exception as e:
                logger.warning("BI KPI指标采集失败: %s", e)
                metrics["kpi"] = {"error": str(e), "source": "bi"}

        config.setdefault("feedback", {})
        config["feedback"]["collected_metrics"] = metrics
        selection_task.config = config
        if self.session is not None:
            await self.session.flush()

        return metrics

    async def get_evaluation(self, task_id: str) -> dict[str, Any]:
        selection_task = await self._get_selection_task(task_id)
        config = selection_task.config or {}
        feedback = config.get("feedback") if isinstance(config.get("feedback"), dict) else {}

        return {
            "task_id": task_id,
            "evaluation": feedback.get("evaluation"),
            "evaluated_at": feedback.get("evaluated_at"),
            "collected_metrics": feedback.get("collected_metrics"),
            "has_evaluation": feedback.get("evaluation") is not None,
        }

    @staticmethod
    def _extract_predictions(decision_output: dict[str, Any]) -> dict[str, float | None]:
        pricing = decision_output.get("pricing") if isinstance(decision_output.get("pricing"), dict) else {}
        supply_chain = decision_output.get("supply_chain") if isinstance(decision_output.get("supply_chain"), dict) else {}
        commercial = decision_output.get("commercial_evaluation") if isinstance(decision_output.get("commercial_evaluation"), dict) else {}

        return {
            "roi": commercial.get("expected_roi"),
            "sales": commercial.get("expected_sales"),
            "acos": commercial.get("expected_acos"),
            "profit_margin": commercial.get("expected_profit_margin"),
            "inventory_turnover": supply_chain.get("expected_inventory_turnover"),
            "recommended_price": pricing.get("recommended_price"),
        }

    async def _collect_actual_metrics(self, task_id: str, config: dict[str, Any]) -> dict[str, float | None]:
        feedback = config.get("feedback") if isinstance(config.get("feedback"), dict) else {}
        collected = feedback.get("collected_metrics") if isinstance(feedback.get("collected_metrics"), dict) else {}

        sales_data = collected.get("sales", {})
        inventory_data = collected.get("inventory", {})
        kpi_data = collected.get("kpi", {})

        actual_sales = None
        if isinstance(sales_data.get("data"), list) and sales_data["data"]:
            latest = sales_data["data"][0] if isinstance(sales_data["data"][0], dict) else {}
            actual_sales = latest.get("total_sales") or latest.get("sales")

        actual_acos = None
        actual_roi = None
        if isinstance(kpi_data.get("data"), dict):
            kpi = kpi_data["data"]
            actual_acos = kpi.get("acos")
            actual_roi = kpi.get("roi")

        actual_inventory_turnover = None
        if isinstance(inventory_data.get("data"), list) and inventory_data["data"]:
            latest_inv = inventory_data["data"][0] if isinstance(inventory_data["data"][0], dict) else {}
            actual_inventory_turnover = latest_inv.get("turnover_rate")

        return {
            "roi": actual_roi,
            "sales": actual_sales,
            "acos": actual_acos,
            "profit_margin": None,
            "inventory_turnover": actual_inventory_turnover,
            "customer_satisfaction": None,
        }

    @staticmethod
    def _calc_deviation(predicted: float | None, actual: float | None) -> dict[str, Any] | None:
        if predicted is None or actual is None:
            return None
        if predicted == 0:
            return {"absolute": actual, "percentage": None, "direction": "predicted_zero"}
        deviation = actual - predicted
        percentage = (deviation / abs(predicted)) * 100
        direction = "above" if deviation > 0 else ("below" if deviation < 0 else "on_target")
        return {
            "absolute": round(deviation, 4),
            "percentage": round(percentage, 2),
            "direction": direction,
        }

    @staticmethod
    def _calc_overall_score(predicted: dict[str, float | None], actual: dict[str, float | None]) -> dict[str, Any]:
        scores: list[float] = []
        weights: dict[str, float] = {
            "roi": 0.3,
            "sales": 0.25,
            "acos": 0.2,
            "profit_margin": 0.15,
            "inventory_turnover": 0.1,
        }

        for metric, weight in weights.items():
            p = predicted.get(metric)
            a = actual.get(metric)
            if p is not None and a is not None and p != 0:
                ratio = min(a / p, 2.0)
                metric_score = max(0.0, min(1.0, ratio))
                scores.append(metric_score * weight)

        total_score = sum(scores)
        total_weight = sum(weights[m] for m in weights if predicted.get(m) is not None and actual.get(m) is not None)

        normalized_score = 0.0 if total_weight == 0 else total_score / total_weight

        grade = "A" if normalized_score >= 0.9 else "B" if normalized_score >= 0.7 else "C" if normalized_score >= 0.5 else "D" if normalized_score >= 0.3 else "F"

        return {
            "score": round(normalized_score, 4),
            "grade": grade,
            "metrics_evaluated": len(scores),
            "total_weight_applied": round(total_weight, 2),
        }

    @staticmethod
    def _generate_recommendation(predicted: dict[str, float | None], actual: dict[str, float | None]) -> str:
        significant_deviations: list[str] = []

        for metric in ["roi", "sales", "acos", "profit_margin", "inventory_turnover"]:
            p = predicted.get(metric)
            a = actual.get(metric)
            if p is not None and a is not None and p != 0:
                deviation_pct = abs((a - p) / p) * 100
                if deviation_pct > 30:
                    significant_deviations.append(metric)

        if not significant_deviations:
            return "on_track"
        if len(significant_deviations) >= 3:
            return "needs_major_adjustment"
        return "needs_minor_adjustment"

    async def _get_selection_task(self, task_id: str) -> Any:
        if self.selection_repo is None:
            raise ValueError("选品任务仓储未初始化")
        try:
            normalized_task_id: Any = UUID(str(task_id))
        except ValueError:
            normalized_task_id = task_id
        task = await self.selection_repo.get_task(normalized_task_id)
        if task is None:
            raise ValueError(f"选品任务不存在: {task_id}")
        return task
