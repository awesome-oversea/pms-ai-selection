from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.crawl_platform_service import CrawlPlatformService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled crawl jobs once or forever")
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", default="real", choices=("mock", "auto", "real"))
    parser.add_argument("--topic", default="pms-data-collection")
    parser.add_argument("--job-key", default=None)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=3600.0)
    return parser.parse_args()


async def _run_once(args: argparse.Namespace) -> dict:
    service = CrawlPlatformService()
    return await service.run_scheduled_jobs_once(query=args.query, mode=args.mode, topic=args.topic, job_key=args.job_key)


async def _run_forever(args: argparse.Namespace) -> None:
    while True:
        result = await _run_once(args)
        print(json.dumps(result, ensure_ascii=False))
        await asyncio.sleep(args.interval_seconds)


def main() -> None:
    args = _parse_args()
    if args.run_once:
        print(json.dumps(asyncio.run(_run_once(args)), ensure_ascii=False))
        return
    asyncio.run(_run_forever(args))


if __name__ == "__main__":
    main()
