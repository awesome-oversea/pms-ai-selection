"""
数据采集Agent(D27-D29)。

负责从多源平台采集选品相关数据:
    - Amazon: BSR榜单、评论分析、价格监控
    - TikTok Shop: 热门商品、达人信息、视频数据
    - Google Trends: 搜索热度、地域分布、相关词
    - 1688: 供应商信息、批发价格、库存状态
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.ali1688_open_client import Ali1688OpenClient
from src.infrastructure.amazon_sp_api_client import AmazonSPAPIClient
from src.infrastructure.google_trends_client import GoogleTrendsClient
from src.infrastructure.http_retry import HTTPRetryPolicy
from src.infrastructure.kafka import send_message
from src.infrastructure.tiktok_business_client import TikTokBusinessClient
from src.services.business_scenario_catalog_service import BusinessScenarioCatalogService
from src.services.external_signal_service import ExternalSignalService

from .base import AgentTool, BaseAgent

logger = logging.getLogger(__name__)
RAW_AMAZON_TOPIC = "raw_amazon"
RAW_TIKTOK_TOPIC = "raw_tiktok"
RAW_TRENDS_TOPIC = "raw_trends"
RAW_1688_TOPIC = "raw_1688"


class DataSource(StrEnum):
    AMAZON = "amazon"
    TIKTOK = "tiktok"
    GOOGLE = "google"
    ALI1688 = "ali1688"


@dataclass
class CollectionResult:
    source: DataSource
    query: str
    data: dict[str, Any]
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    record_count: int = 0
    quality_score: float = 1.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "query": self.query,
            "data": self.data,
            "collected_at": self.collected_at,
            "record_count": self.record_count,
            "quality_score": self.quality_score,
            "error": self.error,
        }


@dataclass
class DataQualityReport:
    total_records: int = 0
    valid_records: int = 0
    empty_fields: int = 0
    duplicate_count: int = 0
    anomaly_count: int = 0
    sources_checked: list[str] = field(default_factory=list)

    @property
    def validity_rate(self) -> float:
        return self.valid_records / max(self.total_records, 1)

    @property
    def is_acceptable(self) -> bool:
        return self.validity_rate >= 0.9 and self.anomaly_count < self.total_records * 0.05


def _normalize_mode(mode: str) -> str:
    resolved = (mode or "auto").strip().lower()
    return resolved if resolved in {"auto", "real", "mock"} else "auto"


def _scenario_meta(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": scenario.get("scenario_id"),
        "description": scenario.get("description"),
        "behavior": scenario.get("behavior", {}),
    }


def _derive_amazon_risk_flag(item: dict[str, Any], scenario: dict[str, Any]) -> str | None:
    if item.get("risk_flag"):
        return str(item["risk_flag"])
    scenario_id = str(scenario.get("scenario_id") or "")
    risk_flag_mapping = {
        "amazon_high_refund": "high_refund",
        "amazon_margin_pressure": "margin_pressure",
        "amazon_hot_selling": "hot_selling",
    }
    return risk_flag_mapping.get(scenario_id)


def _resolve_google_trend_direction(points: list[dict[str, Any]], response: dict[str, Any]) -> str:
    risk_flag = response.get("risk_flag")
    if risk_flag == "spike_then_drop":
        return "down"
    growth_rate_7d = response.get("growth_rate_7d")
    if isinstance(growth_rate_7d, (int, float)):
        if growth_rate_7d > 0.05:
            return "up"
        if growth_rate_7d < -0.05:
            return "down"
    if not points:
        return "flat"
    if points[-1]["value"] > points[0]["value"]:
        return "up"
    if points[-1]["value"] < points[0]["value"]:
        return "down"
    return "flat"


def _derive_supply_risk_flag(item: dict[str, Any], scenario: dict[str, Any]) -> str | None:
    if item.get("risk_flag"):
        return str(item["risk_flag"])
    scenario_id = str(scenario.get("scenario_id") or "")
    risk_flag_mapping = {
        "ali1688_supplier_unstable": "supplier_unstable",
        "ali1688_high_moq_long_leadtime": "high_moq_long_leadtime",
    }
    return risk_flag_mapping.get(scenario_id)


def _build_retry_policy(settings: Any) -> HTTPRetryPolicy:
    return HTTPRetryPolicy(
        max_attempts=settings.http_max_attempts,
        base_backoff_seconds=settings.http_base_backoff_seconds,
        max_backoff_seconds=settings.http_max_backoff_seconds,
    )


def _build_upstream_error(exc: Exception, *, provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "error_code": getattr(exc, "error_code", exc.__class__.__name__),
        "message": str(exc),
        "retryable": bool(getattr(exc, "retryable", False)),
        "http_status": getattr(exc, "http_status", None),
        "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
        "attempts": int(getattr(exc, "attempts", 1) or 1),
    }


def _mark_degraded_payload(payload: dict[str, Any], *, provider: str, exc: Exception, fallback_mode: str) -> dict[str, Any]:
    payload["degraded"] = True
    payload["degradation_reason"] = f"{provider} {getattr(exc, 'error_code', 'request_failed')}; fallback to {fallback_mode}"
    payload["upstream_error"] = _build_upstream_error(exc, provider=provider)
    return payload


def _attach_external_signal_context(
    payload: dict[str, Any],
    *,
    external_bundle: dict[str, Any],
    source_name: str,
) -> dict[str, Any]:
    summary = external_bundle.get("summary") if isinstance(external_bundle.get("summary"), dict) else {}
    source_payload = (
        (external_bundle.get("sources") or {}).get(source_name, {})
        if isinstance(external_bundle.get("sources"), dict)
        else {}
    )
    payload["signal_context"] = {
        "provider": "external_signal_service",
        "source_name": source_name,
        "source_mode": source_payload.get("mode"),
        "source_channel": source_payload.get("source_channel"),
        "enterprise_integrated": bool(source_payload.get("enterprise_integrated", False)),
    }
    payload["signal_readiness"] = {
        "local_business_ready": bool(summary.get("local_business_ready", summary.get("enterprise_ready", False))),
        "enterprise_ready": bool(summary.get("enterprise_ready", False)),
        "readiness_tier": summary.get("readiness_tier", "legacy"),
        "required_real_sources": external_bundle.get("required_real_sources"),
        "real_count": summary.get("real_count", 0),
        "mock_count": summary.get("mock_count", 0),
        "error_count": summary.get("error_count", 0),
        "next_actions": summary.get("next_actions", []),
    }
    return payload


def _build_external_signal_summary(
    source_names: list[str],
    collection_results: list[CollectionResult],
) -> dict[str, Any]:
    fallback_tools: list[str] = []
    fallback_business_sources: set[str] = set()
    local_validation_only_sources: set[str] = set()
    enterprise_ready_sources: set[str] = set()
    source_channel_breakdown: dict[str, int] = {}
    next_actions: list[str] = []

    for source_name, result in zip(source_names, collection_results, strict=False):
        if result.error is not None or not isinstance(result.data, dict):
            continue
        signal_context = result.data.get("signal_context") if isinstance(result.data.get("signal_context"), dict) else {}
        signal_readiness = result.data.get("signal_readiness") if isinstance(result.data.get("signal_readiness"), dict) else {}
        if signal_context.get("provider") != "external_signal_service":
            continue
        fallback_tools.append(source_name)
        business_source = str(signal_context.get("source_name") or source_name)
        fallback_business_sources.add(business_source)
        source_channel = str(signal_context.get("source_channel") or "unknown")
        source_channel_breakdown[source_channel] = source_channel_breakdown.get(source_channel, 0) + 1
        if bool(signal_readiness.get("enterprise_ready")):
            enterprise_ready_sources.add(business_source)
        elif bool(signal_readiness.get("local_business_ready")):
            local_validation_only_sources.add(business_source)
        for action in signal_readiness.get("next_actions", []):
            if isinstance(action, str) and action not in next_actions:
                next_actions.append(action)

    return {
        "has_external_signal_fallbacks": bool(fallback_tools),
        "fallback_tool_count": len(fallback_tools),
        "fallback_tools": sorted(fallback_tools),
        "fallback_business_sources": sorted(fallback_business_sources),
        "local_validation_only_sources": sorted(local_validation_only_sources),
        "enterprise_ready_sources": sorted(enterprise_ready_sources),
        "source_channel_breakdown": source_channel_breakdown,
        "next_actions": next_actions,
    }


def _resolve_record_count(payload: dict[str, Any]) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in ("total_results", "total_suppliers", "total_creators", "total_analyzed", "total_count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    for key in ("products", "suppliers", "creators", "sample_reviews", "top_articles"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _build_raw_collection_event(
    *,
    source: str,
    event_type: str,
    request: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "raw_source": source,
        "request": request,
        "mode": payload.get("mode"),
        "degraded": payload.get("degraded"),
        "payload": payload,
        "collected_at": payload.get("collected_at") or datetime.now(UTC).isoformat(),
    }


async def _publish_raw_collection_event(
    *,
    topic: str,
    source: str,
    event_type: str,
    request: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    await send_message(
        topic,
        _build_raw_collection_event(
            source=source,
            event_type=event_type,
            request=request,
            payload=payload,
        ),
    )


class AmazonBSRTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="amazon_bsr",
            description="采集Amazon BSR榜单数据，包括类目排名、销量估算、价格和评论信息",
            func=self._collect_bsr,
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Amazon类目节点ID或名称"},
                    "top_n": {"type": "integer", "description": "返回Top N商品", "default": 20},
                    "marketplace": {"type": "string", "description": "站点: US/UK/DE/JP", "default": "US"},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["category"],
            },
        )

    async def _collect_bsr(self, category: str, top_n: int = 20, marketplace: str = "US", mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        request_payload = {"category": category, "top_n": top_n, "marketplace": marketplace, "mode": resolved_mode}
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.amazon_api_key:
                client = AmazonSPAPIClient(
                    api_endpoint=settings.amazon_endpoint,
                    api_key=settings.amazon_api_key,
                    marketplace_id=settings.amazon_marketplace,
                    timeout_seconds=settings.amazon_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_catalog_items(keywords=[category], page_size=top_n)
                    items = list(payload.get("items") or payload.get("catalogItems") or [])[:top_n]
                    if items:
                        products = [
                            {
                                "rank": index + 1,
                                "asin": item.get("asin") or item.get("sellerSku") or f"REAL-{index+1}",
                                "name": item.get("title") or item.get("productName") or category,
                                "price": float(item.get("price") or 0),
                                "rating": float(item.get("rating") or 0),
                                "review_count": int(item.get("review_count") or 0),
                                "url": item.get("url"),
                                "marketplace": marketplace,
                                "category_id": category,
                                "crawled_at": datetime.now(UTC).isoformat(),
                            }
                            for index, item in enumerate(items)
                        ]
                        payload = {
                            "source": "amazon_bsr",
                            "mode": "real",
                            "category": category,
                            "marketplace": marketplace,
                            "collected_at": datetime.now(UTC).isoformat(),
                            "total_results": len(products),
                            "products": products,
                            "price_distribution": _calc_price_stats([float(p.get("price") or 0) for p in products]),
                            "rating_distribution": _calc_rating_stats([float(p.get("rating") or 0) for p in products]),
                            "total_est_monthly_revenue": 0.0,
                            "avg_est_monthly_sales": 0,
                        }
                        await send_message("amazon-data", {"event_type": "amazon.bsr.collected", "category": category, "payload": payload})
                        await _publish_raw_collection_event(
                            topic=RAW_AMAZON_TOPIC,
                            source="amazon",
                            event_type="amazon.bsr.collected",
                            request=request_payload,
                            payload=payload,
                        )
                        return payload
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
            real_signal = await ExternalSignalService().collect_business_real_signals(query=category, mode=resolved_mode, required_real_sources=1)
            amazon_signal = (real_signal.get("sources") or {}).get("amazon", {})
            if amazon_signal.get("mode") == "real":
                payload = {
                    "source": "amazon_bsr",
                    "mode": "real",
                    "category": category,
                    "marketplace": marketplace,
                    "collected_at": datetime.now(UTC).isoformat(),
                    "total_results": 1,
                    "products": [
                        {
                            "rank": 1,
                            "asin": f"REAL-{abs(hash(category)) % 100000000}",
                            "title": amazon_signal.get("title") or f"{category} Amazon Search Result",
                            "price": 0.0,
                            "currency": "USD",
                            "reviews": 0,
                            "rating": 0.0,
                            "bsr_rank": 1,
                            "est_monthly_sales": 0,
                            "est_monthly_revenue": 0.0,
                            "category_path": f"Amazon > {marketplace} > {category}",
                            "is_prime_eligible": False,
                            "launch_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                            "real_signal": amazon_signal,
                        }
                    ],
                    "price_distribution": {"min": 0, "max": 0, "avg": 0, "median": 0, "distribution": {"$0-20": 1, "$20-50": 0, "$50-100": 0, "$100+": 0}},
                    "rating_distribution": {"avg": 0, "distribution": {"5 star": 0, "4 star": 0, "3 star": 0, "2 star": 0, "1 star": 1}},
                    "total_est_monthly_revenue": 0.0,
                    "avg_est_monthly_sales": 0,
                }
                _attach_external_signal_context(payload, external_bundle=real_signal, source_name="amazon")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="external_signal")
                await send_message("amazon-data", {"event_type": "amazon.bsr.collected", "category": category, "payload": payload})
                await _publish_raw_collection_event(
                    topic=RAW_AMAZON_TOPIC,
                    source="amazon",
                    event_type="amazon.bsr.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload

        scenario = BusinessScenarioCatalogService().resolve_external_scenario("amazon", category)
        if scenario:
            behavior = scenario.get("behavior", {})
            if behavior.get("error") == "rate_limited":
                payload = {
                    "source": "amazon_bsr",
                    "mode": "mock",
                    "category": category,
                    "marketplace": marketplace,
                    "collected_at": datetime.now(UTC).isoformat(),
                    "total_results": 0,
                    "products": [],
                    "price_distribution": {"min": 0, "max": 0, "avg": 0, "median": 0, "distribution": {"$0-20": 0, "$20-50": 0, "$50-100": 0, "$100+": 0}},
                    "rating_distribution": {"avg": 0, "distribution": {"5 star": 0, "4 star": 0, "3 star": 0, "2 star": 0, "1 star": 0}},
                    "total_est_monthly_revenue": 0.0,
                    "avg_est_monthly_sales": 0,
                    "scenario": _scenario_meta(scenario),
                    "degraded": True,
                    "degradation_reason": "mock rate_limited scenario",
                }
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="mock_scenario")
                await _publish_raw_collection_event(
                    topic=RAW_AMAZON_TOPIC,
                    source="amazon",
                    event_type="amazon.bsr.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload
            products = []
            for index, item in enumerate((scenario.get("response", {}).get("products") or [])[:top_n], start=1):
                price = float(item.get("price") or 0)
                est_monthly_sales = int(item.get("monthly_sales") or item.get("est_monthly_sales") or max(100, 1200 - index * 80))
                products.append(
                    {
                        "rank": index,
                        "asin": item.get("asin") or item.get("id") or f"SCN-AMZ-{index}",
                        "title": item.get("title") or category,
                        "price": price,
                        "currency": "USD",
                        "reviews": int(item.get("review_count") or 0),
                        "rating": float(item.get("rating") or 0),
                        "bsr_rank": index,
                        "est_monthly_sales": est_monthly_sales,
                        "est_monthly_revenue": round(est_monthly_sales * price, 2),
                        "category_path": f"Scenario > {category}",
                        "is_prime_eligible": True,
                        "launch_date": _random_date(months_ago=6),
                        "refund_rate": item.get("refund_rate"),
                        "negative_review_rate": item.get("negative_review_rate"),
                        "profit_margin": item.get("profit_margin"),
                        "ad_cost_ratio": item.get("ad_cost_ratio"),
                        "sales_growth_rate_7d": item.get("sales_growth_rate_7d"),
                        "risk_flag": _derive_amazon_risk_flag(item, scenario),
                    }
                )
            price_stats = _calc_price_stats([float(p.get("price") or 0) for p in products])
            rating_stats = _calc_rating_stats([float(p.get("rating") or 0) for p in products])
            payload = {
                "source": "amazon_bsr",
                "mode": "mock",
                "category": category,
                "marketplace": marketplace,
                "collected_at": datetime.now(UTC).isoformat(),
                "total_results": len(products),
                "products": products,
                "price_distribution": price_stats,
                "rating_distribution": rating_stats,
                "total_est_monthly_revenue": round(sum(float(p.get("est_monthly_revenue") or 0) for p in products), 2),
                "avg_est_monthly_sales": int(sum(int(p.get("est_monthly_sales") or 0) for p in products) / max(len(products), 1)),
                "scenario": _scenario_meta(scenario),
                "degraded": False,
                "degradation_reason": None,
            }
            await _publish_raw_collection_event(
                topic=RAW_AMAZON_TOPIC,
                source="amazon",
                event_type="amazon.bsr.collected",
                request=request_payload,
                payload=payload,
            )
            return payload

        await asyncio.sleep(random.uniform(0.1, 0.3))
        products = []
        for i in range(1, top_n + 1):
            price = round(random.uniform(9.99, 89.99), 2)
            reviews = random.randint(50, 25000)
            rating = round(random.uniform(3.5, 5.0), 1)
            bsr_rank = i
            est_monthly_sales = max(100, int(50000 / (bsr_rank ** 0.8) * random.uniform(0.7, 1.3)))
            products.append({
                "rank": bsr_rank,
                "asin": f"B0{random.randint(10000000, 99999999)}X",
                "title": f"Top {category} Product #{i}",
                "price": price,
                "currency": "USD",
                "reviews": reviews,
                "rating": rating,
                "bsr_rank": bsr_rank,
                "est_monthly_sales": est_monthly_sales,
                "est_monthly_revenue": round(est_monthly_sales * price, 2),
                "category_path": f"Electronics > {category} > Best Sellers",
                "is_prime_eligible": random.choice([True, True, True, False]),
                "launch_date": _random_date(months_ago=random.randint(1, 36)),
            })
        price_stats = _calc_price_stats([p["price"] for p in products])
        rating_stats = _calc_rating_stats([p["rating"] for p in products])
        payload = {
            "source": "amazon_bsr",
            "mode": "mock",
            "category": category,
            "marketplace": marketplace,
            "collected_at": datetime.now(UTC).isoformat(),
            "total_results": len(products),
            "products": products,
            "price_distribution": price_stats,
            "rating_distribution": rating_stats,
            "total_est_monthly_revenue": sum(p["est_monthly_revenue"] for p in products),
            "avg_est_monthly_sales": sum(p["est_monthly_sales"] for p in products) // len(products),
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="mock_preview")
        await send_message("amazon-data", {"event_type": "amazon.bsr.collected", "category": category, "payload": payload})
        await _publish_raw_collection_event(
            topic=RAW_AMAZON_TOPIC,
            source="amazon",
            event_type="amazon.bsr.collected",
            request=request_payload,
            payload=payload,
        )
        return payload


class AmazonReviewTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="amazon_reviews",
            description="分析Amazon产品评论，提取情感倾向、关键词和常见问题",
            func=self._analyze_reviews,
            parameters={
                "type": "object",
                "properties": {
                    "asin": {"type": "string", "description": "产品ASIN"},
                    "max_reviews": {"type": "integer", "description": "最大评论数", "default": 100},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["asin"],
            },
        )

    async def _analyze_reviews(self, asin: str, max_reviews: int = 100, mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.amazon_api_key:
                client = AmazonSPAPIClient(
                    api_endpoint=settings.amazon_endpoint,
                    api_key=settings.amazon_api_key,
                    marketplace_id=settings.amazon_marketplace,
                    timeout_seconds=settings.amazon_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_item_reviews(asin=asin, page_size=max_reviews)
                    items = list(payload.get("reviews") or payload.get("items") or [])[:max_reviews]
                    if items:
                        avg_rating = round(sum(float(item.get("rating") or 0) for item in items) / max(len(items), 1), 2)
                        return {
                            "source": "amazon_reviews",
                            "mode": "real",
                            "asin": asin,
                            "total_analyzed": len(items),
                            "sentiment_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
                            "sentiment_percentages": {"positive": 0.0, "neutral": 0.0, "negative": 0.0},
                            "top_themes": [],
                            "avg_rating": avg_rating,
                            "sample_reviews": items[:10],
                        }
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
            external = await ExternalSignalService().collect_business_real_signals(query=asin, mode=resolved_mode, required_real_sources=1)
            amazon_signal = (external.get("sources") or {}).get("amazon", {})
            if amazon_signal.get("mode") == "real":
                payload = {
                    "source": "amazon_reviews",
                    "mode": "real",
                    "asin": asin,
                    "total_analyzed": 1,
                    "sentiment_breakdown": {"positive": 0, "neutral": 1, "negative": 0},
                    "sentiment_percentages": {"positive": 0.0, "neutral": 100.0, "negative": 0.0},
                    "top_themes": [{"theme": "catalog_signal", "mentions": 1}],
                    "avg_rating": 0.0,
                    "sample_reviews": [{"review_id": f"REAL-{asin}", "rating": 0, "sentiment": "neutral", "theme": "catalog_signal", "snippet": amazon_signal.get("title") or asin}],
                }
                _attach_external_signal_context(payload, external_bundle=external, source_name="amazon")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="external_signal")
                return payload

        await asyncio.sleep(random.uniform(0.05, 0.15))
        positive_themes = [("quality", "quality good great excellent premium durable"), ("value", "value money worth price reasonable affordable"), ("design", "design nice beautiful sleek modern stylish compact"), ("performance", "performance fast smooth responsive powerful efficient"), ("ease_of_use", "easy use simple setup intuitive friendly beginner")]
        negative_themes = [("battery_life", "battery life short poor drain quickly charging issue"), ("durability", "broke fragile cheap flimsy fell apart stopped working"), ("connectivity", "connection bluetooth wifi pairing drop disconnect problem"), ("customer_service", "support service response slow unhelpful warranty"), ("packaging", "package damaged missing box arrived broken shipping")]
        review_samples = []
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        theme_mentions: dict[str, int] = {}
        for i in range(max_reviews):
            rand = random.random()
            if rand < 0.65:
                sentiment = "positive"
                star = random.choice([5, 5, 4, 4])
                theme = positive_themes[i % len(positive_themes)]
            elif rand < 0.85:
                sentiment = "neutral"
                star = random.choice([3, 3, 4])
                theme = random.choice(positive_themes)
            else:
                sentiment = "negative"
                star = random.choice([1, 2, 2])
                theme = negative_themes[i % len(negative_themes)]
            sentiment_counts[sentiment] += 1
            theme_name, keywords = theme
            theme_mentions[theme_name] = theme_mentions.get(theme_name, 0) + 1
            review_samples.append({
                "review_id": f"R{random.randint(10000, 99999)}",
                "rating": star,
                "sentiment": sentiment,
                "theme": theme_name,
                "verified_purchase": random.choice([True, True, True, False]),
                "helpful_votes": random.randint(0, 50),
                "date": _random_date(months_ago=random.randint(0, 12)),
                "snippet": f"This product is {'great' if sentiment == 'positive' else 'okay' if sentiment == 'neutral' else 'disappointing'}. {random.choice(keywords.split())} is notable.",
            })
        sorted_themes = sorted(theme_mentions.items(), key=lambda x: x[1], reverse=True)
        payload = {
            "source": "amazon_reviews",
            "mode": "mock",
            "asin": asin,
            "total_analyzed": len(review_samples),
            "sentiment_breakdown": sentiment_counts,
            "sentiment_percentages": {k: round(v / len(review_samples) * 100, 1) for k, v in sentiment_counts.items()},
            "top_themes": [{"theme": t, "mentions": c} for t, c in sorted_themes[:8]],
            "avg_rating": round(sum(r["rating"] for r in review_samples) / len(review_samples), 2),
            "sample_reviews": review_samples[:10],
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="mock_preview")
        return payload


class AmazonPriceTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="amazon_price",
            description="监控Amazon产品价格历史、促销活动和竞品对比",
            func=self._track_prices,
            parameters={
                "type": "object",
                "properties": {
                    "asin": {"type": "string", "description": "产品ASIN"},
                    "days_history": {"type": "integer", "description": "历史天数", "default": 90},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["asin"],
            },
        )

    async def _track_prices(self, asin: str, days_history: int = 90, mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.amazon_api_key:
                client = AmazonSPAPIClient(
                    api_endpoint=settings.amazon_endpoint,
                    api_key=settings.amazon_api_key,
                    marketplace_id=settings.amazon_marketplace,
                    timeout_seconds=settings.amazon_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_item_offers(asin=asin)
                    offers = list(payload.get("offers") or payload.get("items") or [])
                    prices = [float(item.get("price") or item.get("listing_price") or 0) for item in offers if (item.get("price") or item.get("listing_price")) is not None]
                    if prices:
                        current_price = prices[0]
                        return {
                            "source": "amazon_price",
                            "mode": "real",
                            "asin": asin,
                            "current_price": current_price,
                            "base_price": current_price,
                            "price_min": min(prices),
                            "price_max": max(prices),
                            "price_avg": round(sum(prices) / len(prices), 2),
                            "price_volatility": 0.0,
                            "days_tracked": days_history,
                            "history": [{"date": datetime.now(UTC).strftime("%Y-%m-%d"), "price": current_price, "promo_type": None, "currency": "USD"}],
                            "competitor_prices": {},
                            "buy_box_percentage": 0.0,
                            "promo_events": 0,
                        }
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
        await asyncio.sleep(random.uniform(0.05, 0.12))
        base_price = round(random.uniform(19.99, 79.99), 2)
        history = []
        current_price = base_price
        for day_offset in range(days_history, 0, -1):
            date_str = (datetime.now(UTC) - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            change_factor = random.uniform(-0.03, 0.03)
            promo_chance = random.random()
            if promo_chance < 0.08:
                current_price = round(base_price * random.uniform(0.7, 0.85), 2)
                promo_type = random.choice(["lightning_deal", "coupon", "prime_discount"])
            elif promo_chance < 0.12:
                current_price = round(base_price * random.uniform(0.88, 0.95), 2)
                promo_type = "small_discount"
            else:
                current_price = round(current_price * (1 + change_factor), 2)
                current_price = max(base_price * 0.6, min(base_price * 1.15, current_price))
                promo_type = None
            if day_offset <= 30 or day_offset % 7 == 0 or promo_type:
                history.append({"date": date_str, "price": current_price, "promo_type": promo_type, "currency": "USD"})
        prices_only = [h["price"] for h in history]
        competitor_prices = {
            "competitor_a": round(base_price * random.uniform(0.85, 1.1), 2),
            "competitor_b": round(base_price * random.uniform(0.78, 0.98), 2),
            "competitor_c": round(base_price * random.uniform(0.9, 1.2), 2),
        }
        payload = {
            "source": "amazon_price",
            "mode": "mock",
            "asin": asin,
            "current_price": current_price,
            "base_price": base_price,
            "price_min": min(prices_only),
            "price_max": max(prices_only),
            "price_avg": round(sum(prices_only) / len(prices_only), 2),
            "price_volatility": round((max(prices_only) - min(prices_only)) / min(prices_only) * 100, 1),
            "days_tracked": days_history,
            "history": history[-60:],
            "competitor_prices": competitor_prices,
            "buy_box_percentage": round(random.uniform(75, 98), 1),
            "promo_events": len([h for h in history if h.get("promo_type")]),
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="amazon_sp_api", exc=api_error, fallback_mode="mock_preview")
        return payload


class TikTokProductTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="tiktok_products",
            description="采集TikTok Shop热门商品数据和达人带货表现",
            func=self._collect_tiktok_products,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "top_n": {"type": "integer", "description": "返回数量", "default": 15},
                    "region": {"type": "string", "description": "地区: US/UK/SEA", "default": "US"},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["query"],
            },
        )

    async def _collect_tiktok_products(self, query: str, top_n: int = 15, region: str = "US", mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        request_payload = {"query": query, "top_n": top_n, "region": region, "mode": resolved_mode}
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.tiktok_api_key:
                client = TikTokBusinessClient(
                    api_endpoint=settings.tiktok_endpoint,
                    api_key=settings.tiktok_api_key,
                    timeout_seconds=settings.tiktok_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_products(query=query, region=region, page_size=top_n)
                    products = list(payload.get("products") or payload.get("items") or [])[:top_n]
                    if products:
                        payload = {
                            "source": "tiktok_products",
                            "mode": "real",
                            "query": query,
                            "region": region,
                            "total_results": len(products),
                            "products": products,
                            "total_views": sum(int(item.get("total_views") or item.get("views") or 0) for item in products),
                            "total_engagement": round(sum(float(item.get("engagement_rate") or 0) for item in products) / max(len(products), 1), 2),
                        }
                        await _publish_raw_collection_event(
                            topic=RAW_TIKTOK_TOPIC,
                            source="tiktok",
                            event_type="tiktok.products.collected",
                            request=request_payload,
                            payload=payload,
                        )
                        return payload
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
            external = await ExternalSignalService().collect_business_real_signals(query=query, mode=resolved_mode, required_real_sources=1)
            signal = (external.get("sources") or {}).get("tiktok", {})
            if signal.get("mode") == "real":
                payload = {
                    "source": "tiktok_products",
                    "mode": "real",
                    "query": query,
                    "region": region,
                    "total_results": 1,
                    "products": [{"product_id": f"TT-REAL-{abs(hash(query)) % 100000}", "title": signal.get("title") or query, "total_views": 0, "engagement_rate": 0.0, "region": region}],
                    "total_views": 0,
                    "total_engagement": 0.0,
                }
                _attach_external_signal_context(payload, external_bundle=external, source_name="tiktok")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="tiktok_business_api", exc=api_error, fallback_mode="external_signal")
                await _publish_raw_collection_event(
                    topic=RAW_TIKTOK_TOPIC,
                    source="tiktok",
                    event_type="tiktok.products.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload
        scenario = BusinessScenarioCatalogService().resolve_external_scenario("tiktok", query)
        if scenario:
            behavior = scenario.get("behavior", {})
            if behavior.get("error") == "auth_failed":
                payload = {
                    "source": "tiktok_products",
                    "mode": "mock",
                    "query": query,
                    "region": region,
                    "total_results": 0,
                    "products": [],
                    "total_views": 0,
                    "total_engagement": 0.0,
                    "scenario": _scenario_meta(scenario),
                    "degraded": True,
                    "degradation_reason": "mock auth_failed scenario",
                }
                await _publish_raw_collection_event(
                    topic=RAW_TIKTOK_TOPIC,
                    source="tiktok",
                    event_type="tiktok.products.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload
            trends = scenario.get("response", {}).get("trends") or []
            products = []
            for index, item in enumerate(trends[:top_n], start=1):
                views = int(item.get("views") or 0)
                engagement_rate = float(item.get("engagement_rate") or 0)
                products.append(
                    {
                        "rank": index,
                        "product_id": f"TT-SCN-{index}",
                        "title": item.get("hashtag") or f"{query} trend #{index}",
                        "price_usd": round(views / 10000000 + 9.99, 2),
                        "total_views": views,
                        "total_likes": int(views * max(engagement_rate, 0) * 0.5),
                        "total_shares": int(views * max(engagement_rate, 0) * 0.15),
                        "total_comments": int(views * max(engagement_rate, 0) * 0.08),
                        "engagement_rate": round(engagement_rate * 100 if engagement_rate <= 1 else engagement_rate, 2),
                        "video_count": max(1, int(views / 5000000)),
                        "creator_count": max(1, int(views / 8000000)),
                        "estimated_sales": int(views * float(item.get("estimated_conversion_rate") or 0.01)),
                        "estimated_revenue": round(int(views * float(item.get("estimated_conversion_rate") or 0.01)) * (views / 10000000 + 9.99), 2),
                        "trend_status": "rising" if float(item.get("growth_rate_7d") or 0) > 0 else "stable",
                        "region": region,
                        "risk_flag": item.get("risk_flag"),
                        "growth_rate_7d": item.get("growth_rate_7d"),
                        "estimated_conversion_rate": item.get("estimated_conversion_rate"),
                    }
                )
            payload = {
                "source": "tiktok_products",
                "mode": "mock",
                "query": query,
                "region": region,
                "total_results": len(products),
                "products": products,
                "total_views": sum(int(p.get("total_views") or 0) for p in products),
                "total_engagement": round(sum(float(p.get("engagement_rate") or 0) for p in products) / max(len(products), 1), 2),
                "scenario": _scenario_meta(scenario),
                "degraded": False,
                "degradation_reason": None,
            }
            if api_error is not None:
                _mark_degraded_payload(payload, provider="tiktok_business_api", exc=api_error, fallback_mode="mock_scenario")
            await _publish_raw_collection_event(
                topic=RAW_TIKTOK_TOPIC,
                source="tiktok",
                event_type="tiktok.products.collected",
                request=request_payload,
                payload=payload,
            )
            return payload
        await asyncio.sleep(random.uniform(0.1, 0.25))
        products = []
        for i in range(top_n):
            views = random.randint(50000, 15000000)
            likes = int(views * random.uniform(0.02, 0.12))
            shares = int(views * random.uniform(0.005, 0.03))
            comments = int(views * random.uniform(0.001, 0.01))
            sales = random.randint(100, 50000)
            products.append({
                "rank": i + 1,
                "product_id": f"TT{random.randint(100000, 999999)}",
                "title": f"{query} Viral Product #{i+1} - TikTok Trending",
                "price_usd": round(random.uniform(5.99, 49.99), 2),
                "total_views": views,
                "total_likes": likes,
                "total_shares": shares,
                "total_comments": comments,
                "engagement_rate": round((likes + shares + comments) / max(views, 1) * 100, 2),
                "video_count": random.randint(5, 500),
                "creator_count": random.randint(3, 200),
                "estimated_sales": sales,
                "estimated_revenue": round(sales * random.uniform(5.99, 49.99), 2),
                "trend_status": random.choice(["rising", "hot", "stable", "declining"]),
                "region": region,
            })
        payload = {
            "source": "tiktok_products",
            "mode": "mock",
            "query": query,
            "region": region,
            "total_results": len(products),
            "products": products,
            "total_views": sum(p["total_views"] for p in products),
            "total_engagement": sum(p["engagement_rate"] for p in products) / len(products),
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="tiktok_business_api", exc=api_error, fallback_mode="mock_preview")
        await _publish_raw_collection_event(
            topic=RAW_TIKTOK_TOPIC,
            source="tiktok",
            event_type="tiktok.products.collected",
            request=request_payload,
            payload=payload,
        )
        return payload


class TikTokCreatorTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="tiktok_creators",
            description="获取TikTok达人数据，包括粉丝量、互动率和带货效果",
            func=self._collect_creators,
            parameters={
                "type": "object",
                "properties": {
                    "niche": {"type": "string", "description": "领域/类目"},
                    "min_followers": {"type": "integer", "description": "最低粉丝数", "default": 10000},
                    "max_results": {"type": "integer", "description": "返回数量", "default": 10},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["niche"],
            },
        )

    async def _collect_creators(self, niche: str, min_followers: int = 10000, max_results: int = 10, mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.tiktok_api_key:
                client = TikTokBusinessClient(
                    api_endpoint=settings.tiktok_endpoint,
                    api_key=settings.tiktok_api_key,
                    timeout_seconds=settings.tiktok_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_creators(niche=niche, max_results=max_results)
                    creators = list(payload.get("creators") or payload.get("items") or [])[:max_results]
                    if creators:
                        return {"source": "tiktok_creators", "mode": "real", "niche": niche, "total_creators": len(creators), "creators": creators, "tier_distribution": {}}
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
            external = await ExternalSignalService().collect_business_real_signals(query=niche, mode=resolved_mode, required_real_sources=1)
            signal = (external.get("sources") or {}).get("tiktok", {})
            if signal.get("mode") == "real":
                payload = {"source": "tiktok_creators", "mode": "real", "niche": niche, "total_creators": 1, "creators": [{"creator_id": f"@real_{niche}", "display_name": signal.get("title") or niche, "followers": min_followers, "tier": "micro", "engagement_rate": 0.0}], "tier_distribution": {"micro": 1}}
                _attach_external_signal_context(payload, external_bundle=external, source_name="tiktok")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="tiktok_business_api", exc=api_error, fallback_mode="external_signal")
                return payload
        await asyncio.sleep(random.uniform(0.08, 0.2))
        creators = []
        tier_map = {"nano": (1000, 10000), "micro": (10000, 50000), "mid": (50000, 500000), "macro": (500000, 1000000), "mega": (1000000, 50000000)}
        for i in range(max_results):
            followers = random.randint(min_followers, min_followers * 100)
            avg_views = int(followers * random.uniform(0.05, 0.25))
            avg_likes = int(avg_views * random.uniform(0.04, 0.15))
            if followers < 10000:
                tier = "nano"
            elif followers < 50000:
                tier = "micro"
            elif followers < 500000:
                tier = "mid"
            elif followers < 1000000:
                tier = "macro"
            else:
                tier = "mega"
            creators.append({
                "creator_id": f"@{niche.lower()}_creator_{i+1}",
                "display_name": f"{niche} Expert #{i+1}",
                "followers": followers,
                "tier": tier,
                "avg_video_views": avg_views,
                "avg_likes": avg_likes,
                "engagement_rate": round((avg_likes + avg_views * 0.01) / max(avg_views, 1) * 100, 2),
                "videos_posted": random.randint(50, 2000),
                "niche": niche,
                "estimated_cpm": round(random.uniform(5, 50), 2),
                "collab_success_rate": round(random.uniform(0.6, 0.95), 2),
            })
        creators.sort(key=lambda c: c["followers"], reverse=True)
        payload = {
            "source": "tiktok_creators",
            "mode": "mock",
            "niche": niche,
            "total_creators": len(creators),
            "creators": creators,
            "tier_distribution": {tier: len([c for c in creators if c["tier"] == tier]) for tier in tier_map},
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="tiktok_business_api", exc=api_error, fallback_mode="mock_preview")
        return payload


class GoogleTrendsTool(AgentTool):
    def __init__(self):
        super().__init__(
            name="google_trends",
            description="获取Google Trends搜索趋势、地域分布和相关查询",
            func=self._get_trends,
            parameters={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "关键词列表"},
                    "time_range": {"type": "string", "description": "时间范围: 3m/12m/5y", "default": "12m"},
                    "geo": {"type": "string", "description": "地区代码", "default": "US"},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["keywords"],
            },
        )

    async def _get_trends(self, keywords: list[str], time_range: str = "12m", geo: str = "US", mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        request_payload = {"keywords": list(keywords), "time_range": time_range, "geo": geo, "mode": resolved_mode}
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            client = GoogleTrendsClient(
                api_endpoint=settings.google_trends_endpoint,
                api_key=settings.google_trends_api_key,
                timeout_seconds=settings.google_trends_timeout_seconds,
                retry_policy=_build_retry_policy(settings),
            )
            try:
                html = await client.fetch_interest_over_time(keywords=keywords, geo=geo, time_range=time_range)
                if html:
                    payload = {
                        "source": "google_trends",
                        "mode": "real",
                        "keywords": keywords,
                        "time_range": time_range,
                        "geo": geo,
                        "trend_data": {kw: {"avg_interest": 0, "peak_value": 0, "trend_direction": "flat", "monthly_data": []} for kw in keywords},
                        "regional_interest": [],
                        "related_queries": [],
                        "collected_at": datetime.now(UTC).isoformat(),
                        "raw_page_title_present": "trends" in html.lower(),
                    }
                    await _publish_raw_collection_event(
                        topic=RAW_TRENDS_TOPIC,
                        source="google_trends",
                        event_type="google.trends.collected",
                        request=request_payload,
                        payload=payload,
                    )
                    return payload
            except Exception as exc:
                api_error = exc
                if resolved_mode == "real":
                    raise
            external = await ExternalSignalService().collect_business_real_signals(query=" ".join(keywords), mode=resolved_mode, required_real_sources=1)
            signal = (external.get("sources") or {}).get("google_trends", {})
            if signal.get("mode") == "real":
                payload = {
                    "source": "google_trends",
                    "mode": "real",
                    "keywords": keywords,
                    "time_range": time_range,
                    "geo": geo,
                    "trend_data": {kw: {"avg_interest": 0, "peak_value": 0, "trend_direction": "flat", "monthly_data": []} for kw in keywords},
                    "regional_interest": [],
                    "related_queries": [],
                    "collected_at": datetime.now(UTC).isoformat(),
                    "real_signal": signal,
                }
                _attach_external_signal_context(payload, external_bundle=external, source_name="google_trends")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="google_trends", exc=api_error, fallback_mode="external_signal")
                await _publish_raw_collection_event(
                    topic=RAW_TRENDS_TOPIC,
                    source="google_trends",
                    event_type="google.trends.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload
        scenario = BusinessScenarioCatalogService().resolve_external_scenario("google_trends", " ".join(keywords))
        if scenario:
            response = scenario.get("response", {})
            points = list(response.get("interest_over_time") or [])
            trend_data = {}
            for kw in keywords:
                if points:
                    trend_direction = _resolve_google_trend_direction(points, response)
                    trend_data[kw] = {
                        "avg_interest": round(sum(p["value"] for p in points) / len(points), 1),
                        "peak_value": max(p["value"] for p in points),
                        "trend_direction": trend_direction,
                        "monthly_data": points,
                        "risk_flag": response.get("risk_flag"),
                    }
                else:
                    trend_data[kw] = {
                        "avg_interest": 0,
                        "peak_value": 0,
                        "trend_direction": "flat",
                        "monthly_data": [],
                        "risk_flag": response.get("risk_flag"),
                    }
            payload = {
                "source": "google_trends",
                "mode": "mock",
                "keywords": keywords,
                "time_range": time_range,
                "geo": geo,
                "trend_data": trend_data,
                "regional_interest": [],
                "related_queries": [],
                "collected_at": datetime.now(UTC).isoformat(),
                "growth_rate_30d": response.get("growth_rate_30d"),
                "growth_rate_7d": response.get("growth_rate_7d"),
                "scenario": _scenario_meta(scenario),
                "degraded": False,
                "degradation_reason": None,
            }
            if api_error is not None:
                _mark_degraded_payload(payload, provider="google_trends", exc=api_error, fallback_mode="mock_scenario")
            await _publish_raw_collection_event(
                topic=RAW_TRENDS_TOPIC,
                source="google_trends",
                event_type="google.trends.collected",
                request=request_payload,
                payload=payload,
            )
            return payload
        await asyncio.sleep(random.uniform(0.1, 0.2))
        trend_data = {}
        for kw in keywords:
            points = []
            base_value = random.randint(30, 80)
            for month_offset in range(12, 0, -1):
                seasonal = math.sin(month_offset / 12 * 2 * math.pi) * 20
                noise = random.uniform(-10, 10)
                value = max(5, min(100, int(base_value + seasonal + noise)))
                month_label = (datetime.now(UTC) - timedelta(days=month_offset * 30)).strftime("%Y-%m")
                points.append({"date": month_label, "value": value})
            trend_data[kw] = {
                "avg_interest": round(sum(p["value"] for p in points) / len(points), 1),
                "peak_value": max(p["value"] for p in points),
                "trend_direction": "up" if points[-1]["value"] > points[0]["value"] else "down",
                "monthly_data": points,
            }
        regions = [{"region": "California", "score": random.randint(70, 100)}, {"region": "Texas", "score": random.randint(50, 85)}, {"region": "Florida", "score": random.randint(45, 80)}, {"region": "New York", "score": random.randint(55, 90)}, {"region": "Illinois", "score": random.randint(30, 65)}, {"region": "Pennsylvania", "score": random.randint(25, 60)}, {"region": "Ohio", "score": random.randint(20, 55)}, {"region": "Georgia", "score": random.randint(35, 70)}]
        related_queries = []
        for kw in keywords[:2]:
            related_queries.extend([
                {"query": f"{kw} best seller", "type": "related", "score": random.randint(60, 95)},
                {"query": f"{kw} vs competitor", "type": "comparison", "score": random.randint(40, 80)},
                {"query": f"cheap {kw}", "type": "related", "score": random.randint(30, 70)},
                {"query": f"{kw} review", "type": "related", "score": random.randint(50, 85)},
            ])
        related_queries.sort(key=lambda x: x["score"], reverse=True)
        payload = {
            "source": "google_trends",
            "mode": "mock",
            "keywords": keywords,
            "time_range": time_range,
            "geo": geo,
            "trend_data": trend_data,
            "regional_interest": sorted(regions, key=lambda r: r["score"], reverse=True),
            "related_queries": related_queries[:12],
            "collected_at": datetime.now(UTC).isoformat(),
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="google_trends", exc=api_error, fallback_mode="mock_preview")
        await _publish_raw_collection_event(
            topic=RAW_TRENDS_TOPIC,
            source="google_trends",
            event_type="google.trends.collected",
            request=request_payload,
            payload=payload,
        )
        return payload


class Tool1688(AgentTool):
    def __init__(self):
        super().__init__(
            name="ali1688_supply",
            description="采集1688供应商信息、批发价格和库存数据",
            func=self._collect_supply_chain,
            parameters={
                "type": "object",
                "properties": {
                    "product_keyword": {"type": "string", "description": "产品关键词"},
                    "max_suppliers": {"type": "integer", "description": "最大供应商数", "default": 10},
                    "mode": {"type": "string", "description": "real/auto/mock", "default": "auto"},
                },
                "required": ["product_keyword"],
            },
        )

    async def _collect_supply_chain(self, product_keyword: str, max_suppliers: int = 10, mode: str = "mock") -> dict:
        resolved_mode = _normalize_mode(mode)
        request_payload = {"product_keyword": product_keyword, "max_suppliers": max_suppliers, "mode": resolved_mode}
        api_error: Exception | None = None
        if resolved_mode != "mock":
            settings = get_settings().collection_api
            if settings.ali1688_api_key:
                client = Ali1688OpenClient(
                    api_endpoint=settings.ali1688_endpoint,
                    api_key=settings.ali1688_api_key,
                    secret_key=settings.ali1688_secret_key,
                    timeout_seconds=settings.ali1688_timeout_seconds,
                    retry_policy=_build_retry_policy(settings),
                )
                try:
                    payload = await client.fetch_suppliers(keyword=product_keyword, page_size=max_suppliers)
                    suppliers = list(payload.get("suppliers") or payload.get("items") or [])[:max_suppliers]
                    if suppliers:
                        payload = {
                            "source": "ali1688",
                            "mode": "real",
                            "keyword": product_keyword,
                            "total_suppliers": len(suppliers),
                            "suppliers": suppliers,
                            "price_range_usd": {"min": 0, "max": 0, "median": 0},
                            "avg_lead_time": 0.0,
                            "verified_supplier_ratio": 0.0,
                        }
                        await _publish_raw_collection_event(
                            topic=RAW_1688_TOPIC,
                            source="ali1688",
                            event_type="ali1688.supply.collected",
                            request=request_payload,
                            payload=payload,
                        )
                        return payload
                except Exception as exc:
                    api_error = exc
                    if resolved_mode == "real":
                        raise
            external = await ExternalSignalService().collect_business_real_signals(query=product_keyword, mode=resolved_mode, required_real_sources=1)
            signal = (external.get("sources") or {}).get("ali1688", {})
            if signal.get("mode") == "real":
                payload = {
                    "source": "ali1688",
                    "mode": "real",
                    "keyword": product_keyword,
                    "total_suppliers": 1,
                    "suppliers": [{"supplier_id": f"SUP-REAL-{abs(hash(product_keyword)) % 100000}", "company_name": signal.get("title") or product_keyword, "is_verified": False, "lead_time_days": 0, "moq_tiers": []}],
                    "price_range_usd": {"min": 0, "max": 0, "median": 0},
                    "avg_lead_time": 0.0,
                    "verified_supplier_ratio": 0.0,
                }
                _attach_external_signal_context(payload, external_bundle=external, source_name="ali1688")
                if api_error is not None:
                    _mark_degraded_payload(payload, provider="ali1688_open_api", exc=api_error, fallback_mode="external_signal")
                await _publish_raw_collection_event(
                    topic=RAW_1688_TOPIC,
                    source="ali1688",
                    event_type="ali1688.supply.collected",
                    request=request_payload,
                    payload=payload,
                )
                return payload
        scenario = BusinessScenarioCatalogService().resolve_external_scenario("ali1688", product_keyword)
        if scenario:
            behavior = scenario.get("behavior", {})
            suppliers = []
            for index, item in enumerate((scenario.get("response", {}).get("suppliers") or [])[:max_suppliers], start=1):
                moq = int(item.get("moq") or item.get("min_order") or 0)
                unit_price = float(item.get("unit_price") or item.get("price") or 0)
                suppliers.append(
                    {
                        "supplier_id": item.get("supplier_id") or item.get("id") or f"SUP-SCN-{index}",
                        "company_name": item.get("company_name") or item.get("name") or f"{product_keyword} Scenario Supplier #{index}",
                        "location": item.get("location") or "Scenario Factory",
                        "years_in_business": int(item.get("years_in_business") or 5),
                        "is_verified": bool(item.get("is_verified") or item.get("trade_assurance") or False),
                        "trade_assurance": bool(item.get("trade_assurance") or False),
                        "response_rate": float(item.get("response_rate") or 0.85),
                        "avg_response_hours": float(item.get("avg_response_hours") or 6.0),
                        "moq_tiers": item.get("moq_tiers") or (
                            [{"min_qty": moq, "unit_price_cny": unit_price, "unit_price_usd": round(unit_price * 0.14, 2)}]
                            if moq and unit_price
                            else []
                        ),
                        "lead_time_days": int(item.get("lead_time_days") or 0),
                        "sample_available": bool(item.get("sample_available") or False),
                        "oem_odm_supported": bool(item.get("oem_odm_supported") or False),
                        "monthly_capacity": int(item.get("monthly_capacity") or 10000),
                        "defect_rate_pct": float(item.get("defect_rate_pct") or 1.0),
                        "rating": float(item.get("rating") or 4.2),
                        "transaction_count": int(item.get("transaction_count") or 200),
                        "risk_flag": _derive_supply_risk_flag(item, scenario),
                        "on_time_rate": item.get("on_time_rate"),
                    }
                )
            all_moqs = [tier for supplier in suppliers for tier in supplier.get("moq_tiers", [])]
            payload = {
                "source": "ali1688",
                "mode": "mock",
                "keyword": product_keyword,
                "total_suppliers": len(suppliers),
                "suppliers": suppliers,
                "price_range_usd": {
                    "min": min((tier.get("unit_price_usd") or 0) for tier in all_moqs) if all_moqs else 0,
                    "max": max((tier.get("unit_price_usd") or 0) for tier in all_moqs) if all_moqs else 0,
                    "median": sorted((tier.get("unit_price_usd") or 0) for tier in all_moqs)[len(all_moqs) // 2] if all_moqs else 0,
                },
                "avg_lead_time": round(sum(int(s.get("lead_time_days") or 0) for s in suppliers) / max(len(suppliers), 1), 1),
                "verified_supplier_ratio": round(len([s for s in suppliers if s.get("is_verified")]) / max(len(suppliers), 1), 2),
                "scenario": _scenario_meta(scenario),
                "degraded": False,
                "degradation_reason": None,
            }
            if behavior.get("error") == "partial_data":
                payload["degraded"] = True
                payload["degradation_reason"] = "mock partial_data scenario"
            if api_error is not None:
                _mark_degraded_payload(payload, provider="ali1688_open_api", exc=api_error, fallback_mode="mock_scenario")
            await _publish_raw_collection_event(
                topic=RAW_1688_TOPIC,
                source="ali1688",
                event_type="ali1688.supply.collected",
                request=request_payload,
                payload=payload,
            )
            return payload
        await asyncio.sleep(random.uniform(0.1, 0.22))
        suppliers = []
        for i in range(max_suppliers):
            base_cost = round(random.uniform(2.0, 25.0), 2)
            moq_tiers = []
            qty = 10
            for _ in range(4):
                unit_price = round(base_cost * (1.1 - min(qty / 1000, 0.3)), 2)
                moq_tiers.append({"min_qty": qty, "unit_price_cny": unit_price, "unit_price_usd": round(unit_price * 0.14, 2)})
                qty *= 5
            suppliers.append({
                "supplier_id": f"SUP{random.randint(10000, 99999)}",
                "company_name": f"{product_keyword} Co., Ltd. #{i+1}",
                "location": random.choice(["Shenzhen, Guangdong", "Yiwu, Zhejiang", "Guangzhou, Guangdong", "Dongguan, Guangdong", "Ningbo, Zhejiang", "Foshan, Guangdong"]),
                "years_in_business": random.randint(2, 15),
                "is_verified": random.choice([True, True, True, False]),
                "trade_assurance": random.choice([True, True, False]),
                "response_rate": round(random.uniform(0.7, 0.99), 2),
                "avg_response_hours": round(random.uniform(0.5, 12), 1),
                "moq_tiers": moq_tiers,
                "lead_time_days": random.randint(3, 21),
                "sample_available": random.choice([True, True, True, False]),
                "oem_odm_supported": random.choice([True, True, False]),
                "monthly_capacity": random.randint(5000, 200000),
                "defect_rate_pct": round(random.uniform(0.1, 3.0), 2),
                "rating": round(random.uniform(3.8, 5.0), 1),
                "transaction_count": random.randint(50, 10000),
            })
        suppliers.sort(key=lambda s: s["rating"], reverse=True)
        all_moqs = []
        for s in suppliers:
            all_moqs.extend(s["moq_tiers"])
        payload = {
            "source": "ali1688",
            "mode": "mock",
            "keyword": product_keyword,
            "total_suppliers": len(suppliers),
            "suppliers": suppliers,
            "price_range_usd": {
                "min": min(t["unit_price_usd"] for t in all_moqs),
                "max": max(t["unit_price_usd"] for t in all_moqs),
                "median": sorted(t["unit_price_usd"] for t in all_moqs)[len(all_moqs) // 2],
            },
            "avg_lead_time": round(sum(s["lead_time_days"] for s in suppliers) / len(suppliers), 1),
            "verified_supplier_ratio": round(len([s for s in suppliers if s["is_verified"]]) / len(suppliers), 2),
        }
        if api_error is not None:
            _mark_degraded_payload(payload, provider="ali1688_open_api", exc=api_error, fallback_mode="mock_preview")
        await _publish_raw_collection_event(
            topic=RAW_1688_TOPIC,
            source="ali1688",
            event_type="ali1688.supply.collected",
            request=request_payload,
            payload=payload,
        )
        return payload


class DataCollectionAgent(BaseAgent):
    name = "data_collection"
    agent_type = "data_collection"
    description = "多源官方API与外部信号采集Agent，负责Amazon/TikTok/Google Trends/1688数据获取与融合"
    REQUIRED_INPUT_KEYS = {"query"}

    def __init__(self, config: dict | None = None):
        super().__init__(config=config or {})
        self._register_tools()
        self.quality_threshold = self.config.get("quality_threshold", 0.85)

    def _register_tools(self):
        for tool in [AmazonBSRTool(), AmazonReviewTool(), AmazonPriceTool(), TikTokProductTool(), TikTokCreatorTool(), GoogleTrendsTool(), Tool1688()]:
            self.register_tool(tool)

    async def validate_input(self, input_data: dict[str, Any]):
        await super().validate_input(input_data)
        if "query" not in input_data or not input_data["query"].strip():
            raise ValueError("query不能为空")

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        query = input_data.get("query", "")
        category = input_data.get("category", query)
        asin = input_data.get("asin", f"B0{random.randint(10000000, 99999999)}X")
        niche = input_data.get("niche", category)
        keywords = input_data.get("keywords", [query, f"{category} best seller"])
        mode = _normalize_mode(str(input_data.get("mode") or "auto"))

        retrieve_step = self._create_step("multi_source_collection", "retrieve", input_data=query[:100])
        tasks = [
            asyncio.create_task(self.call_tool("amazon_bsr", category=category, top_n=15, mode=mode), name="amazon_bsr"),
            asyncio.create_task(self.call_tool("amazon_reviews", asin=asin, max_reviews=80, mode=mode), name="amazon_reviews"),
            asyncio.create_task(self.call_tool("amazon_price", asin=asin, days_history=60, mode=mode), name="amazon_price"),
            asyncio.create_task(self.call_tool("tiktok_products", query=query, top_n=12, mode=mode), name="tiktok_products"),
            asyncio.create_task(self.call_tool("tiktok_creators", niche=niche, max_results=8, mode=mode), name="tiktok_creators"),
            asyncio.create_task(self.call_tool("google_trends", keywords=keywords, time_range="12m", mode=mode), name="google_trends"),
            asyncio.create_task(self.call_tool("ali1688_supply", product_keyword=category, max_suppliers=8, mode=mode), name="ali1688"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        source_names = ["amazon_bsr", "amazon_reviews", "amazon_price", "tiktok_products", "tiktok_creators", "google_trends", "ali1688"]
        collection_results = []
        errors = []
        for name, result in zip(source_names, results, strict=False):
            if isinstance(result, Exception):
                errors.append({"source": name, "error": str(result)})
                collection_results.append(CollectionResult(source=DataSource(name.split("_")[0]), query=query, data={}, error=str(result), quality_score=0.0))
            else:
                record_count = _resolve_record_count(result)
                collection_results.append(CollectionResult(source=DataSource(name.split("_")[0]), query=query, data=result, record_count=record_count, quality_score=self._score_quality(result)))
        quality_report = self._generate_quality_report(collection_results)
        successful_sources = [r for r in collection_results if r.error is None]
        failed_sources = [r for r in collection_results if r.error]
        non_real_sources = [
            {
                "source": source_name,
                "mode": ((result.data or {}).get("mode") if isinstance(result.data, dict) else None) or "unknown",
            }
            for source_name, result in zip(source_names, collection_results, strict=False)
            if result.error is None and (((result.data or {}).get("mode") if isinstance(result.data, dict) else None) != "real")
        ]
        source_level_degraded = [
            {
                "source": source_name,
                "degradation_reason": (result.data or {}).get("degradation_reason"),
            }
            for source_name, result in zip(source_names, collection_results, strict=False)
            if result.error is None and isinstance(result.data, dict) and bool(result.data.get("degraded"))
        ]
        external_signal_fallbacks = [
            {
                "source": source_name,
                "source_channel": ((result.data or {}).get("signal_context") or {}).get("source_channel"),
                "readiness_tier": ((result.data or {}).get("signal_readiness") or {}).get("readiness_tier"),
            }
            for source_name, result in zip(source_names, collection_results, strict=False)
            if result.error is None
            and isinstance(result.data, dict)
            and isinstance(result.data.get("signal_context"), dict)
            and (result.data.get("signal_context") or {}).get("provider") == "external_signal_service"
        ]
        external_signal_summary = _build_external_signal_summary(source_names, collection_results)
        degraded = bool(
            failed_sources
            or source_level_degraded
            or (mode == "auto" and (non_real_sources or external_signal_summary.get("has_external_signal_fallbacks")))
        )
        retrieve_step.output_data = f"采集完成: {len(successful_sources)}/{len(collection_results)} 源成功, 总记录数: {sum(r.record_count for r in collection_results)}, 质量评分: {quality_report.validity_rate:.1%}"
        fusion_step = self._create_step("data_fusion", "process")
        fused_data = self._fuse_data(collection_results)
        fusion_step.output_data = f"融合完成: {len(fused_data)} 个维度"

        if mode == "real":
            real_mode_errors = list(errors)
            real_mode_errors.extend(
                {
                    "source": item["source"],
                    "error": f"real mode requires real data but got {item['mode']}"
                }
                for item in non_real_sources
            )
            real_mode_errors.extend(
                {
                    "source": item["source"],
                    "error": item["degradation_reason"] or "real mode received degraded fallback payload",
                }
                for item in source_level_degraded
            )
            real_mode_errors.extend(
                {
                    "source": item["source"],
                    "error": "real mode requires formal source data but got external signal fallback",
                }
                for item in external_signal_fallbacks
            )
            if real_mode_errors:
                raise ValueError(json.dumps({
                    "message": "real mode collection failed",
                    "degraded": False,
                    "errors": real_mode_errors,
                }, ensure_ascii=False))

        llm_summary = ""
        llm_summary_structured: dict[str, Any] = {}
        try:
            from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway

            gateway = LLMGateway(GatewayConfig())
            llm_step = self._create_step("llm_data_summary", "reason")
            summary_payload = {
                "quality": {
                    "validity_rate": round(quality_report.validity_rate, 4),
                    "total_records": quality_report.total_records,
                    "anomaly_count": quality_report.anomaly_count,
                },
                "sources": {
                    "successful": len([r for r in collection_results if r.error is None]),
                    "failed": len([r for r in collection_results if r.error]),
                },
                "fused_insights": fused_data,
            }
            prompt = (
                f"你是跨境电商数据分析师。请基于以下数据采集结果输出结构化结论：\n"
                f"{json.dumps(summary_payload, ensure_ascii=False)}\n\n"
                f"请仅输出JSON对象，包含字段: "
                f"market_heat(1-10), competition_level(low/medium/high), "
                f"supply_chain_maturity(1-10), recommendation(string)"
            )
            llm_result = await gateway.route(prompt=prompt)
            llm_summary = llm_result.response
            llm_summary_structured = self._parse_llm_json_response(llm_result.response)
            llm_step.output_data = f"LLM总结完成 ({llm_result.tokens_used} tokens)"
            llm_step.status = "success"
        except Exception as e:
            logger.warning(f"LLM数据总结降级: {e}")

        return {
            "query": query,
            "category": category,
            "requested_mode": mode,
            "runtime_mode": "degraded" if degraded else mode,
            "degraded": degraded,
            "degradation_reason": "部分数据源未返回真实数据或采集失败" if degraded else None,
            "source_mode_breakdown": [
                {
                    "source": source_name,
                    "mode": ((result.data or {}).get("mode") if isinstance(result.data, dict) else None) or ("error" if result.error else "unknown"),
                    "record_count": result.record_count,
                    "degraded": bool((result.data or {}).get("degraded")) if isinstance(result.data, dict) else False,
                    "degradation_reason": (result.data or {}).get("degradation_reason") if isinstance(result.data, dict) else None,
                    "signal_context": (result.data or {}).get("signal_context") if isinstance(result.data, dict) else None,
                    "signal_readiness": (result.data or {}).get("signal_readiness") if isinstance(result.data, dict) else None,
                    "error": result.error,
                }
                for source_name, result in zip(source_names, collection_results, strict=False)
            ],
            "collection_timestamp": datetime.now(UTC).isoformat(),
            "external_signal_summary": external_signal_summary,
            "sources_summary": {
                "total_sources": len(collection_results),
                "successful": len(successful_sources),
                "failed": len(failed_sources),
                "errors": errors,
                "external_signal_fallbacks": external_signal_fallbacks,
            },
            "quality_report": {"validity_rate": quality_report.validity_rate, "is_acceptable": quality_report.is_acceptable, "total_records": quality_report.total_records, "anomaly_count": quality_report.anomaly_count},
            "amazon_data": {"bsr": collection_results[0].data if not collection_results[0].error else None, "reviews": collection_results[1].data if not collection_results[1].error else None, "price": collection_results[2].data if not collection_results[2].error else None},
            "tiktok_data": {"products": collection_results[3].data if not collection_results[3].error else None, "creators": collection_results[4].data if not collection_results[4].error else None},
            "trend_data": collection_results[5].data if not collection_results[5].error else None,
            "supplier_data": collection_results[6].data if not collection_results[6].error else None,
            "supply_chain_data": collection_results[6].data if not collection_results[6].error else None,
            "fused_insights": fused_data,
            "llm_summary": llm_summary,
            "llm_summary_structured": llm_summary_structured,
        }

    async def format_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        qs = raw_output.get("quality_report", {})
        summary = raw_output.get("sources_summary", {})
        emoji = "✅" if qs.get("is_acceptable") else "⚠️"
        degraded = bool(raw_output.get("degraded"))
        runtime_mode = raw_output.get("runtime_mode") or raw_output.get("requested_mode") or "unknown"
        external_signal_summary = raw_output.get("external_signal_summary", {})
        text_summary = f"{emoji} 数据采集完成 [{raw_output.get('query', '')}]\n成功: {summary.get('successful', 0)}/{summary.get('total_sources', 0)} 个数据源\n质量合格率: {qs.get('validity_rate', 0):.1%}\n异常数据: {qs.get('anomaly_count', 0)} 条\n运行模式: {runtime_mode}\n"
        if degraded and raw_output.get("degradation_reason"):
            text_summary += f"降级原因: {raw_output.get('degradation_reason')}\n"
        if external_signal_summary.get("fallback_tool_count"):
            text_summary += (
                f"external signal fallback: {external_signal_summary.get('fallback_tool_count', 0)} tools / "
                f"{len(external_signal_summary.get('fallback_business_sources', []))} business sources\n"
            )
        return {"status": "success", "summary": text_summary, "data": raw_output, "collection_id": self.agent_id}

    def _score_quality(self, data: dict) -> float:
        if not data:
            return 0.0
        score = 1.0
        required_keys = ["source"]
        for key in required_keys:
            if key not in data:
                score -= 0.2
        record_count = data.get("total_results", data.get("total_suppliers", data.get("total_creators", 0)))
        if record_count == 0:
            score -= 0.3
        return max(0.0, min(1.0, score))

    def _generate_quality_report(self, results: list[CollectionResult]) -> DataQualityReport:
        report = DataQualityReport()
        report.sources_checked = [r.source.value for r in results]
        for r in results:
            report.total_records += r.record_count
            if r.quality_score >= self.quality_threshold:
                report.valid_records += r.record_count
        return report

    def _fuse_data(self, results: list[CollectionResult]) -> dict:
        insights: dict[str, Any] = {}
        bsr_data = results[0].data if not results[0].error else {}
        tiktok_data = results[3].data if not results[3].error else {}
        supply_data = results[6].data if not results[6].error else {}
        bsr_products = bsr_data.get("products", [])
        tiktok_products = tiktok_data.get("products", [])
        suppliers = supply_data.get("suppliers", [])
        if bsr_products and tiktok_products:
            avg_amazon_price = sum(float(p.get("price") or 0) for p in bsr_products) / len(bsr_products)
            avg_tiktok_price = sum(float(p.get("price_usd") or 0) for p in tiktok_products) / len(tiktok_products)
            insights["price_comparison"] = {"amazon_avg": round(avg_amazon_price, 2), "tiktok_avg": round(avg_tiktok_price, 2), "ratio": round(avg_tiktok_price / max(avg_amazon_price, 0.01), 2)}
        if suppliers:
            cost_range = supply_data.get("price_range_usd", {})
            insights["margin_potential"] = {"supply_cost_min": cost_range.get("min", 0), "supply_cost_max": cost_range.get("max", 0), "suggested_retail_low": round(cost_range.get("min", 0) * 3, 2), "suggested_retail_high": round(cost_range.get("max", 0) * 4, 2)}
        total_views = tiktok_data.get("total_views", 0)
        total_revenue = bsr_data.get("total_est_monthly_revenue", 0)
        insights["market_signal"] = {"tiktok_total_views": total_views, "amazon_est_monthly_revenue": total_revenue, "social_commerce_strength": "high" if total_views > 50000000 else "medium" if total_views > 10000000 else "low"}
        return insights


def _calc_price_stats(prices: list[float]) -> dict:
    if not prices:
        return {"min": 0, "max": 0, "avg": 0, "median": 0}
    sorted_p = sorted(prices)
    buckets = {"$0-20": 0, "$20-50": 0, "$50-100": 0, "$100+": 0}
    for p in prices:
        if p < 20:
            buckets["$0-20"] += 1
        elif p < 50:
            buckets["$20-50"] += 1
        elif p < 100:
            buckets["$50-100"] += 1
        else:
            buckets["$100+"] += 1
    return {"min": round(min(prices), 2), "max": round(max(prices), 2), "avg": round(sum(prices) / len(prices), 2), "median": round(sorted_p[len(sorted_p) // 2], 2), "distribution": buckets}


def _calc_rating_stats(ratings: list[float]) -> dict:
    if not ratings:
        return {"avg": 0, "distribution": {}}
    buckets = {"5 star": 0, "4 star": 0, "3 star": 0, "2 star": 0, "1 star": 0}
    for r in ratings:
        if r >= 4.5:
            buckets["5 star"] += 1
        elif r >= 3.5:
            buckets["4 star"] += 1
        elif r >= 2.5:
            buckets["3 star"] += 1
        elif r >= 1.5:
            buckets["2 star"] += 1
        else:
            buckets["1 star"] += 1
    return {"avg": round(sum(ratings) / len(ratings), 2), "distribution": buckets}


def _random_date(months_ago: int = 6) -> str:
    days_ago = random.randint(0, months_ago * 30)
    date = datetime.now(UTC) - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")
