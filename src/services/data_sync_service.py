from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from src.config.settings import get_settings
from src.core.logging import get_logger
from src.infrastructure.kafka import build_dlq_topic, check_kafka_health, send_message
from src.repositories.data_sync_repository import DataSyncRepository

logger = get_logger(__name__)

_EVENT_STATUS_FLOW = ["pending", "sent", "failed", "dead_letter"]


def _event_meta(entity_type: str, consumer_group: str) -> dict[str, Any]:
    return {
        "topic": "pms-agent-event",
        "entity_type": entity_type,
        "schema_version": "v1",
        "compatibility": "backward-compatible additive fields only",
        "idempotency_key": f"{entity_type}:{{aggregate_id}}:{{event_type}}",
        "consumer_group": consumer_group,
        "source": "outbox",
        "status_flow": list(_EVENT_STATUS_FLOW),
        "replay_supported": True,
        "schema_subject": f"{entity_type}.event",
        "schema_registry_key": f"pms.{entity_type}.v1",
    }


def _local_cdc_source_config() -> dict[str, str]:
    return {
        "database.hostname": os.getenv("CDC_LOCAL_POSTGRES_HOST", "pms-postgres"),
        "database.port": os.getenv("CDC_LOCAL_POSTGRES_PORT", "5432"),
        "database.user": os.getenv("CDC_LOCAL_POSTGRES_USER", "pms"),
        "database.password": os.getenv("CDC_LOCAL_POSTGRES_PASSWORD", "pms_dev_2024"),
        "database.dbname": os.getenv("CDC_LOCAL_POSTGRES_DB", "pms_db"),
    }


def _normalize_connector_key(connector_name: str) -> str:
    return connector_name.replace("-", "_")


class DataSyncService:
    EVENT_CATALOG: dict[str, Any] = {
        "product.updated": _event_meta("product", "pms-product-consumer-group"),
        "document.indexed": _event_meta("document", "pms-document-consumer-group"),
        "inventory.updated": _event_meta("inventory", "pms-inventory-consumer-group"),
        "order.updated": _event_meta("order", "pms-order-consumer-group"),
        "shipment.updated": _event_meta("shipment", "pms-shipment-consumer-group"),
        "customer.updated": _event_meta("customer", "pms-customer-consumer-group"),
        "payment.updated": _event_meta("payment", "pms-payment-consumer-group"),
        "refund.updated": _event_meta("refund", "pms-refund-consumer-group"),
        "review.updated": _event_meta("review", "pms-review-consumer-group"),
        "campaign.updated": _event_meta("campaign", "pms-campaign-consumer-group"),
        "supplier.updated": _event_meta("supplier", "pms-supplier-consumer-group"),
    }
    CDC_CATALOG: dict[str, dict[str, Any]] = {
        "oms": {
            "connector_class": "io.debezium.connector.postgresql.PostgresConnector",
            "database_server_name": "oms-cdc",
            "topic_prefix": "cdc.oms",
            "tables": ["public.orders", "public.order_items", "public.refunds"],
            "event_type": "order.updated",
            "entity_type": "order",
            "primary_key": "order_id",
        },
        "crm": {
            "connector_class": "io.debezium.connector.postgresql.PostgresConnector",
            "database_server_name": "crm-cdc",
            "topic_prefix": "cdc.crm",
            "tables": ["public.reviews", "public.complaints", "public.customer_feedbacks"],
            "event_type": "review.updated",
            "entity_type": "review",
            "primary_key": "review_id",
        },
    }

    def __init__(self, session, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.repo = DataSyncRepository(session, tenant_id=self.tenant_id)
        self.kafka_settings = get_settings().kafka

    def get_event_catalog(self) -> dict[str, Any]:
        catalog = dict(self.EVENT_CATALOG)
        for event_type, item in catalog.items():
            if item.get("topic") == "pms-agent-event":
                item = dict(item)
                item["topic"] = self.kafka_settings.topics_agent_event
                catalog[event_type] = item
        return catalog

    def get_cdc_catalog(self) -> dict[str, Any]:
        catalog: dict[str, Any] = {}
        for system_name, item in self.CDC_CATALOG.items():
            catalog[system_name] = {
                **item,
                "topic": self.kafka_settings.topics_agent_event,
                "message_format": "debezium-envelope",
                "required_fields": ["before", "after", "op", "ts_ms", "source"],
            }
        return catalog

    def build_cdc_connector_config(self, *, system_name: str, connector_name: str | None = None) -> dict[str, Any]:
        catalog = self.get_cdc_catalog()
        item = catalog.get(system_name)
        if item is None:
            raise ValueError(f"不支持的CDC系统: {system_name}")
        resolved_name = connector_name or f"{system_name}-debezium-connector"
        connector_key = _normalize_connector_key(resolved_name)
        source_config = _local_cdc_source_config()
        return {
            "name": resolved_name,
            "config": {
                "connector.class": item["connector_class"],
                **source_config,
                "tasks.max": "1",
                "topic.prefix": item["topic_prefix"],
                "database.server.name": item["database_server_name"],
                "plugin.name": "pgoutput",
                "slot.name": f"{connector_key}_slot",
                "publication.name": f"{connector_key}_publication",
                "publication.autocreate.mode": "filtered",
                "snapshot.mode": "initial",
                "table.include.list": ",".join(item["tables"]),
                "tombstones.on.delete": "false",
                "include.schema.changes": "false",
                "value.converter": "org.apache.kafka.connect.json.JsonConverter",
                "value.converter.schemas.enable": "false",
                "key.converter": "org.apache.kafka.connect.json.JsonConverter",
                "key.converter.schemas.enable": "false",
                "transforms": "route",
                "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
                "transforms.route.regex": ".*",
                "transforms.route.replacement": self.kafka_settings.topics_agent_event,
            },
            "system_name": system_name,
            "event_type": item["event_type"],
            "entity_type": item["entity_type"],
            "tables": item["tables"],
            "topic": self.kafka_settings.topics_agent_event,
            "topic_prefix": item["topic_prefix"],
            "database": {
                "host": source_config["database.hostname"],
                "port": source_config["database.port"],
                "dbname": source_config["database.dbname"],
                "user": source_config["database.user"],
            },
        }

    async def publish_cdc_event(
        self,
        *,
        system_name: str,
        aggregate_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        op: str,
        ts_ms: int | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        catalog = self.get_cdc_catalog()
        item = catalog.get(system_name)
        if item is None:
            raise ValueError(f"不支持的CDC系统: {system_name}")
        normalized_ts_ms = int(ts_ms or int(datetime.now(UTC).timestamp() * 1000))
        payload = {
            "before": before,
            "after": after,
            "op": op,
            "ts_ms": normalized_ts_ms,
            "source": {
                "system": system_name,
                "connector": item["connector_class"],
                "topic_prefix": item["topic_prefix"],
                **(source or {}),
            },
            "schema_version": "debezium.v1",
            "message_format": "debezium-envelope",
        }
        return await self.publish_domain_event(aggregate_id=aggregate_id, payload=payload, event_type=item["event_type"])

    async def publish_domain_event(self, *, aggregate_id: str, payload: dict[str, Any], event_type: str) -> dict[str, Any]:
        catalog = self.get_event_catalog()
        event_meta = catalog.get(event_type)
        if event_meta is None:
            raise ValueError(f"不支持的事件类型: {event_type}")
        entity_type = event_meta["entity_type"]
        event_key = f"{entity_type}:{aggregate_id}:{event_type}"
        existing = await self.repo.get_event_by_key(event_key)
        if existing is not None:
            return self._serialize_event(existing)
        event_payload = {
            "schema_version": event_meta["schema_version"],
            "compatibility": event_meta["compatibility"],
            "consumer_group": event_meta.get("consumer_group"),
            "status_flow": event_meta.get("status_flow", ["pending", "sent", "failed", "dead_letter"]),
            "replay_supported": event_meta.get("replay_supported", True),
            **payload,
        }
        event = await self.repo.create_event(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            event_type=event_type,
            aggregate_id=aggregate_id,
            topic=event_meta["topic"],
            event_key=event_key,
            payload=event_payload,
            source=event_meta["source"],
        )
        return self._serialize_event(event)

    async def publish_product_event(self, *, aggregate_id: str, payload: dict[str, Any], event_type: str = "product.updated") -> dict[str, Any]:
        return await self.publish_domain_event(aggregate_id=aggregate_id, payload=payload, event_type=event_type)

    async def dispatch_pending_events(self, limit: int = 20, max_retries: int = 2) -> dict[str, Any]:
        events = await self.repo.list_pending(limit=limit)
        dispatched = 0
        dead_lettered = 0
        failed = 0
        for event in events:
            ok, error = await self._dispatch_event(event)
            if ok:
                await self.repo.mark_sent(event)
                dispatched += 1
            else:
                should_dead_letter = int(event.retry_count or 0) + 1 > max_retries
                await self.repo.mark_failed(event, error or "unknown", dead_letter=should_dead_letter)
                if should_dead_letter:
                    dead_lettered += 1
                else:
                    failed += 1
        return {
            "total": len(events),
            "dispatched": dispatched,
            "failed": failed,
            "dead_lettered": dead_lettered,
            "dlq_topic": build_dlq_topic(self.kafka_settings.topics_agent_event),
            "topics": sorted({event.topic for event in events}),
            "entity_types": sorted({event.entity_type for event in events}),
            "consumer_groups": sorted({(event.payload or {}).get("consumer_group") for event in events if (event.payload or {}).get("consumer_group")}),
        }

    async def list_dead_letter(self, limit: int = 20) -> dict[str, Any]:
        events = await self.repo.list_dead_letter(limit=limit)
        return {"total": len(events), "events": [self._serialize_event(event) for event in events]}

    async def replay_dead_letter(self, event_id: str) -> dict[str, Any]:
        event = await self.repo.get_event(event_id)
        if event is None:
            raise ValueError(f"事件不存在: {event_id}")
        await self.repo.reset_for_replay(event)
        result = await self.dispatch_pending_events(limit=1)
        refreshed = await self.repo.get_event(event_id)
        return {"result": result, "event": self._serialize_event(refreshed)}

    async def build_platform_governance(self) -> dict[str, Any]:
        kafka_health = await check_kafka_health()
        dead_letter = await self.list_dead_letter(limit=20)
        catalog = self.get_event_catalog()
        topics = sorted({item.get("topic") for item in catalog.values()})
        consumer_groups = sorted({item.get("consumer_group") for item in catalog.values() if item.get("consumer_group")})
        cdc_catalog = self.get_cdc_catalog()
        debezium_connectors = [self.build_cdc_connector_config(system_name=system_name) for system_name in sorted(cdc_catalog)]
        return {
            "kafka_health": kafka_health,
            "topics": topics,
            "dlq_topic": build_dlq_topic(self.kafka_settings.topics_agent_event),
            "dead_letter_total": dead_letter.get("total", 0),
            "replay_supported": True,
            "idempotency_enabled": True,
            "consumer_groups": consumer_groups,
            "catalog_size": len(catalog),
            "cdc_catalog_size": len(cdc_catalog),
            "debezium_connectors": debezium_connectors,
            "kafka_connect": {
                "rest_url": "http://localhost:8083",
                "compose_service": "kafka-connect",
                "plugin": "debezium-connector-postgres",
                "ready": True,
            },
            "status_flow": ["pending", "sent", "failed", "dead_letter"],
        }

    async def _dispatch_event(self, event: Any) -> tuple[bool, str | None]:
        try:
            payload = event.payload or {}
            message = {
                "event_id": str(event.id),
                "tenant_id": str(event.tenant_id),
                "entity_type": event.entity_type,
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
                "schema_version": payload.get("schema_version", "v1"),
                "payload": payload,
            }
            for key in ["before", "after", "op", "ts_ms", "source", "message_format"]:
                if key in payload:
                    message[key] = payload.get(key)
            ok = await send_message(event.topic, message, key=event.event_key.encode("utf-8"))
            if not ok:
                return False, "kafka_send_failed"
            return True, None
        except Exception as e:
            logger.warning(f"数据同步事件发送失败: {e}")
            return False, str(e)

    @staticmethod
    def _serialize_event(event: Any) -> dict[str, Any]:
        payload = event.payload or {}
        return {
            "event_id": str(event.id),
            "tenant_id": str(event.tenant_id),
            "entity_type": event.entity_type,
            "event_type": event.event_type,
            "aggregate_id": event.aggregate_id,
            "topic": event.topic,
            "event_key": event.event_key,
            "status": event.status,
            "source": event.source,
            "retry_count": event.retry_count,
            "last_error": event.last_error,
            "schema_version": payload.get("schema_version", "v1"),
            "payload": payload,
            "published_at": event.published_at.isoformat() if event.published_at else None,
            "last_attempt_at": event.last_attempt_at.isoformat() if event.last_attempt_at else None,
        }
