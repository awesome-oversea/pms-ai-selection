from __future__ import annotations

import asyncio
from types import SimpleNamespace

import src.infrastructure.kafka as kafka_runtime


def test_send_message_recreates_producer_when_event_loop_changes(monkeypatch):
    created: list[FakeProducer] = []

    class FakeProducer:
        def __init__(self, name: str):
            self.name = name
            self.started_on = None
            self.sent: list[tuple[str, dict, bytes | None]] = []

        async def start(self):
            self.started_on = asyncio.get_running_loop()

        async def send_and_wait(self, topic: str, value: dict, key: bytes | None = None):
            assert self.started_on is asyncio.get_running_loop()
            self.sent.append((topic, value, key))
            return SimpleNamespace(partition=0, offset=len(self.sent) - 1)

        async def stop(self):
            return None

    def _create_producer():
        producer = FakeProducer(name=f"producer-{len(created) + 1}")
        created.append(producer)
        return producer

    monkeypatch.setattr(kafka_runtime, "_KAFKA_AVAILABLE", True)
    monkeypatch.setattr(kafka_runtime, "_broker_reachable", lambda timeout_seconds=0.3: True)
    monkeypatch.setattr(kafka_runtime, "_create_producer", _create_producer)
    monkeypatch.setattr(kafka_runtime, "_producer", None)
    monkeypatch.setattr(kafka_runtime, "_producer_started", False)
    monkeypatch.setattr(kafka_runtime, "_producer_loop", None)
    monkeypatch.setattr(kafka_runtime, "_memory_messages", [])

    asyncio.run(kafka_runtime.send_message("pms-data-collection", {"id": 1}))
    asyncio.run(kafka_runtime.send_message("pms-data-collection", {"id": 2}))

    assert len(created) == 2
    assert created[0].sent[0][1]["id"] == 1
    assert created[1].sent[0][1]["id"] == 2
    assert kafka_runtime._producer is created[1]
    assert kafka_runtime.get_memory_messages("pms-data-collection") == []


def test_ensure_topics_includes_raw_collection_topics(monkeypatch):
    created_topics: list[SimpleNamespace] = []

    class FakeAdminClient:
        async def start(self):
            return None

        async def list_topics(self):
            return {
                "pms-data-collection": object(),
                "pms-agent-event": object(),
            }

        async def create_topics(self, new_topics):
            created_topics.extend(new_topics)

        async def close(self):
            return None

    def _fake_admin_client(*, bootstrap_servers):
        return FakeAdminClient()

    def _fake_new_topic(name, num_partitions, replication_factor, topic_configs):
        return SimpleNamespace(
            name=name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            topic_configs=topic_configs,
        )

    monkeypatch.setattr(kafka_runtime, "AIOKafkaAdminClient", _fake_admin_client)
    monkeypatch.setattr(kafka_runtime, "NewTopic", _fake_new_topic)

    asyncio.run(kafka_runtime.ensure_topics())

    created_names = {topic.name for topic in created_topics}
    assert {"raw_amazon", "raw_tiktok", "raw_trends", "raw_1688", "raw_news"}.issubset(created_names)


def test_topic_names_from_metadata_accepts_mapping_and_sequence():
    assert kafka_runtime._topic_names_from_metadata({"raw_amazon": object()}) == {"raw_amazon"}
    assert kafka_runtime._topic_names_from_metadata(["raw_tiktok", "raw_trends"]) == {
        "raw_tiktok",
        "raw_trends",
    }
