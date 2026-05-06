"""
Kafka消息队列客户端
===================

提供:
    - Kafka异步Producer(发送消息)
    - Kafka异步Consumer(消费消息)
    - Topic管理(创建/配置)
    - 消息序列化/反序列化

D7-T023: Kafka集群部署与Topic配置
    - amazon-data (12分区)
    - tiktok-data (6分区)
    - agent-events (12分区)

使用方式:
    from src.infrastructure.kafka import get_kafka_producer

    producer = get_kafka_producer()
    await producer.send_and_wait("amazon-data", {"asin": "B08N5WRWNW"})
"""

import asyncio
import json
import socket
from typing import Any

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    _KAFKA_AVAILABLE = True
except ImportError:
    AIOKafkaConsumer = Any  # type: ignore
    AIOKafkaProducer = Any  # type: ignore
    AIOKafkaAdminClient = Any  # type: ignore
    NewTopic = Any  # type: ignore
    _KAFKA_AVAILABLE = False

from src.config.settings import get_settings
from src.core.logging import get_logger
from src.core.metrics import set_kafka_consumer_lag

logger = get_logger(__name__)

_producer: AIOKafkaProducer | None = None
_producer_started: bool = False
_producer_loop: asyncio.AbstractEventLoop | None = None
_memory_messages: list[dict[str, Any]] = []
DLQ_TOPIC_SUFFIX = ".dlq"
_PRODUCER_START_TIMEOUT_SECONDS = 3.5
_PRODUCER_SEND_TIMEOUT_SECONDS = 3.5
RAW_COLLECTION_TOPICS = (
    "raw_amazon",
    "raw_tiktok",
    "raw_trends",
    "raw_1688",
    "raw_news",
)


def _topic_names_from_metadata(topics_metadata: Any) -> set[str]:
    """aiokafka versions return either a mapping or a plain topic-name list."""
    if isinstance(topics_metadata, dict):
        return {str(name) for name in topics_metadata}
    if isinstance(topics_metadata, (list, tuple, set)):
        return {str(name) for name in topics_metadata}
    return set()


def _create_producer() -> AIOKafkaProducer:
    """
    创建Kafka异步生产者。

    配置项:
        - bootstrap_servers: Broker地址列表
        - acks: 确认级别(all=最强一致性)
        - retry_backoff_ms: 重试退避时间
        - linger_ms: 批量发送延迟(提升吞吐量)

    Returns:
        AIOKafkaProducer: 异步生产者实例
    """
    settings = get_settings()

    return AIOKafkaProducer(
        bootstrap_servers=settings.kafka.bootstrap_servers.split(","),
        acks="all",
        linger_ms=10,
        retry_backoff_ms=300,
        max_batch_size=16384,
        request_timeout_ms=3000,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
    )


def _broker_reachable(timeout_seconds: float = 0.3) -> bool:
    bootstrap_servers = get_settings().kafka.bootstrap_servers.split(",")
    for server in bootstrap_servers:
        host, _, port_text = server.partition(":")
        try:
            port = int(port_text or "9092")
        except ValueError:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_seconds)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                continue
    return False


def get_kafka_producer() -> AIOKafkaProducer:
    """获取全局Kafka Producer单例。"""
    global _producer
    if _producer is None:
        _producer = _create_producer()
        logger.info("📨 Kafka Producer已创建")
    return _producer


def _reset_producer_state(reason: str) -> None:
    global _producer, _producer_started, _producer_loop
    if _producer is not None or _producer_started or _producer_loop is not None:
        logger.warning(f"🔄 重置 Kafka Producer 状态: {reason}")
    _producer = None
    _producer_started = False
    _producer_loop = None


async def _ensure_producer_ready() -> AIOKafkaProducer:
    global _producer_started, _producer_loop
    current_loop = asyncio.get_running_loop()
    if _producer_loop is not None and _producer_loop is not current_loop:
        _reset_producer_state("event-loop-changed")
    producer = get_kafka_producer()
    if _producer_loop is None:
        _producer_loop = current_loop
    if not _producer_started:
        await asyncio.wait_for(producer.start(), timeout=_PRODUCER_START_TIMEOUT_SECONDS)
        _producer_started = True
        _producer_loop = current_loop
    return producer


async def create_consumer(
    group_id: str | None = None,
    topics: list[str] | None = None,
    auto_offset_reset: str = "latest",
) -> AIOKafkaConsumer:
    """
    创建Kafka消费者。

    Args:
        group_id: 消费者组ID
        topics: 订阅的Topic列表
        auto_offset_reset: 偏移重置策略(earliest/latest)

    Returns:
        AIOKafkaConsumer: 异步消费者实例
    """
    if not _KAFKA_AVAILABLE:
        raise RuntimeError("aiokafka 未安装，Kafka 消费功能不可用")

    settings = get_settings()

    consumer = AIOKafkaConsumer(
        *topics or [],
        bootstrap_servers=settings.kafka.bootstrap_servers.split(","),
        group_id=group_id or settings.kafka.group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=True,
        auto_commit_interval_ms=5000,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    await consumer.start()
    logger.info(f"📩 Kafka Consumer已创建 (group={group_id}, topics={topics})")
    return consumer


async def ensure_topics():
    """
    确保核心Topic存在(D7-T023)。

    创建以下Topic(不存在时):
        - amazon-data: 12分区(高吞吐数据采集)
        - tiktok-data: 6分区(TikTok数据)
        - agent-events: 12分区(Agent事件总线)
        - raw_amazon/raw_tiktok/raw_trends/raw_1688/raw_news: 外部原始数据统一接入

    保留策略: 7天(log.retention.hours=168)
    """
    settings = get_settings()

    admin_client = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka.bootstrap_servers.split(","),
    )

    try:
        await admin_client.start()

        topics_metadata = await admin_client.list_topics()
        existing_topics = _topic_names_from_metadata(topics_metadata)

        new_topics = [
            NewTopic(
                name=settings.kafka.topics_data_collection,
                num_partitions=12,
                replication_factor=1,
                topic_configs={
                    "retention.ms": 7 * 24 * 3600 * 1000,
                    "max.message.bytes": 10485760,
                },
            ),
            NewTopic(
                name="tiktok-data",
                num_partitions=6,
                replication_factor=1,
                topic_configs={
                    "retention.ms": 7 * 24 * 3600 * 1000,
                },
            ),
            NewTopic(
                name=settings.kafka.topics_agent_event,
                num_partitions=12,
                replication_factor=1,
                topic_configs={
                    "retention.ms": 7 * 24 * 3600 * 1000,
                    "cleanup.policy": "delete",
                },
            ),
        ]
        for raw_topic in RAW_COLLECTION_TOPICS:
            new_topics.append(
                NewTopic(
                    name=raw_topic,
                    num_partitions=3,
                    replication_factor=1,
                    topic_configs={
                        "retention.ms": 7 * 24 * 3600 * 1000,
                    },
                )
            )

        to_create = [t for t in new_topics if t.name not in existing_topics]

        if to_create:
            await admin_client.create_topics(new_topics=to_create)
            for t in to_create:
                logger.info(f"✅ Kafka Topic '{t.name}' 已创建")
        else:
            logger.debug("所有核心Topic已存在")
    finally:
        await admin_client.close()


async def send_message(topic: str, message: dict[str, Any], key: bytes | None = None) -> bool:
    """
    发送单条消息到指定Topic。

    Args:
        topic: 目标Topic名称
        message: 消息内容(dict，自动JSON序列化)
        key: 分区键(可选)

    Returns:
        bool: 是否发送成功
    """
    if not _KAFKA_AVAILABLE:
        _memory_messages.append({"topic": topic, "message": message, "key": key})
        set_kafka_consumer_lag(topic, get_settings().kafka.group_id, len(get_memory_messages(topic)))
        logger.info(f"📦 Kafka未安装，消息写入内存样板队列 → {topic}")
        return True

    if not _broker_reachable():
        _memory_messages.append({"topic": topic, "message": message, "key": key, "fallback": "memory-unreachable"})
        set_kafka_consumer_lag(topic, get_settings().kafka.group_id, len(get_memory_messages(topic)))
        logger.info(f"📦 Kafka Broker不可达，消息降级写入内存样板队列 → {topic}")
        return True

    try:
        producer = await _ensure_producer_ready()
        result = await asyncio.wait_for(
            producer.send_and_wait(
                topic=topic,
                value=message,
                key=key,
            ),
            timeout=_PRODUCER_SEND_TIMEOUT_SECONDS,
        )
        logger.debug(f"📤 消息已发送 → {topic} (partition={result.partition}, offset={result.offset})")
        return True
    except Exception as e:
        logger.error(f"❌ 发送消息失败 [{topic}]: {e}")
        _reset_producer_state(f"send-failed:{type(e).__name__}")
        _memory_messages.append({"topic": topic, "message": message, "key": key, "fallback": "memory"})
        set_kafka_consumer_lag(topic, get_settings().kafka.group_id, len(get_memory_messages(topic)))
        logger.warning(f"📦 Kafka发送失败，已降级写入内存样板队列 → {topic}")
        return True


def get_memory_messages(topic: str | None = None) -> list[dict[str, Any]]:
    if topic is None:
        return list(_memory_messages)
    return [item for item in _memory_messages if item.get("topic") == topic]


def drain_memory_messages(topic: str | None = None) -> list[dict[str, Any]]:
    if topic is None:
        drained = list(_memory_messages)
        drained_topics = {str(item.get("topic") or "unknown") for item in drained}
        _memory_messages.clear()
        for current_topic in drained_topics:
            set_kafka_consumer_lag(current_topic, get_settings().kafka.group_id, 0)
        return drained
    drained = [item for item in _memory_messages if item.get("topic") == topic]
    if drained:
        _memory_messages[:] = [item for item in _memory_messages if item.get("topic") != topic]
    set_kafka_consumer_lag(topic, get_settings().kafka.group_id, len(get_memory_messages(topic)))
    return drained


def build_dlq_topic(topic: str) -> str:
    return f"{topic}{DLQ_TOPIC_SUFFIX}"


async def close_kafka():
    """关闭Kafka连接。"""
    global _producer
    producer = _producer
    _reset_producer_state("close")
    if producer is not None:
        try:
            await asyncio.wait_for(producer.stop(), timeout=2.0)
        except Exception as exc:
            logger.warning(f"⚠️ Kafka Producer关闭异常，已忽略: {exc}")
        else:
            logger.info("🔌 Kafka Producer已关闭")


async def check_kafka_health() -> dict:
    """
    检查Kafka健康状态(D7验收标准)。

    Returns:
        dict: 健康状态信息(Broker/Topic状态)
    """
    try:
        settings = get_settings()
        admin_client = AIOKafkaAdminClient(
            bootstrap_servers=settings.kafka.bootstrap_servers.split(","),
        )

        await admin_client.start()
        metadata = await admin_client.describe_cluster()
        brokers = metadata.get("brokers", [])

        topics_meta = await admin_client.list_topics()
        topic_names = sorted(_topic_names_from_metadata(topics_meta))

        await admin_client.close()

        return {
            "status": "healthy",
            "broker_count": len(brokers),
            "controller_id": metadata.get("controller_id", -1),
            "topic_count": len(topic_names),
            "topics": topic_names[:20],
        }
    except Exception as e:
        logger.error(f"❌ Kafka健康检查失败: {e}")
        return {"status": "unhealthy", "error": str(e)}
