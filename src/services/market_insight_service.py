from __future__ import annotations

from typing import Any

from src.services.market_trend_service import MarketTrendService


class MarketInsightService:
    def __init__(self, trend_service: MarketTrendService | None = None) -> None:
        self.trend_service = trend_service or MarketTrendService()

    async def predict(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.predict_trends(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_google_trends_aggregate(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_google_trends_aggregate(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_bsr_demand_supply_ratio(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_bsr_demand_supply_ratio(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_oms_sales_benchmark(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_oms_sales_benchmark(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_forum_topic_trends(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_forum_topic_trends(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_tiktok_tag_trends(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_tiktok_tag_trends(
            query=query,
            category=category,
            target_market=target_market,
        )

    async def get_supply_demand_lifecycle(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        return await self.trend_service.get_supply_demand_lifecycle(
            query=query,
            category=category,
            target_market=target_market,
        )
