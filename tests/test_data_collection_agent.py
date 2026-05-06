from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-data-collection-agent-32chars")

import pytest
from src.agents.data_collection import DataCollectionAgent


def _patch_llm_gateway(monkeypatch) -> None:
    class _FakeGateway:
        def __init__(self, config) -> None:
            self.config = config

        async def route(self, prompt: str):
            return SimpleNamespace(
                response='{"market_heat": 6, "competition_level": "medium", "supply_chain_maturity": 7, "recommendation": "watch"}',
                tokens_used=16,
            )

    monkeypatch.setattr("src.infrastructure.llm_gateway.LLMGateway", _FakeGateway)


@pytest.mark.asyncio
async def test_data_collection_agent_runs_with_auto_mode_real_paths(monkeypatch):
    async def _fake_send(topic, message, key=None):
        return True

    async def _fake_collect_business_real_signals(self, *, query, mode="auto", required_real_sources=3):
        return {
            "query": query,
            "requested_mode": mode,
            "sources": {
                "amazon": {"source": "amazon", "mode": "real", "title": f"{query} amazon", "source_channel": "public_web_signal", "enterprise_integrated": False},
                "tiktok": {"source": "tiktok", "mode": "real", "title": f"{query} tiktok", "source_channel": "public_web_signal", "enterprise_integrated": False},
                "google_trends": {"source": "google_trends", "mode": "real", "title": f"{query} trends", "source_channel": "public_web_signal", "enterprise_integrated": False},
                "ali1688": {"source": "ali1688", "mode": "real", "title": f"{query} supply", "source_channel": "public_web_signal", "enterprise_integrated": False},
                "media_news": {"source": "media_news", "mode": "real", "title": f"{query} news", "source_channel": "open_api_signal", "enterprise_integrated": False},
            },
            "summary": {
                "real_count": 5,
                "mock_count": 0,
                "error_count": 0,
                "all_real": True,
                "local_business_ready": True,
                "enterprise_ready": False,
                "readiness_tier": "local_business_ready",
                "next_actions": ["treat this bundle as local business validation only"],
            },
        }

    async def _fake_google_trends(self, **kwargs):
        return "<html><title>Google Trends</title></html>"

    monkeypatch.setattr("src.agents.data_collection.send_message", _fake_send)
    monkeypatch.setattr("src.agents.data_collection.ExternalSignalService.collect_business_real_signals", _fake_collect_business_real_signals)
    monkeypatch.setattr("src.agents.data_collection.GoogleTrendsClient.fetch_interest_over_time", _fake_google_trends)
    _patch_llm_gateway(monkeypatch)

    agent = DataCollectionAgent(config={"quality_threshold": 0.1})
    result = await agent.run({"query": "蓝牙耳机", "category": "bluetooth earbuds", "mode": "auto"})

    assert result.success is True
    payload = result.output["data"]
    assert payload["sources_summary"]["total_sources"] == 7
    assert payload["requested_mode"] == "auto"
    assert payload["runtime_mode"] in {"auto", "degraded"}
    assert isinstance(payload["degraded"], bool)
    assert len(payload["source_mode_breakdown"]) == 7
    amazon_breakdown = next(item for item in payload["source_mode_breakdown"] if item["source"] == "amazon_bsr")
    assert amazon_breakdown["signal_context"]["provider"] == "external_signal_service"
    assert amazon_breakdown["signal_context"]["source_channel"] == "public_web_signal"
    assert amazon_breakdown["signal_readiness"]["local_business_ready"] is True
    assert payload["external_signal_summary"]["has_external_signal_fallbacks"] is True
    assert "amazon" in payload["external_signal_summary"]["fallback_business_sources"]
    assert "amazon" in payload["external_signal_summary"]["local_validation_only_sources"]
    assert payload["sources_summary"]["external_signal_fallbacks"]
    assert "amazon_data" in payload
    assert "tiktok_data" in payload
    assert "trend_data" in payload
    assert "supplier_data" in payload
    assert "supply_chain_data" in payload


@pytest.mark.asyncio
async def test_data_collection_agent_real_mode_fails_when_no_real_sources(monkeypatch):
    async def _fake_send(topic, message, key=None):
        return True

    async def _fake_collect_business_real_signals(self, *, query, mode="auto", required_real_sources=3):
        return {
            "query": query,
            "requested_mode": mode,
            "sources": {
                "amazon": {"source": "amazon", "mode": "mock"},
                "tiktok": {"source": "tiktok", "mode": "mock"},
                "google_trends": {"source": "google_trends", "mode": "mock"},
                "ali1688": {"source": "ali1688", "mode": "mock"},
                "media_news": {"source": "media_news", "mode": "mock"},
            },
            "summary": {
                "real_count": 0,
                "mock_count": 5,
                "error_count": 0,
                "all_real": False,
                "local_business_ready": False,
                "enterprise_ready": False,
                "readiness_tier": "mock_only",
            },
        }

    async def _fake_google_trends(self, **kwargs):
        return "<html><title>Google Trends</title></html>"

    monkeypatch.setattr("src.agents.data_collection.send_message", _fake_send)
    monkeypatch.setattr("src.agents.data_collection.ExternalSignalService.collect_business_real_signals", _fake_collect_business_real_signals)
    monkeypatch.setattr("src.agents.data_collection.GoogleTrendsClient.fetch_interest_over_time", _fake_google_trends)
    _patch_llm_gateway(monkeypatch)

    agent = DataCollectionAgent(config={"quality_threshold": 0.1})
    result = await agent.run({"query": "蓝牙耳机", "category": "bluetooth earbuds", "mode": "real"})

    assert result.success is False
    assert "real mode collection failed" in (result.error or "")


@pytest.mark.asyncio
async def test_data_collection_agent_mock_tools_load_business_scenarios():
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    amazon = await agent.call_tool("amazon_bsr", category="portable blender margin", mode="mock")
    tiktok = await agent.call_tool("tiktok_products", query="viral spike blender", mode="mock")
    trends = await agent.call_tool("google_trends", keywords=["portable blender drop"], mode="mock")
    supply = await agent.call_tool("ali1688_supply", product_keyword="supplier unstable", mode="mock")

    assert amazon["scenario"]["scenario_id"] == "amazon_margin_pressure"
    assert amazon["products"][0]["risk_flag"] == "margin_pressure"

    assert tiktok["scenario"]["scenario_id"] == "tiktok_trend_spike"
    assert tiktok["products"][0]["title"] == "#portableblender"
    assert tiktok["total_views"] > 0

    assert trends["scenario"]["scenario_id"] == "google_trends_spike_then_drop"
    assert trends["trend_data"]["portable blender drop"]["risk_flag"] == "spike_then_drop"
    assert trends["trend_data"]["portable blender drop"]["trend_direction"] == "down"
    assert trends["growth_rate_7d"] < 0

    assert supply["scenario"]["scenario_id"] == "ali1688_supplier_unstable"
    assert supply["total_suppliers"] == 2
    assert supply["avg_lead_time"] == 24.5
    assert supply["degraded"] is True
    assert supply["degradation_reason"] == "mock partial_data scenario"
    assert supply["suppliers"][0]["risk_flag"] == "supplier_unstable"


@pytest.mark.asyncio
async def test_data_collection_agent_mock_tiktok_auth_failure_is_degraded():
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    result = await agent.call_tool("tiktok_products", query="auth token failed", mode="mock")

    assert result["scenario"]["scenario_id"] == "tiktok_auth_failed"
    assert result["degraded"] is True
    assert result["degradation_reason"] == "mock auth_failed scenario"
    assert result["total_results"] == 0


@pytest.mark.asyncio
async def test_data_collection_agent_mock_amazon_rate_limit_is_degraded():
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    result = await agent.call_tool("amazon_bsr", category="Amazon 429 限流", mode="mock")

    assert result["scenario"]["scenario_id"] == "amazon_rate_limited"
    assert result["degraded"] is True
    assert result["degradation_reason"] == "mock rate_limited scenario"
    assert result["total_results"] == 0


@pytest.mark.asyncio
async def test_data_collection_agent_mock_tools_cover_extended_business_scenarios():
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    amazon_refund = await agent.call_tool("amazon_bsr", category="便携制冰机退款差评很多", mode="mock")
    amazon_hot = await agent.call_tool("amazon_bsr", category="厨房封口机爆款热卖", mode="mock")
    tiktok_conversion = await agent.call_tool("tiktok_products", query="portable ice maker 高热低转化", mode="mock")
    trends_growth = await agent.call_tool("google_trends", keywords=["蓝牙音箱 增长"], mode="mock")
    trends_empty = await agent.call_tool("google_trends", keywords=["厨房用品 冷门"], mode="mock")
    supply_long_lead = await agent.call_tool("ali1688_supply", product_keyword="高moq 长交期", mode="mock")

    assert amazon_refund["scenario"]["scenario_id"] == "amazon_high_refund"
    assert amazon_refund["products"][0]["risk_flag"] == "high_refund"
    assert amazon_refund["products"][0]["refund_rate"] > 0.1

    assert amazon_hot["scenario"]["scenario_id"] == "amazon_hot_selling"
    assert amazon_hot["products"][0]["risk_flag"] == "hot_selling"
    assert amazon_hot["total_results"] >= 1

    assert tiktok_conversion["scenario"]["scenario_id"] == "tiktok_high_heat_low_conversion"
    assert tiktok_conversion["products"][0]["risk_flag"] == "high_heat_low_conversion"
    assert tiktok_conversion["products"][0]["estimated_conversion_rate"] == 0.011

    assert trends_growth["scenario"]["scenario_id"] == "google_trends_growth"
    assert trends_growth["trend_data"]["蓝牙音箱 增长"]["trend_direction"] == "up"
    assert trends_growth["growth_rate_30d"] > 0

    assert trends_empty["scenario"]["scenario_id"] == "google_trends_empty"
    assert trends_empty["trend_data"]["厨房用品 冷门"]["monthly_data"] == []
    assert trends_empty["trend_data"]["厨房用品 冷门"]["peak_value"] == 0

    assert supply_long_lead["scenario"]["scenario_id"] == "ali1688_high_moq_long_leadtime"
    assert supply_long_lead["suppliers"][0]["risk_flag"] == "high_moq_long_leadtime"
    assert supply_long_lead["degraded"] is not True


@pytest.mark.asyncio
async def test_data_collection_agent_publishes_raw_source_topics(monkeypatch):
    published: list[tuple[str, dict]] = []

    async def _fake_send(topic, message, key=None):
        published.append((topic, message))
        return True

    monkeypatch.setattr("src.agents.data_collection.send_message", _fake_send)

    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    await agent.call_tool("amazon_bsr", category="portable blender margin", mode="mock")
    await agent.call_tool("tiktok_products", query="viral spike blender", mode="mock")
    await agent.call_tool("google_trends", keywords=["portable blender drop"], mode="mock")
    await agent.call_tool("ali1688_supply", product_keyword="supplier unstable", mode="mock")

    raw_events = {topic: message for topic, message in published if topic.startswith("raw_")}

    assert sorted(raw_events.keys()) == ["raw_1688", "raw_amazon", "raw_tiktok", "raw_trends"]
    assert raw_events["raw_amazon"]["event_type"] == "amazon.bsr.collected"
    assert raw_events["raw_amazon"]["request"]["category"] == "portable blender margin"
    assert raw_events["raw_amazon"]["payload"]["source"] == "amazon_bsr"

    assert raw_events["raw_tiktok"]["event_type"] == "tiktok.products.collected"
    assert raw_events["raw_tiktok"]["request"]["query"] == "viral spike blender"
    assert raw_events["raw_tiktok"]["payload"]["source"] == "tiktok_products"

    assert raw_events["raw_trends"]["event_type"] == "google.trends.collected"
    assert raw_events["raw_trends"]["request"]["keywords"] == ["portable blender drop"]
    assert raw_events["raw_trends"]["payload"]["source"] == "google_trends"

    assert raw_events["raw_1688"]["event_type"] == "ali1688.supply.collected"
    assert raw_events["raw_1688"]["request"]["product_keyword"] == "supplier unstable"
    assert raw_events["raw_1688"]["payload"]["source"] == "ali1688"


@pytest.mark.asyncio
async def test_data_collection_agent_marks_real_fallback_payload_as_degraded(monkeypatch):
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    async def _fake_call_tool(name: str, **kwargs):
        payloads = {
            "amazon_bsr": {
                "source": "amazon_bsr",
                "mode": "real",
                "total_results": 1,
                "products": [{"asin": "REAL-1", "price": 29.9}],
                "degraded": True,
                "degradation_reason": "amazon_sp_api rate_limited; fallback to external_signal",
                "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            },
            "amazon_reviews": {"source": "amazon_reviews", "mode": "real", "total_analyzed": 10, "sample_reviews": [{}]},
            "amazon_price": {"source": "amazon_price", "mode": "real", "current_price": 29.9, "total_results": 1},
            "tiktok_products": {"source": "tiktok_products", "mode": "real", "total_results": 1, "products": [{"price_usd": 19.9}], "total_views": 1000},
            "tiktok_creators": {"source": "tiktok_creators", "mode": "real", "total_creators": 1, "creators": [{}]},
            "google_trends": {"source": "google_trends", "mode": "real", "total_results": 1, "trend_data": {"speaker": {"peak_value": 10}}},
            "ali1688_supply": {"source": "ali1688", "mode": "real", "total_suppliers": 1, "suppliers": [{"supplier_id": "SUP-1"}], "price_range_usd": {"min": 3, "max": 5}},
        }
        return payloads[name]

    monkeypatch.setattr(agent, "call_tool", _fake_call_tool)
    _patch_llm_gateway(monkeypatch)

    payload = await agent.execute({"query": "bluetooth speaker", "category": "bluetooth speaker", "mode": "auto"})

    assert payload["degraded"] is True
    assert payload["runtime_mode"] == "degraded"
    amazon_breakdown = next(item for item in payload["source_mode_breakdown"] if item["source"] == "amazon_bsr")
    assert amazon_breakdown["mode"] == "real"
    assert amazon_breakdown["degraded"] is True
    assert "fallback" in (amazon_breakdown["degradation_reason"] or "")
    assert amazon_breakdown["signal_context"]["provider"] == "external_signal_service"
    assert payload["external_signal_summary"]["fallback_tool_count"] == 1
    assert payload["sources_summary"]["external_signal_fallbacks"][0]["source"] == "amazon_bsr"


@pytest.mark.asyncio
async def test_data_collection_agent_auto_mode_marks_external_signal_fallback_without_source_error_as_degraded(monkeypatch):
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    async def _fake_call_tool(name: str, **kwargs):
        if name == "amazon_bsr":
            return {
                "source": "amazon_bsr",
                "mode": "real",
                "total_results": 1,
                "products": [{"asin": "REAL-1", "price": 29.9}],
                "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            }
        return {"source": name, "mode": "real", "total_results": 1, "products": [{}]}

    monkeypatch.setattr(agent, "call_tool", _fake_call_tool)
    _patch_llm_gateway(monkeypatch)

    payload = await agent.execute({"query": "bluetooth speaker", "category": "bluetooth speaker", "mode": "auto"})

    assert payload["degraded"] is True
    assert payload["runtime_mode"] == "degraded"
    assert payload["external_signal_summary"]["fallback_tool_count"] == 1
    assert payload["external_signal_summary"]["local_validation_only_sources"] == ["amazon"]


@pytest.mark.asyncio
async def test_amazon_bsr_external_signal_payload_contains_signal_readiness(monkeypatch):
    async def _fake_send(topic, message, key=None):
        return True

    async def _fake_collect_business_real_signals(self, *, query, mode="auto", required_real_sources=3):
        return {
            "query": query,
            "requested_mode": mode,
            "required_real_sources": required_real_sources,
            "sources": {
                "amazon": {
                    "source": "amazon",
                    "mode": "real",
                    "title": f"{query} amazon",
                    "source_channel": "public_web_signal",
                    "enterprise_integrated": False,
                }
            },
            "summary": {
                "real_count": 1,
                "mock_count": 0,
                "error_count": 0,
                "local_business_ready": True,
                "enterprise_ready": False,
                "readiness_tier": "local_business_ready",
                "next_actions": ["treat this bundle as local business validation only"],
            },
        }

    monkeypatch.setattr("src.agents.data_collection.send_message", _fake_send)
    monkeypatch.setattr("src.agents.data_collection.ExternalSignalService.collect_business_real_signals", _fake_collect_business_real_signals)

    agent = DataCollectionAgent(config={"quality_threshold": 0.1})
    result = await agent.call_tool("amazon_bsr", category="bluetooth speaker", mode="auto")

    assert result["signal_context"]["provider"] == "external_signal_service"
    assert result["signal_context"]["source_channel"] == "public_web_signal"
    assert result["signal_readiness"]["local_business_ready"] is True
    assert result["signal_readiness"]["enterprise_ready"] is False
    assert result["signal_readiness"]["readiness_tier"] == "local_business_ready"


@pytest.mark.asyncio
async def test_data_collection_agent_real_mode_rejects_degraded_real_payload(monkeypatch):
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    async def _fake_call_tool(name: str, **kwargs):
        if name == "amazon_bsr":
            return {
                "source": "amazon_bsr",
                "mode": "real",
                "total_results": 1,
                "products": [{"asin": "REAL-1"}],
                "degraded": True,
                "degradation_reason": "amazon_sp_api rate_limited; fallback to external_signal",
            }
        return {"source": name, "mode": "real", "total_results": 1, "products": [{}]}

    monkeypatch.setattr(agent, "call_tool", _fake_call_tool)
    _patch_llm_gateway(monkeypatch)

    with pytest.raises(ValueError) as exc_info:
        await agent.execute({"query": "bluetooth speaker", "category": "bluetooth speaker", "mode": "real"})

    assert "real mode collection failed" in str(exc_info.value)
    assert "amazon_bsr" in str(exc_info.value)


@pytest.mark.asyncio
async def test_data_collection_agent_real_mode_rejects_external_signal_fallback(monkeypatch):
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})

    async def _fake_call_tool(name: str, **kwargs):
        if name == "amazon_bsr":
            return {
                "source": "amazon_bsr",
                "mode": "real",
                "total_results": 1,
                "products": [{"asin": "REAL-1"}],
                "signal_context": {"provider": "external_signal_service", "source_name": "amazon", "source_channel": "public_web_signal"},
                "signal_readiness": {"local_business_ready": True, "enterprise_ready": False, "readiness_tier": "local_business_ready"},
            }
        return {"source": name, "mode": "real", "total_results": 1, "products": [{}]}

    monkeypatch.setattr(agent, "call_tool", _fake_call_tool)
    _patch_llm_gateway(monkeypatch)

    with pytest.raises(ValueError) as exc_info:
        await agent.execute({"query": "bluetooth speaker", "category": "bluetooth speaker", "mode": "real"})

    assert "real mode collection failed" in str(exc_info.value)
    assert "external signal fallback" in str(exc_info.value)
