from __future__ import annotations

import argparse
import asyncio
import json

from src.services.crawl_platform_service import CrawlPlatformService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local crawl platform jobs")
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", default="mock", choices=("mock", "auto", "real"))
    parser.add_argument("--topic", default="pms-data-collection")
    parser.add_argument("--engine", default="all", choices=("all", "scrapy-compatible", "playwright-compatible"))
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    result = await CrawlPlatformService().run_local_crawl(query=args.query, mode=args.mode, topic=args.topic, engine=args.engine)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())
