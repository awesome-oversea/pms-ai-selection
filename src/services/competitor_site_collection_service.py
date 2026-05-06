from __future__ import annotations

from typing import Any


class CompetitorSiteCollectionService:
    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        return {
            "source": "competitor_site_collection",
            "query": query,
            "mode": mode,
            "pages": [
                {"site": "brand-site", "title": f"{query} 官方站产品页", "price": None, "promotion": "seasonal-discount", "render_mode": "playwright-compatible"},
                {"site": "shopify-store", "title": f"{query} 竞品详情页", "price": None, "promotion": "bundle-offer", "render_mode": "playwright-compatible"},
            ],
            "dynamic_render_ready": True,
            "knowledge_ready": True,
        }
