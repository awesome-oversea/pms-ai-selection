from __future__ import annotations

from typing import Any

from src.agents.market_insight import MarketInsightAgent
from src.agents.product_planner import ProductPlannerAgent
from src.services.channel_delivery_service import ChannelDeliveryService
import contextlib


class CompetitorAnalysisService:
    def __init__(self, channel_delivery_service: ChannelDeliveryService | None = None) -> None:
        self.market_agent = MarketInsightAgent()
        self.product_agent = ProductPlannerAgent()
        self.channel_delivery_service = channel_delivery_service or ChannelDeliveryService()

    @staticmethod
    def _build_window_alerts(samples: list[dict[str, Any]], *, negative_rate_threshold: float = 0.2, price_change_threshold: float = 0.12) -> dict[str, Any]:
        normalized = [item for item in samples if isinstance(item, dict)]
        if not normalized:
            return {
                "window": {"sample_count": 0, "negative_rate": 0.0, "price_change_rate": 0.0},
                "alerts": [],
                "alert_triggered": False,
            }
        negative_keywords = {"bad", "broken", "refund", "complaint", "差评", "退货", "投诉", "破损", "问题"}
        negative_count = 0
        prices: list[float] = []
        for item in normalized:
            text = f"{item.get('review') or item.get('comment') or item.get('feedback') or ''}".lower()
            sentiment = str(item.get("sentiment") or "").lower()
            if sentiment == "negative" or any(keyword in text for keyword in negative_keywords):
                negative_count += 1
            if item.get("price") is not None:
                with contextlib.suppress(TypeError, ValueError):
                    prices.append(float(item.get("price")))
        negative_rate = negative_count / max(len(normalized), 1)
        price_change_rate = 0.0
        if len(prices) >= 2 and prices[0] > 0:
            price_change_rate = (prices[-1] - prices[0]) / prices[0]
        alerts = []
        if negative_rate > negative_rate_threshold:
            alerts.append({"type": "negative_review_spike", "severity": "high", "metric": {"negative_rate": round(negative_rate, 4), "threshold": negative_rate_threshold}})
        if abs(price_change_rate) > price_change_threshold:
            alerts.append({"type": "price_change_spike", "severity": "medium", "metric": {"price_change_rate": round(price_change_rate, 4), "threshold": price_change_threshold}})
        return {
            "window": {
                "sample_count": len(normalized),
                "negative_rate": round(negative_rate, 4),
                "price_change_rate": round(price_change_rate, 4),
            },
            "alerts": alerts,
            "alert_triggered": bool(alerts),
        }

    @staticmethod
    def _build_change_signals(competitor_profiles: list[dict[str, Any]], trends: dict[str, Any]) -> list[dict[str, Any]]:
        if not competitor_profiles:
            return [
                {"type": "price_shift", "severity": "low", "description": "竞品价格数据不足"},
                {"type": "rating_shift", "severity": "low", "description": "竞品评分数据不足"},
                {"type": "ranking_shift", "severity": "low", "description": "竞品排名数据不足"},
            ]

        prices = [float(item.get("price", 0) or 0) for item in competitor_profiles if item.get("price") is not None]
        ratings = [float(item.get("rating", 0) or 0) for item in competitor_profiles if item.get("rating") is not None]
        ranks = [float(item.get("rank", 0) or 0) for item in competitor_profiles if item.get("rank") is not None]

        price_delta = (max(prices) - min(prices)) if len(prices) >= 2 else 0.0
        rating_delta = (max(ratings) - min(ratings)) if len(ratings) >= 2 else 0.0
        rank_delta = (max(ranks) - min(ranks)) if len(ranks) >= 2 else 0.0
        trend_direction = trends.get("direction", "stable") if isinstance(trends, dict) else "stable"

        return [
            {
                "type": "price_shift",
                "severity": "high" if price_delta >= 10 else ("medium" if price_delta >= 5 else "low"),
                "description": f"竞品价格波动区间 {round(price_delta, 2)}",
                "metric": {"delta": round(price_delta, 2), "unit": "usd"},
            },
            {
                "type": "rating_shift",
                "severity": "medium" if rating_delta >= 0.8 else "low",
                "description": f"竞品评分波动区间 {round(rating_delta, 2)}",
                "metric": {"delta": round(rating_delta, 2), "unit": "score"},
            },
            {
                "type": "ranking_shift",
                "severity": "high" if rank_delta >= 30 else ("medium" if rank_delta >= 10 else "low"),
                "description": f"竞品排名波动区间 {round(rank_delta, 2)}，市场趋势 {trend_direction}",
                "metric": {"delta": round(rank_delta, 2), "unit": "rank"},
            },
        ]

    async def analyze(
        self,
        *,
        product_name: str,
        category: str,
        target_market: str = "US",
        monitor_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market_result = await self.market_agent.run(
            {
                "query": product_name,
                "category": category,
                "target_market": target_market,
            }
        )
        diff_result = await self.product_agent.call_tool(
            "competitor_diff",
            category=category,
            competitors=[f"{category} Brand A", f"{category} Brand B", f"{category} Brand C"],
        )

        market_data = market_result.get("data", market_result)
        landscape = market_data.get("competitor_landscape", {})
        trends = market_data.get("trends", {})
        competitor_profiles = diff_result.get("competitor_profiles", []) if isinstance(diff_result, dict) else []

        avg_competitor_price = 0.0
        if competitor_profiles:
            avg_competitor_price = round(
                sum(float(item.get("price", 0) or 0) for item in competitor_profiles) / len(competitor_profiles),
                2,
            )

        monitor_cfg = monitor_config or {}
        change_signals = self._build_change_signals(competitor_profiles, trends if isinstance(trends, dict) else {})
        alert_items = [item for item in change_signals if item.get("severity") in {"medium", "high"}]
        auto_report = {
            "summary": f"已完成 {category} 类目竞品监控，识别 {len(alert_items)} 个需要关注的变化信号。",
            "top_alerts": alert_items[:3],
            "recommended_actions": [
                "跟踪价格变化",
                "跟踪评分下滑风险",
                "跟踪头部玩家排名变化",
            ],
        }
        alerts = {
            "enabled": True,
            "channel": monitor_cfg.get("alert_channel", "in_app"),
            "count": len(alert_items),
            "items": alert_items[:5],
        }

        return {
            "product_name": product_name,
            "category": category,
            "target_market": target_market,
            "monitoring": {
                "enabled": True,
                "sources": ["market_insight", "competitor_diff"],
                "competitor_count": landscape.get("total_competitors", 0),
                "schedule": monitor_cfg.get("schedule", "daily"),
                "watch_fields": monitor_cfg.get("watch_fields", ["price", "rating", "rank"]),
            },
            "competitor_landscape": landscape,
            "price_comparison": {
                "average_competitor_price": avg_competitor_price,
                "profiles": competitor_profiles,
            },
            "change_signals": change_signals,
            "analysis_report": {
                "summary": f"已完成 {category} 类目竞品分析，共监控 {landscape.get('total_competitors', 0)} 个竞品。",
                "key_risks": market_data.get("opportunity_score", {}).get("risk_factors", []),
                "recommended_actions": [
                    "跟踪价格变化",
                    "跟踪头部玩家集中度",
                    "结合市场趋势调整差异化策略",
                ],
            },
            "auto_report": auto_report,
            "alerts": alerts,
        }

    async def run_monitor_job(
        self,
        *,
        product_name: str,
        category: str,
        target_market: str = "US",
        monitor_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        monitor_cfg = monitor_config or {}
        result = await self.analyze(
            product_name=product_name,
            category=category,
            target_market=target_market,
            monitor_config=monitor_cfg,
        )
        window_runtime = self._build_window_alerts(
            list(monitor_cfg.get("samples") or []),
            negative_rate_threshold=float(monitor_cfg.get("negative_rate_threshold", 0.2)),
            price_change_threshold=float(monitor_cfg.get("price_change_threshold", 0.12)),
        )
        if window_runtime["alerts"]:
            result["alerts"]["items"] = [*window_runtime["alerts"], *result["alerts"].get("items", [])]
            result["alerts"]["count"] = len(result["alerts"]["items"])

        job_summary = {
            "job_type": monitor_cfg.get("job_type", "scheduled"),
            "schedule": result["monitoring"].get("schedule", "daily"),
            "trigger_mode": monitor_cfg.get("trigger_mode", "periodic"),
            "executed": True,
        }

        delivery_result: dict[str, Any] | None = None
        webhook_url = monitor_cfg.get("webhook_url")
        alert_channel = monitor_cfg.get("alert_channel", "in_app")
        if webhook_url and alert_channel == "dingtalk" and result["alerts"]["count"] > 0:
            alert_lines = [f"- {item['type']}: {item.get('description') or item.get('metric')}" for item in result["alerts"].get("items", [])]
            delivery_result = await self.channel_delivery_service.send_report(
                channel="dingtalk",
                webhook_url=webhook_url,
                title=f"竞品预警 - {product_name}",
                content="\n".join([
                    f"商品: {product_name}",
                    f"类目: {category}",
                    f"监控周期: {job_summary['schedule']}",
                    "预警摘要:",
                    *alert_lines,
                ]),
                report_url=None,
            )

        result["monitor_job"] = job_summary
        result["window_aggregation"] = window_runtime
        result["notification"] = {
            "channel": alert_channel,
            "delivered": bool(delivery_result),
            "delivery_result": delivery_result,
        }
        return result
