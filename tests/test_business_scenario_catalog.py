from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.services.business_scenario_catalog_service import BusinessScenarioCatalogService

SCENARIO_ROOT = Path("D:/Project/fms/artifacts/mock_scenarios")


def _read(relative: str) -> dict:
    return json.loads((SCENARIO_ROOT / relative).read_text(encoding="utf-8"))


def test_external_business_scenarios_cover_risk_and_heat_patterns():
    amazon = _read("external_api/amazon_high_refund.json")
    trends = _read("external_api/google_trends_spike_then_drop.json")
    tiktok = _read("external_api/tiktok_high_heat_low_conversion.json")

    assert amazon["response"]["products"][0]["refund_rate"] > 0.1
    assert trends["response"]["risk_flag"] == "spike_then_drop"
    assert tiktok["response"]["trends"][0]["risk_flag"] == "high_heat_low_conversion"


def test_erp_listing_draft_scenario_exists():
    listing = _read("erp/listing_draft_created.json")
    assert listing["response"]["status"] == "draft_created"
    assert listing["response"]["accepted"] is True


def test_new_business_scenarios_cover_margin_supply_and_profit_alerts():
    margin = _read("external_api/amazon_margin_pressure.json")
    supplier = _read("external_api/ali1688_high_moq_long_leadtime.json")
    profit = _read("erp/profit_trace_decline.json")

    assert margin["response"]["products"][0]["risk_flag"] == "margin_pressure"
    assert supplier["response"]["suppliers"][0]["risk_flag"] == "high_moq_long_leadtime"
    assert profit["response"]["risk_flag"] == "profit_decline"


@pytest.mark.parametrize(
    ("source", "query", "expected_scenario_id"),
    [
        ("amazon", "portable blender margin", "amazon_margin_pressure"),
        ("amazon", "亚马逊接口429限流", "amazon_rate_limited"),
        ("amazon", "便携制冰机退款差评很多", "amazon_high_refund"),
        ("tiktok", "viral spike blender", "tiktok_trend_spike"),
        ("tiktok", "TikTok 授权失败 token 失效", "tiktok_auth_failed"),
        ("google_trends", "portable blender drop", "google_trends_spike_then_drop"),
        ("google_trends", "蓝牙音箱暴涨后回落", "google_trends_spike_then_drop"),
        ("ali1688", "supplier unstable", "ali1688_supplier_unstable"),
        ("ali1688", "1688 供应商不稳定 波动很大", "ali1688_supplier_unstable"),
        ("tiktok", "auth token failed", "tiktok_auth_failed"),
    ],
)
def test_business_scenario_catalog_resolves_runtime_queries(
    source: str,
    query: str,
    expected_scenario_id: str,
):
    service = BusinessScenarioCatalogService(root=SCENARIO_ROOT / "external_api")

    scenario = service.resolve_external_scenario(source, query)

    assert scenario is not None
    assert scenario["scenario_id"] == expected_scenario_id
