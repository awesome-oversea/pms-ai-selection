from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.core.logging import get_logger
from src.infrastructure.kafka import _KAFKA_AVAILABLE, create_consumer, send_message
from src.services.erp_feedback_consumer import (
    ERP_FEEDBACK_TOPICS,
    handle_erp_domain_event,
    handle_erp_feedback_event,
)

logger = get_logger(__name__)

ERP_FEEDBACK_CONSUMER_GROUP = "pms-erp-feedback-consumer"
ERP_DOMAIN_EVENT_TOPICS = [
    "erp.domain.inventory_changed",
    "erp.domain.order_changed",
    "erp.domain.price_changed",
    "erp.domain.campaign_changed",
    "erp.domain.product_changed",
]
CONSUME_BATCH_SIZE = 50
CONSUME_POLL_TIMEOUT_MS = 1000
DLQ_TOPIC = "pms.erp_feedback.dlq"


class ErpFeedbackWorker:
    """
    ERP反馈消费者Worker。

    职责:
    - 持续订阅ERP反馈Topic(erp.suggestion.approved/rejected/executed等)
    - 持续订阅ERP域事件Topic(erp.domain.inventory_changed等)
    - 批量消费消息，调用handle_erp_feedback_event/handle_erp_domain_event处理
    - 处理失败的消息发送到DLQ(Dead Letter Queue)
    - 提供优雅停止机制
    """

    def __init__(
        self,
        *,
        feedback_topics: list[str] | None = None,
        domain_event_topics: list[str] | None = None,
        consumer_group: str = ERP_FEEDBACK_CONSUMER_GROUP,
        batch_size: int = CONSUME_BATCH_SIZE,
        poll_timeout_ms: int = CONSUME_POLL_TIMEOUT_MS,
    ) -> None:
        self.feedback_topics = feedback_topics or ERP_FEEDBACK_TOPICS
        self.domain_event_topics = domain_event_topics or ERP_DOMAIN_EVENT_TOPICS
        self.consumer_group = consumer_group
        self.batch_size = batch_size
        self.poll_timeout_ms = poll_timeout_ms
        self._running = False
        self._consumer = None
        self._stats: dict[str, Any] = {
            "consumed": 0,
            "processed": 0,
            "failed": 0,
            "dlq_sent": 0,
            "started_at": None,
            "last_consumed_at": None,
        }

    async def start(self) -> None:
        if not _KAFKA_AVAILABLE:
            logger.warning("aiokafka 未安装，ERP反馈消费者Worker以内存模式运行")
            self._running = True
            self._stats["started_at"] = datetime.now(UTC).isoformat()
            return

        all_topics = self.feedback_topics + self.domain_event_topics
        try:
            self._consumer = await create_consumer(
                group_id=self.consumer_group,
                topics=all_topics,
                auto_offset_reset="latest",
            )
            self._running = True
            self._stats["started_at"] = datetime.now(UTC).isoformat()
            logger.info(
                "ERP反馈消费者Worker已启动: topics=%s group=%s",
                all_topics,
                self.consumer_group,
            )
        except Exception:
            logger.exception("ERP反馈消费者Worker启动失败")
            raise

    async def run_forever(self) -> None:
        await self.start()
        while self._running:
            try:
                await self._consume_batch()
            except asyncio.CancelledError:
                logger.info("ERP反馈消费者Worker被取消")
                break
            except Exception:
                logger.exception("ERP反馈消费者Worker消费异常，5秒后重试")
                await asyncio.sleep(5)

    async def _consume_batch(self) -> None:
        if self._consumer is None:
            await asyncio.sleep(1)
            return

        batch: list[dict[str, Any]] = []
        try:
            async for message in self._consumer:
                if not self._running:
                    break
                value = message.value
                if isinstance(value, dict):
                    batch.append(value)
                if len(batch) >= self.batch_size:
                    break
        except Exception:
            logger.exception("Kafka消费异常")
            return

        if not batch:
            return

        self._stats["consumed"] += len(batch)
        self._stats["last_consumed_at"] = datetime.now(UTC).isoformat()

        for event in batch:
            await self._process_event(event)

    async def _process_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event_type", "")
        try:
            if event_type.startswith("erp.suggestion.") or event_type.startswith("erp.feedback."):
                result = await handle_erp_feedback_event(event)
            elif event_type.startswith("erp.domain."):
                result = await handle_erp_domain_event(event)
            else:
                result = await handle_erp_feedback_event(event)

            status = result.get("status", "unknown")
            if status in {"processed", "skipped", "not_found"}:
                self._stats["processed"] += 1
            else:
                self._stats["failed"] += 1
                await self._send_to_dlq(event, result)

        except Exception:
            self._stats["failed"] += 1
            logger.exception("处理ERP反馈事件异常: event_type=%s", event_type)
            await self._send_to_dlq(event, {"error": "processing_exception", "event_type": event_type})

    async def _send_to_dlq(self, original_event: dict[str, Any], error_info: dict[str, Any]) -> None:
        try:
            await send_message(
                topic=DLQ_TOPIC,
                message={
                    "original_event": original_event,
                    "error": error_info,
                    "dlq_timestamp": datetime.now(UTC).isoformat(),
                    "source": "pms-erp-feedback-worker",
                },
            )
            self._stats["dlq_sent"] += 1
        except Exception:
            logger.exception("发送DLQ消息失败")

    async def stop(self) -> None:
        self._running = False
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:
                logger.exception("停止Kafka消费者异常")
            self._consumer = None
        logger.info("ERP反馈消费者Worker已停止: stats=%s", self._stats)

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)


async def run_worker(*, interval_seconds: float | None = None) -> None:
    worker = ErpFeedbackWorker()
    try:
        await worker.run_forever()
    except asyncio.CancelledError:
        await worker.stop()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
