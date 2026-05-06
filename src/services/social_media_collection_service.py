from __future__ import annotations

from typing import Any


class SocialMediaCollectionService:
    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        return {
            "source": "social_media_collection",
            "query": query,
            "mode": mode,
            "posts": [
                {"platform": "instagram", "title": f"{query} visual trend", "tags": ["minimal", "premium"], "image_ready": True},
                {"platform": "pinterest", "title": f"{query} inspiration pin", "tags": ["travel", "sport"], "image_ready": True},
            ],
            "multimodal_ready": True,
            "knowledge_ready": True,
        }
