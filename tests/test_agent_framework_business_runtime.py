from __future__ import annotations

import pytest
from src.agents.data_collection import DataCollectionAgent
from src.agents.framework_adapter import AgentFrameworkAdapterRegistry


class _FakeCollected:
    def __init__(self, output: dict):
        self._output = output

    def to_dict(self) -> dict:
        return {"output": self._output}


def _external_signal_payload(*, source: str, record_key: str, records: object, source_name: str) -> dict:
    payload = {
        "source": source,
        "mode": "real",
        record_key: records,
        "signal_context": {
            "provider": "external_signal_service",
            "source_name": source_name,
            "source_channel": "public_web_signal",
        },
        "signal_readiness": {
            "local_business_ready": True,
            "enterprise_ready": False,
            "readiness_tier": "local_business_ready",
            "next_actions": [f"replace_{source_name}_with_formal_api"],
        },
    }
    if isinstance(records, list):
        payload["total_results"] = len(records)
        payload["total_suppliers"] = len(records)
    return payload


@pytest.mark.asyncio
async def test_framework_business_outputs_surface_readiness_and_use_auto_mode(monkeypatch):
    registry = AgentFrameworkAdapterRegistry()
    call_modes: list[tuple[str, str | None]] = []
    run_modes: list[str | None] = []

    async def _fake_call_tool(self, tool_name: str, **kwargs):
        call_modes.append((tool_name, kwargs.get("mode")))
        if tool_name == "amazon_bsr":
            return _external_signal_payload(
                source="amazon_bsr",
                record_key="products",
                records=[{"asin": "B0001"}],
                source_name="amazon",
            )
        if tool_name == "google_trends":
            return _external_signal_payload(
                source="google_trends",
                record_key="trend_data",
                records={"portable blender": {"avg_interest": 78}},
                source_name="google_trends",
            )
        if tool_name == "ali1688_supply":
            return _external_signal_payload(
                source="ali1688",
                record_key="suppliers",
                records=[{"supplier_id": "SUP-1"}],
                source_name="ali1688",
            )
        if tool_name == "tiktok_products":
            return {
                "source": "tiktok_products",
                "mode": "real",
                "products": [{"product_id": "TK-1"}],
                "total_results": 1,
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    async def _fake_run(self, input_data: dict):
        run_modes.append(input_data.get("mode"))
        return _FakeCollected(
            {
                "amazon_data": await _fake_call_tool(self, "amazon_bsr", mode=input_data.get("mode")),
                "tiktok_data": await _fake_call_tool(self, "tiktok_products", mode=input_data.get("mode")),
                "trend_data": await _fake_call_tool(self, "google_trends", mode=input_data.get("mode")),
                "supply_chain_data": await _fake_call_tool(self, "ali1688_supply", mode=input_data.get("mode")),
                "external_signal_summary": {
                    "has_external_signal_fallbacks": True,
                    "fallback_tool_count": 3,
                    "fallback_business_sources": ["amazon", "google_trends", "ali1688"],
                    "local_validation_only_sources": ["amazon", "google_trends", "ali1688"],
                },
            }
        )

    monkeypatch.setattr(DataCollectionAgent, "call_tool", _fake_call_tool)
    monkeypatch.setattr(DataCollectionAgent, "run", _fake_run)

    autogen = await registry.invoke_autogen_compatible(
        input_data={"query": "portable blender", "category": "electronics", "target_market": "US"}
    )
    assert autogen["framework"] == "autogen-compatible"
    assert autogen["requested_mode"] == "auto"
    assert autogen["collection_readiness"]["governance_status"] == "local_validation_only"
    assert autogen["collection_readiness"]["fallback_tool_count"] == 3
    assert autogen["business_summary"]["collection_local_business_ready"] is True
    assert autogen["business_summary"]["collection_enterprise_ready"] is False

    langchain = await registry.invoke_langchain_compatible(
        input_data={"query": "portable blender", "category": "electronics", "target_market": "US"}
    )
    assert langchain["summary"]["supplier_count"] == 1
    assert len(langchain["tool_calls"]) == 3
    assert langchain["collection_readiness"]["governance_status"] == "local_validation_only"
    assert langchain["business_summary"]["pricing_signal_ready"] is True
    assert langchain["business_summary"]["pricing_enterprise_ready"] is False
    assert langchain["business_summary"]["trend_signal_ready"] is True
    assert langchain["business_summary"]["trend_enterprise_ready"] is False

    crewai = await registry.invoke_crewai_compatible(
        input_data={"query": "portable blender", "category": "electronics", "target_market": "US"}
    )
    assert crewai["summary"]["supplier_count"] == 1
    assert len(crewai["crew"]["tasks"]) == 3
    assert crewai["business_summary"]["competitor_scan_ready"] is True
    assert crewai["business_summary"]["competitor_scan_enterprise_ready"] is False
    assert crewai["business_summary"]["social_signal_ready"] is True
    assert crewai["business_summary"]["social_signal_enterprise_ready"] is True
    assert crewai["business_summary"]["supply_scan_enterprise_ready"] is False

    ray = await registry.invoke_ray_compatible(
        input_data={"query": "portable blender", "category": "electronics", "target_market": "US"}
    )
    assert ray["summary"]["actor_count"] == 3
    assert ray["summary"]["supplier_count"] == 1
    assert ray["business_summary"]["market_signal_ready"] is True
    assert ray["business_summary"]["market_signal_enterprise_ready"] is False
    assert ray["business_summary"]["supply_signal_ready"] is True
    assert ray["business_summary"]["supply_signal_enterprise_ready"] is False

    dify = await registry.invoke_dify_compatible(input_data={"query": "output market brief", "category": "electronics"})
    assert dify["routing"]["template_key"] == "selection-electronics-brief"
    assert dify["business_summary"]["next_action"]

    assert run_modes == ["auto"]
    assert all(mode == "auto" for _, mode in call_modes)
