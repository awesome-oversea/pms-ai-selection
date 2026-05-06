from __future__ import annotations

from pathlib import Path

import pytest
from src.services.crawl_platform_service import CrawlPlatformService
from src.services.local_crawl_runtime_service import LocalCrawlRuntimeService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_local_crawl_runtime_acceptance_writes_outputs(tmp_path: Path):
    fixture_root = PROJECT_ROOT / "artifacts" / "crawl_platform" / "targets"
    runtime_root = tmp_path / "runtime"
    acceptance_path = tmp_path / "acceptance.json"
    service = LocalCrawlRuntimeService(
        fixture_root=fixture_root,
        runtime_root=runtime_root,
        acceptance_path=acceptance_path,
    )

    result = await service.run_acceptance(query="bluetooth speaker")

    assert result["accepted"] is True
    assert acceptance_path.exists()
    assert result["scrapy"]["ready"] is True
    assert result["playwright"]["ready"] is True


@pytest.mark.asyncio
async def test_crawl_platform_scheduler_run_once_records_artifact(tmp_path: Path):
    fixture_root = PROJECT_ROOT / "artifacts" / "crawl_platform" / "targets"
    runtime_service = LocalCrawlRuntimeService(
        fixture_root=fixture_root,
        runtime_root=tmp_path / "runtime",
        acceptance_path=tmp_path / "acceptance.json",
    )
    service = CrawlPlatformService(
        artifact_path=tmp_path / "latest_run.json",
        scheduler_artifact_path=tmp_path / "scheduler_latest.json",
        runtime_service=runtime_service,
    )

    result = await service.run_scheduled_jobs_once(query="bluetooth speaker", mode="real", job_key="forum_hourly")

    assert result["accepted"] is True
    assert result["job_count"] == 1
    assert result["jobs"][0]["job_key"] == "forum_hourly"
    assert (tmp_path / "scheduler_latest.json").exists()
