from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.workers.data_sync_consumer import DataSyncConsumer


async def _main() -> dict:
    consumer = DataSyncConsumer(topic="pms-agent-event", consumer_group="pms-multi-entity-consumer-group")
    result = await consumer.consume_batch([])
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_main()), ensure_ascii=False, indent=2))
