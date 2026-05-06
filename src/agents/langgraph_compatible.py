from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.agents.commercial import CommercialAgent
from src.agents.data_collection import DataCollectionAgent
from src.agents.market_insight import MarketInsightAgent
from src.agents.product_planner import ProductPlannerAgent
from src.agents.report_generator import ReportGeneratorAgent
from src.agents.risk_assessor import RiskAssessorAgent
from src.agents.selection_master import SelectionMaster, SelectionPhase, SelectionState, SelectionStatus
from src.core.metrics import AGENT_ACTIVE_WORKFLOWS, AGENT_COST_USD_TOTAL, AGENT_TOKENS_TOTAL
from src.core.security import add_audit_log
from src.infrastructure.tracing import bind_trace_tags, get_request_id, get_trace_id, trace_snapshot
from src.services.local_knowledge_service import LocalKnowledgeService


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class GraphSnapshot:
    snapshot_id: str
    workflow_key: str
    framework: str
    current_node: str
    next_node: str | None
    state: dict[str, Any] = field(default_factory=dict)
    breakpoints: list[str] = field(default_factory=list)
    waiting_human_input: bool = False
    status: str = "running"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "workflow_key": self.workflow_key,
            "framework": self.framework,
            "current_node": self.current_node,
            "next_node": self.next_node,
            "state": self.state,
            "breakpoints": self.breakpoints,
            "waiting_human_input": self.waiting_human_input,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class LangGraphCompatibleRunner:
    DEFAULT_BREAKPOINTS = {"commercial_evaluation", "risk_assessment"}
    NODE_SEQUENCE = [
        "data_collection",
        "market_analysis",
        "product_planning",
        "commercial_evaluation",
        "risk_assessment",
        "report_generation",
    ]
    PARALLEL_NODES: list[str] = []
    SEQUENTIAL_NODES = list(NODE_SEQUENCE)
    MARKET_OPPORTUNITY_ABORT_THRESHOLD = 30.0
    PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD = 35.0
    MAX_PRODUCT_PLANNING_REVISIONS = 2
    SNAPSHOT_STORE: dict[str, GraphSnapshot] = {}
    COST_STORE: dict[str, dict[str, Any]] = {}

    def __init__(self) -> None:
        self._snapshots = self.__class__.SNAPSHOT_STORE
        self._node_agents = {
            "data_collection": DataCollectionAgent,
            "market_analysis": MarketInsightAgent,
            "product_planning": ProductPlannerAgent,
            "commercial_evaluation": CommercialAgent,
            "risk_assessment": RiskAssessorAgent,
            "report_generation": ReportGeneratorAgent,
        }

    @staticmethod
    def _agent_output(agent_result: dict[str, Any]) -> dict[str, Any]:
        output = agent_result.get("output") if isinstance(agent_result, dict) else None
        if isinstance(output, dict):
            data = output.get("data")
            return data if isinstance(data, dict) else output
        data = agent_result.get("data") if isinstance(agent_result, dict) else None
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _estimate_agent_usage(node: str, payload: dict[str, Any]) -> dict[str, Any]:
        seed = " ".join(str(payload.get(key) or "") for key in ["query", "category", "target_market", "priority"])
        tokens = max(32, len(seed) * 2 + len(node) * 5)
        cost = round(tokens / 1000 * 0.0012, 6)
        return {"agent": node, "tokens_used": tokens, "cost_usd": cost}

    def _update_cost_store(self, *, node: str, payload: dict[str, Any], snapshot: GraphSnapshot) -> dict[str, Any]:
        usage = self._estimate_agent_usage(node, payload)
        tenant_id = str((snapshot.state.get("input") or {}).get("tenant_id") or "unknown-tenant")
        usage["tenant_id"] = tenant_id
        usage["trace_id"] = get_trace_id()
        usage["request_id"] = get_request_id()
        AGENT_TOKENS_TOTAL.labels(agent=node, tenant_id=tenant_id).inc(int(usage["tokens_used"]))
        AGENT_COST_USD_TOTAL.labels(agent=node, tenant_id=tenant_id).inc(float(usage["cost_usd"]))
        cost_entry = self.COST_STORE.setdefault(
            snapshot.snapshot_id,
            {"tenant_id": tenant_id, "agents": {}, "totals": {"tokens_used": 0, "cost_usd": 0.0}},
        )
        cost_entry["agents"][node] = usage
        cost_entry["totals"]["tokens_used"] += int(usage["tokens_used"])
        cost_entry["totals"]["cost_usd"] = round(
            float(cost_entry["totals"]["cost_usd"]) + float(usage["cost_usd"]),
            6,
        )
        return usage

    def _build_cost_summary(self, snapshot_id: str) -> dict[str, Any]:
        cost_entry = self.COST_STORE.get(snapshot_id) or {
            "tenant_id": "unknown-tenant",
            "agents": {},
            "totals": {"tokens_used": 0, "cost_usd": 0.0},
        }
        agents = list((cost_entry.get("agents") or {}).values())
        return {
            "tenant_id": cost_entry.get("tenant_id"),
            "agent_count": len(agents),
            "agents": agents,
            "totals": cost_entry.get("totals") or {"tokens_used": 0, "cost_usd": 0.0},
            "updated_at": _now_iso(),
        }

    @staticmethod
    def _empty_knowledge_result(query: str, case_type: str) -> dict[str, Any]:
        return {
            "query": query,
            "case_type": case_type,
            "total_found": 0,
            "processing_time_ms": 0.0,
            "results": [],
        }

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace("%", "").replace("$", "").replace(",", "")
            try:
                return float(normalized)
            except ValueError:
                return None
        return None

    @classmethod
    def _extract_nested_float(cls, payload: dict[str, Any], *paths: tuple[str, ...]) -> float | None:
        for path in paths:
            current: Any = payload
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            score = cls._coerce_float(current)
            if score is not None:
                return score
        return None

    @classmethod
    def _extract_opportunity_score(cls, market_output: dict[str, Any]) -> float | None:
        if not isinstance(market_output, dict):
            return None
        return cls._extract_nested_float(
            market_output,
            ("opportunity_score", "overall"),
            ("opportunity_score", "overall_score"),
            ("opportunity_score",),
            ("opportunity_score_value",),
        )

    @classmethod
    def _extract_differentiation_score(cls, product_output: dict[str, Any]) -> float | None:
        if not isinstance(product_output, dict):
            return None
        return cls._extract_nested_float(
            product_output,
            ("differentiation", "overall"),
            ("differentiation", "overall_score"),
            ("differentiation_score",),
        )

    @classmethod
    def _summarize_case_hits(cls, result: dict[str, Any], *, case_type: str, limit: int = 3) -> list[dict[str, Any]]:
        items = list(result.get("results") or [])
        summarized: list[dict[str, Any]] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            summarized.append(
                {
                    "case_type": case_type,
                    "source": item.get("source") or metadata.get("source") or metadata.get("filename"),
                    "score": cls._coerce_float(item.get("score")),
                    "snippet": str(item.get("content") or "")[:180],
                    "citation": item.get("citation"),
                }
            )
        return summarized

    async def _load_historical_context(self, query: str) -> dict[str, Any]:
        empty_history = self._empty_knowledge_result(query, "selection_history_case")
        empty_reviews = self._empty_knowledge_result(query, "crm_review_case")
        empty_performance = {
            "query": query,
            "case_type": "historical_performance",
            "total_found": 0,
            "results": [],
        }
        if not query:
            return {
                "similar_history_cases": empty_history,
                "review_cases": empty_reviews,
                "historical_performance": empty_performance,
                "preloaded_case_evidence": [],
            }

        try:
            service = LocalKnowledgeService()
        except Exception as exc:
            return {
                "similar_history_cases": {**empty_history, "error": str(exc)},
                "review_cases": {**empty_reviews, "error": str(exc)},
                "historical_performance": empty_performance,
                "preloaded_case_evidence": [],
            }

        try:
            similar_history_cases = await service.query_selection_cases(query=query, top_k=3, threshold=0.1)
        except ValueError:
            similar_history_cases = empty_history
        except Exception as exc:
            similar_history_cases = {**empty_history, "error": str(exc)}

        review_query = f"{query} 评价 投诉 差评 好评"
        try:
            review_cases = await service.query_review_cases(query=review_query, top_k=3, threshold=0.1)
        except ValueError:
            review_cases = {**empty_reviews, "query": review_query}
        except Exception as exc:
            review_cases = {**empty_reviews, "query": review_query, "error": str(exc)}

        return {
            "similar_history_cases": similar_history_cases,
            "review_cases": review_cases,
            "historical_performance": empty_performance,
            "preloaded_case_evidence": self._summarize_case_hits(
                similar_history_cases,
                case_type="selection_history_case",
            )
            + self._summarize_case_hits(review_cases, case_type="crm_review_case"),
        }

    @staticmethod
    def _build_workflow_payload(input_data: dict[str, Any], selection_state: SelectionState) -> dict[str, Any]:
        payload = dict(input_data)
        payload.update(
            {
                "session_id": selection_state.session_id,
                "query": selection_state.query,
                "category": selection_state.category,
                "target_market": selection_state.target_market,
                "budget_range": selection_state.budget_range,
                "investment_budget": selection_state.investment_budget,
                "priority": selection_state.priority,
                "auto_approve": selection_state.auto_approve,
            }
        )
        return payload

    def _build_agent_payload(
        self,
        *,
        node: str,
        base_payload: dict[str, Any],
        historical_context: dict[str, Any],
        upstream_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        payload = dict(base_payload)
        payload["historical_context"] = historical_context
        payload["similar_history_cases"] = historical_context.get("similar_history_cases")
        payload["review_cases"] = historical_context.get("review_cases")
        payload["preloaded_case_evidence"] = list(historical_context.get("preloaded_case_evidence") or [])
        payload["workflow_context"] = {
            "framework": "langgraph-compatible",
            "historical_context_loaded": bool(payload["preloaded_case_evidence"]),
            "upstream_nodes": [name for name, result in upstream_results.items() if result],
        }
        for name, result in upstream_results.items():
            payload[f"{name}_result"] = result

        if node == "report_generation":
            payload["agent_results"] = {
                "data_collection": upstream_results.get("data_collection") or {},
                "market_insight": upstream_results.get("market_analysis") or {},
                "product_planning": upstream_results.get("product_planning") or {},
                "commercial": upstream_results.get("commercial_evaluation") or {},
                "risk_assessment": upstream_results.get("risk_assessment") or {},
            }
            payload["format"] = base_payload.get("report_format", "json")
        return payload

    async def _invoke_agent(
        self,
        *,
        node: str,
        snapshot_id: str,
        tenant_id: Any,
        payload: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bind_trace_tags(current_agent=node, workflow_snapshot_id=snapshot_id)
        add_audit_log(
            action="agent.workflow.node.start",
            actor={"username": "selection_master", "tenant_id": tenant_id},
            target_type="agent_node",
            target_id=node,
            result="running",
            detail={
                "snapshot_id": snapshot_id,
                "trace": trace_snapshot(),
                "input": {
                    "query": payload.get("query"),
                    "category": payload.get("category"),
                    "target_market": payload.get("target_market"),
                },
            },
        )

        if node == "commercial_evaluation":
            if state is not None:
                master = SelectionMaster({"force_legacy": True})
                state.setdefault("selection_master_summary", master.build_langgraph_compatible_summary())
            agent = CommercialAgent(config={"commercial_rules": payload.get("commercial_rules")})
        else:
            agent = self._node_agents[node]()

        result = await agent.run(payload)
        data = result.to_dict()
        add_audit_log(
            "agent.workflow.node.complete",
            actor={"username": "selection_master", "tenant_id": tenant_id},
            target_type="agent_node",
            target_id=node,
            result="success",
            detail={
                "snapshot_id": snapshot_id,
                "trace": trace_snapshot(),
                "output_keys": sorted(data.keys()),
            },
        )
        return data

    def _build_final_response(
        self,
        *,
        snapshot: GraphSnapshot,
        selection_state: SelectionState,
        master: SelectionMaster,
        execution_log: list[dict[str, Any]],
        historical_context: dict[str, Any],
        last_node: str,
        risk_output: dict[str, Any] | None = None,
        report_output: dict[str, Any] | None = None,
        status_reason: str | None = None,
    ) -> dict[str, Any]:
        risk_payload = risk_output or {}
        report_payload = report_output or {}
        decision_output = master._build_decision_output(selection_state, execution_log)
        go_no_go = selection_state.commercial_evaluation_result.get("go_no_go", "PENDING")
        go_no_go_decision = go_no_go.get("decision") if isinstance(go_no_go, dict) else str(go_no_go)

        cost_summary = self._build_cost_summary(snapshot.snapshot_id)
        final_output = {
            "session_id": selection_state.session_id,
            "status": selection_state.status.value,
            "final_phase": selection_state.current_phase.value,
            "execution_log": execution_log,
            "results": {
                "data_collection": selection_state.data_collection_result,
                "market_analysis": selection_state.market_analysis_result,
                "product_planning": selection_state.product_planning_result,
                "commercial_evaluation": selection_state.commercial_evaluation_result,
                "risk_assessment": risk_payload,
                "report_generation": report_payload,
            },
            "historical_context": historical_context,
            "state_summary": {
                **selection_state.to_dict(),
                "product_revision_count": int(selection_state.metadata.get("product_revision_count") or 0),
                "business_warning_count": len(list(selection_state.metadata.get("business_warnings") or [])),
            },
            "retry_count": selection_state.retry_count,
            "error_count": len(selection_state.error_log),
            "generated_at": _now_iso(),
            "decision_output": decision_output,
            "go_no_go": go_no_go,
            "go_no_go_decision": go_no_go_decision,
            "framework": "langgraph-compatible",
            "agent_cost_summary": cost_summary,
            "trace": trace_snapshot(),
            "langgraph_execution": {
                "orchestrator": "LangGraphCompatibleRunner",
                "graph_type": "StateGraph",
                "parallel_nodes": list(self.PARALLEL_NODES),
                "sequential_nodes": list(self.SEQUENTIAL_NODES),
                "conditional_nodes": ["market_analysis", "product_planning"],
                "decision_gates": {
                    "market_opportunity_abort_threshold": self.MARKET_OPPORTUNITY_ABORT_THRESHOLD,
                    "product_differentiation_revise_threshold": self.PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD,
                    "max_product_planning_revisions": self.MAX_PRODUCT_PLANNING_REVISIONS,
                },
                "historical_context_loaded": bool(historical_context.get("preloaded_case_evidence")),
                "preloaded_case_evidence_count": len(list(historical_context.get("preloaded_case_evidence") or [])),
                "risk_assessor_integrated": bool(risk_payload),
                "report_generator_integrated": bool(report_payload),
                "token_cost_tracking": cost_summary,
                "trace_id": get_trace_id(),
            },
            "report": report_payload,
        }
        if status_reason:
            final_output["status_reason"] = status_reason
        final_output["summary"] = master._generate_summary(final_output, selection_state)

        snapshot.status = "completed"
        snapshot.current_node = last_node
        snapshot.next_node = None
        snapshot.waiting_human_input = False
        snapshot.state["historical_context"] = historical_context
        snapshot.state["business_status"] = selection_state.status.value
        snapshot.state["final_output"] = final_output
        snapshot.updated_at = _now_iso()
        with suppress(ValueError):
            AGENT_ACTIVE_WORKFLOWS.labels(framework="langgraph-compatible").dec()

        return {
            "snapshot": snapshot.to_dict(),
            "status": snapshot.status,
            "results": snapshot.state.get("results", {}),
            "decision_output": final_output.get("decision_output"),
            "report": final_output.get("report"),
            "agent_cost_summary": cost_summary,
            "trace": trace_snapshot(),
            "selection_master_output": final_output,
        }

    def build_state_graph(self) -> dict[str, Any]:
        return {
            "framework": "langgraph-compatible",
            "workflow_key": "selection_workflow",
            "graph_type": "StateGraph",
            "entry_point": "data_collection",
            "nodes": [
                {
                    "id": node,
                    "agent": node,
                    "type": "report" if node == "report_generation" else "agent",
                    "checkpoint": node in self.DEFAULT_BREAKPOINTS,
                    "execution_mode": "conditional" if node in {"market_analysis", "product_planning"} else "sequential",
                }
                for node in self.NODE_SEQUENCE
            ],
            "edges": [
                {"from": "data_collection", "to": "market_analysis", "condition": "success"},
                {
                    "from": "market_analysis",
                    "to": "product_planning",
                    "condition": f"opportunity_score >= {self.MARKET_OPPORTUNITY_ABORT_THRESHOLD}",
                },
                {
                    "from": "market_analysis",
                    "to": "completed",
                    "condition": f"opportunity_score < {self.MARKET_OPPORTUNITY_ABORT_THRESHOLD}",
                },
                {
                    "from": "product_planning",
                    "to": "product_planning",
                    "condition": (
                        "differentiation_score < "
                        f"{self.PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD} and revision_count < {self.MAX_PRODUCT_PLANNING_REVISIONS}"
                    ),
                },
                {
                    "from": "product_planning",
                    "to": "commercial_evaluation",
                    "condition": f"differentiation_score >= {self.PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD}",
                },
                {
                    "from": "product_planning",
                    "to": "completed",
                    "condition": (
                        "differentiation_score < "
                        f"{self.PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD} and revision_count >= {self.MAX_PRODUCT_PLANNING_REVISIONS}"
                    ),
                },
                {"from": "commercial_evaluation", "to": "risk_assessment", "condition": "success"},
                {"from": "risk_assessment", "to": "report_generation", "condition": "success"},
            ],
            "supports": ["snapshot", "resume", "single-step", "breakpoint", "human-in-the-loop", "conditional-branching"],
        }

    async def invoke(self, *, input_data: dict[str, Any], breakpoints: list[str] | None = None, single_step: bool = False) -> dict[str, Any]:
        snapshot = GraphSnapshot(
            snapshot_id=f"lgg-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            workflow_key="selection_workflow",
            framework="langgraph-compatible",
            current_node="data_collection",
            next_node=self.NODE_SEQUENCE[0],
            breakpoints=list(dict.fromkeys((breakpoints or []) + list(self.DEFAULT_BREAKPOINTS))),
            state={
                "input": input_data,
                "results": {},
                "execution_log": [],
                "selection_master_summary": None,
            },
        )
        snapshot.state["snapshot_id"] = snapshot.snapshot_id
        self._snapshots[snapshot.snapshot_id] = snapshot
        AGENT_ACTIVE_WORKFLOWS.labels(framework="langgraph-compatible").inc()
        bind_trace_tags(workflow_snapshot_id=snapshot.snapshot_id, workflow_key=snapshot.workflow_key)
        self.COST_STORE[snapshot.snapshot_id] = {
            "tenant_id": str((input_data or {}).get("tenant_id") or "unknown-tenant"),
            "agents": {},
            "totals": {"tokens_used": 0, "cost_usd": 0.0},
        }
        if not single_step and not breakpoints:
            result = await self._run_compiled_workflow(snapshot.snapshot_id)
        else:
            result = await self._run_from_snapshot(snapshot.snapshot_id, human_input=None, single_step=single_step)
        result["graph"] = self.build_state_graph()
        return result

    async def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        snapshot = self._snapshots.get(snapshot_id)
        return snapshot.to_dict() if snapshot is not None else None

    async def list_snapshots(self, limit: int = 20) -> dict[str, Any]:
        items = sorted(self._snapshots.values(), key=lambda item: item.updated_at, reverse=True)[:limit]
        return {"total": len(items), "items": [item.to_dict() for item in items]}

    async def step(self, snapshot_id: str) -> dict[str, Any]:
        return await self._run_from_snapshot(snapshot_id, human_input=None, single_step=True)

    async def resume(self, snapshot_id: str, *, human_input: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._run_from_snapshot(snapshot_id, human_input=human_input, single_step=False)

    async def pause(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"快照不存在: {snapshot_id}")
        if snapshot.status not in ("running", "waiting_human_input"):
            raise ValueError(f"仅运行中的工作流可暂停，当前状态: {snapshot.status}")
        snapshot.status = "paused"
        snapshot.waiting_human_input = True
        snapshot.updated_at = _now_iso()
        add_audit_log(
            "agent.platform.workflow.pause",
            actor={
                "username": "selection_master",
                "tenant_id": (snapshot.state.get("input") or {}).get("tenant_id"),
            },
            target_type="agent_workflow_snapshot",
            target_id=snapshot.snapshot_id,
            result="success",
            detail={"current_node": snapshot.current_node},
        )
        return {
            "snapshot": snapshot.to_dict(),
            "status": "paused",
            "paused": True,
            "current_node": snapshot.current_node,
        }

    async def rollback(self, snapshot_id: str, *, target_node: str | None = None) -> dict[str, Any]:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"快照不存在: {snapshot_id}")

        execution_log = list(snapshot.state.get("execution_log") or [])
        results = dict(snapshot.state.get("results") or {})
        target = target_node or snapshot.current_node or self.NODE_SEQUENCE[0]
        if target not in self.NODE_SEQUENCE:
            raise ValueError(f"不支持的回滚节点: {target}")

        rollback_index = self.NODE_SEQUENCE.index(target)
        kept_nodes = set(self.NODE_SEQUENCE[:rollback_index])
        removed_nodes = [
            node
            for node in self.NODE_SEQUENCE[rollback_index:]
            if node in results or any(str(item.get("node")) == node for item in execution_log)
        ]

        snapshot.state["results"] = {key: value for key, value in results.items() if key in kept_nodes}
        snapshot.state["execution_log"] = [
            item for item in execution_log if str(item.get("node")) in kept_nodes
        ]
        snapshot.state.pop("final_output", None)
        snapshot.waiting_human_input = False
        snapshot.status = "rolled_back"
        snapshot.current_node = target
        snapshot.next_node = target
        snapshot.updated_at = _now_iso()
        snapshot.state.setdefault("rollback_history", []).append(
            {
                "rolled_back_at": snapshot.updated_at,
                "target_node": target,
                "removed_nodes": removed_nodes,
                "trace_id": get_trace_id(),
                "request_id": get_request_id(),
            }
        )

        cost_entry = self.COST_STORE.get(snapshot.snapshot_id)
        if cost_entry is not None:
            agents = dict(cost_entry.get("agents") or {})
            cost_entry["agents"] = {key: value for key, value in agents.items() if key in kept_nodes}
            total_tokens = sum(
                int((value or {}).get("tokens_used") or 0)
                for value in cost_entry["agents"].values()
            )
            total_cost = round(
                sum(float((value or {}).get("cost_usd") or 0.0) for value in cost_entry["agents"].values()),
                6,
            )
            cost_entry["totals"] = {"tokens_used": total_tokens, "cost_usd": total_cost}

        add_audit_log(
            "agent.platform.workflow.rollback",
            actor={
                "username": "selection_master",
                "tenant_id": (snapshot.state.get("input") or {}).get("tenant_id"),
            },
            target_type="agent_workflow_snapshot",
            target_id=snapshot.snapshot_id,
            result="success",
            detail={
                "target_node": target,
                "removed_nodes": removed_nodes,
                "trace": trace_snapshot(),
            },
        )
        return {
            "snapshot": snapshot.to_dict(),
            "status": snapshot.status,
            "rolled_back": True,
            "target_node": target,
            "removed_nodes": removed_nodes,
            "agent_cost_summary": self._build_cost_summary(snapshot.snapshot_id),
            "trace": trace_snapshot(),
        }

    async def _run_from_snapshot(
        self,
        snapshot_id: str,
        *,
        human_input: dict[str, Any] | None,
        single_step: bool,
    ) -> dict[str, Any]:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"快照不存在: {snapshot_id}")

        if snapshot.status == "paused":
            snapshot.status = "running"
            snapshot.waiting_human_input = False
            snapshot.updated_at = _now_iso()

        if human_input:
            snapshot.waiting_human_input = False
            snapshot.state.setdefault("human_inputs", []).append({**human_input, "received_at": _now_iso()})
            snapshot.state["human_decision"] = human_input
            if human_input.get("action") == "terminate":
                snapshot.status = "terminated"
                snapshot.updated_at = _now_iso()
                return {"snapshot": snapshot.to_dict(), "status": snapshot.status, "terminated": True}

        start_node = snapshot.next_node or self.NODE_SEQUENCE[0]
        start_index = self.NODE_SEQUENCE.index(start_node) if start_node in self.NODE_SEQUENCE else 0
        for idx in range(start_index, len(self.NODE_SEQUENCE)):
            node = self.NODE_SEQUENCE[idx]
            snapshot.current_node = node
            snapshot.next_node = node
            snapshot.updated_at = _now_iso()

            if idx > start_index and node in snapshot.breakpoints:
                snapshot.waiting_human_input = True
                snapshot.status = "waiting_human_input"
                snapshot.next_node = node
                snapshot.updated_at = _now_iso()
                return {
                    "snapshot": snapshot.to_dict(),
                    "status": snapshot.status,
                    "breakpoint_hit": node,
                    "results": snapshot.state.get("results", {}),
                }

            node_result = await self._execute_node(node=node, state=snapshot.state)
            usage = self._update_cost_store(
                node=node,
                payload=dict(snapshot.state.get("input") or {}),
                snapshot=snapshot,
            )
            snapshot.state.setdefault("results", {})[node] = node_result
            snapshot.state.setdefault("execution_log", []).append(
                {
                    "node": node,
                    "completed_at": _now_iso(),
                    "success": True,
                    "tokens_used": usage["tokens_used"],
                    "cost_usd": usage["cost_usd"],
                    "trace_id": usage["trace_id"],
                }
            )
            next_node = self.NODE_SEQUENCE[idx + 1] if idx + 1 < len(self.NODE_SEQUENCE) else None
            snapshot.next_node = next_node
            snapshot.status = "running" if next_node else "completed"
            snapshot.updated_at = _now_iso()

            if single_step:
                return {
                    "snapshot": snapshot.to_dict(),
                    "status": snapshot.status,
                    "single_step": True,
                    "executed_node": node,
                    "result": node_result,
                }

        snapshot.waiting_human_input = False
        snapshot.status = "completed"
        snapshot.updated_at = _now_iso()
        with suppress(ValueError):
            AGENT_ACTIVE_WORKFLOWS.labels(framework="langgraph-compatible").dec()
        return {
            "snapshot": snapshot.to_dict(),
            "status": snapshot.status,
            "results": snapshot.state.get("results", {}),
            "decision_output": self._agent_output(
                snapshot.state.get("results", {}).get("commercial_evaluation") or {}
            ).get("decision_output"),
            "report": self._agent_output(snapshot.state.get("results", {}).get("report_generation") or {}),
            "agent_cost_summary": self._build_cost_summary(snapshot.snapshot_id),
            "trace": trace_snapshot(),
        }

    async def _execute_node(self, *, node: str, state: dict[str, Any]) -> dict[str, Any]:
        input_data = dict(state.get("input") or {})
        results = state.get("results") or {}
        snapshot_id = str(state.get("snapshot_id") or input_data.get("session_id") or "workflow")
        historical_context = (
            state.get("historical_context")
            if isinstance(state.get("historical_context"), dict)
            else None
        )
        if historical_context is None:
            historical_context = await self._load_historical_context(str(input_data.get("query") or ""))
            state["historical_context"] = historical_context
        upstream_results = {
            "data_collection": self._agent_output(results.get("data_collection") or {}),
            "market_analysis": self._agent_output(results.get("market_analysis") or {}),
            "product_planning": self._agent_output(results.get("product_planning") or {}),
            "commercial_evaluation": self._agent_output(results.get("commercial_evaluation") or {}),
            "risk_assessment": self._agent_output(results.get("risk_assessment") or {}),
        }
        payload = self._build_agent_payload(
            node=node,
            base_payload=input_data,
            historical_context=historical_context,
            upstream_results=upstream_results,
        )
        return await self._invoke_agent(
            node=node,
            snapshot_id=snapshot_id,
            tenant_id=input_data.get("tenant_id"),
            payload=payload,
            state=state,
        )

    async def _run_compiled_workflow(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"快照不存在: {snapshot_id}")

        input_data = dict(snapshot.state.get("input") or {})
        session_id = input_data.get("session_id") or snapshot.snapshot_id
        selection_state = SelectionState(
            session_id=session_id,
            query=input_data.get("query", ""),
            category=input_data.get("category", ""),
            target_market=input_data.get("target_market", "US"),
            budget_range=input_data.get("budget_range", [10.0, 100.0]),
            investment_budget=float(input_data.get("investment_budget") or 50000.0),
            priority=str(input_data.get("priority") or "normal"),
            auto_approve=bool(input_data.get("auto_approve", False)),
            max_retries=SelectionMaster.MAX_RETRIES,
        )
        master = SelectionMaster({"force_legacy": True})
        snapshot.state["selection_master_summary"] = master.build_langgraph_compatible_summary()

        base_payload = self._build_workflow_payload(input_data, selection_state)
        historical_context = await self._load_historical_context(selection_state.query)
        selection_state.metadata["historical_context"] = historical_context
        snapshot.state["historical_context"] = historical_context

        execution_log: list[dict[str, Any]] = []
        risk_output: dict[str, Any] = {}
        report_output: dict[str, Any] = {}
        empty_result: dict[str, Any] = {}

        async def run_node(node: str, mode: str, upstream_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
            snapshot.current_node = node
            snapshot.next_node = node
            snapshot.updated_at = _now_iso()
            payload = self._build_agent_payload(
                node=node,
                base_payload=base_payload,
                historical_context=historical_context,
                upstream_results=upstream_results,
            )
            data = await self._invoke_agent(
                node=node,
                snapshot_id=snapshot.snapshot_id,
                tenant_id=payload.get("tenant_id"),
                payload=payload,
                state=snapshot.state,
            )
            usage = self._update_cost_store(node=node, payload=payload, snapshot=snapshot)
            snapshot.state.setdefault("results", {})[node] = data
            snapshot.state.setdefault("execution_log", []).append(
                {
                    "node": node,
                    "completed_at": _now_iso(),
                    "success": bool(data.get("success", True)),
                    "mode": mode,
                    "tokens_used": usage["tokens_used"],
                    "cost_usd": usage["cost_usd"],
                    "trace_id": usage["trace_id"],
                }
            )
            return data

        data_collection_result = await run_node(
            "data_collection",
            "sequential",
            {
                "data_collection": empty_result,
                "market_analysis": empty_result,
                "product_planning": empty_result,
                "commercial_evaluation": empty_result,
                "risk_assessment": empty_result,
            },
        )
        selection_state.current_phase = SelectionPhase.DATA_COLLECTION
        selection_state.data_collection_result = self._agent_output(data_collection_result)
        execution_log.append(
            {
                "phase": "data_collection",
                "success": True,
                "status": SelectionStatus.PROCEED.value,
                "mode": "sequential",
                "action": "transition_to_market_analysis",
            }
        )

        market_analysis_result = await run_node(
            "market_analysis",
            "conditional",
            {
                "data_collection": selection_state.data_collection_result,
                "market_analysis": empty_result,
                "product_planning": empty_result,
                "commercial_evaluation": empty_result,
                "risk_assessment": empty_result,
            },
        )
        selection_state.current_phase = SelectionPhase.MARKET_ANALYSIS
        selection_state.market_analysis_result = self._agent_output(market_analysis_result)
        opportunity_score = self._extract_opportunity_score(selection_state.market_analysis_result)
        if (
            opportunity_score is not None
            and opportunity_score < self.MARKET_OPPORTUNITY_ABORT_THRESHOLD
        ):
            status_reason = f"market opportunity score below threshold ({opportunity_score})"
            selection_state.status = SelectionStatus.ABORT_MARKET
            selection_state.metadata.setdefault("business_warnings", []).append(
                {
                    "phase": "market_analysis",
                    "message": status_reason,
                    "score": opportunity_score,
                }
            )
            execution_log.append(
                {
                    "phase": "market_analysis",
                    "success": True,
                    "status": SelectionStatus.ABORT_MARKET.value,
                    "mode": "conditional",
                    "action": "terminate",
                    "opportunity_score": opportunity_score,
                }
            )
            return self._build_final_response(
                snapshot=snapshot,
                selection_state=selection_state,
                master=master,
                execution_log=execution_log,
                historical_context=historical_context,
                last_node="market_analysis",
                risk_output=risk_output,
                report_output=report_output,
                status_reason=status_reason,
            )

        execution_log.append(
            {
                "phase": "market_analysis",
                "success": True,
                "status": SelectionStatus.PROCEED.value,
                "mode": "conditional",
                "action": "transition_to_product_planning",
                "opportunity_score": opportunity_score,
            }
        )

        product_revision_count = 0
        while True:
            product_planning_result = await run_node(
                "product_planning",
                "conditional",
                {
                    "data_collection": selection_state.data_collection_result,
                    "market_analysis": selection_state.market_analysis_result,
                    "product_planning": selection_state.product_planning_result,
                    "commercial_evaluation": empty_result,
                    "risk_assessment": empty_result,
                },
            )
            selection_state.current_phase = SelectionPhase.PRODUCT_PLANNING
            selection_state.product_planning_result = self._agent_output(product_planning_result)
            differentiation_score = self._extract_differentiation_score(selection_state.product_planning_result)
            if (
                differentiation_score is None
                or differentiation_score >= self.PRODUCT_DIFFERENTIATION_REVISE_THRESHOLD
            ):
                execution_log.append(
                    {
                        "phase": "product_planning",
                        "success": True,
                        "status": SelectionStatus.PROCEED.value,
                        "mode": "conditional",
                        "action": "transition_to_commercial_evaluation",
                        "differentiation_score": differentiation_score,
                        "revision_count": product_revision_count,
                    }
                )
                break

            product_revision_count += 1
            selection_state.metadata["product_revision_count"] = product_revision_count
            if product_revision_count >= self.MAX_PRODUCT_PLANNING_REVISIONS:
                status_reason = (
                    "product differentiation stayed below threshold "
                    f"after {product_revision_count} revisions ({differentiation_score})"
                )
                selection_state.status = SelectionStatus.TERMINATE
                selection_state.metadata.setdefault("business_warnings", []).append(
                    {
                        "phase": "product_planning",
                        "message": status_reason,
                        "score": differentiation_score,
                        "revision_count": product_revision_count,
                    }
                )
                execution_log.append(
                    {
                        "phase": "product_planning",
                        "success": True,
                        "status": SelectionStatus.TERMINATE.value,
                        "mode": "conditional",
                        "action": "terminate_max_product_revisions",
                        "differentiation_score": differentiation_score,
                        "revision_count": product_revision_count,
                    }
                )
                return self._build_final_response(
                    snapshot=snapshot,
                    selection_state=selection_state,
                    master=master,
                    execution_log=execution_log,
                    historical_context=historical_context,
                    last_node="product_planning",
                    risk_output=risk_output,
                    report_output=report_output,
                    status_reason=status_reason,
                )

            execution_log.append(
                {
                    "phase": "product_planning",
                    "success": True,
                    "status": SelectionStatus.REVISE_PRODUCT.value,
                    "mode": "conditional",
                    "action": f"revise_attempt_{product_revision_count}",
                    "differentiation_score": differentiation_score,
                    "revision_count": product_revision_count,
                }
            )

        commercial_result = await run_node(
            "commercial_evaluation",
            "sequential",
            {
                "data_collection": selection_state.data_collection_result,
                "market_analysis": selection_state.market_analysis_result,
                "product_planning": selection_state.product_planning_result,
                "commercial_evaluation": empty_result,
                "risk_assessment": empty_result,
            },
        )
        selection_state.current_phase = SelectionPhase.COMMERCIAL_EVALUATION
        selection_state.commercial_evaluation_result = self._agent_output(commercial_result)
        execution_log.append(
            {
                "phase": "commercial_evaluation",
                "success": True,
                "status": SelectionStatus.PROCEED.value,
                "mode": "sequential",
                "action": "transition_to_risk_assessment",
            }
        )

        risk_result = await run_node(
            "risk_assessment",
            "sequential",
            {
                "data_collection": selection_state.data_collection_result,
                "market_analysis": selection_state.market_analysis_result,
                "product_planning": selection_state.product_planning_result,
                "commercial_evaluation": selection_state.commercial_evaluation_result,
                "risk_assessment": empty_result,
            },
        )
        risk_output = self._agent_output(risk_result)
        execution_log.append(
            {
                "phase": "risk_assessment",
                "success": True,
                "status": SelectionStatus.PROCEED.value,
                "mode": "sequential",
                "action": "transition_to_report_generation",
            }
        )

        report_result = await run_node(
            "report_generation",
            "sequential",
            {
                "data_collection": selection_state.data_collection_result,
                "market_analysis": selection_state.market_analysis_result,
                "product_planning": selection_state.product_planning_result,
                "commercial_evaluation": selection_state.commercial_evaluation_result,
                "risk_assessment": risk_output,
            },
        )
        report_output = self._agent_output(report_result)
        execution_log.append(
            {
                "phase": "report_generation",
                "success": True,
                "status": SelectionStatus.PROCEED.value,
                "mode": "sequential",
                "action": "complete",
            }
        )

        selection_state.current_phase = SelectionPhase.COMPLETED
        selection_state.status = SelectionStatus.PROCEED
        return self._build_final_response(
            snapshot=snapshot,
            selection_state=selection_state,
            master=master,
            execution_log=execution_log,
            historical_context=historical_context,
            last_node="report_generation",
            risk_output=risk_output,
            report_output=report_output,
        )
