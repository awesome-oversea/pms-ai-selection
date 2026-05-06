from __future__ import annotations

import pytest

from src.services.market_insight_service import MarketInsightService


@pytest.mark.asyncio
async def test_market_insight_service_delegates_to_market_trend_service() -> None:
    class _FakeTrendService:
        async def predict_trends(self, *, query, category, target_market="US"):
            return {
                "query": query,
                "category": category,
                "target_market": target_market,
                "selection_signal": {"recommended_action": "create_selection_task"},
            }

    service = MarketInsightService(trend_service=_FakeTrendService())
    result = await service.predict(query="bluetooth headset", category="electronics", target_market="US")

    assert result["query"] == "bluetooth headset"
    assert result["selection_signal"]["recommended_action"] == "create_selection_task"
