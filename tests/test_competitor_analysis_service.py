from __future__ import annotations

import pytest
from src.services.competitor_analysis_service import CompetitorAnalysisService


@pytest.mark.asyncio
async def test_competitor_analysis_service_returns_monitoring_report():
    class _FakeMarketAgent:
        async def run(self, payload):
            return {
                "data": {
                    "competitor_landscape": {
                        "total_competitors": 12,
                        "top_players": [{"name": "BrandA"}],
                        "HHI": 1350,
                    },
                    "trends": {"direction": "up"},
                    "opportunity_score": {"risk_factors": ["价格竞争"]},
                }
            }

    class _FakeProductAgent:
        async def call_tool(self, tool_name, **kwargs):
            return {
                "competitor_profiles": [
                    {"name": "BrandA", "price": 29.99},
                    {"name": "BrandB", "price": 34.99},
                    {"name": "BrandC", "price": 39.99},
                ]
            }

    service = CompetitorAnalysisService()
    service.market_agent = _FakeMarketAgent()
    service.product_agent = _FakeProductAgent()

    result = await service.analyze(
        product_name="蓝牙耳机",
        category="electronics",
        target_market="US",
        monitor_config={"schedule": "daily", "alert_channel": "in_app", "watch_fields": ["price", "rating", "rank"]},
    )
    assert result["monitoring"]["enabled"] is True
    assert result["monitoring"]["schedule"] == "daily"
    assert result["competitor_landscape"]["total_competitors"] == 12
    assert result["price_comparison"]["average_competitor_price"] == 34.99
    assert {item["type"] for item in result["change_signals"]} == {"price_shift", "rating_shift", "ranking_shift"}
    assert result["alerts"]["enabled"] is True
    assert result["auto_report"]["top_alerts"]


@pytest.mark.asyncio
async def test_competitor_monitor_job_delivers_dingtalk_alert():
    class _FakeMarketAgent:
        async def run(self, payload):
            return {
                "data": {
                    "competitor_landscape": {
                        "total_competitors": 12,
                        "top_players": [{"name": "BrandA"}],
                        "HHI": 1350,
                    },
                    "trends": {"direction": "up"},
                    "opportunity_score": {"risk_factors": ["价格竞争"]},
                }
            }

    class _FakeProductAgent:
        async def call_tool(self, tool_name, **kwargs):
            return {
                "competitor_profiles": [
                    {"name": "BrandA", "price": 29.99, "rating": 4.2, "rank": 5},
                    {"name": "BrandB", "price": 39.99, "rating": 3.3, "rank": 28},
                    {"name": "BrandC", "price": 45.99, "rating": 4.0, "rank": 41},
                ]
            }

    class _FakeChannelDeliveryService:
        async def send_report(self, *, webhook_url: str, title: str, content: str, report_url: str | None = None):
            return {
                "channel": "dingtalk",
                "delivered": True,
                "title": title,
                "webhook_url": webhook_url,
                "content": content,
                "report_url": report_url,
            }

    service = CompetitorAnalysisService(channel_delivery_service=_FakeChannelDeliveryService())
    service.market_agent = _FakeMarketAgent()
    service.product_agent = _FakeProductAgent()

    result = await service.run_monitor_job(
        product_name="蓝牙耳机",
        category="electronics",
        target_market="US",
        monitor_config={
            "schedule": "daily",
            "job_type": "scheduled",
            "trigger_mode": "periodic",
            "alert_channel": "dingtalk",
            "webhook_url": "http://fake-dingtalk.local/hook",
        },
    )

    assert result["monitor_job"]["executed"] is True
    assert result["monitor_job"]["schedule"] == "daily"
    assert result["notification"]["channel"] == "dingtalk"
    assert result["notification"]["delivered"] is True
    assert result["notification"]["delivery_result"]["channel"] == "dingtalk"
