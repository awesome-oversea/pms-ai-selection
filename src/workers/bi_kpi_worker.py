from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from src.config.settings import get_settings
from src.core.logging import get_logger
from src.infrastructure.database import get_async_session_factory
from src.services.erp_integration_service import ErpIntegrationService

logger = get_logger(__name__)


async def run_worker(*, interval_seconds: float | None = None, bootstrap_delay_seconds: float | None = None) -> None:
    worker = BIDailyKpiWorker(interval_seconds=interval_seconds, bootstrap_delay_seconds=bootstrap_delay_seconds)
    await worker.run_forever()


class BIDailyKpiWorker:
    def __init__(self, *, interval_seconds: float | None = None, bootstrap_delay_seconds: float | None = None, config_name: str = "default"):
        settings = get_settings().selection_execution
        self.interval_seconds = interval_seconds or settings.bi_daily_kpi_interval_seconds
        self.bootstrap_delay_seconds = bootstrap_delay_seconds if bootstrap_delay_seconds is not None else settings.bi_daily_kpi_bootstrap_delay_seconds
        self.config_name = config_name
        self._running = False

    async def run_once(self, *, day: str | None = None) -> dict[str, object]:
        factory = get_async_session_factory()
        async with factory() as session:
            service = ErpIntegrationService(session)
            result = await service.sync_daily_bi_kpis(name=self.config_name, day=day)
            await session.commit()
            return result

    async def run_forever(self) -> None:
        self._running = True
        logger.info("BI daily KPI worker started")
        if self.bootstrap_delay_seconds > 0:
            await asyncio.sleep(self.bootstrap_delay_seconds)
        while self._running:
            try:
                today = datetime.now(UTC).date().isoformat()
                await self.run_once(day=today)
            except Exception as e:
                logger.warning(f"BI daily KPI worker run failed: {e}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
