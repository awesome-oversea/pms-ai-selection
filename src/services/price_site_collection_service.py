from __future__ import annotations

from typing import Any


class PriceSiteCollectionService:
    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        return {
            "source": "price_site_collection",
            "query": query,
            "mode": mode,
            "price_curves": [
                {"site": "camelcamelcamel-compatible", "period": "90d", "trend": "up", "price_low": 24.9, "price_high": 39.9},
                {"site": "price-tracker-compatible", "period": "180d", "trend": "stable", "price_low": 22.9, "price_high": 41.9},
            ],
            "history_ready": True,
            "knowledge_ready": True,
        }
