from __future__ import annotations

import pytest
from src.services.market_trend_service import MarketTrendService


@pytest.mark.asyncio
async def test_market_trend_service_predicts_multi_source_summary(monkeypatch):
    class _FakeDataAgent:
        async def run(self, payload):
            return {
                "data": {
                    "amazon_data": {"ok": True},
                    "tiktok_data": {"ok": True},
                    "trend_data": {"ok": True},
                    "supply_chain_data": {"ok": True},
                    "quality_report": {"validity_rate": 0.95},
                }
            }

    class _FakeMarketAgent:
        async def run(self, payload):
            return {
                "data": {
                    "trends": {
                        "direction": "up",
                        "strength": 82,
                        "confidence": 88,
                        "description": "搜索热度上升",
                        "key_drivers": ["TikTok热度", "Google Trends上升"],
                    },
                    "opportunity_score": {
                        "overall_score": 78,
                        "recommendation": "strong_recommend",
                        "risk_factors": ["竞争升温"],
                    },
                }
            }

    class _FakeSignalService:
        async def collect_business_real_signals(self, *, query, mode="auto", required_real_sources=3):
            return {
                "query": query,
                "requested_mode": mode,
                "source_profile": "cross_border_ecommerce",
                "required_real_sources": required_real_sources,
                "sources": {
                    "amazon": {"mode": "real"},
                    "tiktok": {"mode": "real"},
                    "google_trends": {"mode": "real"},
                    "ali1688": {"mode": "mock"},
                    "media_news": {"mode": "mock"},
                },
                "summary": {
                    "real_count": 3,
                    "mock_count": 2,
                    "error_count": 0,
                    "all_real": False,
                    "local_business_ready": True,
                    "enterprise_ready": False,
                    "readiness_tier": "local_business_ready",
                    "source_channel_summary": {
                        "public_web_signal": {
                            "source_count": 4,
                            "real_count": 3,
                            "mock_count": 1,
                            "error_count": 0,
                            "sources": ["amazon", "tiktok", "google_trends", "ali1688"],
                        },
                        "open_api_signal": {
                            "source_count": 1,
                            "real_count": 0,
                            "mock_count": 1,
                            "error_count": 0,
                            "sources": ["media_news"],
                        },
                    },
                },
            }

    service = MarketTrendService()
    service.data_agent = _FakeDataAgent()
    service.market_agent = _FakeMarketAgent()
    service.signal_service = _FakeSignalService()

    result = await service.predict_trends(query="蓝牙耳机", category="electronics", target_market="US")
    assert result["sources"]["amazon"] is True
    assert result["sources"]["tiktok"] is True
    assert result["sources"]["google_trends"] is True
    assert result["sources"]["ali1688"] is True
    assert result["trend_prediction"]["direction"] == "up"
    assert set(result["trend_prediction"]["windows"].keys()) == {"7d", "14d", "30d"}
    assert result["trend_prediction"]["windows"]["7d"]["data_basis"]["real_sources"] == 3
    assert result["trend_prediction"]["windows"]["7d"]["data_basis"]["local_business_ready"] is True
    assert result["trend_prediction"]["windows"]["7d"]["data_basis"]["enterprise_ready"] is False
    assert result["trend_prediction"]["windows"]["7d"]["data_basis"]["readiness_tier"] == "local_business_ready"
    assert result["trend_prediction"]["trend_score"] > 0
    assert result["trend_prediction"]["product_fit_score"] > 0
    assert result["decision_bridge"]["market_summary"]["trend_direction"] == "up"
    assert result["selection_signal"]["should_enter_selection"] is True
    assert result["signal_bundle"]["summary"]["real_count"] == 3

    aggregate = await service.get_google_trends_aggregate(query="蓝牙耳机", category="electronics", target_market="US")
    assert aggregate["dataset"] == "google_trends_wide_aggregate"
    assert aggregate["growth"]["peak_heat"] >= aggregate["window_metrics"]["7d"]["avg_heat"]

    ratio = await service.get_bsr_demand_supply_ratio(query="蓝牙耳机", category="electronics", target_market="US")
    assert ratio["topic"] == "amazon_bsr_realtime"
    assert ratio["demand_supply_ratio"] > 0
    assert ratio["signal_ready"] is True
    assert ratio["signal_readiness"]["local_business_ready"] is True
    assert ratio["signal_readiness"]["enterprise_ready"] is False

    benchmark = await service.get_oms_sales_benchmark(query="蓝牙耳机", category="electronics", target_market="US")
    assert benchmark["dataset"] == "oms_sales_benchmark"
    assert "benchmark_ratio" in benchmark

    topics = await service.get_forum_topic_trends(query="蓝牙耳机", category="electronics", target_market="US")
    assert topics["dataset"] == "forum_topic_trends"
    assert topics["topic_count"] >= 1

    lifecycle = await service.get_supply_demand_lifecycle(query="蓝牙耳机", category="electronics", target_market="US")
    assert lifecycle["dataset"] == "supply_demand_lifecycle"
    assert lifecycle["lifecycle_stage"] in {"growth", "maturity", "early_or_declining"}
