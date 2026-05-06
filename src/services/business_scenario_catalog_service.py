from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def _default_scenario_root() -> Path:
    return Path(__file__).resolve().parents[2] / "artifacts" / "mock_scenarios" / "external_api"


@dataclass(frozen=True)
class ScenarioRule:
    scenario_id: str
    keywords: tuple[str, ...]


class BusinessScenarioCatalogService:
    EXTERNAL_RULES: dict[str, tuple[ScenarioRule, ...]] = {
        "amazon": (
            ScenarioRule("amazon_rate_limited", ("rate limit", "rate limited", "too many requests", "429", "限流", "频控")),
            ScenarioRule("amazon_high_refund", ("refund", "return", "complaint", "ice maker", "退款", "退货", "差评")),
            ScenarioRule("amazon_margin_pressure", ("margin", "profit", "acos", "ad cost", "blender", "利润", "广告费")),
            ScenarioRule("amazon_hot_selling", ("hot", "viral", "best seller", "爆款", "热卖", "sealer")),
        ),
        "tiktok": (
            ScenarioRule("tiktok_auth_failed", ("auth", "oauth", "token", "鉴权", "授权")),
            ScenarioRule("tiktok_high_heat_low_conversion", ("low conversion", "ice maker", "高热低转化", "转化低")),
            ScenarioRule("tiktok_trend_spike", ("spike", "viral", "blender", "爆发", "暴涨", "爆款")),
        ),
        "google_trends": (
            ScenarioRule("google_trends_empty", ("empty", "no demand", "冷门", "空结果")),
            ScenarioRule("google_trends_spike_then_drop", ("spike then drop", "drop", "decline", "回落", "暴涨后回落")),
            ScenarioRule("google_trends_growth", ("growth", "rising", "增长", "上升", "trend")),
        ),
        "ali1688": (
            ScenarioRule("ali1688_supplier_unstable", ("unstable", "supplier", "波动", "不稳定", "供应商异常")),
            ScenarioRule("ali1688_high_moq_long_leadtime", ("moq", "lead time", "交期", "起订量", "高moq")),
        ),
    }

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_scenario_root()

    @staticmethod
    def _normalize_query(value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    @lru_cache(maxsize=64)
    def load_external_scenario(self, scenario_id: str) -> dict[str, Any]:
        path = self.root / f"{scenario_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def resolve_external_scenario(self, source: str, query: str) -> dict[str, Any] | None:
        normalized_source = (source or "").strip().lower()
        normalized_query = self._normalize_query(query)
        for rule in self.EXTERNAL_RULES.get(normalized_source, ()):
            if any(keyword in normalized_query for keyword in rule.keywords):
                return self.load_external_scenario(rule.scenario_id)
        return None
