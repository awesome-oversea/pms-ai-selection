from __future__ import annotations

import httpx
import pytest
from src.services.external_signal_service import ExternalSignalService


@pytest.mark.asyncio
async def test_collect_rss_signals_falls_back_to_mock_and_publishes(monkeypatch):
    service = ExternalSignalService()
    published: dict[str, object] = {}

    async def _fake_fetch_media_rss(query: str):
        raise RuntimeError("rss unavailable")

    async def _fake_send_message(topic: str, message: dict, key=None):
        published["topic"] = topic
        published["message"] = message
        return True

    monkeypatch.setattr(service, "_fetch_media_rss", _fake_fetch_media_rss)
    monkeypatch.setattr("src.services.external_signal_service.send_message", _fake_send_message)

    result = await service.collect_rss_signals(query="蓝牙耳机", mode="auto")
    assert result["source"] == "media_rss"
    assert result["mode"] == "mock"
    assert result["query"] == "蓝牙耳机"
    assert result["top_articles"][0]["title"] == "mock rss article for 蓝牙耳机"
    assert result["fallback_reason"] == "rss unavailable"
    assert published["topic"] == "pms-data-collection"
    assert published["message"]["event_type"] == "rss.collected"


@pytest.mark.asyncio
async def test_collect_gdelt_event_signals_classifies_and_associates_categories(monkeypatch):
    service = ExternalSignalService()
    published: dict[str, object] = {}

    async def _fake_fetch_media_news(query: str):
        return {
            "source": "media_news",
            "mode": "real",
            "query": query,
            "url": "https://api.gdeltproject.org/api/v2/doc/doc?query=bluetooth%20speaker",
            "total_count": 2,
            "top_articles": [
                {
                    "title": "US tariff pressure hits bluetooth speaker imports",
                    "url": "https://example.com/trade",
                    "sourceCountry": "US",
                    "seendate": "20260419",
                },
                {
                    "title": "Retail demand recovery lifts wireless audio sales",
                    "url": "https://example.com/economic",
                    "sourceCountry": "US",
                    "seendate": "20260419",
                },
            ],
        }

    async def _fake_send_message(topic: str, message: dict, key=None):
        published["topic"] = topic
        published["message"] = message
        return True

    monkeypatch.setattr(service, "_fetch_media_news", _fake_fetch_media_news)
    monkeypatch.setattr("src.services.external_signal_service.send_message", _fake_send_message)

    result = await service.collect_gdelt_event_signals(query="bluetooth speaker", mode="real")

    assert result["mode"] == "real"
    assert result["classification_summary"]["trade"] == 1
    assert result["classification_summary"]["economic"] == 1
    assert result["degradation"]["degraded"] is False
    assert result["top_articles"][0]["event_category"] == "trade"
    assert any(item["category"] == "electronics" for item in result["category_associations"])
    assert published["topic"] == "raw_news"
    assert published["message"]["event_type"] == "gdelt.collected"
    assert published["message"]["query"] == "bluetooth speaker"
    assert published["message"]["payload"]["source"] == "media_news"


@pytest.mark.asyncio
async def test_collect_gdelt_event_signals_auto_falls_back_with_degradation_evidence(monkeypatch):
    service = ExternalSignalService()

    async def _fake_fetch_media_news(query: str):
        request = httpx.Request("GET", service._gdelt_url(query))
        response = httpx.Response(status_code=429, request=request)
        raise httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)

    monkeypatch.setattr(service, "_fetch_media_news", _fake_fetch_media_news)

    result = await service.collect_gdelt_event_signals(query="bluetooth speaker", mode="auto")

    assert result["mode"] == "mock"
    assert result["degradation"]["degraded"] is True
    assert result["degradation"]["http_status"] == 429
    assert result["classification_summary"]["classified_count"] == 2
    assert result["business_summary"]["market_bias"] in {"risk-off", "watchlist", "opportunity"}


@pytest.mark.asyncio
async def test_collect_business_real_signals_separates_local_business_ready_from_enterprise_ready(monkeypatch):
    service = ExternalSignalService()

    async def _fake_real_web_signal(query: str):
        return {"source": "amazon", "mode": "real", "query": query, "title": f"{query} signal"}

    async def _fake_tiktok(query: str):
        return {"source": "tiktok", "mode": "real", "query": query, "title": f"{query} tiktok"}

    async def _fake_google_trends(query: str):
        return {"source": "google_trends", "mode": "real", "query": query, "title": f"{query} trends"}

    async def _fake_ali1688(query: str):
        raise RuntimeError("ali1688 throttled")

    async def _fake_gdelt(*, query: str, mode: str = "auto"):
        return {
            "source": "media_news",
            "mode": "real",
            "query": query,
            "top_articles": [{"title": f"{query} article"}],
        }

    monkeypatch.setattr(service, "_fetch_amazon", _fake_real_web_signal)
    monkeypatch.setattr(service, "_fetch_tiktok", _fake_tiktok)
    monkeypatch.setattr(service, "_fetch_google_trends", _fake_google_trends)
    monkeypatch.setattr(service, "_fetch_ali1688", _fake_ali1688)
    monkeypatch.setattr(service, "collect_gdelt_event_signals", _fake_gdelt)

    result = await service.collect_business_real_signals(query="bluetooth speaker", mode="auto", required_real_sources=3)

    summary = result["summary"]
    assert summary["real_count"] == 4
    assert summary["mock_count"] == 1
    assert summary["error_count"] == 0
    assert summary["local_business_ready"] is True
    assert summary["enterprise_ready"] is False
    assert summary["readiness_tier"] == "local_business_ready"
    assert summary["source_channel_summary"]["public_web_signal"]["real_count"] == 3
    assert summary["source_channel_summary"]["open_api_signal"]["real_count"] == 1
    assert "treat this bundle as local business validation only" in summary["next_actions"][-1]
