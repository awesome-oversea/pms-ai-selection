from __future__ import annotations

from typing import Any

from src.services.external_signal_service import ExternalSignalService


class MediaBlogCollectionService:
    def __init__(self, signal_service: ExternalSignalService | None = None) -> None:
        self.signal_service = signal_service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        rss_bundle = await self.signal_service.build_rss_subscription_bundle(query=query, mode=mode)
        payload = rss_bundle.get("payload") or {}
        articles = list(payload.get("top_articles") or [])
        enriched_articles = []
        for item in articles:
            title = str(item.get("title") or "")
            enriched_articles.append(
                {
                    **item,
                    "summary": title[:80],
                    "knowledge_tags": [query, "industry-media", "blog-review"],
                    "ingest_ready": True,
                }
            )
        return {
            "source": "media_blog_collection",
            "query": query,
            "mode": mode,
            "article_count": len(enriched_articles),
            "articles": enriched_articles,
            "knowledge_ready": len(enriched_articles) > 0,
            "rss_subscription": rss_bundle,
        }
