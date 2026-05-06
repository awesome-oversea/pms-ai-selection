from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.crawlers.amazon import AntiCrawlConfig, ProxyPool
from src.infrastructure.kafka import get_memory_messages, send_message
from src.services.competitor_site_collection_service import CompetitorSiteCollectionService
from src.services.crawl_governance_service import BloomFilterDeduper, CrawlDataQualityService, CrawlGovernanceService
from src.services.forum_collection_service import ForumCollectionService
from src.services.local_crawl_runtime_service import LocalCrawlRuntimeService
from src.services.media_blog_collection_service import MediaBlogCollectionService
from src.services.patent_signal_service import PatentSignalService
from src.services.price_site_collection_service import PriceSiteCollectionService
from src.services.proxy_provider_service import ProxyProviderService
from src.services.social_media_collection_service import SocialMediaCollectionService


class CrawlPlatformService:
    DEFAULT_ARTIFACT_PATH = Path("artifacts/crawl_platform/latest_run.json")
    DEFAULT_SCHEDULER_ARTIFACT_PATH = Path("artifacts/crawl_platform/scheduler_latest.json")

    def __init__(
        self,
        artifact_path: Path | None = None,
        *,
        scheduler_artifact_path: Path | None = None,
        runtime_service: LocalCrawlRuntimeService | None = None,
    ) -> None:
        self.proxy_provider = ProxyProviderService()
        self.proxy_pool = ProxyPool(
            self.proxy_provider.resolve_proxy_pool(),
            max_failures=AntiCrawlConfig.PROXY_MAX_FAILURES,
            cooldown_seconds=AntiCrawlConfig.PROXY_COOLDOWN_SECONDS,
        )
        self.deduper = BloomFilterDeduper(size=4096)
        self.quality = CrawlDataQualityService()
        self.governance = CrawlGovernanceService()
        self.artifact_path = artifact_path or self.DEFAULT_ARTIFACT_PATH
        self.scheduler_artifact_path = scheduler_artifact_path or self.DEFAULT_SCHEDULER_ARTIFACT_PATH
        self.runtime_service = runtime_service or LocalCrawlRuntimeService()

    def build_status(self) -> dict[str, Any]:
        jobs = self._build_jobs()
        latest_run = self._read_json(self.artifact_path)
        latest_scheduler_run = self._read_json(self.scheduler_artifact_path)
        runtime_status = self.runtime_service.build_status()
        proxy_provider_runtime = self.proxy_provider.build_status()
        proxy_pool_status = self.proxy_pool.build_status()
        proxy_pool_status["source"] = proxy_provider_runtime["proxy_pool_source"]
        proxy_pool_status["configured_proxy_count"] = proxy_provider_runtime["configured_proxy_count"]
        latest_acceptance = runtime_status.get("latest_acceptance") or {}
        scrapy_ready = bool(runtime_status["scrapy"]["installed"])
        playwright_ready = bool(runtime_status["playwright"]["package_installed"])
        acceptance_ready = bool(latest_acceptance.get("accepted"))
        engines = [
            {
                "engine_key": "scrapy-compatible",
                "runtime": "scrapy-cli",
                "strengths": ["forum-crawl", "content-extract", "batch-schedule"],
                "ready": scrapy_ready,
                "acceptance_ready": bool(latest_acceptance.get("scrapy", {}).get("ready")),
            },
            {
                "engine_key": "playwright-compatible",
                "runtime": "chromium-browser",
                "strengths": ["dynamic-page", "rendered-dom", "anti-bot-friendly"],
                "ready": playwright_ready,
                "acceptance_ready": bool(latest_acceptance.get("playwright", {}).get("ready")),
            },
        ]
        return {
            "platform": "unified-crawl-platform",
            "engines": engines,
            "engine_count": len(engines),
            "deployment": {
                "mode": "local-real-scrapy-playwright-runner" if scrapy_ready and playwright_ready else "local-scrapy-playwright-runner",
                "runner": "CrawlPlatformService.run_local_crawl",
                "scheduler_runner": "CrawlPlatformService.run_scheduled_jobs_once",
                "artifact_path": self.artifact_path.as_posix(),
                "scheduler_artifact_path": self.scheduler_artifact_path.as_posix(),
                "runtime_acceptance_artifact": runtime_status["acceptance_artifact"],
                "scrapy_command": "python -m scrapy crawl local_site -a start_url=<fixture_url> -a query=<keyword>",
                "playwright_command": "python -m src.workers.crawl_runner --engine playwright-compatible --query <keyword> --mode real",
                "scheduler_command": "python -m src.workers.crawl_scheduler_worker --run-once --query <keyword> --mode real",
                "storage_topic": "pms-data-collection",
                "ready": True,
            },
            "latest_run": latest_run,
            "latest_scheduler_run": latest_scheduler_run,
            "runtime_acceptance": runtime_status,
            "proxy_pool": proxy_pool_status,
            "proxy_provider_runtime": proxy_provider_runtime,
            "dedupe": {
                "engine": "bloom-filter",
                "size": self.deduper.size,
                "ready": True,
            },
            "quality": {
                "supported_sources": sorted(self.quality.REQUIRED_BY_SOURCE.keys()),
                "ready": True,
            },
            "governance": {
                "default_user_agent": self.governance.DEFAULT_USER_AGENT,
                "robots_policy": "respect-robots-when-available",
                "privacy_redaction": True,
                "ready": True,
            },
            "scheduler": {
                "job_count": len(jobs),
                "enabled_job_count": sum(1 for job in jobs if job["enabled"]),
                "artifact_path": self.scheduler_artifact_path.as_posix(),
                "latest_run": latest_scheduler_run,
                "ready": True,
            },
            "jobs": jobs,
            "job_count": len(jobs),
            "ready": True,
            "local_real_ready": acceptance_ready,
        }

    async def run_local_crawl(
        self,
        *,
        query: str,
        mode: str = "mock",
        topic: str = "pms-data-collection",
        engine: str = "all",
    ) -> dict[str, Any]:
        real_engine_runs: list[dict[str, Any]] = []
        if mode == "real":
            raw_results = await self._run_real_engine_collectors(query=query, engine=engine)
            collector_count = len(raw_results)
            real_engine_runs = [
                {
                    "engine": str(result.get("engine")),
                    "runtime": str(result.get("runtime")),
                    "ready": bool(result.get("ready")),
                    "item_count": int(result.get("item_count") or 0),
                    "output_path": result.get("output_path"),
                }
                for result in raw_results
            ]
            selected_engines = sorted({str(result.get("engine") or engine) for result in raw_results})
        else:
            collector_definitions = self._resolve_collectors(query=query, mode=mode, engine=engine)
            raw_results = await asyncio.gather(*(collector for _, collector in collector_definitions))
            collector_count = len(collector_definitions)
            selected_engines = sorted({engine_key for engine_key, _ in collector_definitions})
        records = self._flatten_records(raw_results)
        quality = CrawlDataQualityService().validate_records(source="rss", records=records)
        accepted_records = quality["accepted_records"]
        published = 0
        for record in accepted_records:
            await send_message(topic, {"event_type": "crawl.record.collected", "query": query, "payload": record})
            published += 1
        run = {
            "query": query,
            "mode": mode,
            "requested_engine": engine,
            "engines": selected_engines,
            "collector_count": collector_count,
            "source_count": len(raw_results),
            "record_count": len(records),
            "published_count": published,
            "duplicate_count": quality["duplicate_count"],
            "storage": {
                "topic": topic,
                "memory_message_count": len(get_memory_messages(topic)),
                "artifact_path": self.artifact_path.as_posix(),
            },
            "quality": {key: value for key, value in quality.items() if key != "accepted_records"},
            "runtime_mode": "real-engine-runtime" if mode == "real" else "compatible-collector-runtime",
            "real_engine_runs": real_engine_runs,
            "ran_at": datetime.now(UTC).isoformat(),
            "ready": published > 0,
        }
        self._write_json(self.artifact_path, run)
        return run

    async def run_scheduled_jobs_once(
        self,
        *,
        query: str,
        mode: str = "real",
        topic: str = "pms-data-collection",
        job_key: str | None = None,
    ) -> dict[str, Any]:
        job_results: list[dict[str, Any]] = []
        for job in self._build_jobs():
            if not job["enabled"]:
                continue
            if job_key and job["job_key"] != job_key:
                continue
            run = await self.run_local_crawl(query=query, mode=mode, topic=topic, engine=job["engine"])
            job_results.append(
                {
                    "job_key": job["job_key"],
                    "engine": job["engine"],
                    "schedule": job["schedule"],
                    "ready": run["ready"],
                    "published_count": run["published_count"],
                    "record_count": run["record_count"],
                    "artifact_path": run["storage"]["artifact_path"],
                }
            )
        payload = {
            "query": query,
            "mode": mode,
            "job_count": len(job_results),
            "jobs": job_results,
            "accepted": bool(job_results) and all(job["ready"] for job in job_results),
            "ran_at": datetime.now(UTC).isoformat(),
            "artifact_path": self.scheduler_artifact_path.as_posix(),
        }
        self._write_json(self.scheduler_artifact_path, payload)
        return payload

    async def _run_real_engine_collectors(self, *, query: str, engine: str) -> list[dict[str, Any]]:
        collectors: list[dict[str, Any]] = []
        if engine in {"all", "scrapy-compatible"}:
            collectors.append(await self.runtime_service.run_scrapy_fixture(query=query))
        if engine in {"all", "playwright-compatible"}:
            collectors.append(await self.runtime_service.run_playwright_fixture(query=query))
        return collectors

    def _resolve_collectors(self, *, query: str, mode: str, engine: str) -> list[tuple[str, Any]]:
        engine_key = engine or "all"
        scrapy_collectors = [
            ("scrapy-compatible", ForumCollectionService().collect(query=query, mode=mode)),
            ("scrapy-compatible", MediaBlogCollectionService().collect(query=query, mode=mode)),
            ("scrapy-compatible", PriceSiteCollectionService().collect(query=query, mode=mode)),
        ]
        playwright_collectors = [
            ("playwright-compatible", CompetitorSiteCollectionService().collect(query=query, mode=mode)),
            ("playwright-compatible", SocialMediaCollectionService().collect(query=query, mode=mode)),
            ("playwright-compatible", PatentSignalService().collect(query=query, mode=mode)),
        ]
        if engine_key == "scrapy-compatible":
            return scrapy_collectors
        if engine_key == "playwright-compatible":
            return playwright_collectors
        return scrapy_collectors + playwright_collectors

    def _build_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "job_key": "competitor_site_daily",
                "engine": "playwright-compatible",
                "schedule": "0 3 * * *",
                "targets": ["brand-site", "shopify-store"],
                "enabled": True,
            },
            {
                "job_key": "forum_hourly",
                "engine": "scrapy-compatible",
                "schedule": "0 * * * *",
                "targets": ["reddit", "sellercentral-forum"],
                "enabled": True,
            },
            {
                "job_key": "media_blog_daily",
                "engine": "scrapy-compatible",
                "schedule": "30 2 * * *",
                "targets": ["media-blog", "industry-news"],
                "enabled": True,
            },
            {
                "job_key": "patent_weekly",
                "engine": "playwright-compatible",
                "schedule": "0 4 * * 1",
                "targets": ["patent-office", "trademark-office"],
                "enabled": True,
            },
        ]

    def _flatten_records(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for result in results:
            source = str(result.get("source") or result.get("runtime") or "crawl")
            for item in result.get("records") or []:
                title = str(item.get("title") or source)
                records.append({"source": source, "title": title, "url": item.get("url") or f"local://{source}/{len(records) + 1}", **item})
            for key in ("pages", "threads", "posts", "price_curves", "articles"):
                for item in result.get(key) or []:
                    title = str(item.get("title") or item.get("topic") or item.get("site") or source)
                    records.append({"source": source, "title": title, "url": item.get("url") or f"local://{source}/{len(records) + 1}", **item})
            if result.get("search_url"):
                records.append({"source": source, "title": f"{result.get('query')} patent search", "url": result["search_url"]})
        return records

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
