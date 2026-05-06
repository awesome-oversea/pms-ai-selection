from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from src.config.settings import get_settings
from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry
from src.infrastructure.kafka import send_message


class ExternalSignalService:
    BUSINESS_SOURCE_NAMES = ("amazon", "tiktok", "google_trends", "ali1688", "media_news")
    BUSINESS_SOURCE_CHANNELS: dict[str, str] = {
        "amazon": "public_web_signal",
        "tiktok": "public_web_signal",
        "google_trends": "public_web_signal",
        "ali1688": "public_web_signal",
        "media_news": "open_api_signal",
    }
    GDELT_EVENT_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
        "trade": ("tariff", "import", "export", "shipping", "customs", "trade", "port", "container", "supply chain"),
        "political": ("election", "government", "policy", "minister", "senate", "president", "war", "sanction", "regulation"),
        "economic": ("inflation", "economy", "consumer", "retail", "spending", "recession", "interest rate", "currency", "demand"),
    }
    PRODUCT_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
        "electronics": ("bluetooth", "speaker", "audio", "wireless", "chip", "battery", "electronics", "earbuds"),
        "home_living": ("home", "kitchen", "furniture", "storage", "household"),
        "beauty_personal_care": ("beauty", "cosmetic", "skincare", "makeup", "personal care"),
        "apparel_accessories": ("fashion", "apparel", "clothing", "shoe", "bag", "accessory"),
        "sports_outdoor": ("fitness", "sport", "outdoor", "camping", "cycling"),
        "baby_maternity": ("baby", "toddler", "maternity", "infant"),
        "pet_supplies": ("pet", "dog", "cat", "petcare"),
    }
    POSITIVE_IMPACT_KEYWORDS = ("boost", "recovery", "ease", "drop", "cools", "stabilize", "growth")
    NEGATIVE_IMPACT_KEYWORDS = ("tariff", "ban", "delay", "restriction", "surge", "war", "shortage", "inflation")

    def __init__(
        self,
        timeout_seconds: float = 8.0,
        *,
        max_attempts: int | None = None,
        base_backoff_seconds: float | None = None,
        max_backoff_seconds: float | None = None,
    ) -> None:
        collection_settings = get_settings().collection_api
        self.timeout_seconds = timeout_seconds
        self.retry_policy = HTTPRetryPolicy(
            max_attempts=max_attempts or collection_settings.http_max_attempts,
            base_backoff_seconds=(
                collection_settings.http_base_backoff_seconds
                if base_backoff_seconds is None
                else base_backoff_seconds
            ),
            max_backoff_seconds=(
                collection_settings.http_max_backoff_seconds
                if max_backoff_seconds is None
                else max_backoff_seconds
            ),
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PMS-SelectionBot/1.0; +https://example.invalid/pms)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8,application/rss+xml,application/xml;q=0.9",
        }

    async def _get_text(self, url: str) -> str:
        return await request_with_retry(
            "GET",
            url,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
            follow_redirects=True,
            response_kind="text",
            policy=self.retry_policy,
        )

    async def _get_json(self, url: str) -> dict[str, Any]:
        return await request_with_retry(
            "GET",
            url,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
            follow_redirects=True,
            response_kind="json",
            policy=self.retry_policy,
        )

    async def _get_bytes(self, url: str) -> bytes:
        return await request_with_retry(
            "GET",
            url,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
            follow_redirects=True,
            response_kind="bytes",
            policy=self.retry_policy,
        )

    @staticmethod
    def _extract_title(html: str) -> str | None:
        matched = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not matched:
            return None
        return re.sub(r"\s+", " ", matched.group(1)).strip()[:200]

    async def _fetch_wikipedia(self, query: str) -> dict[str, Any]:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(query)}"
        payload = await self._get_json(url)
        return {
            "source": "wikipedia",
            "mode": "real",
            "title": payload.get("title"),
            "summary": payload.get("extract"),
            "page_url": payload.get("content_urls", {}).get("desktop", {}).get("page"),
        }

    async def _fetch_github(self, query: str) -> dict[str, Any]:
        url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page=3"
        payload = await self._get_json(url)
        items = payload.get("items", [])[:3]
        return {
            "source": "github",
            "mode": "real",
            "total_count": payload.get("total_count", 0),
            "top_items": [
                {
                    "name": item.get("full_name"),
                    "stars": item.get("stargazers_count"),
                    "url": item.get("html_url"),
                }
                for item in items
            ],
        }

    async def _fetch_hackernews(self, query: str) -> dict[str, Any]:
        url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage=3"
        payload = await self._get_json(url)
        hits = payload.get("hits", [])[:3]
        return {
            "source": "hackernews",
            "mode": "real",
            "total_count": payload.get("nbHits", 0),
            "top_hits": [
                {
                    "title": item.get("title"),
                    "points": item.get("points"),
                    "url": item.get("url"),
                }
                for item in hits
            ],
        }

    async def _fetch_amazon(self, query: str) -> dict[str, Any]:
        url = f"https://www.amazon.com/s?k={quote_plus(query)}"
        html = await self._get_text(url)
        return {
            "source": "amazon",
            "mode": "real",
            "query": query,
            "url": url,
            "title": self._extract_title(html),
            "content_length": len(html),
            "signals": {
                "has_search_results_marker": "s-result-item" in html or "results for" in html.lower(),
                "has_price_marker": "$" in html or "a-price" in html,
            },
        }

    async def _fetch_tiktok(self, query: str) -> dict[str, Any]:
        tag = re.sub(r"[^A-Za-z0-9_]+", "", query) or quote_plus(query)
        url = f"https://www.tiktok.com/tag/{tag}"
        html = await self._get_text(url)
        return {
            "source": "tiktok",
            "mode": "real",
            "query": query,
            "url": url,
            "title": self._extract_title(html),
            "content_length": len(html),
            "signals": {
                "has_tag_marker": tag.lower() in html.lower(),
                "has_video_marker": "video" in html.lower(),
            },
        }

    async def _fetch_google_trends(self, query: str) -> dict[str, Any]:
        url = f"https://trends.google.com/trends/explore?q={quote_plus(query)}&geo=US"
        html = await self._get_text(url)
        return {
            "source": "google_trends",
            "mode": "real",
            "query": query,
            "url": url,
            "title": self._extract_title(html),
            "content_length": len(html),
            "signals": {
                "has_trends_marker": "trends" in html.lower(),
                "has_query_marker": query.lower().split()[0] in html.lower() if query.split() else False,
            },
        }

    async def _fetch_ali1688(self, query: str) -> dict[str, Any]:
        url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(query)}"
        html = await self._get_text(url)
        return {
            "source": "ali1688",
            "mode": "real",
            "query": query,
            "url": url,
            "title": self._extract_title(html),
            "content_length": len(html),
            "signals": {
                "has_supplier_marker": "供应" in html or "supplier" in html.lower(),
                "has_price_marker": "价格" in html or "price" in html.lower(),
            },
        }

    async def _fetch_media_news(self, query: str) -> dict[str, Any]:
        url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={quote_plus(query)}&mode=artlist&format=json&maxrecords=5"
        payload = await self._get_json(url)
        articles = payload.get("articles", [])[:5]
        return {
            "source": "media_news",
            "mode": "real",
            "query": query,
            "url": url,
            "total_count": len(articles),
            "top_articles": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source_country": item.get("sourceCountry"),
                    "seendate": item.get("seendate"),
                }
                for item in articles
            ],
        }

    @staticmethod
    def _gdelt_url(query: str) -> str:
        return f"https://api.gdeltproject.org/api/v2/doc/doc?query={quote_plus(query)}&mode=artlist&format=json&maxrecords=5"

    @staticmethod
    def _normalize_text(parts: list[str]) -> str:
        return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip().lower()

    @staticmethod
    def _extract_http_status(exc: Exception) -> int | None:
        if isinstance(exc, UpstreamHTTPError):
            return exc.http_status
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            return exc.response.status_code
        return None

    @staticmethod
    def _extract_retry_after(exc: Exception) -> float | None:
        if isinstance(exc, UpstreamHTTPError):
            return exc.retry_after_seconds
        return None

    @staticmethod
    def _build_upstream_error(exc: Exception, *, source: str) -> dict[str, Any]:
        return {
            "source": source,
            "error_code": getattr(exc, "error_code", exc.__class__.__name__),
            "message": str(exc),
            "retryable": bool(getattr(exc, "retryable", False)),
            "http_status": getattr(exc, "http_status", None),
            "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
            "attempts": int(getattr(exc, "attempts", 1) or 1),
        }

    def _classify_gdelt_event_category(self, text: str) -> str:
        scores = {
            category: sum(1 for keyword in keywords if keyword in text)
            for category, keywords in self.GDELT_EVENT_CATEGORY_KEYWORDS.items()
        }
        best_category = max(scores, key=scores.get)
        return best_category if scores[best_category] > 0 else "economic"

    def _infer_related_categories(self, query: str, text: str) -> list[str]:
        combined = self._normalize_text([query, text])
        matched = [
            category
            for category, keywords in self.PRODUCT_CATEGORY_KEYWORDS.items()
            if any(keyword in combined for keyword in keywords)
        ]
        return matched or ["general_merchandise"]

    def _infer_impact_direction(self, text: str) -> str:
        if any(keyword in text for keyword in self.NEGATIVE_IMPACT_KEYWORDS):
            return "negative"
        if any(keyword in text for keyword in self.POSITIVE_IMPACT_KEYWORDS):
            return "positive"
        return "neutral"

    def _build_gdelt_article(self, *, query: str, article: dict[str, Any]) -> dict[str, Any]:
        title = str(article.get("title") or "")
        text = self._normalize_text([query, title, str(article.get("sourceCountry") or "")])
        event_category = self._classify_gdelt_event_category(text)
        related_categories = self._infer_related_categories(query, text)
        impact_direction = self._infer_impact_direction(text)
        return {
            "title": title,
            "url": article.get("url"),
            "source_country": article.get("sourceCountry"),
            "seendate": article.get("seendate"),
            "event_category": event_category,
            "impact_direction": impact_direction,
            "impact_score": 3 if impact_direction == "negative" else 2 if impact_direction == "neutral" else 1,
            "related_categories": related_categories,
            "association_reason": f"query/title keyword match -> {', '.join(related_categories)}",
        }

    def _build_gdelt_category_associations(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        aggregated: dict[str, dict[str, Any]] = {}
        for article in articles:
            for category in article.get("related_categories", []):
                entry = aggregated.setdefault(
                    category,
                    {
                        "category": category,
                        "article_count": 0,
                        "event_categories": set(),
                    },
                )
                entry["article_count"] += 1
                entry["event_categories"].add(article.get("event_category"))
        return [
            {
                "category": category,
                "article_count": payload["article_count"],
                "event_categories": sorted(item for item in payload["event_categories"] if item),
                "confidence": "high" if payload["article_count"] >= 2 else "medium",
            }
            for category, payload in sorted(
                aggregated.items(),
                key=lambda item: (-item[1]["article_count"], item[0]),
            )
        ]

    def _build_gdelt_business_summary(
        self,
        *,
        query: str,
        mode: str,
        articles: list[dict[str, Any]],
        degraded: bool,
        reason: str | None,
        http_status: int | None,
    ) -> dict[str, Any]:
        category_breakdown = dict.fromkeys(self.GDELT_EVENT_CATEGORY_KEYWORDS, 0)
        impact_breakdown = {"positive": 0, "neutral": 0, "negative": 0}
        for article in articles:
            category_breakdown[str(article.get("event_category") or "economic")] += 1
            impact_breakdown[str(article.get("impact_direction") or "neutral")] += 1
        associations = self._build_gdelt_category_associations(articles)
        market_bias = "risk-off" if impact_breakdown["negative"] >= max(1, impact_breakdown["positive"]) else "watchlist"
        if impact_breakdown["positive"] > impact_breakdown["negative"]:
            market_bias = "opportunity"
        headline = (
            f"GDELT事件摘要：{query} 共关联 {len(articles)} 条事件，"
            f"贸易/政治/经济分布为 {category_breakdown['trade']}/{category_breakdown['political']}/{category_breakdown['economic']}。"
        )
        recommended_actions = [
            "优先复核受贸易与关税影响的采购成本假设",
            "将高关联品类加入近7天舆情与价格联合观察清单",
        ]
        if market_bias == "opportunity":
            recommended_actions[0] = "优先复核需求恢复相关品类的补货与投放窗口"
        return {
            "headline": headline,
            "market_bias": market_bias,
            "recommended_actions": recommended_actions,
            "degradation_note": reason if degraded else None,
            "classification_summary": {
                **category_breakdown,
                "classified_count": len(articles),
            },
            "impact_direction_breakdown": impact_breakdown,
            "category_associations": associations,
            "mode": mode,
            "http_status": http_status,
        }

    def _build_mock_gdelt_articles(self, query: str) -> list[dict[str, Any]]:
        seeds = [
            {"title": f"Tariff pressure reshapes {query} import costs", "url": None, "sourceCountry": "US", "seendate": None},
            {"title": f"Consumer demand recovery lifts {query} seasonal momentum", "url": None, "sourceCountry": "US", "seendate": None},
        ]
        return [self._build_gdelt_article(query=query, article=seed) for seed in seeds]

    def _build_gdelt_payload(
        self,
        *,
        query: str,
        mode: str,
        articles: list[dict[str, Any]],
        degraded: bool,
        reason: str | None,
        http_status: int | None,
        retry_after_seconds: float | None,
        url: str | None = None,
        fallback_mode: str | None = None,
    ) -> dict[str, Any]:
        business_summary = self._build_gdelt_business_summary(
            query=query,
            mode=mode,
            articles=articles,
            degraded=degraded,
            reason=reason,
            http_status=http_status,
        )
        return {
            "source": "media_news",
            "mode": mode,
            "query": query,
            "url": url or self._gdelt_url(query),
            "total_count": len(articles),
            "top_articles": articles,
            "classification_summary": business_summary["classification_summary"],
            "category_associations": business_summary["category_associations"],
            "business_summary": business_summary,
            "degradation": {
                "degraded": degraded,
                "reason": reason,
                "http_status": http_status,
                "retry_after_seconds": retry_after_seconds,
                "fallback_mode": fallback_mode,
                "live_endpoint_ready": mode == "real" and not degraded,
                "businessization_ready": bool(articles),
            },
            "ready": bool(articles),
        }

    async def _publish_gdelt_raw_event(self, *, query: str, payload: dict[str, Any]) -> None:
        await send_message(
            "raw_news",
            {
                "event_type": "gdelt.collected",
                "raw_source": "gdelt",
                "query": query,
                "mode": payload.get("mode"),
                "degraded": (payload.get("degradation") or {}).get("degraded"),
                "payload": payload,
                "collected_at": datetime.now(UTC).isoformat(),
            },
        )

    async def collect_gdelt_event_signals(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        if mode == "mock":
            payload = self._build_gdelt_payload(
                query=query,
                mode="mock",
                articles=self._build_mock_gdelt_articles(query),
                degraded=False,
                reason=None,
                http_status=None,
                retry_after_seconds=None,
                fallback_mode=None,
            )
            await self._publish_gdelt_raw_event(query=query, payload=payload)
            return payload

        try:
            payload = await self._fetch_media_news(query)
            articles = [self._build_gdelt_article(query=query, article=article) for article in payload.get("top_articles", [])]
            gdelt_payload = self._build_gdelt_payload(
                query=query,
                mode=str(payload.get("mode") or "real"),
                articles=articles,
                degraded=False,
                reason=None,
                http_status=None,
                retry_after_seconds=None,
                url=payload.get("url"),
                fallback_mode=None,
            )
            await self._publish_gdelt_raw_event(query=query, payload=gdelt_payload)
            return gdelt_payload
        except Exception as exc:
            http_status = self._extract_http_status(exc)
            retry_after_seconds = self._extract_retry_after(exc)
            reason = str(exc)
            fallback_articles = self._build_mock_gdelt_articles(query)
            fallback_payload = self._build_gdelt_payload(
                query=query,
                mode="mock",
                articles=fallback_articles,
                degraded=True,
                reason=reason,
                http_status=http_status,
                retry_after_seconds=retry_after_seconds,
                fallback_mode="mock-gdelt-scenarios",
            )
            if mode == "real":
                error_payload = {
                    "source": "media_news",
                    "mode": "error",
                    "query": query,
                    "url": self._gdelt_url(query),
                    "total_count": 0,
                    "top_articles": [],
                    "classification_summary": {"political": 0, "economic": 0, "trade": 0, "classified_count": 0},
                    "category_associations": [],
                    "business_summary": {
                        "headline": f"GDELT真实端点暂不可用：{query}",
                        "market_bias": "watchlist",
                        "recommended_actions": [
                            "保留实时事件抓取重试，并用 fallback 预览校验品类联动逻辑",
                            "在恢复真实端点前，继续观察贸易与宏观类高风险关键词",
                        ],
                        "degradation_note": reason,
                        "classification_summary": {"political": 0, "economic": 0, "trade": 0, "classified_count": 0},
                        "impact_direction_breakdown": {"positive": 0, "neutral": 0, "negative": 0},
                        "category_associations": [],
                        "mode": "error",
                        "http_status": http_status,
                    },
                    "degradation": {
                        "degraded": True,
                        "reason": reason,
                        "http_status": http_status,
                        "retry_after_seconds": retry_after_seconds,
                        "fallback_mode": "mock-preview",
                        "live_endpoint_ready": False,
                        "businessization_ready": True,
                    },
                    "upstream_error": self._build_upstream_error(exc, source="gdelt"),
                    "fallback_preview": fallback_payload,
                    "ready": False,
                }
                await self._publish_gdelt_raw_event(query=query, payload=error_payload)
                return error_payload
            await self._publish_gdelt_raw_event(query=query, payload=fallback_payload)
            return fallback_payload

    async def _fetch_media_rss(self, query: str) -> dict[str, Any]:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        xml_bytes = await self._get_bytes(url)
        root = ET.fromstring(xml_bytes)
        items: list[dict[str, Any]] = []
        for item in root.findall(".//channel/item")[:5]:
            source_node = item.find("source")
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "url": (item.findtext("link") or "").strip() or None,
                    "source": (source_node.text or "").strip() if source_node is not None and source_node.text else None,
                    "pub_date": (item.findtext("pubDate") or "").strip() or None,
                }
            )
        return {
            "source": "media_rss",
            "mode": "real",
            "query": query,
            "url": url,
            "total_count": len(items),
            "top_articles": items,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _build_mock_response(query: str, source: str) -> dict[str, Any]:
        if source == "wikipedia":
            return {"source": source, "mode": "mock", "title": query, "summary": f"mock summary for {query}", "page_url": None}
        if source == "github":
            return {"source": source, "mode": "mock", "total_count": 1, "top_items": [{"name": f"mock/{query}", "stars": 1, "url": None}]}
        return {"source": source, "mode": "mock", "total_count": 1, "top_hits": [{"title": f"mock {query}", "points": 1, "url": None}]}

    @staticmethod
    def _build_business_mock_response(query: str, source: str) -> dict[str, Any]:
        return {
            "source": source,
            "mode": "mock",
            "query": query,
            "record_count": 1,
            "signals": {
                "keyword": query,
                "availability": "mocked",
            },
        }

    @staticmethod
    def _build_rss_mock_response(query: str) -> dict[str, Any]:
        return {
            "source": "media_rss",
            "mode": "mock",
            "query": query,
            "total_count": 1,
            "top_articles": [
                {
                    "title": f"mock rss article for {query}",
                    "url": None,
                    "source": "mock",
                    "pub_date": None,
                }
            ],
        }

    @staticmethod
    def _is_enterprise_integrated_source(payload: dict[str, Any]) -> bool:
        channel = str(payload.get("source_channel") or "").strip().lower()
        integration_level = str(payload.get("integration_level") or "").strip().lower()
        return bool(
            payload.get("enterprise_ready") is True
            or payload.get("enterprise_integrated") is True
            or integration_level == "enterprise"
            or channel == "enterprise_api"
        )

    @classmethod
    def _build_source_channel_summary(cls, results: dict[str, Any]) -> dict[str, Any]:
        channel_summary: dict[str, dict[str, Any]] = {}
        for source_name, payload in results.items():
            channel = cls.BUSINESS_SOURCE_CHANNELS.get(source_name, "unknown")
            summary = channel_summary.setdefault(
                channel,
                {
                    "source_count": 0,
                    "real_count": 0,
                    "mock_count": 0,
                    "error_count": 0,
                    "sources": [],
                },
            )
            summary["source_count"] += 1
            summary["sources"].append(source_name)
            mode = str((payload or {}).get("mode") or "unknown").lower()
            if mode == "real":
                summary["real_count"] += 1
            elif mode == "mock":
                summary["mock_count"] += 1
            elif mode == "error":
                summary["error_count"] += 1
        return channel_summary

    @classmethod
    def _annotate_business_source_payload(cls, source_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        annotated = dict(payload)
        annotated.setdefault("source", source_name)
        annotated.setdefault("source_channel", cls.BUSINESS_SOURCE_CHANNELS.get(source_name, "unknown"))
        annotated.setdefault("enterprise_integrated", cls._is_enterprise_integrated_source(annotated))
        return annotated

    @staticmethod
    def _build_business_signal_next_actions(
        *,
        required_real_sources: int,
        real_sources: list[str],
        mock_sources: list[str],
        error_sources: list[str],
        local_business_ready: bool,
        enterprise_ready: bool,
    ) -> list[str]:
        actions: list[str] = []
        if not local_business_ready:
            missing_sources = max(required_real_sources - len(real_sources), 0)
            actions.append(
                f"add at least {missing_sources} more real signal sources to reach the local validation threshold of {required_real_sources}"
            )
        if error_sources:
            actions.append(
                "stabilize upstream availability, throttling, and credentials for: " + ", ".join(sorted(error_sources))
            )
        if mock_sources:
            actions.append(
                "replace mock-only sources with real integrations or reusable public signal fallbacks: "
                + ", ".join(sorted(mock_sources))
            )
        if local_business_ready and not enterprise_ready:
            actions.append(
                "treat this bundle as local business validation only; do not mark it as enterprise integration complete"
            )
        return actions or ["keep the current multi-source regression path stable and continue replacing placeholders with formal integrations"]

    @classmethod
    def _build_business_signal_summary(
        cls,
        *,
        results: dict[str, Any],
        required_real_sources: int,
    ) -> dict[str, Any]:
        real_sources = sorted(source for source, item in results.items() if item.get("mode") == "real")
        mock_sources = sorted(source for source, item in results.items() if item.get("mode") == "mock")
        error_sources = sorted(source for source, item in results.items() if item.get("mode") == "error")
        enterprise_integrated_sources = sorted(
            source for source, item in results.items() if item.get("mode") == "real" and cls._is_enterprise_integrated_source(item)
        )
        real_count = len(real_sources)
        mock_count = len(mock_sources)
        error_count = len(error_sources)
        local_business_ready = real_count >= required_real_sources
        enterprise_ready = local_business_ready and len(enterprise_integrated_sources) >= required_real_sources
        readiness_tier = "not_ready"
        if enterprise_ready:
            readiness_tier = "enterprise_ready"
        elif local_business_ready:
            readiness_tier = "local_business_ready"
        elif real_count > 0:
            readiness_tier = "partial_real_signals"
        elif mock_count > 0 and error_count == 0:
            readiness_tier = "mock_only"
        elif error_count > 0:
            readiness_tier = "blocked"

        return {
            "real_count": real_count,
            "mock_count": mock_count,
            "error_count": error_count,
            "all_real": real_count == len(results),
            "local_business_ready": local_business_ready,
            "enterprise_ready": enterprise_ready,
            "readiness_tier": readiness_tier,
            "source_names": list(results.keys()),
            "real_sources": real_sources,
            "mock_sources": mock_sources,
            "error_sources": error_sources,
            "enterprise_integrated_sources": enterprise_integrated_sources,
            "source_channel_summary": cls._build_source_channel_summary(results),
            "next_actions": cls._build_business_signal_next_actions(
                required_real_sources=required_real_sources,
                real_sources=real_sources,
                mock_sources=mock_sources,
                error_sources=error_sources,
                local_business_ready=local_business_ready,
                enterprise_ready=enterprise_ready,
            ),
        }

    async def collect_minimal_real_signals(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        handlers = {
            "wikipedia": self._fetch_wikipedia,
            "github": self._fetch_github,
            "hackernews": self._fetch_hackernews,
        }
        results: dict[str, Any] = {}
        for source, handler in handlers.items():
            if mode == "mock":
                results[source] = self._build_mock_response(query, source)
                continue
            try:
                results[source] = await handler(query)
            except Exception as exc:
                if mode == "real":
                    results[source] = {"source": source, "mode": "error", "error": str(exc), "retryable": True}
                else:
                    fallback = self._build_mock_response(query, source)
                    fallback["fallback_reason"] = str(exc)
                    results[source] = fallback
        real_count = sum(1 for item in results.values() if item.get("mode") == "real")
        mock_count = sum(1 for item in results.values() if item.get("mode") == "mock")
        error_count = sum(1 for item in results.values() if item.get("mode") == "error")
        return {
            "query": query,
            "requested_mode": mode,
            "sources": results,
            "summary": {
                "real_count": real_count,
                "mock_count": mock_count,
                "error_count": error_count,
                "all_real": real_count == 3,
            },
        }

    async def collect_business_real_signals(
        self,
        *,
        query: str,
        mode: str = "auto",
        required_real_sources: int = 3,
    ) -> dict[str, Any]:
        handlers = {
            "amazon": self._fetch_amazon,
            "tiktok": self._fetch_tiktok,
            "google_trends": self._fetch_google_trends,
            "ali1688": self._fetch_ali1688,
            "media_news": self._fetch_media_news,
        }
        results: dict[str, Any] = {}
        for source, handler in handlers.items():
            if mode == "mock":
                if source == "media_news":
                    results[source] = self._build_gdelt_payload(
                        query=query,
                        mode="mock",
                        articles=self._build_mock_gdelt_articles(query),
                        degraded=False,
                        reason=None,
                        http_status=None,
                        retry_after_seconds=None,
                        fallback_mode=None,
                    )
                else:
                    results[source] = self._build_business_mock_response(query, source)
                continue
            try:
                if source == "media_news":
                    results[source] = await self.collect_gdelt_event_signals(query=query, mode=mode)
                else:
                    results[source] = await handler(query)
            except Exception as exc:
                if mode == "real":
                    results[source] = {"source": source, "mode": "error", "query": query, "error": str(exc), "retryable": True}
                else:
                    fallback = self._build_business_mock_response(query, source)
                    fallback["fallback_reason"] = str(exc)
                    fallback["degraded"] = True
                    fallback["degradation_reason"] = f"{source} upstream degraded; fallback to mock"
                    fallback["upstream_error"] = self._build_upstream_error(exc, source=source)
                    results[source] = fallback
        annotated_results = {
            source_name: self._annotate_business_source_payload(source_name, item)
            for source_name, item in results.items()
        }
        return {
            "query": query,
            "requested_mode": mode,
            "source_profile": "cross_border_ecommerce",
            "required_real_sources": required_real_sources,
            "sources": annotated_results,
            "summary": self._build_business_signal_summary(results=annotated_results, required_real_sources=required_real_sources),
        }

    async def collect_rss_signals(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        if mode == "mock":
            result = self._build_rss_mock_response(query)
        else:
            try:
                result = await self._fetch_media_rss(query)
            except Exception as exc:
                if mode == "real":
                    result = {
                        "source": "media_rss",
                        "mode": "error",
                        "query": query,
                        "error": str(exc),
                        "retryable": True,
                    }
                else:
                    result = self._build_rss_mock_response(query)
                    result["fallback_reason"] = str(exc)

        await send_message(
            "pms-data-collection",
            {
                "event_type": "rss.collected",
                "query": query,
                "source": "media_rss",
                "payload": result,
            },
        )
        return result

    async def build_rss_subscription_bundle(self, *, query: str, mode: str = "auto") -> dict[str, Any]:
        result = await self.collect_rss_signals(query=query, mode=mode)
        articles = result.get("top_articles", []) if isinstance(result, dict) else []
        hosts = sorted({urlparse(item.get("url") or "").netloc for item in articles if item.get("url")})
        return {
            "query": query,
            "mode": mode,
            "source": "media_rss",
            "subscription_ready": result.get("mode") in {"real", "mock"},
            "article_count": len(articles),
            "publishers": sorted({(item.get("source") or "unknown") for item in articles}),
            "hosts": hosts,
            "payload": result,
        }
