from __future__ import annotations

from typing import Any

from src.services.external_signal_service import ExternalSignalService


class PatentSignalService:
    def __init__(self, signal_service: ExternalSignalService | None = None) -> None:
        self.signal_service = signal_service or ExternalSignalService()

    async def collect(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        keyword = query.strip()
        search_url = f"https://patents.google.com/?q={keyword.replace(' ', '+')}"
        title_snapshot = await self.signal_service._fetch_google_trends(keyword) if mode != "mock" else {"mode": "mock", "query": keyword}
        return {
            "source": "patent_public_pages",
            "query": keyword,
            "mode": mode,
            "search_url": search_url,
            "snapshot": title_snapshot,
            "risk_checks": ["patent-similarity", "trademark-conflict", "legal-status"],
            "knowledge_ready": True,
        }
