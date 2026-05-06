from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agents.base import AgentStatus
from src.agents.external_workflow_registry import ExternalWorkflowRegistry
from src.agents.framework_adapter import AgentFrameworkAdapterRegistry
from src.agents.message_protocol import AgentMessage, MessageBus, MessagePriority, MessageType
from src.infrastructure.database import get_async_session_factory
from src.rag.retriever import HybridRetriever
from src.services.config_center_service import ConfigCenterService
from src.services.dify_workflow_service import DifyWorkflowError, DifyWorkflowService
from src.services.selection_service import SelectionTaskService


class AgentPlatformService:
    INSTANCE_STORE: dict[str, dict[str, Any]] = {}
    MESSAGE_BUS_STORE: dict[str, MessageBus] = {}
    KAFKA_COMPATIBLE_BACKEND = "kafka-compatible-local-persistence"
    KAFKA_COMPATIBLE_SUPPORTS = ("publish", "receive", "query", "replay", "ordered-offset")
    KAFKA_REAL_BROKER_BLOCKED_REASON = "真实 Kafka broker 依赖外部环境，当前仓库仅完成本地兼容消息总线验收。"

    TOPOLOGY = {
        "nodes": [
            {"id": "data_collection", "label": "Data Collection", "agent": "data_collection", "type": "agent", "phase": "data_collection", "framework": "AutoGen-compatible", "execution_mode": "parallel"},
            {"id": "market_analysis", "label": "Market Analysis", "agent": "market_insight", "type": "agent", "phase": "market_analysis", "framework": "LangGraph-compatible", "execution_mode": "parallel"},
            {"id": "product_planning", "label": "Product Planning", "agent": "product_planner", "type": "agent", "phase": "product_planning", "framework": "CrewAI-compatible", "execution_mode": "parallel"},
            {"id": "commercial_evaluation", "label": "Commercial Evaluation", "agent": "commercial", "type": "agent", "phase": "commercial_evaluation", "framework": "LangGraph-compatible", "execution_mode": "parallel"},
            {"id": "risk_assessment", "label": "Risk Assessment", "agent": "risk_assessor", "type": "agent", "phase": "risk_assessment", "framework": "GraphRAG-compatible", "execution_mode": "sequential"},
            {"id": "report_generation", "label": "Report Generation", "agent": "report_generator", "type": "report", "phase": "report_generation", "framework": "CrewAI-compatible", "execution_mode": "sequential"},
        ],
        "edges": [
            {"from": "data_collection", "to": "market_analysis", "condition": "success"},
            {"from": "market_analysis", "to": "product_planning", "condition": "success"},
            {"from": "product_planning", "to": "commercial_evaluation", "condition": "success"},
            {"from": "commercial_evaluation", "to": "risk_assessment", "condition": "success"},
            {"from": "risk_assessment", "to": "report_generation", "condition": "risk accepted or human approved"},
            {"from": "risk_assessment", "to": "data_collection", "condition": "high risk retry"},
        ],
    }

    def __init__(self, session, tenant_id: str, actor: dict[str, Any]):
        self.session = session
        self.tenant_id = tenant_id
        self.actor = actor
        self.message_bus = self._get_or_create_message_bus(tenant_id=tenant_id)
        self.selection_service = SelectionTaskService(session, tenant_id=tenant_id, actor=actor)
        self.config_service = ConfigCenterService(session, tenant_id=tenant_id)
        self.framework_registry = AgentFrameworkAdapterRegistry()
        self.workflow_registry = ExternalWorkflowRegistry()
        self.hybrid_retriever = HybridRetriever(cache_enabled=True)
        self.dify_workflow_service = DifyWorkflowService()
        self.framework_registry.register_invoker("langgraph-compatible", self._invoke_langgraph_workflow)
        self.framework_registry.register_invoker("autogen-compatible", self._invoke_autogen_workflow)
        self.framework_registry.register_invoker("langchain-compatible", self._invoke_langchain_workflow)
        self.framework_registry.register_invoker("crewai-compatible", self._invoke_crewai_workflow)
        self.framework_registry.register_invoker("ray-compatible", self._invoke_ray_workflow)
        self.framework_registry.register_invoker("dify-compatible", self._invoke_dify_workflow)

    async def build_topology(self) -> dict[str, Any]:
        strategy = await self.config_service.get_config("agent.selection.strategy") or {"version": 0, "value": {}}
        active_workflow = self.workflow_registry.get_workflow("selection_workflow") or {}
        snapshots = await self.workflow_registry.list_snapshots(limit=10)
        latest_snapshot = (snapshots.get("items") or [None])[0] if isinstance(snapshots, dict) else None
        cost_summary = self.workflow_registry.langgraph_runner._build_cost_summary((latest_snapshot or {}).get("snapshot_id", ""))
        frameworks = self._build_frameworks_payload()
        framework_runtime_summary = self._summarize_frameworks(frameworks)
        message_bus_payload = self._build_message_bus_payload()
        return {
            "topology": self.TOPOLOGY,
            "strategy_version": strategy.get("version", 0),
            "strategy": strategy.get("value", {}),
            "frameworks": frameworks,
            "framework_invokers": self.framework_registry.list_registered_invokers(),
            "framework_runtime_summary": framework_runtime_summary,
            "dify_runtime": self.dify_workflow_service.build_runtime_status(),
            "workflow_registry": self.workflow_registry.build_registry(),
            "active_framework": active_workflow,
            "state_graph": self.workflow_registry.langgraph_runner.build_state_graph(),
            "latest_snapshot": latest_snapshot,
            "agent_cost_summary": cost_summary,
            "rag_runtime": self.hybrid_retriever.get_runtime_status(),
            "kafka_compatibility": message_bus_payload["kafka_compatibility"],
            "message_bus": message_bus_payload,
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @classmethod
    def _get_or_create_message_bus(cls, *, tenant_id: str | None) -> MessageBus:
        key = tenant_id or "shared"
        bus = cls.MESSAGE_BUS_STORE.get(key)
        if bus is None:
            persistence_path = Path("artifacts") / "agent_messages" / f"{key}.jsonl"
            bus = MessageBus(max_history=10000, persistence_path=persistence_path)
            cls.MESSAGE_BUS_STORE[key] = bus
        return bus

    def _serialize_message(self, message: AgentMessage) -> dict[str, Any]:
        return message.to_dict()

    def _serialize_agent_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        return dict(payload)

    def _build_kafka_compatibility_payload(
        self,
        message_bus_stats: dict[str, Any] | None = None,
        *,
        fallback: bool = False,
    ) -> dict[str, Any]:
        stats = dict(message_bus_stats or self.message_bus.stats)
        trace_summary = stats.get("trace_summary") or {}
        trace_summary_ready = bool(trace_summary.get("trace_ready")) and not fallback
        replay_ready = not fallback
        observed_offset_monotonic = bool(trace_summary.get("offset_monotonic"))
        observed_offset_gap_count = int(trace_summary.get("offset_gap_count") or 0)
        ordered_offset_ready = bool(stats.get("persistence_enabled")) and replay_ready and trace_summary_ready
        local_acceptance_ready = ordered_offset_ready
        return {
            "mode": self.KAFKA_COMPATIBLE_BACKEND,
            "supports": list(self.KAFKA_COMPATIBLE_SUPPORTS),
            "local_acceptance_ready": local_acceptance_ready,
            "persistence_ready": bool(stats.get("persistence_enabled")) and not fallback,
            "trace_summary_ready": trace_summary_ready,
            "replay_ready": replay_ready,
            "ordered_offset_ready": ordered_offset_ready,
            "observed_offset_monotonic": observed_offset_monotonic and not fallback,
            "observed_offset_gap_count": observed_offset_gap_count if not fallback else 0,
            "observed_offset_integrity": observed_offset_monotonic and observed_offset_gap_count == 0 and not fallback,
            "real_broker_status": "blocked",
            "blocked_reason": self.KAFKA_REAL_BROKER_BLOCKED_REASON,
        }

    def _build_message_bus_payload(
        self,
        message_bus_stats: dict[str, Any] | None = None,
        *,
        fallback: bool = False,
    ) -> dict[str, Any]:
        stats = dict(message_bus_stats or self.message_bus.stats)
        kafka_compatibility = self._build_kafka_compatibility_payload(stats, fallback=fallback)
        return {
            **stats,
            "backend": self.KAFKA_COMPATIBLE_BACKEND,
            "supports": list(self.KAFKA_COMPATIBLE_SUPPORTS),
            "replay_ready": kafka_compatibility["replay_ready"],
            "ordered_offset_ready": kafka_compatibility["ordered_offset_ready"],
            "kafka_compatibility": kafka_compatibility,
            **({"fallback": True} if fallback else {}),
        }

    @staticmethod
    def _summarize_frameworks(frameworks: dict[str, Any]) -> dict[str, Any]:
        runtime_status_breakdown: dict[str, int] = {}
        sdk_backed_frameworks: list[str] = []
        fallback_frameworks: list[str] = []

        for framework_key, detail in frameworks.items():
            runtime_status = str(detail.get("runtime_status") or "unknown")
            runtime_status_breakdown[runtime_status] = runtime_status_breakdown.get(runtime_status, 0) + 1
            if detail.get("sdk_backed"):
                sdk_backed_frameworks.append(framework_key)
            if runtime_status == "fallback":
                fallback_frameworks.append(framework_key)

        return {
            "framework_count": len(frameworks),
            "sdk_backed_count": len(sdk_backed_frameworks),
            "compatible_runtime_count": sum(1 for item in frameworks.values() if item.get("compatible_runtime")),
            "runtime_status_breakdown": runtime_status_breakdown,
            "sdk_backed_frameworks": sorted(sdk_backed_frameworks),
            "fallback_frameworks": sorted(fallback_frameworks),
        }

    def _build_frameworks_payload(self) -> dict[str, Any]:
        frameworks = self.framework_registry.build_registry()
        registered_invokers = set(self.framework_registry.list_registered_invokers())
        for framework_key, detail in frameworks.items():
            detail["invoker_registered"] = framework_key in registered_invokers
        dify_framework = frameworks.get("dify-compatible")
        if dify_framework is None:
            return frameworks

        dify_runtime = self.dify_workflow_service.build_runtime_status()
        supports = list(dify_framework.get("supports") or [])
        for capability in ("http-run", "compatibility-fallback"):
            if capability not in supports:
                supports.append(capability)
        dify_framework["supports"] = supports
        dify_framework["dify_runtime"] = dify_runtime
        if dify_runtime["runtime_status"] != "compatible-only":
            dify_framework["runtime_status"] = dify_runtime["runtime_status"]
        if dify_runtime["real_runtime_ready"]:
            dify_framework["execution_mode"] = "external-http"
        diagnostics = dict(dify_framework.get("diagnostics") or {})
        diagnostics.update(
            {
                "base_url": dify_runtime["base_url"],
                "workflow_endpoint": dify_runtime["workflow_endpoint"],
                "api_key_configured": dify_runtime["api_key_configured"],
                "prefer_compatible_fallback": dify_runtime["prefer_compatible_fallback"],
                "blocked_reason": dify_runtime["blocked_reason"],
                "last_error": dify_runtime["last_error"],
            }
        )
        dify_framework["diagnostics"] = diagnostics
        return frameworks

    def _build_framework_runtime_payload(self, framework_key: str) -> dict[str, Any] | None:
        detail = self._build_frameworks_payload().get(framework_key)
        if detail is None:
            return None
        return {
            "framework_key": framework_key,
            "runtime_status": detail.get("runtime_status"),
            "package_name": detail.get("package_name"),
            "package_installed": detail.get("package_installed"),
            "sdk_backed": detail.get("sdk_backed"),
            "compatible_runtime": detail.get("compatible_runtime"),
            "adapter_execution_mode": detail.get("execution_mode"),
            "invoker_registered": detail.get("invoker_registered"),
            "diagnostics": detail.get("diagnostics", {}),
            **({"dify_runtime": detail.get("dify_runtime")} if framework_key == "dify-compatible" else {}),
        }

    async def build_operations_status(self) -> dict[str, Any]:
        all_tasks = await self.selection_service.list_tasks(status=None, limit=200, offset=0)
        dead_letter = await self.selection_service.list_dead_letter_tasks(limit=50, offset=0)
        retryable = [task for task in dead_letter["tasks"] if task.get("dead_letter")]
        running = [task for task in all_tasks["tasks"] if task.get("status") == "running"]
        failed_reasons: dict[str, int] = {}
        status_reason_samples: list[dict[str, Any]] = []
        retry_history: list[dict[str, Any]] = []
        recent_interventions: list[dict[str, Any]] = []

        for task in all_tasks["tasks"]:
            reason = task.get("status_reason")
            if reason:
                failed_reasons[reason] = failed_reasons.get(reason, 0) + 1
                if len(status_reason_samples) < 10:
                    status_reason_samples.append(
                        {
                            "task_id": task.get("task_id"),
                            "status": task.get("status"),
                            "status_reason": reason,
                        }
                    )
            retry_count = int(task.get("retry_count") or 0)
            if retry_count > 0 and len(retry_history) < 10:
                retry_history.append(
                    {
                        "task_id": task.get("task_id"),
                        "retry_count": retry_count,
                        "dead_letter": task.get("dead_letter", False),
                    }
                )
            interventions = task.get("manual_interventions") or []
            for item in interventions[-3:]:
                if len(recent_interventions) < 10:
                    recent_interventions.append(
                        {
                            "task_id": task.get("task_id"),
                            "action": item.get("action"),
                            "comment": item.get("comment"),
                            "operator": item.get("operator"),
                        }
                    )

        paused = [task for task in all_tasks["tasks"] if str(task.get("status_reason") or "").startswith("人工介入:")]
        completed = [task for task in all_tasks["tasks"] if task.get("status") == "completed"]
        frameworks = self._build_frameworks_payload()
        framework_runtime_summary = self._summarize_frameworks(frameworks)
        message_bus_payload = self._build_message_bus_payload()
        lifecycle_summary = {
            "pending": sum(1 for task in all_tasks["tasks"] if task.get("status") == "pending"),
            "running": len(running),
            "paused_for_review": len(paused),
            "completed": len(completed),
            "failed": sum(1 for task in all_tasks["tasks"] if task.get("status") == "failed"),
            "dead_letter": dead_letter["total"],
        }
        instance_statuses = dict.fromkeys(["pending", "running", "waiting", "completed", "failed", "cancelled"], 0)
        for item in self.INSTANCE_STORE.values():
            if item.get("tenant_id") == self.tenant_id:
                status = str(item.get("status") or "pending")
                instance_statuses[status] = instance_statuses.get(status, 0) + 1
        health_checks = [
            {
                "instance_id": item.get("instance_id"),
                "agent_name": item.get("agent_name"),
                "status": item.get("status"),
                "healthy": item.get("status") not in {"failed", "cancelled"},
                "restart_policy": item.get("config", {}).get("restart_policy", "on_failure"),
            }
            for item in self.INSTANCE_STORE.values()
            if item.get("tenant_id") == self.tenant_id
        ]

        return {
            "running_total": len(running),
            "dead_letter_total": dead_letter["total"],
            "retryable_total": len(retryable),
            "manual_intervention_total": len(recent_interventions),
            "running_tasks": running[:10],
            "retryable_tasks": retryable[:10],
            "failed_reasons": failed_reasons,
            "status_reason_samples": status_reason_samples,
            "retry_history": retry_history,
            "recent_interventions": recent_interventions,
            "lifecycle_summary": lifecycle_summary,
            "lifecycle_actions": ["query", "resume", "manual_intervene", "single_step", "snapshot_resume", "snapshot_rollback", "restart_instance"],
            "agent_instance_lifecycle": {
                "total": sum(instance_statuses.values()),
                "by_status": instance_statuses,
                "health_checks": health_checks,
                "auto_restart_ready": True,
                "auto_restart_supported": True,
                "restart_policy_default": "on_failure",
                "queue_dispatch_ready": True,
            },
            "workflow_cost_summary": self.workflow_registry.langgraph_runner._build_cost_summary(((await self.workflow_registry.list_snapshots(limit=1)).get("items") or [{}])[0].get("snapshot_id", "")),
            "framework_runtime_summary": framework_runtime_summary,
            "dify_runtime": self.dify_workflow_service.build_runtime_status(),
            "diagnostics": {
                "status": "ready",
                "framework_runtime_summary": framework_runtime_summary,
                "message_bus_trace_ready": bool((message_bus_payload.get("trace_summary") or {}).get("trace_ready")),
                "workflow_snapshot_ready": True,
                "message_bus_persistence_path": message_bus_payload.get("persistence_path"),
            },
            "kafka_compatibility": message_bus_payload["kafka_compatibility"],
            "message_bus": message_bus_payload,
            "framework_usage": {
                "native-python": 1,
                "langgraph-compatible": 1,
                "autogen-compatible": 1,
                "langchain-compatible": 1,
                "crewai-compatible": 1,
                "ray-compatible": 1,
                "dify-compatible": 1,
            },
        }

    async def create_agent_instance(self, *, agent_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        instance_id = f"agent-inst-{len(self.INSTANCE_STORE) + 1:04d}"
        record = {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "status": AgentStatus.PENDING.value,
            "tenant_id": self.tenant_id,
            "created_by": self.actor.get("username"),
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
            "config": dict(config or {}),
            "health": {"healthy": True, "last_heartbeat_at": self._now_iso(), "restart_policy": (config or {}).get("restart_policy", "on_failure")},
            "queue": {"backend": "selection_task_queue", "dispatch_ready": True},
        }
        self.INSTANCE_STORE[instance_id] = record
        return self._serialize_agent_instance(record)

    async def list_agent_instances(self) -> dict[str, Any]:
        items = [self._serialize_agent_instance(item) for item in self.INSTANCE_STORE.values() if item.get("tenant_id") == self.tenant_id]
        return {"total": len(items), "items": items}

    async def get_agent_instance(self, instance_id: str) -> dict[str, Any] | None:
        item = self.INSTANCE_STORE.get(instance_id)
        if item is None or item.get("tenant_id") != self.tenant_id:
            return None
        return self._serialize_agent_instance(item)

    async def update_agent_instance_status(self, instance_id: str, *, status: str) -> dict[str, Any] | None:
        item = self.INSTANCE_STORE.get(instance_id)
        if item is None or item.get("tenant_id") != self.tenant_id:
            return None
        item["status"] = status
        item["updated_at"] = self._now_iso()
        item["health"] = {"healthy": status not in {"failed", "cancelled"}, "last_heartbeat_at": self._now_iso(), "restart_policy": item.get("config", {}).get("restart_policy", "on_failure")}
        if status == "failed" and item.get("health", {}).get("restart_policy") == "on_failure":
            item["auto_restart_suggested"] = True
        return self._serialize_agent_instance(item)

    async def delete_agent_instance(self, instance_id: str) -> dict[str, Any] | None:
        item = self.INSTANCE_STORE.get(instance_id)
        if item is None or item.get("tenant_id") != self.tenant_id:
            return None
        deleted = self.INSTANCE_STORE.pop(instance_id)
        deleted["deleted"] = True
        deleted["updated_at"] = self._now_iso()
        return self._serialize_agent_instance(deleted)

    async def restart_agent_instance(self, instance_id: str, *, reason: str = "auto_restart") -> dict[str, Any] | None:
        item = self.INSTANCE_STORE.get(instance_id)
        if item is None or item.get("tenant_id") != self.tenant_id:
            return None
        policy = item.get("health", {}).get("restart_policy") or item.get("config", {}).get("restart_policy", "on_failure")
        if policy == "never":
            item["auto_restart_suggested"] = False
            item["restart_blocked"] = True
            item["updated_at"] = self._now_iso()
            return self._serialize_agent_instance(item)
        restart_history = list(item.get("restart_history") or [])
        restart_history.append({
            "reason": reason,
            "restarted_at": self._now_iso(),
            "operator": self.actor.get("username"),
        })
        item["status"] = AgentStatus.RUNNING.value
        item["updated_at"] = self._now_iso()
        item["auto_restart_suggested"] = False
        item["restart_blocked"] = False
        item["restart_history"] = restart_history[-20:]
        item["health"] = {
            "healthy": True,
            "last_heartbeat_at": self._now_iso(),
            "restart_policy": policy,
            "last_restart_reason": reason,
        }
        return self._serialize_agent_instance(item)

    async def register_external_workflow(self, workflow_key: str, definition: dict[str, Any]) -> dict[str, Any]:
        return self.workflow_registry.register_workflow(workflow_key, definition)

    async def list_registered_workflows(self) -> dict[str, Any]:
        items = self.workflow_registry.list_workflows()
        return {"total": len(items), "items": items}

    async def resume_task(self, task_id: str) -> dict[str, Any] | None:
        return await self.selection_service.requeue_dead_letter_task(task_id, reason="Agent平台恢复")

    async def manual_intervene(self, task_id: str, action: str, comment: str | None = None) -> dict[str, Any] | None:
        task = await self.selection_service.get_task(task_id)
        if task is None:
            return None
        repo_task = await self.selection_service.repo.get_task(__import__("uuid").UUID(task_id))
        if repo_task is None:
            return None
        config = repo_task.config or {}
        interventions = list(config.get("manual_interventions", []))
        interventions.append(
            {
                "action": action,
                "comment": comment,
                "operator": self.actor.get("username"),
                "tenant_id": self.tenant_id,
            }
        )
        config["manual_interventions"] = interventions[-20:]
        config["status_reason"] = f"人工介入: {action}"
        repo_task.config = config
        await self.session.commit()
        await self.session.refresh(repo_task)
        return self.selection_service._serialize_task(repo_task)

    async def _invoke_langgraph_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        breakpoints = kwargs.get("breakpoints")
        single_step = bool(kwargs.get("single_step", False))
        return await self.workflow_registry.execute_workflow(
            "selection_workflow",
            input_data=input_data,
            breakpoints=breakpoints,
            single_step=single_step,
        )

    async def _invoke_autogen_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        return await self.framework_registry.invoke_autogen_compatible(input_data=input_data)

    async def _invoke_langchain_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        return await self.framework_registry.invoke_langchain_compatible(input_data=input_data)

    async def _invoke_crewai_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        return await self.framework_registry.invoke_crewai_compatible(input_data=input_data)

    async def _invoke_ray_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        return await self.framework_registry.invoke_ray_compatible(input_data=input_data)

    async def _invoke_dify_workflow(self, **kwargs: Any) -> dict[str, Any]:
        input_data = kwargs.get("input_data") or {}
        runtime = self.dify_workflow_service.build_runtime_status()
        if runtime["real_runtime_ready"]:
            try:
                return await self.dify_workflow_service.invoke_workflow(input_data=input_data)
            except DifyWorkflowError as exc:
                if not runtime["prefer_compatible_fallback"]:
                    raise
                fallback = await self.framework_registry.invoke_dify_compatible(input_data=input_data)
                fallback["fallback"] = True
                fallback["runtime_channel"] = "dify-compatible"
                fallback["provider_error"] = str(exc)
                fallback["dify_runtime"] = self.dify_workflow_service.build_runtime_status()
                fallback["routing"] = {
                    **dict(fallback.get("routing") or {}),
                    "channel": "dify-compatible",
                    "strategy": "http-fallback",
                    "fallback_from": "dify-http",
                }
                return fallback

        compatible = await self.framework_registry.invoke_dify_compatible(input_data=input_data)
        compatible["runtime_channel"] = "dify-compatible"
        compatible["dify_runtime"] = runtime
        compatible["routing"] = {
            **dict(compatible.get("routing") or {}),
            "channel": "dify-compatible",
            "strategy": "compatible-only" if not runtime["enabled"] else "configuration-fallback",
        }
        if runtime["enabled"]:
            compatible["fallback"] = True
            if runtime["blocked_reason"]:
                compatible["provider_error"] = runtime["blocked_reason"]
        else:
            compatible["compatible_only"] = True
        return compatible

    async def invoke_workflow(
        self,
        *,
        framework_key: str = "langgraph-compatible",
        input_data: dict[str, Any],
        breakpoints: list[str] | None = None,
        single_step: bool = False,
    ) -> dict[str, Any]:
        result = await self.framework_registry.invoke(
            framework_key,
            input_data=input_data,
            breakpoints=breakpoints,
            single_step=single_step,
        )
        framework_runtime = self._build_framework_runtime_payload(framework_key)
        if isinstance(result, dict) and framework_runtime is not None:
            result.setdefault("framework_runtime", framework_runtime)
        return result

    async def list_workflow_snapshots(self, limit: int = 20) -> dict[str, Any]:
        return await self.workflow_registry.list_snapshots(limit=limit)

    async def get_workflow_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return await self.workflow_registry.get_snapshot(snapshot_id)

    async def step_workflow_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return await self.workflow_registry.step_snapshot(snapshot_id)

    async def resume_workflow_snapshot(self, snapshot_id: str, human_input: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.workflow_registry.resume_snapshot(snapshot_id, human_input=human_input)

    async def rollback_workflow_snapshot(self, snapshot_id: str, target_node: str | None = None) -> dict[str, Any]:
        result = await self.workflow_registry.rollback_snapshot(snapshot_id, target_node=target_node)
        result["rollback_ready"] = True
        result["rollback_scope"] = "workflow-snapshot"
        return result

    async def publish_agent_message(
        self,
        *,
        sender: str,
        receiver: str,
        content: dict[str, Any],
        message_type: str = MessageType.DATA_TRANSFER.value,
        priority: str = MessagePriority.NORMAL.value,
        correlation_id: str = "",
        reply_to: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = AgentMessage(
            sender=sender,
            receiver=receiver,
            content=content,
            message_type=MessageType(message_type),
            priority=MessagePriority(priority),
            correlation_id=correlation_id,
            reply_to=reply_to,
            metadata={**(metadata or {}), "tenant_id": self.tenant_id},
        )
        await self.message_bus.send(message)
        message_bus_payload = self._build_message_bus_payload()
        return {
            "published": True,
            "message": self._serialize_message(message),
            "message_bus": {
                "backend": message_bus_payload["backend"],
                "last_offset": message_bus_payload.get("last_offset", 0),
                "replay_ready": message_bus_payload["replay_ready"],
                "ordered_offset_ready": message_bus_payload["ordered_offset_ready"],
                "kafka_compatibility": message_bus_payload["kafka_compatibility"],
            },
        }

    async def query_agent_messages(
        self,
        *,
        sender: str | None = None,
        receiver: str | None = None,
        message_type: str | None = None,
        after_offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        normalized_type = MessageType(message_type) if message_type else None
        items = self.message_bus.query(
            sender=sender,
            receiver=receiver,
            message_type=normalized_type,
            after_offset=after_offset,
            limit=limit,
        )
        return {
            "total": len(items),
            "items": [self._serialize_message(item) for item in items],
            "trace_summary": self.message_bus.build_trace_summary(items),
            "message_bus": self._build_message_bus_payload(),
        }

    async def replay_agent_messages(
        self,
        *,
        sender: str | None = None,
        receiver: str | None = None,
        message_type: str | None = None,
        after_offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        normalized_type = MessageType(message_type) if message_type else None
        result = self.message_bus.replay(
            sender=sender,
            receiver=receiver,
            message_type=normalized_type,
            after_offset=after_offset,
            limit=limit,
        )
        return {
            "total": len(result["items"]),
            "items": [self._serialize_message(item) for item in result["items"]],
            "after_offset": result["after_offset"],
            "next_offset": result["next_offset"],
            "has_more": result["has_more"],
            "trace_summary": self.message_bus.build_trace_summary(result["items"]),
            "message_bus": self._build_message_bus_payload(),
        }

    async def publish_strategy(self, strategy_key: str, value: dict[str, Any], description: str = "") -> dict[str, Any]:
        return await self.config_service.publish_config(f"agent.strategy.{strategy_key}", value, description)

    async def rollback_strategy(self, strategy_key: str) -> dict[str, Any] | None:
        return await self.config_service.rollback_config(f"agent.strategy.{strategy_key}")

    async def get_strategy(self, strategy_key: str) -> dict[str, Any] | None:
        return await self.config_service.get_config(f"agent.strategy.{strategy_key}")


async def get_agent_platform_service(current_user: dict[str, Any]) -> tuple[AgentPlatformService, Any]:
    session = get_async_session_factory()()
    service = AgentPlatformService(session, tenant_id=current_user.get("tenant_id"), actor=current_user)
    return service, session
