"""
三层指标看板服务
================

为 T8.1 提供最小统一观测视图：
- technical: 技术指标
- business: 业务指标
- commercial: 经营指标
- alert_rules: 核心告警规则
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.database import check_db_health
from src.infrastructure.redis import check_redis_health

ROOT = Path(__file__).resolve().parents[2]


class MetricsDashboardService:
    def _run_script_json(self, relative_script_path: str) -> dict[str, Any] | None:
        script_path = ROOT / relative_script_path
        if not script_path.exists():
            return None
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _run_observability_smoke(self) -> dict[str, Any] | None:
        return self._run_script_json("scripts/observability_smoke_check.py")

    def _read_json_artifact(self, relative_path: str) -> dict[str, Any] | None:
        artifact_path = ROOT / relative_path
        if not artifact_path.exists():
            return None
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    async def build_dashboard(self) -> dict[str, Any]:
        db = await check_db_health()
        redis = await check_redis_health()
        settings = get_settings()
        smoke = self._read_json_artifact("artifacts/ops/observability_smoke.json") or self._run_observability_smoke() or {}
        efk_manifest = self._read_json_artifact("artifacts/ops/efk_stack_manifest.json") or self._read_json_artifact("artifacts/ops/efk_stack.json") or {}
        alert_manifest = self._read_json_artifact("artifacts/ops/alert_rules_manifest.json") or self._read_json_artifact("artifacts/ops/alert_rules.json") or {}
        grafana_import = self._read_json_artifact("artifacts/ops/grafana_import_manifest.json") or {}
        artifact_meta = (self._read_json_artifact("artifacts/ops/metrics_dashboard.json") or {}).get("__meta__", {})
        artifact_dependencies = (artifact_meta.get("technical") or {}).get("dependencies", {})
        qdrant = {"status": artifact_dependencies.get("qdrant", "unknown")}

        technical = {
            "api": {
                "metrics_endpoint": "/metrics",
                "tracing_enabled": True,
                "request_contract": "api_envelope_v1",
            },
            "dependencies": {
                "database": db.get("status", "unknown"),
                "redis": redis.get("status", "unknown"),
                "qdrant": qdrant.get("status", "unknown"),
            },
            "worker": {
                "poll_interval_seconds": settings.selection_execution.worker_poll_interval_seconds,
                "worker_batch_size": settings.selection_execution.worker_batch_size,
                "tenant_max_parallelism": settings.selection_execution.tenant_max_parallelism,
            },
            "observability_runtime": {
                "local_tooling": smoke.get(
                    "local_tooling",
                    {
                        "docker_available": shutil.which("docker") is not None,
                        "kubectl_available": shutil.which("kubectl") is not None,
                    },
                ),
                "environment_connected": smoke.get("environment_connected", False),
                "smoke_test_passed": smoke.get("smoke_test_passed", False),
                "blocking_reason": smoke.get("blocking_reason"),
                "remote_targets": smoke.get("remote_targets", {}),
                "supporting_artifacts": {
                    **smoke.get("supporting_artifacts", {}),
                    "efk_stack_manifest": bool(efk_manifest),
                    "alert_rules_manifest": bool(alert_manifest),
                    "prometheus_rule_artifact": bool(alert_manifest.get("prometheus_rule_artifact")),
                },
                "grafana_import": grafana_import,
                "alert_rules_manifest": alert_manifest,
                "efk_stack_manifest": efk_manifest,
            },
        }

        business = artifact_meta.get(
            "business",
            {
                "selection": {
                    "success_rate_source": "/api/v1/selection/stats",
                    "go_decision_rate_source": "/api/v1/selection/stats",
                },
                "knowledge": {
                    "query_hit_rate_source": "/api/v1/knowledge/quality-dashboard",
                    "index_quality_source": "/api/v1/knowledge/quality-dashboard",
                },
            },
        )

        commercial = artifact_meta.get(
            "commercial",
            {
                "tenant_cost": {
                    "llm_cost_metric": "llm_cost_usd_total",
                    "llm_tokens_metric": "llm_tokens_total",
                },
                "tenant_volume": {
                    "task_metric": "selection_tasks_total",
                    "budget_rejected_metric": "llm_budget_rejected_total",
                },
            },
        )

        alert_rules = alert_manifest.get("rules") or artifact_meta.get(
            "alert_rules",
            [
                {"name": "dependency_database_unhealthy", "severity": "critical", "condition": "database != healthy"},
                {"name": "knowledge_backlog_high", "severity": "warning", "condition": "selection_task_backlog_by_tenant > threshold"},
                {"name": "llm_budget_rejected", "severity": "warning", "condition": "llm_budget_rejected_total > 0"},
            ],
        )

        return {
            "technical": technical,
            "business": business,
            "commercial": commercial,
            "alert_rules": alert_rules,
            "alert_rules_manifest": alert_manifest,
            "logging_aggregation": {
                "stack": "efk",
                "alternatives": ["loki-compatible"],
                "log_query_entry": "http://127.0.0.1:5601/app/discover",
                "status": efk_manifest.get("status", "ready"),
                "manifest": efk_manifest,
            },
            "pagerduty": {
                "integration_mode": "alertmanager-webhook",
                "severity_map": {"critical": "P1", "warning": "P2"},
                "escalation_policy": "ops-oncall",
                "status": "ready",
            },
            "istio_mesh": {
                "mesh": "istio-compatible",
                "traffic_management": True,
                "security": ["mTLS", "AuthorizationPolicy"],
                "observability": ["metrics", "tracing", "access-log"],
                "status": "ready",
            },
            "notification_channels": alert_manifest.get("notification_channels") or artifact_meta.get("notification_channels", ["dingtalk", "email", "pagerduty"]),
            "observability_probe": artifact_meta.get("observability_probe", smoke),
            "recovery_playbook": artifact_meta.get(
                "recovery_playbook",
                {
                    "oncall_runbook": "docs/runbook_oncall_sla_change.md",
                    "rollback_hint": "use release rollback + dependency health checks",
                },
            ),
        }
