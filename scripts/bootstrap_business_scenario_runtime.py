from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "bootstrap-business-scenario-runtime-32chars")
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.data_collection import DataCollectionAgent
from src.infrastructure.kafka import close_kafka


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_item(response: dict[str, Any]) -> dict[str, Any]:
    for key in ("products", "suppliers"):
        items = response.get(key) or []
        if items:
            return dict(items[0])
    return {}


def _extract_actual(response: dict[str, Any]) -> dict[str, Any]:
    trend_data = response.get("trend_data") or {}
    return {
        "scenario_id": (response.get("scenario") or {}).get("scenario_id"),
        "degraded": response.get("degraded"),
        "degradation_reason": response.get("degradation_reason"),
        "total_results": response.get("total_results"),
        "total_views": response.get("total_views"),
        "total_suppliers": response.get("total_suppliers"),
        "avg_lead_time": response.get("avg_lead_time"),
        "growth_rate_30d": response.get("growth_rate_30d"),
        "growth_rate_7d": response.get("growth_rate_7d"),
        "risk_flags": [item.get("risk_flag") for item in (response.get("products") or response.get("suppliers") or []) if item.get("risk_flag")],
        "trend_directions": {keyword: values.get("trend_direction") for keyword, values in trend_data.items()},
        "peak_values": {keyword: values.get("peak_value") for keyword, values in trend_data.items()},
        "monthly_data_lengths": {keyword: len(values.get("monthly_data") or []) for keyword, values in trend_data.items()},
    }


def _check(name: str, passed: bool, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "expected": expected,
        "actual": actual,
    }


def _record_case(case_id: str, tool: str, kwargs: dict[str, Any], response: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "tool": tool,
        "kwargs": kwargs,
        "accepted": all(item["passed"] for item in checks),
        "actual": _extract_actual(response),
        "checks": checks,
    }


async def _run() -> dict[str, Any]:
    agent = DataCollectionAgent(config={"quality_threshold": 0.1})
    cases: list[dict[str, Any]] = []

    amazon_high_refund_kwargs = {"category": "portable ice maker refund complaint", "mode": "mock"}
    amazon_high_refund = await agent.call_tool("amazon_bsr", **amazon_high_refund_kwargs)
    amazon_high_refund_item = _first_item(amazon_high_refund)
    cases.append(
        _record_case(
            "amazon_high_refund",
            "amazon_bsr",
            amazon_high_refund_kwargs,
            amazon_high_refund,
            [
                _check("scenario_id", (amazon_high_refund.get("scenario") or {}).get("scenario_id") == "amazon_high_refund", "amazon_high_refund", (amazon_high_refund.get("scenario") or {}).get("scenario_id")),
                _check("risk_flag", amazon_high_refund_item.get("risk_flag") == "high_refund", "high_refund", amazon_high_refund_item.get("risk_flag")),
                _check("refund_rate_threshold", float(amazon_high_refund_item.get("refund_rate") or 0) > 0.1, ">0.1", amazon_high_refund_item.get("refund_rate")),
                _check("stable_degraded_field", amazon_high_refund.get("degraded") is False, False, amazon_high_refund.get("degraded")),
            ],
        )
    )

    amazon_hot_selling_kwargs = {"category": "kitchen sealer best seller", "mode": "mock"}
    amazon_hot_selling = await agent.call_tool("amazon_bsr", **amazon_hot_selling_kwargs)
    amazon_hot_selling_item = _first_item(amazon_hot_selling)
    cases.append(
        _record_case(
            "amazon_hot_selling",
            "amazon_bsr",
            amazon_hot_selling_kwargs,
            amazon_hot_selling,
            [
                _check("scenario_id", (amazon_hot_selling.get("scenario") or {}).get("scenario_id") == "amazon_hot_selling", "amazon_hot_selling", (amazon_hot_selling.get("scenario") or {}).get("scenario_id")),
                _check("risk_flag", amazon_hot_selling_item.get("risk_flag") == "hot_selling", "hot_selling", amazon_hot_selling_item.get("risk_flag")),
                _check("has_results", int(amazon_hot_selling.get("total_results") or 0) >= 1, ">=1", amazon_hot_selling.get("total_results")),
                _check("stable_degraded_field", amazon_hot_selling.get("degraded") is False, False, amazon_hot_selling.get("degraded")),
            ],
        )
    )

    amazon_rate_limited_kwargs = {"category": "Amazon 429 limit", "mode": "mock"}
    amazon_rate_limited = await agent.call_tool("amazon_bsr", **amazon_rate_limited_kwargs)
    cases.append(
        _record_case(
            "amazon_rate_limited",
            "amazon_bsr",
            amazon_rate_limited_kwargs,
            amazon_rate_limited,
            [
                _check("scenario_id", (amazon_rate_limited.get("scenario") or {}).get("scenario_id") == "amazon_rate_limited", "amazon_rate_limited", (amazon_rate_limited.get("scenario") or {}).get("scenario_id")),
                _check("degraded", amazon_rate_limited.get("degraded") is True, True, amazon_rate_limited.get("degraded")),
                _check("degradation_reason", amazon_rate_limited.get("degradation_reason") == "mock rate_limited scenario", "mock rate_limited scenario", amazon_rate_limited.get("degradation_reason")),
                _check("empty_result", int(amazon_rate_limited.get("total_results") or 0) == 0, 0, amazon_rate_limited.get("total_results")),
            ],
        )
    )

    tiktok_auth_failed_kwargs = {"query": "auth token failed", "mode": "mock"}
    tiktok_auth_failed = await agent.call_tool("tiktok_products", **tiktok_auth_failed_kwargs)
    cases.append(
        _record_case(
            "tiktok_auth_failed",
            "tiktok_products",
            tiktok_auth_failed_kwargs,
            tiktok_auth_failed,
            [
                _check("scenario_id", (tiktok_auth_failed.get("scenario") or {}).get("scenario_id") == "tiktok_auth_failed", "tiktok_auth_failed", (tiktok_auth_failed.get("scenario") or {}).get("scenario_id")),
                _check("degraded", tiktok_auth_failed.get("degraded") is True, True, tiktok_auth_failed.get("degraded")),
                _check("degradation_reason", tiktok_auth_failed.get("degradation_reason") == "mock auth_failed scenario", "mock auth_failed scenario", tiktok_auth_failed.get("degradation_reason")),
                _check("empty_result", int(tiktok_auth_failed.get("total_results") or 0) == 0, 0, tiktok_auth_failed.get("total_results")),
            ],
        )
    )

    tiktok_high_heat_low_conversion_kwargs = {"query": "portable ice maker high heat low conversion", "mode": "mock"}
    tiktok_high_heat_low_conversion = await agent.call_tool("tiktok_products", **tiktok_high_heat_low_conversion_kwargs)
    tiktok_high_heat_low_conversion_item = _first_item(tiktok_high_heat_low_conversion)
    cases.append(
        _record_case(
            "tiktok_high_heat_low_conversion",
            "tiktok_products",
            tiktok_high_heat_low_conversion_kwargs,
            tiktok_high_heat_low_conversion,
            [
                _check("scenario_id", (tiktok_high_heat_low_conversion.get("scenario") or {}).get("scenario_id") == "tiktok_high_heat_low_conversion", "tiktok_high_heat_low_conversion", (tiktok_high_heat_low_conversion.get("scenario") or {}).get("scenario_id")),
                _check("risk_flag", tiktok_high_heat_low_conversion_item.get("risk_flag") == "high_heat_low_conversion", "high_heat_low_conversion", tiktok_high_heat_low_conversion_item.get("risk_flag")),
                _check("conversion_rate", float(tiktok_high_heat_low_conversion_item.get("estimated_conversion_rate") or 0) == 0.011, 0.011, tiktok_high_heat_low_conversion_item.get("estimated_conversion_rate")),
                _check("stable_degraded_field", tiktok_high_heat_low_conversion.get("degraded") is False, False, tiktok_high_heat_low_conversion.get("degraded")),
            ],
        )
    )

    tiktok_trend_spike_kwargs = {"query": "viral spike blender", "mode": "mock"}
    tiktok_trend_spike = await agent.call_tool("tiktok_products", **tiktok_trend_spike_kwargs)
    tiktok_trend_spike_item = _first_item(tiktok_trend_spike)
    cases.append(
        _record_case(
            "tiktok_trend_spike",
            "tiktok_products",
            tiktok_trend_spike_kwargs,
            tiktok_trend_spike,
            [
                _check("scenario_id", (tiktok_trend_spike.get("scenario") or {}).get("scenario_id") == "tiktok_trend_spike", "tiktok_trend_spike", (tiktok_trend_spike.get("scenario") or {}).get("scenario_id")),
                _check("content_title", tiktok_trend_spike_item.get("title") == "#portableblender", "#portableblender", tiktok_trend_spike_item.get("title")),
                _check("view_signal", int(tiktok_trend_spike.get("total_views") or 0) > 0, ">0", tiktok_trend_spike.get("total_views")),
                _check("stable_degraded_field", tiktok_trend_spike.get("degraded") is False, False, tiktok_trend_spike.get("degraded")),
            ],
        )
    )

    google_trends_growth_kwargs = {"keywords": ["bluetooth speaker growth"], "mode": "mock"}
    google_trends_growth = await agent.call_tool("google_trends", **google_trends_growth_kwargs)
    google_growth_entry = (google_trends_growth.get("trend_data") or {}).get("bluetooth speaker growth", {})
    cases.append(
        _record_case(
            "google_trends_growth",
            "google_trends",
            google_trends_growth_kwargs,
            google_trends_growth,
            [
                _check("scenario_id", (google_trends_growth.get("scenario") or {}).get("scenario_id") == "google_trends_growth", "google_trends_growth", (google_trends_growth.get("scenario") or {}).get("scenario_id")),
                _check("trend_direction", google_growth_entry.get("trend_direction") == "up", "up", google_growth_entry.get("trend_direction")),
                _check("growth_rate_30d", float(google_trends_growth.get("growth_rate_30d") or 0) > 0, ">0", google_trends_growth.get("growth_rate_30d")),
                _check("stable_degraded_field", google_trends_growth.get("degraded") is False, False, google_trends_growth.get("degraded")),
            ],
        )
    )

    google_trends_empty_kwargs = {"keywords": ["kitchen product no demand"], "mode": "mock"}
    google_trends_empty = await agent.call_tool("google_trends", **google_trends_empty_kwargs)
    google_empty_entry = (google_trends_empty.get("trend_data") or {}).get("kitchen product no demand", {})
    cases.append(
        _record_case(
            "google_trends_empty",
            "google_trends",
            google_trends_empty_kwargs,
            google_trends_empty,
            [
                _check("scenario_id", (google_trends_empty.get("scenario") or {}).get("scenario_id") == "google_trends_empty", "google_trends_empty", (google_trends_empty.get("scenario") or {}).get("scenario_id")),
                _check("monthly_data_empty", google_empty_entry.get("monthly_data") == [], [], google_empty_entry.get("monthly_data")),
                _check("peak_value", int(google_empty_entry.get("peak_value") or 0) == 0, 0, google_empty_entry.get("peak_value")),
                _check("stable_degraded_field", google_trends_empty.get("degraded") is False, False, google_trends_empty.get("degraded")),
            ],
        )
    )

    google_trends_spike_drop_kwargs = {"keywords": ["portable blender drop"], "mode": "mock"}
    google_trends_spike_drop = await agent.call_tool("google_trends", **google_trends_spike_drop_kwargs)
    google_spike_drop_entry = (google_trends_spike_drop.get("trend_data") or {}).get("portable blender drop", {})
    cases.append(
        _record_case(
            "google_trends_spike_then_drop",
            "google_trends",
            google_trends_spike_drop_kwargs,
            google_trends_spike_drop,
            [
                _check("scenario_id", (google_trends_spike_drop.get("scenario") or {}).get("scenario_id") == "google_trends_spike_then_drop", "google_trends_spike_then_drop", (google_trends_spike_drop.get("scenario") or {}).get("scenario_id")),
                _check("trend_direction", google_spike_drop_entry.get("trend_direction") == "down", "down", google_spike_drop_entry.get("trend_direction")),
                _check("risk_flag", google_spike_drop_entry.get("risk_flag") == "spike_then_drop", "spike_then_drop", google_spike_drop_entry.get("risk_flag")),
                _check("growth_rate_7d", float(google_trends_spike_drop.get("growth_rate_7d") or 0) < 0, "<0", google_trends_spike_drop.get("growth_rate_7d")),
            ],
        )
    )

    ali1688_supplier_unstable_kwargs = {"product_keyword": "supplier unstable", "mode": "mock"}
    ali1688_supplier_unstable = await agent.call_tool("ali1688_supply", **ali1688_supplier_unstable_kwargs)
    ali1688_supplier_unstable_item = _first_item(ali1688_supplier_unstable)
    cases.append(
        _record_case(
            "ali1688_supplier_unstable",
            "ali1688_supply",
            ali1688_supplier_unstable_kwargs,
            ali1688_supplier_unstable,
            [
                _check("scenario_id", (ali1688_supplier_unstable.get("scenario") or {}).get("scenario_id") == "ali1688_supplier_unstable", "ali1688_supplier_unstable", (ali1688_supplier_unstable.get("scenario") or {}).get("scenario_id")),
                _check("degraded", ali1688_supplier_unstable.get("degraded") is True, True, ali1688_supplier_unstable.get("degraded")),
                _check("degradation_reason", ali1688_supplier_unstable.get("degradation_reason") == "mock partial_data scenario", "mock partial_data scenario", ali1688_supplier_unstable.get("degradation_reason")),
                _check("risk_flag", ali1688_supplier_unstable_item.get("risk_flag") == "supplier_unstable", "supplier_unstable", ali1688_supplier_unstable_item.get("risk_flag")),
            ],
        )
    )

    ali1688_high_moq_kwargs = {"product_keyword": "high moq lead time", "mode": "mock"}
    ali1688_high_moq = await agent.call_tool("ali1688_supply", **ali1688_high_moq_kwargs)
    ali1688_high_moq_item = _first_item(ali1688_high_moq)
    cases.append(
        _record_case(
            "ali1688_high_moq_long_leadtime",
            "ali1688_supply",
            ali1688_high_moq_kwargs,
            ali1688_high_moq,
            [
                _check("scenario_id", (ali1688_high_moq.get("scenario") or {}).get("scenario_id") == "ali1688_high_moq_long_leadtime", "ali1688_high_moq_long_leadtime", (ali1688_high_moq.get("scenario") or {}).get("scenario_id")),
                _check("risk_flag", ali1688_high_moq_item.get("risk_flag") == "high_moq_long_leadtime", "high_moq_long_leadtime", ali1688_high_moq_item.get("risk_flag")),
                _check("avg_lead_time", float(ali1688_high_moq.get("avg_lead_time") or 0) > 20, ">20", ali1688_high_moq.get("avg_lead_time")),
                _check("stable_degraded_field", ali1688_high_moq.get("degraded") is False, False, ali1688_high_moq.get("degraded")),
            ],
        )
    )

    accepted_cases = [case for case in cases if case["accepted"]]
    payload = {
        "accepted": len(accepted_cases) == len(cases),
        "total_cases": len(cases),
        "passed_cases": len(accepted_cases),
        "failed_cases": len(cases) - len(accepted_cases),
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": cases,
    }
    artifact_path = PROJECT_ROOT / "artifacts" / "ops" / "business_scenario_runtime_acceptance.json"
    _write_json(artifact_path, payload)
    await close_kafka()
    return payload


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
