from __future__ import annotations

import pytest
from src.infrastructure.dingtalk_client import DingtalkClient


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


@pytest.mark.asyncio
async def test_dingtalk_client_test_and_send(monkeypatch):
    monkeypatch.setattr("src.infrastructure.dingtalk_client.httpx.AsyncClient", _Client)
    client = DingtalkClient(webhook_url="http://fake-dingtalk.local/hook")
    tested = await client.test_connection()
    sent = await client.send_text(title="日报", content="报告已生成")
    assert tested["status"] == "ok"
    assert sent["errcode"] == 0
    assert "日报" in _Client.last_payload["text"]["content"]
