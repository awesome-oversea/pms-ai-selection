from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agents.data_collection import DataCollectionAgent
from src.agents.market_insight import MarketInsightAgent
from src.services.external_signal_service import ExternalSignalService


class MarketTrendService:
    def __init__(self) -> None:
        self.data_agent = DataCollectionAgent()
        self.market_agent = MarketInsightAgent()
        self.signal_service = ExternalSignalService()

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if isinstance(value, str):
                cleaned = value.replace("%", "").replace(",", "").strip()
                if not cleaned:
                    return default
                return float(cleaned)
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            if isinstance(value, str):
                cleaned = value.replace(",", "").strip()
                if not cleaned:
                    return default
                return int(float(cleaned))
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_growth(new_value: float, old_value: float) -> float:
        if old_value <= 0:
            return 0.0 if new_value <= 0 else 100.0
        return round(((new_value - old_value) / old_value) * 100, 4)

    @staticmethod
    def _resolve_local_business_ready(signal_summary: dict[str, Any]) -> bool:
        return bool(signal_summary.get("local_business_ready", signal_summary.get("enterprise_ready", False)))

    def _build_signal_data_basis(self, signal_bundle: dict[str, Any]) -> dict[str, Any]:
        signal_summary = signal_bundle.get("summary", {}) if isinstance(signal_bundle.get("summary", {}), dict) else {}
        return {
            "real_sources": signal_summary.get("real_count", 0),
            "required_real_sources": signal_bundle.get("required_real_sources"),
            "local_business_ready": self._resolve_local_business_ready(signal_summary),
            "enterprise_ready": signal_summary.get("enterprise_ready", False),
            "readiness_tier": signal_summary.get("readiness_tier", "legacy"),
            "source_profile": signal_bundle.get("source_profile"),
            "source_channel_summary": signal_summary.get("source_channel_summary", {}),
        }

    async def _collect_base_bundle(self, *, query: str, category: str, target_market: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        signal_bundle = await self.signal_service.collect_business_real_signals(query=query, mode="auto")
        collection = await self.data_agent.run(
            {
                "query": query,
                "category": category,
                "target_market": target_market,
                "keywords": [query, category],
                "niche": category,
                "asin": "B000TREND001",
            }
        )
        market = await self.market_agent.run(
            {
                "query": query,
                "category": category,
                "target_market": target_market,
            }
        )
        return signal_bundle, collection.get("data", collection), market.get("data", market)

    async def predict_trends(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, collection_data, market_data = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        trend = market_data.get("trends", {})
        opportunity = market_data.get("opportunity_score", {})

        signal_sources = signal_bundle.get("sources", {})
        supplier_payload = collection_data.get("supplier_data") if isinstance(collection_data.get("supplier_data"), dict) else {}
        if not supplier_payload:
            alt_supply_payload = collection_data.get("supply_chain_data")
            supplier_payload = alt_supply_payload if isinstance(alt_supply_payload, dict) else {}
        source_summary = {
            "amazon": bool(collection_data.get("amazon_data")) or signal_sources.get("amazon", {}).get("mode") == "real",
            "tiktok": bool(collection_data.get("tiktok_data")) or signal_sources.get("tiktok", {}).get("mode") == "real",
            "google_trends": bool(collection_data.get("trend_data")) or signal_sources.get("google_trends", {}).get("mode") == "real",
            "ali1688": bool(supplier_payload) or signal_sources.get("ali1688", {}).get("mode") == "real",
            "media_news": signal_sources.get("media_news", {}).get("mode") == "real",
        }
        signal_data_basis = self._build_signal_data_basis(signal_bundle)

        direction = trend.get("direction", "stable")
        strength = int(trend.get("strength", 0) or 0)
        confidence = int(trend.get("confidence", 0) or 0)
        opportunity_score = int(opportunity.get("overall_score", 0) or 0)
        product_fit_score = min(100, max(0, round((strength * 0.45) + (opportunity_score * 0.55))))
        trend_score = min(100, max(0, round((strength * 0.6) + (confidence * 0.4))))
        windows = {
            "7d": {
                "direction": direction,
                "trend_score": trend_score,
                "confidence": confidence,
                "data_basis": signal_data_basis,
            },
            "14d": {
                "direction": direction,
                "trend_score": min(100, trend_score + 2),
                "confidence": max(0, confidence - 2),
                "data_basis": signal_data_basis,
            },
            "30d": {
                "direction": direction,
                "trend_score": max(0, trend_score - 3),
                "confidence": max(0, confidence - 5),
                "data_basis": signal_data_basis,
            },
        }
        recommended_action = "create_selection_task" if opportunity_score >= 60 else "monitor_only"
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "sources": source_summary,
            "trend_prediction": {
                "direction": direction,
                "strength": strength,
                "confidence": confidence,
                "description": trend.get("description", ""),
                "key_drivers": trend.get("key_drivers", []),
                "windows": windows,
                "trend_score": trend_score,
                "product_fit_score": product_fit_score,
            },
            "opportunity_summary": {
                "overall_score": opportunity_score,
                "recommendation": opportunity.get("recommendation", "caution"),
                "risk_factors": opportunity.get("risk_factors", []),
            },
            "selection_signal": {
                "should_enter_selection": direction in {"up", "stable"} and opportunity_score >= 60,
                "recommended_action": recommended_action,
                "product_fit_score": product_fit_score,
            },
            "decision_bridge": {
                "market_summary": {
                    "trend_direction": direction,
                    "trend_strength": strength,
                    "trend_confidence": confidence,
                    "opportunity_score": opportunity_score,
                },
                "recommendation_reasons": [trend.get("description", ""), f"趋势评分 {trend_score}", f"商品匹配度 {product_fit_score}"],
                "recommended_action": recommended_action,
            },
            "collection_quality": collection_data.get("quality_report", {}),
            "market_insight": market_data,
            "signal_bundle": signal_bundle,
        }

    async def get_google_trends_aggregate(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, _, market_data = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        trend = market_data.get("trends", {}) if isinstance(market_data.get("trends"), dict) else {}
        strength = self._coerce_float(trend.get("strength"))
        confidence = self._coerce_float(trend.get("confidence"))
        last_7d = round(min(100.0, strength), 4)
        last_30d = round(max(1.0, strength - 8.0), 4)
        aggregate = {
            "query": query,
            "category": category,
            "target_market": target_market,
            "dataset": "google_trends_wide_aggregate",
            "window_metrics": {
                "7d": {"avg_heat": last_7d, "peak_heat": round(min(100.0, last_7d + 6.0), 4)},
                "30d": {"avg_heat": last_30d, "peak_heat": round(min(100.0, last_30d + 12.0), 4)},
            },
            "growth": {
                "growth_7d_vs_30d": self._safe_growth(last_7d, last_30d),
                "peak_heat": round(min(100.0, max(last_7d, last_30d) + confidence * 0.1), 4),
            },
            "trend_direction": trend.get("direction", "stable"),
            "confidence": confidence,
            "source_bundle": signal_bundle.get("summary", {}),
        }
        return aggregate

    async def get_bsr_demand_supply_ratio(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, collection_data, market_data = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        amazon_data = collection_data.get("amazon_data") if isinstance(collection_data.get("amazon_data"), dict) else {}
        products = amazon_data.get("products") if isinstance(amazon_data.get("products"), list) else []
        supply_count = max(1, len(products))
        sales_rank_values = [self._coerce_int(item.get("sales_rank")) for item in products if isinstance(item, dict) and item.get("sales_rank") is not None]
        avg_sales_rank = round(sum(sales_rank_values) / len(sales_rank_values), 4) if sales_rank_values else None
        opportunity = market_data.get("opportunity_score") if isinstance(market_data.get("opportunity_score"), dict) else {}
        demand_index = max(1.0, self._coerce_float(opportunity.get("overall_score"), 50.0))
        ratio = round(demand_index / supply_count, 4)
        signal_summary = signal_bundle.get("summary", {}) if isinstance(signal_bundle.get("summary"), dict) else {}
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "topic": "amazon_bsr_realtime",
            "supply_count": supply_count,
            "demand_index": round(demand_index, 4),
            "demand_supply_ratio": ratio,
            "avg_sales_rank": avg_sales_rank,
            "signal_ready": self._resolve_local_business_ready(signal_summary),
            "signal_readiness": {
                "local_business_ready": self._resolve_local_business_ready(signal_summary),
                "enterprise_ready": signal_summary.get("enterprise_ready", False),
                "readiness_tier": signal_summary.get("readiness_tier", "legacy"),
            },
        }

    async def get_oms_sales_benchmark(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, collection_data, market_data = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        amazon_data = collection_data.get("amazon_data") if isinstance(collection_data.get("amazon_data"), dict) else {}
        products = amazon_data.get("products") if isinstance(amazon_data.get("products"), list) else []
        own_store_sales = round(sum(self._coerce_float(item.get("monthly_sales"), 0.0) for item in products[:5]), 4)
        market_opportunity = self._coerce_float((market_data.get("opportunity_score") or {}).get("overall_score"), 50.0)
        market_sales_proxy = round(max(own_store_sales, 1.0) * max(market_opportunity / 50.0, 1.0), 4)
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "dataset": "oms_sales_benchmark",
            "own_store_sales_proxy": own_store_sales,
            "market_sales_proxy": market_sales_proxy,
            "growth_gap_percent": self._safe_growth(own_store_sales, market_sales_proxy) * -1 if market_sales_proxy else 0.0,
            "benchmark_ratio": round(own_store_sales / market_sales_proxy, 4) if market_sales_proxy else 0.0,
            "source_bundle": signal_bundle.get("summary", {}),
        }

    async def get_forum_topic_trends(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, _, market_data = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        key_drivers = (market_data.get("trends") or {}).get("key_drivers") if isinstance((market_data.get("trends") or {}).get("key_drivers"), list) else []
        media_articles = ((signal_bundle.get("sources") or {}).get("media_news") or {}).get("top_articles") if isinstance(((signal_bundle.get("sources") or {}).get("media_news") or {}).get("top_articles"), list) else []
        topics = []
        for idx, driver in enumerate(key_drivers[:5], start=1):
            topics.append({
                "topic": str(driver),
                "heat": max(10, 100 - idx * 12),
                "source": "market_trend_key_driver",
            })
        for article in media_articles[:5]:
            title = str(article.get("title") or "").strip()
            if title:
                topics.append({
                    "topic": title[:80],
                    "heat": 55,
                    "source": "media_news",
                })
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "dataset": "forum_topic_trends",
            "topics": topics[:10],
            "topic_count": len(topics[:10]),
        }

    async def get_tiktok_tag_trends(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        signal_bundle, collection_data, _ = await self._collect_base_bundle(query=query, category=category, target_market=target_market)
        tiktok_data = collection_data.get("tiktok_data") if isinstance(collection_data.get("tiktok_data"), dict) else {}
        products = tiktok_data.get("products") if isinstance(tiktok_data.get("products"), list) else []
        tags: dict[str, dict[str, Any]] = {}
        base_date = datetime.now(UTC)
        for idx, item in enumerate(products[:20]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").lower()
            derived_tags = [
                query.replace(" ", "").lower(),
                category.replace(" ", "").lower(),
                str(item.get("trend_status") or "stable").lower(),
            ]
            if "viral" in title:
                derived_tags.append("viral")
            if "trending" in title:
                derived_tags.append("trending")
            engagement_rate = self._coerce_float(item.get("engagement_rate"), 0.0)
            views = self._coerce_float(item.get("total_views"), 0.0)
            creator_count = self._coerce_int(item.get("creator_count"), 0)
            for tag in {tag for tag in derived_tags if tag}:
                bucket = tags.setdefault(tag, {"tag": f"#{tag}", "mentions": 0, "engagement_total": 0.0, "views_total": 0.0, "creator_total": 0, "timeline": []})
                bucket["mentions"] += 1
                bucket["engagement_total"] += engagement_rate
                bucket["views_total"] += views
                bucket["creator_total"] += creator_count
                bucket["timeline"].append(
                    {
                        "date": (base_date.replace(hour=0, minute=0, second=0, microsecond=0)).isoformat(),
                        "engagement_rate": round(engagement_rate, 4),
                        "views": round(views, 4),
                    }
                )
        ranking = []
        for item in tags.values():
            mentions = max(1, int(item["mentions"]))
            ranking.append(
                {
                    "tag": item["tag"],
                    "mentions": mentions,
                    "avg_engagement_rate": round(item["engagement_total"] / mentions, 4),
                    "avg_views": round(item["views_total"] / mentions, 4),
                    "avg_creator_count": round(item["creator_total"] / mentions, 4),
                    "timeline": item["timeline"][:7],
                }
            )
        ranking.sort(key=lambda item: (item.get("avg_engagement_rate", 0.0), item.get("mentions", 0)), reverse=True)
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "dataset": "tiktok_tag_trends",
            "tags": ranking[:10],
            "tag_count": len(ranking[:10]),
            "source_bundle": signal_bundle.get("summary", {}),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    async def get_supply_demand_lifecycle(self, *, query: str, category: str, target_market: str = "US") -> dict[str, Any]:
        trends = await self.get_google_trends_aggregate(query=query, category=category, target_market=target_market)
        ratio = await self.get_bsr_demand_supply_ratio(query=query, category=category, target_market=target_market)
        benchmark = await self.get_oms_sales_benchmark(query=query, category=category, target_market=target_market)
        demand_supply_ratio = self._coerce_float(ratio.get("demand_supply_ratio"), 0.0)
        benchmark_ratio = self._coerce_float(benchmark.get("benchmark_ratio"), 0.0)
        growth = self._coerce_float((trends.get("growth") or {}).get("growth_7d_vs_30d"), 0.0)
        if growth >= 20 and demand_supply_ratio >= 10:
            lifecycle_stage = "growth"
        elif growth >= 0 and benchmark_ratio >= 0.8:
            lifecycle_stage = "maturity"
        else:
            lifecycle_stage = "early_or_declining"
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "dataset": "supply_demand_lifecycle",
            "lifecycle_stage": lifecycle_stage,
            "demand_supply_ratio": demand_supply_ratio,
            "benchmark_ratio": benchmark_ratio,
            "trend_growth_percent": growth,
            "updated_at": datetime.now(UTC).isoformat(),
        }
