from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from src.core.logging import get_logger
from src.infrastructure.database import get_async_session_factory
from src.services.model_finetune_service import ModelFinetuneService

logger = get_logger(__name__)


async def run_worker(*, interval_seconds: float = 604800.0, tenant_id: str = "00000000-0000-0000-0000-000000000001") -> None:
    worker = WeeklyModelFinetuneWorker(interval_seconds=interval_seconds, tenant_id=tenant_id)
    await worker.run_forever()


class WeeklyModelFinetuneWorker:
    def __init__(self, *, interval_seconds: float = 604800.0, tenant_id: str = "00000000-0000-0000-0000-000000000001"):
        self.interval_seconds = interval_seconds
        self.tenant_id = tenant_id
        self._running = False

    async def run_once(self, *, registry_key: str = "default", train_days: int = 7) -> dict:
        factory = get_async_session_factory()
        async with factory() as session:
            service = ModelFinetuneService(session, tenant_id=self.tenant_id)
            result = await service.run_weekly_finetune(registry_key=registry_key, train_days=train_days)
            await session.commit()
            return result

    async def run_forever(self) -> None:
        self._running = True
        logger.info("weekly model finetune worker started")
        while self._running:
            try:
                logger.info("trigger weekly model finetune at %s", datetime.now(UTC).isoformat())
                await self.run_once()
            except Exception as exc:
                logger.warning(f"weekly model finetune worker failed: {exc}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
