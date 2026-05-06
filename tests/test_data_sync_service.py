from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

from types import SimpleNamespace

import pytest
from src.services.data_sync_service import DataSyncService


class _FakeRepo:
    def __init__(self):
        self.events = []

    async def get_event_by_key(self, event_key):
        return next((e for e in self.events if e.event_key == event_key), None)

    async def create_event(self, **kwargs):
        event = SimpleNamespace(
            id=f"evt-{len(self.events)+1}",
            tenant_id=kwargs["tenant_id"],
            entity_type=kwargs["entity_type"],
            event_type=kwargs["event_type"],
            aggregate_id=kwargs["aggregate_id"],
            topic=kwargs["topic"],
            event_key=kwargs["event_key"],
            payload=kwargs["payload"],
            status="pending",
            source=kwargs.get("source", "outbox"),
            retry_count=0,
            last_error=None,
            published_at=None,
            last_attempt_at=None,
        )
        self.events.append(event)
        return event

    async def list_pending(self, limit=20):
        return [e for e in self.events if e.status in {"pending", "failed"}][:limit]

    async def mark_sent(self, event):
        event.status = "sent"
        return event

    async def mark_failed(self, event, error, dead_letter=False):
        event.retry_count += 1
        event.last_error = error
        event.status = "dead_letter" if dead_letter else "failed"
        return event

    async def list_dead_letter(self, limit=20):
        return [e for e in self.events if e.status == "dead_letter"][:limit]

    async def get_event(self, event_id):
        return next((e for e in self.events if str(e.id) == str(event_id)), None)

    async def reset_for_replay(self, event):
        event.status = "pending"
        event.last_error = None
        return event


@pytest.mark.asyncio
async def test_data_sync_service_idempotent_publish(monkeypatch):
    async def _fake_send(topic, message, key=None):
        return True

    monkeypatch.setattr("src.services.data_sync_service.send_message", _fake_send)

    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = _FakeRepo()
    created1 = await service.publish_product_event(aggregate_id="prod-001", payload={"name": "样板商品"})
    created2 = await service.publish_product_event(aggregate_id="prod-001", payload={"name": "样板商品"})
    document = await service.publish_domain_event(aggregate_id="doc-001", payload={"filename": "demo.txt"}, event_type="document.indexed")
    inventory = await service.publish_domain_event(aggregate_id="inv-001", payload={"warehouse": "WH-A", "delta": 5}, event_type="inventory.updated")
    catalog = service.get_event_catalog()
    assert created1["event_id"] == created2["event_id"]
    assert created1["schema_version"] == "v1"
    assert document["entity_type"] == "document"
    assert inventory["entity_type"] == "inventory"
    assert len(catalog) >= 10
    assert set(catalog.keys()) >= {"product.updated", "document.indexed", "inventory.updated", "order.updated", "supplier.updated"}
    assert catalog["product.updated"]["schema_subject"] == "product.event"
    assert catalog["product.updated"]["schema_registry_key"] == "pms.product.v1"
    assert catalog["product.updated"]["status_flow"] == ["pending", "sent", "failed", "dead_letter"]


@pytest.mark.asyncio
async def test_data_sync_service_builds_cdc_connector_config():
    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    config = service.build_cdc_connector_config(system_name="oms")
    catalog = service.get_cdc_catalog()
    assert config["system_name"] == "oms"
    assert config["config"]["connector.class"] == "io.debezium.connector.postgresql.PostgresConnector"
    assert config["config"]["database.hostname"] == "pms-postgres"
    assert config["config"]["plugin.name"] == "pgoutput"
    assert config["config"]["publication.autocreate.mode"] == "filtered"
    assert "public.orders" in config["config"]["table.include.list"]
    assert config["database"]["host"] == "pms-postgres"
    assert catalog["crm"]["message_format"] == "debezium-envelope"


@pytest.mark.asyncio
async def test_data_sync_service_publishes_cdc_event_with_debezium_envelope(monkeypatch):
    captured = {}

    async def _fake_send(topic, message, key=None):
        captured["topic"] = topic
        captured["message"] = message
        return True

    monkeypatch.setattr("src.services.data_sync_service.send_message", _fake_send)

    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = _FakeRepo()
    created = await service.publish_cdc_event(
        system_name="crm",
        aggregate_id="review-001",
        before={"review_id": "review-001", "rating": 4.2},
        after={"review_id": "review-001", "rating": 4.8},
        op="u",
        ts_ms=1713081600000,
        source={"table": "public.reviews"},
    )
    result = await service.dispatch_pending_events(limit=10, max_retries=0)

    assert created["event_type"] == "review.updated"
    assert result["dispatched"] == 1
    assert captured["message"]["op"] == "u"
    assert captured["message"]["before"]["rating"] == 4.2
    assert captured["message"]["after"]["rating"] == 4.8
    assert captured["message"]["source"]["system"] == "crm"
    assert captured["message"]["ts_ms"] == 1713081600000


@pytest.mark.asyncio
async def test_data_sync_service_cdc_event_reaches_memory_queue(monkeypatch):
    from src.infrastructure.kafka import drain_memory_messages

    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = _FakeRepo()
    drain_memory_messages()

    await service.publish_cdc_event(
        system_name="oms",
        aggregate_id="order-002",
        before={"order_id": "order-002", "quantity": 1},
        after={"order_id": "order-002", "quantity": 3},
        op="u",
        ts_ms=1713081600001,
        source={"table": "public.orders"},
    )
    result = await service.dispatch_pending_events(limit=10, max_retries=0)
    queued = drain_memory_messages()

    assert result["dispatched"] == 1
    assert queued[0]["message"]["op"] == "u"
    assert queued[0]["message"]["before"]["quantity"] == 1
    assert queued[0]["message"]["after"]["quantity"] == 3
    assert queued[0]["message"]["source"]["table"] == "public.orders"


@pytest.mark.asyncio
async def test_data_sync_service_dead_letter_and_replay(monkeypatch):
    calls = {"count": 0}

    async def _fake_send(topic, message, key=None):
        calls["count"] += 1
        return calls["count"] >= 3

    monkeypatch.setattr("src.services.data_sync_service.send_message", _fake_send)

    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = _FakeRepo()
    created = await service.publish_product_event(aggregate_id="prod-002", payload={"name": "样板商品"})
    assert created["status"] == "pending"

    result1 = await service.dispatch_pending_events(limit=10, max_retries=0)
    assert result1["dead_lettered"] == 1
    assert result1["dlq_topic"].endswith(".dlq")

    dlq = await service.list_dead_letter(limit=10)
    assert dlq["total"] >= 1

    replayed = await service.replay_dead_letter(dlq["events"][0]["event_id"])
    assert replayed["event"]["status"] in {"sent", "failed", "dead_letter"}


@pytest.mark.asyncio
async def test_data_sync_service_build_platform_governance(monkeypatch):
    async def _fake_send(topic, message, key=None):
        return True

    async def _fake_kafka_health():
        return {"status": "healthy", "broker_count": 1, "topic_count": 2}

    monkeypatch.setattr("src.services.data_sync_service.send_message", _fake_send)
    monkeypatch.setattr("src.services.data_sync_service.check_kafka_health", _fake_kafka_health)

    service = DataSyncService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca"})
    service.repo = _FakeRepo()
    await service.publish_product_event(aggregate_id="prod-003", payload={"name": "治理商品"})
    governance = await service.build_platform_governance()
    assert governance["kafka_health"]["status"] == "healthy"
    assert governance["dlq_topic"].endswith(".dlq")
    assert governance["replay_supported"] is True
    assert governance["idempotency_enabled"] is True
    assert governance["catalog_size"] >= 10
