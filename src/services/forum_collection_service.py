from __future__ import annotations

from typing import Any


class ForumCollectionService:
    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        return {
            "source": "forum_collection",
            "query": query,
            "mode": mode,
            "threads": [
                {"platform": "reddit", "topic": f"{query} trend discussion", "heat": 87, "sentiment": "mixed"},
                {"platform": "sellercentral", "topic": f"{query} complaint topic", "heat": 72, "sentiment": "negative"},
            ],
            "topic_ready": True,
            "knowledge_ready": True,
        }
