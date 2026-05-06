from __future__ import annotations

from typing import Any

from src.infrastructure.feature_engine import FeatureEngine
from src.infrastructure.tracing import bind_trace_tags, get_request_id, get_trace_id
from src.services.knowledge_service import KnowledgeService
from src.services.local_knowledge_service import LocalKnowledgeService


class DataSyncConsumer:
    def __init__(self, topic: str, consumer_group: str = "pms-consumer-group"):
        self.topic = topic
        self.consumer_group = consumer_group
        self.processed: list[dict[str, Any]] = []
        self.feature_engine = FeatureEngine()

    async def consume_batch(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.processed.extend(messages)
        entity_types = sorted({item.get("entity_type") for item in messages if item.get("entity_type")})
        bind_trace_tags(data_sync_topic=self.topic, consumer_group=self.consumer_group)
        return {
            "topic": self.topic,
            "consumer_group": self.consumer_group,
            "entity_types": entity_types,
            "consumed": len(messages),
            "last_event_id": messages[-1]["event_id"] if messages else None,
            "trace_id": get_trace_id(),
            "request_id": get_request_id(),
        }

    async def consume_review_events(
        self,
        messages: list[dict[str, Any]],
        *,
        session: Any = None,
        tenant_id: str | None = None,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        consumed = await self.consume_batch(messages)
        knowledge_service = (
            KnowledgeService(session, tenant_id=tenant_id, actor=actor)
            if session is not None and hasattr(session, "execute")
            else LocalKnowledgeService()
        )
        ingested_cases: list[dict[str, Any]] = []
        vector_updates: list[dict[str, Any]] = []
        skipped = 0
        for item in messages:
            if item.get("event_type") != "review.updated":
                skipped += 1
                continue
            payload = item.get("payload") or {}
            review = {
                "id": payload.get("review_id") or item.get("aggregate_id") or item.get("event_id"),
                "task_id": payload.get("task_id"),
                "product_id": payload.get("product_id"),
                "product_name": payload.get("product_name") or payload.get("task_query"),
                "asin": payload.get("asin"),
                "feedback": payload.get("feedback"),
                "customer_score": payload.get("rating"),
                "review_count": payload.get("review_count") or 1,
                "ticket_id": payload.get("ticket_id"),
                "customer_id": payload.get("customer_id"),
            }
            ingested = await knowledge_service.ingest_review_case(review)
            ingested_cases.append(ingested)
            vector_sync = ingested.get("vector_sync") if isinstance(ingested.get("vector_sync"), dict) else None
            if vector_sync is not None:
                vector_updates.append({
                    "review_id": ingested.get("review_id"),
                    "document_id": ingested.get("doc_id"),
                    **vector_sync,
                })
        return {
            **consumed,
            "case_type": "crm_review_case",
            "ingested_cases": ingested_cases,
            "ingested_count": len(ingested_cases),
            "vector_updates": vector_updates,
            "vector_updated_count": len(vector_updates),
            "skipped": skipped,
        }

    async def consume_feature_events(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        consumed = await self.consume_batch(messages)
        updated_features: list[dict[str, Any]] = []
        skipped = 0
        for item in messages:
            event_type = item.get("event_type")
            if event_type not in {"order.updated", "review.updated", "sales", "price", "rank", "review"}:
                skipped += 1
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            event_payload = dict(item)
            event_payload["payload"] = payload
            event_payload["event_type"] = event_type
            if not event_payload.get("product_id"):
                event_payload["product_id"] = payload.get("product_id") or payload.get("task_id") or item.get("aggregate_id")
            updated = await self.feature_engine.process_event(event_payload)
            updated_features.append(updated)
        product_ids = sorted({item.get("product_id") for item in updated_features if item.get("product_id")})
        return {
            **consumed,
            "feature_store_updated": True,
            "updated_features": updated_features,
            "updated_count": len(updated_features),
            "product_ids": product_ids,
            "skipped": skipped,
            "engine_stats": self.feature_engine.get_stats(),
        }
