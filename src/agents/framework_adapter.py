from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable
from typing import Any

from src.agents.data_collection import DataCollectionAgent


class AgentFrameworkAdapterRegistry:
    FRAMEWORK_PACKAGE_MAP = {
        "langgraph-compatible": "langgraph",
        "autogen-compatible": "autogen",
        "langchain-compatible": "langchain",
        "crewai-compatible": "crewai",
        "ray-compatible": "ray",
        "dify-compatible": None,
        "native-python": None,
    }

    def __init__(self) -> None:
        self._invokers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}

    def _resolve_runtime_status(self, framework_key: str, default_status: str) -> dict[str, Any]:
        package_name = self.FRAMEWORK_PACKAGE_MAP.get(framework_key)
        package_installed = True if package_name is None else importlib.util.find_spec(package_name) is not None
        compatible_runtime = framework_key in {"native-python", "langgraph-compatible", "autogen-compatible", "langchain-compatible", "crewai-compatible", "ray-compatible", "dify-compatible"}
        runtime_status = "active" if framework_key == "native-python" else "installed"
        if not package_installed and package_name is not None:
            runtime_status = "fallback"
        elif compatible_runtime and framework_key == "langgraph-compatible":
            runtime_status = "active" if package_installed else "fallback"
        sdk_backed = bool(package_installed and package_name)
        return {
            "runtime_status": runtime_status,
            "package_name": package_name,
            "package_installed": package_installed,
            "sdk_backed": sdk_backed,
            "compatible_runtime": compatible_runtime,
            "execution_mode": "sdk-backed" if sdk_backed else "application-compatible",
            "diagnostics": {
                "detection_method": "importlib.util.find_spec",
                "import_ready": package_installed,
                "fallback_reason": None if package_installed or package_name is None else f"package '{package_name}' not installed",
                "default_status": default_status,
            },
        }

    @staticmethod
    def _signal_strength(count: int, *, high_threshold: int = 5, medium_threshold: int = 1) -> str:
        if count >= high_threshold:
            return "high"
        if count >= medium_threshold:
            return "medium"
        return "low"

    @classmethod
    def _build_business_summary(
        cls,
        *,
        framework_key: str,
        query: str,
        category: str,
        target_market: str,
        source_count: int,
        market_signal_count: int = 0,
        trend_signal_count: int = 0,
        social_signal_count: int = 0,
        supplier_count: int = 0,
        competitor_count: int = 0,
        recommended_next_action: str,
    ) -> dict[str, Any]:
        combined_market_signal = market_signal_count + trend_signal_count + social_signal_count
        market_strength = cls._signal_strength(combined_market_signal, high_threshold=8, medium_threshold=1)
        supply_strength = cls._signal_strength(supplier_count, high_threshold=5, medium_threshold=1)
        competition_strength = cls._signal_strength(competitor_count, high_threshold=5, medium_threshold=1)
        return {
            "summary_version": "2026-04-19",
            "framework_key": framework_key,
            "market_signal_strength": market_strength,
            "supply_signal_strength": supply_strength,
            "competition_signal_strength": competition_strength,
            "signal_scorecard": {
                "source_count": source_count,
                "market_signal_count": market_signal_count,
                "trend_signal_count": trend_signal_count,
                "social_signal_count": social_signal_count,
                "supplier_count": supplier_count,
                "competitor_count": competitor_count,
            },
            "operations_view": f"运营视角：{target_market} 市场下 {category} 的线索强度为 {market_strength}，当前已覆盖 {source_count} 类来源。",
            "procurement_view": f"采购视角：供应信号为 {supply_strength}，可继续跟进 {supplier_count} 个供应侧样本并核对交期与起订量。",
            "finance_view": f"财务视角：竞品/供给样本强度为 {competition_strength}，建议结合成本、毛利和周转预估做筛选。",
            "next_action": recommended_next_action,
            "query": query,
            "category": category,
            "target_market": target_market,
        }

    @staticmethod
    def _resolve_workflow_mode(input_data: dict[str, Any]) -> str:
        mode = str(input_data.get("mode") or "auto").strip().lower()
        return mode if mode in {"auto", "real", "mock"} else "auto"

    @classmethod
    def _resolve_tool_readiness(cls, *, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        signal_context = payload.get("signal_context") if isinstance(payload.get("signal_context"), dict) else {}
        signal_readiness = payload.get("signal_readiness") if isinstance(payload.get("signal_readiness"), dict) else {}
        mode = str(payload.get("mode") or "unknown").strip().lower()
        provider = str(signal_context.get("provider") or "").strip().lower() or None
        source_channel = str(signal_context.get("source_channel") or "").strip().lower() or None
        local_business_ready = False
        enterprise_ready = False
        readiness_tier = ""
        next_actions = [str(item).strip() for item in signal_readiness.get("next_actions", []) if str(item).strip()]

        if signal_readiness:
            local_business_ready = bool(signal_readiness.get("local_business_ready", signal_readiness.get("enterprise_ready", False)))
            enterprise_ready = bool(signal_readiness.get("enterprise_ready", False))
            readiness_tier = str(signal_readiness.get("readiness_tier") or "").strip().lower()
        elif mode == "real":
            local_business_ready = True
            enterprise_ready = True
            readiness_tier = "enterprise_ready"
        elif mode == "mock":
            readiness_tier = "mock_only"
        elif mode == "auto":
            readiness_tier = "not_ready"

        if not readiness_tier:
            if enterprise_ready:
                readiness_tier = "enterprise_ready"
            elif local_business_ready:
                readiness_tier = "local_business_ready"
            elif mode == "mock":
                readiness_tier = "mock_only"
            else:
                readiness_tier = "not_ready"

        business_interpretation = "not_ready"
        if enterprise_ready:
            business_interpretation = "enterprise_ready"
        elif local_business_ready and provider == "external_signal_service":
            business_interpretation = "local_validation_only"
        elif local_business_ready:
            business_interpretation = "enterprise_ready"
        elif mode == "mock":
            business_interpretation = "mock_only"

        return {
            "tool": tool_name,
            "mode": mode,
            "provider": provider,
            "source_channel": source_channel,
            "local_business_ready": local_business_ready,
            "enterprise_ready": enterprise_ready,
            "readiness_tier": readiness_tier,
            "business_interpretation": business_interpretation,
            "is_external_signal_fallback": provider == "external_signal_service",
            "next_actions": next_actions,
        }

    @classmethod
    def _build_collection_readiness(
        cls,
        *,
        tool_payloads: dict[str, Any],
        external_signal_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summary = external_signal_summary if isinstance(external_signal_summary, dict) else {}
        tool_readiness: dict[str, dict[str, Any]] = {}
        local_validation_only_tools: list[str] = []
        enterprise_ready_tools: list[str] = []
        mock_only_tools: list[str] = []
        not_ready_tools: list[str] = []
        next_actions: list[str] = []

        for tool_name, payload in tool_payloads.items():
            if not isinstance(payload, dict):
                continue
            readiness = cls._resolve_tool_readiness(tool_name=tool_name, payload=payload)
            tool_readiness[tool_name] = readiness
            next_actions.extend(readiness.get("next_actions", []))
            interpretation = readiness.get("business_interpretation")
            if interpretation == "local_validation_only":
                local_validation_only_tools.append(tool_name)
            elif interpretation == "enterprise_ready":
                enterprise_ready_tools.append(tool_name)
            elif interpretation == "mock_only":
                mock_only_tools.append(tool_name)
            else:
                not_ready_tools.append(tool_name)

        governance_status = "mixed"
        if local_validation_only_tools:
            governance_status = "local_validation_only"
        elif enterprise_ready_tools and not mock_only_tools and not not_ready_tools:
            governance_status = "enterprise_ready"
        elif mock_only_tools and not enterprise_ready_tools and not local_validation_only_tools:
            governance_status = "mock_only"
        elif not tool_readiness:
            governance_status = "unknown"
        elif not_ready_tools and not (enterprise_ready_tools or local_validation_only_tools):
            governance_status = "not_ready"

        return {
            "governance_status": governance_status,
            "has_external_signal_fallbacks": bool(summary.get("has_external_signal_fallbacks")) or bool(local_validation_only_tools),
            "fallback_tool_count": int(summary.get("fallback_tool_count") or len(local_validation_only_tools)),
            "fallback_business_sources": list(summary.get("fallback_business_sources") or []),
            "local_validation_only_sources": list(summary.get("local_validation_only_sources") or []),
            "local_validation_only_tools": sorted(local_validation_only_tools),
            "enterprise_ready_tools": sorted(enterprise_ready_tools),
            "mock_only_tools": sorted(mock_only_tools),
            "not_ready_tools": sorted(not_ready_tools),
            "local_business_ready_tool_count": sum(1 for item in tool_readiness.values() if item.get("local_business_ready")),
            "enterprise_ready_tool_count": sum(1 for item in tool_readiness.values() if item.get("enterprise_ready")),
            "tool_readiness": tool_readiness,
            "next_actions": sorted({item for item in next_actions if item}),
            "external_signal_summary": summary,
        }

    @staticmethod
    def _resolve_supply_payload(payload: dict[str, Any]) -> dict[str, Any]:
        supplier_payload = payload.get("supplier_data")
        if isinstance(supplier_payload, dict):
            return supplier_payload
        supply_chain_payload = payload.get("supply_chain_data")
        return supply_chain_payload if isinstance(supply_chain_payload, dict) else {}

    def build_registry(self) -> dict[str, Any]:
        registry = {
            "native-python": {
                "type": "built-in",
                "status": "active",
                "use_cases": ["selection_workflow", "agent_platform_operations"],
                "notes": "当前生产主路径",
                "supports": ["invoke", "sync-run"],
            },
            "langgraph-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["selection_workflow", "debug_workflow", "human_in_loop"],
                "notes": "用于复杂状态机工作流的兼容抽象层",
                "supports": ["invoke", "snapshot", "single-step", "breakpoint", "human-intervention"],
            },
            "autogen-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["multi_source_collection", "multi_agent_dialogue"],
                "notes": "兼容 AutoGen 多Agent对话，当前以应用侧多角色会话编排落地",
                "supports": ["invoke", "multi-agent-dialogue", "tool-handoff", "source-aggregation"],
            },
            "langchain-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["rapid_prototype", "tool_calling", "selection_research"],
                "notes": "兼容 LangChain Chain/Tool 原型，当前以应用侧 Tool 编排落地",
                "supports": ["invoke", "tool-calling", "chain-summary", "service-integration"],
            },
            "crewai-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["parallel_competitor_analysis", "task_collaboration"],
                "notes": "兼容 CrewAI 并行任务，当前以应用侧 crew/task 聚合编排落地",
                "supports": ["invoke", "parallel-task", "task-summary", "crew-result-merge"],
            },
            "ray-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["actor_parallelism", "distributed_execution"],
                "notes": "兼容 Ray Actor 并行执行，当前以应用侧 actor-shard 聚合落地",
                "supports": ["invoke", "actor-parallel", "shard-merge", "distributed-summary"],
            },
            "dify-compatible": {
                "type": "external-compatible",
                "status": "integrated",
                "use_cases": ["prompt_orchestration"],
                "notes": "用于低代码流程编排的兼容抽象层，当前以模板路由与变量渲染落地",
                "supports": ["invoke", "template-routing", "variable-rendering"],
            },
        }
        for framework_key, detail in registry.items():
            detail.update(self._resolve_runtime_status(framework_key, str(detail.get("status") or "integrated")))
        return registry

    def register_invoker(self, framework_key: str, invoker: Callable[..., Awaitable[dict[str, Any]]]) -> None:
        self._invokers[framework_key] = invoker

    async def invoke_autogen_compatible(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "electronics")
        target_market = str(input_data.get("target_market") or "US")
        mode = self._resolve_workflow_mode(input_data)
        data_agent = DataCollectionAgent()
        transcript = [
            {
                "role": "coordinator",
                "agent": "autogen-compatible.coordinator",
                "message": f"启动多Agent对话，围绕 {query} 进行 Amazon/TikTok/Google/1688 多源采集。",
            },
            {
                "role": "planner",
                "agent": "autogen-compatible.planner",
                "message": f"分配子任务：amazon_bsr + tiktok_products + google_trends + ali1688_supply；品类={category}，市场={target_market}。",
            },
        ]
        collected = await data_agent.run(
            {
                "query": query,
                "category": category,
                "target_market": target_market,
                "keywords": [query, category],
                "niche": category,
                "asin": str(input_data.get("asin") or "B000AUTOGEN001"),
                "mode": mode,
            }
        )
        payload = collected.to_dict() if hasattr(collected, "to_dict") else collected
        data = payload.get("output") if isinstance(payload, dict) and isinstance(payload.get("output"), dict) else payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}
        supply_payload = self._resolve_supply_payload(data)
        source_summary = {
            "amazon_products": len((data.get("amazon_data") or {}).get("products") or []) if isinstance(data.get("amazon_data"), dict) else 0,
            "tiktok_products": len((data.get("tiktok_data") or {}).get("products") or []) if isinstance(data.get("tiktok_data"), dict) else 0,
            "google_keywords": len((data.get("trend_data") or {}).get("trend_data") or {}) if isinstance(data.get("trend_data"), dict) else 0,
            "supplier_count": len(supply_payload.get("suppliers") or []),
        }
        collection_readiness = self._build_collection_readiness(
            tool_payloads={
                "amazon_bsr": data.get("amazon_data"),
                "tiktok_products": data.get("tiktok_data"),
                "google_trends": data.get("trend_data"),
                "ali1688_supply": supply_payload,
            },
            external_signal_summary=data.get("external_signal_summary") if isinstance(data.get("external_signal_summary"), dict) else None,
        )
        transcript.extend(
            [
                {
                    "role": "collector",
                    "agent": "autogen-compatible.collector",
                    "message": f"采集完成：Amazon={source_summary['amazon_products']}，TikTok={source_summary['tiktok_products']}，Google关键词={source_summary['google_keywords']}，1688供应商={source_summary['supplier_count']}。",
                },
                {
                    "role": "summarizer",
                    "agent": "autogen-compatible.summarizer",
                    "message": "已汇总多源数据，生成统一采集摘要并返回给上游编排层。",
                },
            ]
        )
        return {
            "framework": "autogen-compatible",
            "status": "completed",
            "conversation_mode": "multi_agent_dialogue",
            "requested_mode": mode,
            "input": {"query": query, "category": category, "target_market": target_market},
            "participants": [
                "autogen-compatible.coordinator",
                "autogen-compatible.planner",
                "autogen-compatible.collector",
                "autogen-compatible.summarizer",
            ],
            "transcript": transcript,
            "source_summary": source_summary,
            "collection_readiness": collection_readiness,
            "business_summary": {
                **self._build_business_summary(
                    framework_key="autogen-compatible",
                    query=query,
                    category=category,
                    target_market=target_market,
                    source_count=4,
                    market_signal_count=source_summary["amazon_products"],
                    trend_signal_count=source_summary["google_keywords"],
                    social_signal_count=source_summary["tiktok_products"],
                    supplier_count=source_summary["supplier_count"],
                    competitor_count=source_summary["amazon_products"],
                    recommended_next_action="继续汇总多源采集结果，生成候选清单并进入人工复核。",
                ),
                "collection_local_business_ready": collection_readiness["local_business_ready_tool_count"] > 0,
                "collection_enterprise_ready": bool(collection_readiness["tool_readiness"]) and not collection_readiness["local_validation_only_tools"] and not collection_readiness["mock_only_tools"] and not collection_readiness["not_ready_tools"],
                "signal_governance_status": collection_readiness["governance_status"],
            },
            "data_collection": data,
        }

    async def invoke_langchain_compatible(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "electronics")
        target_market = str(input_data.get("target_market") or "US")
        mode = self._resolve_workflow_mode(input_data)
        data_agent = DataCollectionAgent()
        amazon_result = await data_agent.call_tool("amazon_bsr", category=category, top_n=10, marketplace=target_market, mode=mode)
        trends_result = await data_agent.call_tool("google_trends", keywords=[query, category], time_range="12m", geo=target_market, mode=mode)
        suppliers_result = await data_agent.call_tool("ali1688_supply", product_keyword=query, max_suppliers=8, mode=mode)
        collection_readiness = self._build_collection_readiness(
            tool_payloads={
                "amazon_bsr": amazon_result,
                "google_trends": trends_result,
                "ali1688_supply": suppliers_result,
            }
        )
        tool_calls = [
            {"tool": "amazon_bsr", "status": "success", "records": len((amazon_result or {}).get("products", [])) if isinstance(amazon_result, dict) else 0},
            {"tool": "google_trends", "status": "success", "records": len((trends_result or {}).get("trend_data") or {}) if isinstance(trends_result, dict) else 0},
            {"tool": "ali1688_supply", "status": "success", "records": len((suppliers_result or {}).get("suppliers", [])) if isinstance(suppliers_result, dict) else 0},
        ]
        summary = {
            "query": query,
            "category": category,
            "target_market": target_market,
            "amazon_product_count": tool_calls[0]["records"],
            "trend_keyword_count": tool_calls[1]["records"],
            "supplier_count": tool_calls[2]["records"],
        }
        return {
            "framework": "langchain-compatible",
            "status": "completed",
            "execution_mode": "tool_calling_chain",
            "requested_mode": mode,
            "tool_calls": tool_calls,
            "summary": summary,
            "collection_readiness": collection_readiness,
            "business_summary": {
                **self._build_business_summary(
                    framework_key="langchain-compatible",
                    query=query,
                    category=category,
                    target_market=target_market,
                    source_count=3,
                    market_signal_count=summary["amazon_product_count"],
                    trend_signal_count=summary["trend_keyword_count"],
                    supplier_count=summary["supplier_count"],
                    competitor_count=summary["amazon_product_count"],
                    recommended_next_action="优先核对趋势词、竞品售价和供应报价，输出首轮测款建议。",
                ),
                "pricing_signal_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("local_business_ready")),
                "pricing_enterprise_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("enterprise_ready")),
                "trend_signal_ready": bool((collection_readiness["tool_readiness"].get("google_trends") or {}).get("local_business_ready")),
                "trend_enterprise_ready": bool((collection_readiness["tool_readiness"].get("google_trends") or {}).get("enterprise_ready")),
                "signal_governance_status": collection_readiness["governance_status"],
            },
            "outputs": {
                "amazon_bsr": amazon_result,
                "google_trends": trends_result,
                "ali1688_supply": suppliers_result,
            },
        }

    async def invoke_crewai_compatible(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "electronics")
        target_market = str(input_data.get("target_market") or "US")
        mode = self._resolve_workflow_mode(input_data)
        data_agent = DataCollectionAgent()
        amazon_task = await data_agent.call_tool("amazon_bsr", category=category, top_n=8, marketplace=target_market, mode=mode)
        tiktok_task = await data_agent.call_tool("tiktok_products", query=query, top_n=8, region=target_market, mode=mode)
        supplier_task = await data_agent.call_tool("ali1688_supply", product_keyword=query, max_suppliers=6, mode=mode)
        collection_readiness = self._build_collection_readiness(
            tool_payloads={
                "amazon_bsr": amazon_task,
                "tiktok_products": tiktok_task,
                "ali1688_supply": supplier_task,
            }
        )
        tasks = [
            {"task": "amazon_competitor_scan", "status": "completed", "records": len((amazon_task or {}).get("products", [])) if isinstance(amazon_task, dict) else 0},
            {"task": "tiktok_signal_scan", "status": "completed", "records": len((tiktok_task or {}).get("products", [])) if isinstance(tiktok_task, dict) else 0},
            {"task": "supplier_scan", "status": "completed", "records": len((supplier_task or {}).get("suppliers", [])) if isinstance(supplier_task, dict) else 0},
        ]
        merged_summary = {
            "query": query,
            "category": category,
            "target_market": target_market,
            "competitor_count": tasks[0]["records"],
            "social_signal_count": tasks[1]["records"],
            "supplier_count": tasks[2]["records"],
        }
        return {
            "framework": "crewai-compatible",
            "status": "completed",
            "execution_mode": "parallel_task_crew",
            "requested_mode": mode,
            "crew": {
                "agents": ["market_analyst", "social_signal_analyst", "supply_analyst"],
                "tasks": tasks,
            },
            "summary": merged_summary,
            "collection_readiness": collection_readiness,
            "business_summary": {
                **self._build_business_summary(
                    framework_key="crewai-compatible",
                    query=query,
                    category=category,
                    target_market=target_market,
                    source_count=3,
                    market_signal_count=merged_summary["competitor_count"],
                    social_signal_count=merged_summary["social_signal_count"],
                    supplier_count=merged_summary["supplier_count"],
                    competitor_count=merged_summary["competitor_count"],
                    recommended_next_action="按竞品、社媒热度和供应稳定性汇总任务结果，推进候选款排序。",
                ),
                "competitor_scan_ready": bool((collection_readiness["tool_readiness"].get("amazon_bsr") or {}).get("local_business_ready")),
                "competitor_scan_enterprise_ready": bool((collection_readiness["tool_readiness"].get("amazon_bsr") or {}).get("enterprise_ready")),
                "social_signal_ready": bool((collection_readiness["tool_readiness"].get("tiktok_products") or {}).get("local_business_ready")),
                "social_signal_enterprise_ready": bool((collection_readiness["tool_readiness"].get("tiktok_products") or {}).get("enterprise_ready")),
                "supply_scan_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("local_business_ready")),
                "supply_scan_enterprise_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("enterprise_ready")),
                "signal_governance_status": collection_readiness["governance_status"],
            },
            "outputs": {
                "amazon_competitor_scan": amazon_task,
                "tiktok_signal_scan": tiktok_task,
                "supplier_scan": supplier_task,
            },
        }

    async def invoke_ray_compatible(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "electronics")
        target_market = str(input_data.get("target_market") or "US")
        mode = self._resolve_workflow_mode(input_data)
        data_agent = DataCollectionAgent()
        amazon_task = await data_agent.call_tool("amazon_bsr", category=category, top_n=6, marketplace=target_market, mode=mode)
        trends_task = await data_agent.call_tool("google_trends", keywords=[query, category], time_range="12m", geo=target_market, mode=mode)
        supplier_task = await data_agent.call_tool("ali1688_supply", product_keyword=query, max_suppliers=5, mode=mode)
        collection_readiness = self._build_collection_readiness(
            tool_payloads={
                "amazon_bsr": amazon_task,
                "google_trends": trends_task,
                "ali1688_supply": supplier_task,
            }
        )
        actor_shards = [
            {"actor": "ray-compatible.market_actor", "task": "amazon_bsr", "status": "completed", "records": len((amazon_task or {}).get("products", [])) if isinstance(amazon_task, dict) else 0},
            {"actor": "ray-compatible.trend_actor", "task": "google_trends", "status": "completed", "records": len((trends_task or {}).get("trend_data") or {}) if isinstance(trends_task, dict) else 0},
            {"actor": "ray-compatible.supply_actor", "task": "ali1688_supply", "status": "completed", "records": len((supplier_task or {}).get("suppliers", [])) if isinstance(supplier_task, dict) else 0},
        ]
        return {
            "framework": "ray-compatible",
            "status": "completed",
            "execution_mode": "actor_parallelism",
            "requested_mode": mode,
            "actors": actor_shards,
            "summary": {
                "query": query,
                "category": category,
                "target_market": target_market,
                "actor_count": len(actor_shards),
                "supplier_count": actor_shards[2]["records"],
            },
            "collection_readiness": collection_readiness,
            "business_summary": {
                **self._build_business_summary(
                    framework_key="ray-compatible",
                    query=query,
                    category=category,
                    target_market=target_market,
                    source_count=3,
                    market_signal_count=actor_shards[0]["records"],
                    trend_signal_count=actor_shards[1]["records"],
                    supplier_count=actor_shards[2]["records"],
                    competitor_count=actor_shards[0]["records"],
                    recommended_next_action="保留并行分片结果，合并供应与趋势信号后再进入人工判断。",
                ),
                "distributed_market_scan": True,
                "market_signal_ready": bool((collection_readiness["tool_readiness"].get("amazon_bsr") or {}).get("local_business_ready")) and bool((collection_readiness["tool_readiness"].get("google_trends") or {}).get("local_business_ready")),
                "market_signal_enterprise_ready": bool((collection_readiness["tool_readiness"].get("amazon_bsr") or {}).get("enterprise_ready")) and bool((collection_readiness["tool_readiness"].get("google_trends") or {}).get("enterprise_ready")),
                "supply_signal_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("local_business_ready")),
                "supply_signal_enterprise_ready": bool((collection_readiness["tool_readiness"].get("ali1688_supply") or {}).get("enterprise_ready")),
                "signal_governance_status": collection_readiness["governance_status"],
            },
            "outputs": {
                "amazon_bsr": amazon_task,
                "google_trends": trends_task,
                "ali1688_supply": supplier_task,
            },
        }

    async def invoke_dify_compatible(self, *, input_data: dict[str, Any]) -> dict[str, Any]:
        query = str(input_data.get("query") or "").strip()
        if not query:
            raise ValueError("query不能为空")
        category = str(input_data.get("category") or "general")
        template_key = "selection-market-brief"
        if category in {"electronics", "consumer_electronics"}:
            template_key = "selection-electronics-brief"
        rendered_prompt = (
            "你是跨境电商选品分析助手。"
            f"\n品类: {category}"
            f"\n问题: {query}"
            "\n请输出市场机会、竞品风险、供应链关注点和下一步动作。"
        )
        return {
            "framework": "dify-compatible",
            "status": "completed",
            "execution_mode": "prompt_orchestration",
            "template_key": template_key,
            "variables": {"query": query, "category": category},
            "rendered_prompt": rendered_prompt,
            "routing": {
                "template_key": template_key,
                "channel": "dify-compatible",
                "strategy": "category-first",
            },
            "business_summary": self._build_business_summary(
                framework_key="dify-compatible",
                query=query,
                category=category,
                target_market="global",
                source_count=1,
                recommended_next_action="根据模板输出补齐市场机会、风险和供应链关注点，再交由人工定稿。",
            ),
        }

    async def invoke(self, framework_key: str, **kwargs: Any) -> dict[str, Any]:
        if framework_key not in self._invokers:
            raise KeyError(f"框架未注册可调用适配器: {framework_key}")
        return await self._invokers[framework_key](**kwargs)

    def get_framework(self, framework_key: str) -> dict[str, Any] | None:
        framework = self.build_registry().get(framework_key)
        if framework is None:
            return None
        return {
            **framework,
            "invoker_registered": framework_key in self._invokers,
        }

    def list_registered_invokers(self) -> list[str]:
        return sorted(self._invokers.keys())
