from __future__ import annotations

from typing import Any

from src.agents.langgraph_compatible import LangGraphCompatibleRunner


class ExternalWorkflowRegistry:
    _GLOBAL_REGISTRY: dict[str, dict[str, Any]] = {
        "selection_workflow": {
            "active_framework": "langgraph-compatible",
            "fallback_framework": "native-python",
            "runtime_mode": "dual-path",
            "diagnostics": {
                "graph_state": True,
                "resume_supported": True,
                "human_intervention_supported": True,
                "single_step_supported": True,
            },
        },
        "prompt_orchestration": {
            "active_framework": "dify-compatible",
            "fallback_framework": "native-python",
            "runtime_mode": "template-routing",
            "diagnostics": {
                "graph_state": False,
                "resume_supported": False,
                "human_intervention_supported": False,
                "template_routing_supported": True,
            },
        },
        "distributed_execution": {
            "active_framework": "ray-compatible",
            "fallback_framework": "native-python",
            "runtime_mode": "actor-parallel",
            "diagnostics": {
                "graph_state": False,
                "resume_supported": False,
                "human_intervention_supported": False,
                "actor_parallel_supported": True,
            },
        },
    }

    def __init__(self) -> None:
        self.langgraph_runner = LangGraphCompatibleRunner()
        self._registry = self.__class__._GLOBAL_REGISTRY

    def build_registry(self) -> dict[str, Any]:
        return {key: dict(value) for key, value in self._registry.items()}

    async def execute_workflow(self, workflow_key: str, *, input_data: dict[str, Any], breakpoints: list[str] | None = None, single_step: bool = False) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_key)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_key}")
        if workflow.get("active_framework") == "langgraph-compatible":
            return await self.langgraph_runner.invoke(input_data=input_data, breakpoints=breakpoints, single_step=single_step)
        return {
            "workflow_key": workflow_key,
            "framework": workflow.get("active_framework"),
            "status": "registered_only",
            "input": input_data,
            "registry_entry": workflow,
        }

    async def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return await self.langgraph_runner.get_snapshot(snapshot_id)

    async def list_snapshots(self, limit: int = 20) -> dict[str, Any]:
        return await self.langgraph_runner.list_snapshots(limit=limit)

    async def step_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return await self.langgraph_runner.step(snapshot_id)

    async def resume_snapshot(self, snapshot_id: str, *, human_input: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.langgraph_runner.resume(snapshot_id, human_input=human_input)

    async def rollback_snapshot(self, snapshot_id: str, *, target_node: str | None = None) -> dict[str, Any]:
        return await self.langgraph_runner.rollback(snapshot_id, target_node=target_node)

    def register_workflow(self, workflow_key: str, definition: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(definition)
        normalized.setdefault("active_framework", "native-python")
        normalized.setdefault("fallback_framework", "native-python")
        normalized.setdefault("runtime_mode", "registered")
        diagnostics = normalized.get("diagnostics") if isinstance(normalized.get("diagnostics"), dict) else {}
        normalized["diagnostics"] = diagnostics
        self._registry[workflow_key] = normalized
        return {"workflow_key": workflow_key, "definition": dict(normalized)}

    def list_workflows(self) -> list[dict[str, Any]]:
        return [{"workflow_key": key, **value} for key, value in self.build_registry().items()]

    def get_workflow(self, workflow_key: str) -> dict[str, Any] | None:
        workflow = self._registry.get(workflow_key)
        return dict(workflow) if workflow is not None else None
