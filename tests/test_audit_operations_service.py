from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.core.data_masking import mask_sensitive_data
from src.services.audit_operations_service import AuditOperationsService


class _FakeRepo:
    def __init__(self, session, tenant_id=None):
        self.session = session
        self.tenant_id = tenant_id

    async def build_operations_status(self, limit=20):
        return {
            "tenant_id": self.tenant_id,
            "total": 1,
            "recent_actions": [
                {
                    "action": "system.audit.query",
                    "username": "admin",
                    "result": "success",
                    "occurred_at": "2026-04-11T00:00:00+00:00",
                }
            ],
            "export_policy": "manual export via audit-operations",
            "archive_policy": "retain latest records in db and archive externally by schedule",
            "trace_export_ready": True,
            "cross_system_trace_supported": True,
            "trace_query_ready": True,
            "supported_filters": ["username", "target_id", "action", "request_id", "trace_id"],
        }


@pytest.mark.asyncio
async def test_audit_operations_status_exposes_trace_query_capability(monkeypatch):
    monkeypatch.setattr("src.services.audit_operations_service.AuditLogRepository", _FakeRepo)
    service = AuditOperationsService(session=SimpleNamespace(), tenant_id="tenant-1")
    status = await service.build_status()
    assert status["trace_export_ready"] is True
    assert status["cross_system_trace_supported"] is True
    assert status["trace_query_ready"] is True
    assert set(status["supported_filters"]) >= {"request_id", "trace_id"}


def test_mask_sensitive_data_covers_name_address_and_contact_fields():
    payload = {
        "customer_name": "张三丰",
        "full_name": "Alice Johnson",
        "phone": "13812345678",
        "email": "alice@example.com",
        "address": "浙江省杭州市西湖区文三路100号A座1201室",
        "passport": "E123456789",
        "nested": {
            "receiver": "李四",
            "wechat": "wxid_12345678",
        },
    }
    masked = mask_sensitive_data(payload)
    assert masked["customer_name"] != payload["customer_name"]
    assert masked["full_name"] != payload["full_name"]
    assert masked["phone"] == "138****5678"
    assert masked["email"] == "ali***@example.com"
    assert masked["address"] != payload["address"]
    assert masked["passport"] != payload["passport"]
    assert masked["nested"]["receiver"] != payload["nested"]["receiver"]
    assert masked["nested"]["wechat"] != payload["nested"]["wechat"]


@pytest.mark.asyncio
async def test_query_logs_masks_pii_from_persistent_or_memory_sources(monkeypatch):
    async def _fake_list_audit_logs_persistent(**kwargs):
        return [
            {
                "timestamp": "2026-04-16T00:00:00+00:00",
                "action": "selection.submit",
                "actor": {"username": "alice", "tenant_id": "tenant-1"},
                "detail": {
                    "customer_name": "张三",
                    "phone": "13812345678",
                    "email": "alice@example.com",
                    "address": "杭州市西湖区文三路100号",
                },
            }
        ]

    monkeypatch.setattr("src.services.audit_operations_service.list_audit_logs_persistent", _fake_list_audit_logs_persistent)
    service = AuditOperationsService(session=SimpleNamespace(), tenant_id="tenant-1")
    result = await service.query_logs(limit=10)
    detail = result["logs"][0]["detail"]
    assert detail["customer_name"] != "张三"
    assert detail["phone"] == "138****5678"
    assert detail["email"] == "ali***@example.com"
    assert detail["address"] != "杭州市西湖区文三路100号"


def test_mask_sensitive_data_covers_extended_pii_fields():
    payload = {
        "bank_card": "6222 0000 1234 5678",
        "token": "tok_live_abcdefghijklmnopqrstuvwxyz0123456789",
        "password": "SuperSecretPassword!",
    }
    masked = mask_sensitive_data(payload)
    assert masked["bank_card"] != payload["bank_card"]
    assert masked["token"] != payload["token"]
    assert masked["password"] != payload["password"]


def test_mask_sensitive_data_supports_configured_pii_field_patterns(monkeypatch):
    monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)
    monkeypatch.setenv("SEC_PII_FIELD_PATTERNS", "employee_name")
    from src.config.settings import get_settings

    get_settings.cache_clear()
    masked = mask_sensitive_data({"employee_name": "赵敏"})
    assert masked["employee_name"] != "赵敏"

    monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
    monkeypatch.delenv("SEC_PII_FIELD_PATTERNS", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_query_logs_merges_memory_when_persistent_empty(monkeypatch):
    async def _fake_list_audit_logs_persistent(**kwargs):
        return []

    def _fake_list_audit_logs(**kwargs):
        return [
            {
                "timestamp": "2026-04-16T00:00:00+00:00",
                "action": "auth.register",
                "actor": {"username": "alice", "tenant_id": "tenant-1"},
                "result": "success",
                "detail": {"request_id": "req-1", "trace_id": "tr-1"},
            }
        ]

    monkeypatch.setattr("src.services.audit_operations_service.list_audit_logs_persistent", _fake_list_audit_logs_persistent)
    monkeypatch.setattr("src.services.audit_operations_service.list_audit_logs", _fake_list_audit_logs)
    service = AuditOperationsService(session=SimpleNamespace(), tenant_id="tenant-1")
    result = await service.query_logs(limit=10)
    assert result["total"] == 1
    assert result["source"] == "persistent+memory"
    assert result["logs"][0]["action"] == "auth.register"


@pytest.mark.asyncio
async def test_query_logs_filters_memory_logs_by_tenant(monkeypatch):
    async def _fake_list_audit_logs_persistent(**kwargs):
        raise RuntimeError("db offline")

    def _fake_list_audit_logs(**kwargs):
        return [
            {
                "timestamp": "2026-04-16T00:00:00+00:00",
                "action": "auth.register",
                "actor": {"username": "alice", "tenant_id": "tenant-1"},
                "result": "success",
                "detail": {"request_id": "req-1", "trace_id": "tr-1"},
            },
            {
                "timestamp": "2026-04-16T00:00:01+00:00",
                "action": "auth.register",
                "actor": {"username": "bob", "tenant_id": "tenant-2"},
                "result": "success",
                "detail": {"request_id": "req-2", "trace_id": "tr-2"},
            },
        ]

    monkeypatch.setattr("src.services.audit_operations_service.list_audit_logs_persistent", _fake_list_audit_logs_persistent)
    monkeypatch.setattr("src.services.audit_operations_service.list_audit_logs", _fake_list_audit_logs)
    service = AuditOperationsService(session=SimpleNamespace(), tenant_id="tenant-1")
    result = await service.query_logs(limit=10)
    assert result["total"] == 1
    assert result["source"] == "memory"
    assert result["logs"][0]["actor"]["tenant_id"] == "tenant-1"
