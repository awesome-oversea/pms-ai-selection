from __future__ import annotations

import pytest
from src.config.settings import get_settings
from src.infrastructure.wechat_client import WechatClient
from src.services.channel_delivery_service import ChannelDeliveryService


@pytest.mark.asyncio
async def test_channel_delivery_service_dingtalk_report():
    class _FakeClient:
        async def test_connection(self):
            return {"status": "ok", "result": {"errcode": 0}}

        async def send_text(self, title: str, content: str):
            return {"errcode": 0, "title": title, "content": content}

    service = ChannelDeliveryService(dingtalk_client=_FakeClient())
    tested = await service.test_dingtalk("http://fake")
    delivered = await service.send_report(channel="dingtalk", webhook_url="http://fake", title="日报", content="报告生成完成", report_url="http://report")
    assert tested["channel"] == "dingtalk"
    assert tested["message_type"] == "connectivity_test"
    assert tested["audit_meta"]["template_used"] == "healthcheck"
    assert delivered["delivered"] is True
    assert delivered["template_used"] == "summary_with_link"
    assert delivered["audit_meta"]["has_report_url"] is True
    assert delivered["result"]["title"] == "日报"


def test_channel_delivery_service_verifies_callback_signature(monkeypatch):
    monkeypatch.setenv("SEC_CHANNEL_CALLBACK_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("SEC_CHANNEL_CALLBACK_TTL_SECONDS", "300")
    monkeypatch.setenv("SEC_DINGTALK_CALLBACK_TOKEN", "ding-token")
    monkeypatch.setenv("SEC_DINGTALK_CALLBACK_SECRET", "ding-secret")
    get_settings.cache_clear()

    service = ChannelDeliveryService()
    signature = service.build_callback_signature(
        channel="dingtalk",
        token="ding-token",
        secret="ding-secret",
        timestamp="1700000000",
        nonce="nonce-001",
    )
    verified = service.verify_callback_url(
        channel="dingtalk",
        timestamp="1700000000",
        nonce="nonce-001",
        signature=signature,
        challenge="echo-123",
        now_seconds=1700000001,
    )
    assert verified["verified"] is True
    assert verified["verification_mode"] == "hmac-sha256"
    assert verified["challenge"] == "echo-123"

    monkeypatch.delenv("SEC_CHANNEL_CALLBACK_VERIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("SEC_CHANNEL_CALLBACK_TTL_SECONDS", raising=False)
    monkeypatch.delenv("SEC_DINGTALK_CALLBACK_TOKEN", raising=False)
    monkeypatch.delenv("SEC_DINGTALK_CALLBACK_SECRET", raising=False)
    get_settings.cache_clear()


def test_channel_delivery_service_callback_verification_disabled(monkeypatch):
    monkeypatch.delenv("SEC_CHANNEL_CALLBACK_VERIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("SEC_DINGTALK_CALLBACK_TOKEN", raising=False)
    monkeypatch.delenv("SEC_DINGTALK_CALLBACK_SECRET", raising=False)
    get_settings.cache_clear()

    service = ChannelDeliveryService()
    verified = service.verify_callback_url(
        channel="dingtalk",
        timestamp="1700000000",
        nonce="nonce-001",
        signature="ignored-signature",
        challenge="local-ok",
    )
    assert verified["verified"] is True
    assert verified["verification_mode"] == "disabled"
    assert verified["challenge"] == "local-ok"


@pytest.mark.asyncio
async def test_channel_delivery_service_wechat_interactive_card():
    class _FakeWechatClient:
        async def send_markdown_card(self, *, title: str, markdown: str):
            return {"errcode": 0, "title": title, "markdown": markdown}

    service = ChannelDeliveryService(wechat_client=_FakeWechatClient())
    delivered = await service.send_interactive_card(
        channel="wechat",
        webhook_url="http://fake-wechat",
        title="选品审批",
        task_id="task-001",
        summary="请审批",
        callback_base_url="http://localhost:8000",
    )

    assert delivered["delivered"] is True
    assert delivered["channel"] == "wechat"
    assert delivered["message_type"] == "interactive_selection_card"
    assert len(delivered["card"]["actions"]) == 3
    assert delivered["result"]["errcode"] == 0


@pytest.mark.asyncio
async def test_wechat_client_send_markdown_card(monkeypatch):
    class _Resp:
        def __init__(self, payload=None, status_code=200):
            self._payload = payload or {"errcode": 0}
            self.status_code = status_code

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    class _Client:
        last_payload = None

        def __init__(self, timeout=10):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            _Client.last_payload = json
            return _Resp({"errcode": 0, "errmsg": "ok"})

    monkeypatch.setattr("src.infrastructure.wechat_client.httpx.AsyncClient", _Client)
    client = WechatClient(webhook_url="http://fake-wechat.local/hook")
    result = await client.send_markdown_card(title="审批通知", markdown="请审批任务")

    assert result["errcode"] == 0
    assert _Client.last_payload["msgtype"] == "markdown"
    assert "审批通知" in _Client.last_payload["markdown"]["content"]
