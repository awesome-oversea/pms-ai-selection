from __future__ import annotations

from typing import Any

import httpx


class DingtalkClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class DingtalkClient:
    def __init__(self, *, webhook_url: str, timeout_seconds: float = 10.0) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        payload = {"msgtype": "text", "text": {"content": "PMS 钉钉通道连接测试"}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                data = response.json()
            return {"status": "ok", "result": data}
        except httpx.TimeoutException as e:
            raise DingtalkClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            raise DingtalkClientError(str(e), error_code=f"http_{code}", retryable=code >= 500)
        except Exception as e:
            raise DingtalkClientError(str(e), error_code="transport_error", retryable=True)

    async def send_text(self, title: str, content: str) -> dict[str, Any]:
        payload = {"msgtype": "text", "text": {"content": f"[{title}]\n{content}"}}
        return await self.send_payload(payload)

    async def send_action_card(self, *, title: str, markdown: str, actions: list[dict[str, str]]) -> dict[str, Any]:
        btns = [{"title": item.get("title", "打开"), "actionURL": item.get("url", "")} for item in actions]
        payload = {
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": markdown,
                "btnOrientation": "0",
                "btns": btns,
            },
        }
        return await self.send_payload(payload)

    async def send_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            raise DingtalkClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            raise DingtalkClientError(str(e), error_code=f"http_{code}", retryable=code >= 500)
        except Exception as e:
            raise DingtalkClientError(str(e), error_code="transport_error", retryable=True)
