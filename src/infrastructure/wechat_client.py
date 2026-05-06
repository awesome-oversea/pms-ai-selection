from __future__ import annotations

from typing import Any

import httpx


class WechatClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class WechatClient:
    def __init__(self, *, webhook_url: str, timeout_seconds: float = 10.0) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        payload = {"msgtype": "text", "text": {"content": "PMS 企业微信通道连接测试"}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                data = response.json()
            return {"status": "ok", "result": data}
        except httpx.TimeoutException as e:
            raise WechatClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            raise WechatClientError(str(e), error_code=f"http_{code}", retryable=code >= 500)
        except Exception as e:
            raise WechatClientError(str(e), error_code="transport_error", retryable=True)

    async def send_text(self, title: str, content: str) -> dict[str, Any]:
        payload = {"msgtype": "text", "text": {"content": f"[{title}]\n{content}"}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            raise WechatClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            raise WechatClientError(str(e), error_code=f"http_{code}", retryable=code >= 500)
        except Exception as e:
            raise WechatClientError(str(e), error_code="transport_error", retryable=True)
