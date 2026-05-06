from __future__ import annotations

import httpx
import pytest
from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry


class _FakeAsyncClient:
    responses: list[httpx.Response] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def request(self, method: str, url: str, headers=None, params=None) -> httpx.Response:
        if not self.responses:
            raise AssertionError("no fake responses configured")
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_request_with_retry_retries_rate_limit_then_succeeds(monkeypatch):
    first_request = httpx.Request("GET", "https://example.com/catalog")
    second_request = httpx.Request("GET", "https://example.com/catalog")
    _FakeAsyncClient.responses = [
        httpx.Response(429, request=first_request, headers={"Retry-After": "1"}),
        httpx.Response(200, request=second_request, json={"items": [{"id": "ok"}]}),
    ]
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.infrastructure.http_retry.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("src.infrastructure.http_retry.asyncio.sleep", _fake_sleep)

    payload = await request_with_retry(
        "GET",
        "https://example.com/catalog",
        timeout_seconds=3.0,
        response_kind="json",
        policy=HTTPRetryPolicy(max_attempts=2, base_backoff_seconds=0.2, max_backoff_seconds=1.0),
    )

    assert payload["items"][0]["id"] == "ok"
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_request_with_retry_raises_structured_rate_limit_after_exhausted_retries(monkeypatch):
    request = httpx.Request("GET", "https://example.com/catalog")
    _FakeAsyncClient.responses = [
        httpx.Response(429, request=request, headers={"Retry-After": "2"}),
        httpx.Response(429, request=request, headers={"Retry-After": "2"}),
    ]

    async def _fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("src.infrastructure.http_retry.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("src.infrastructure.http_retry.asyncio.sleep", _fake_sleep)

    with pytest.raises(UpstreamHTTPError) as exc_info:
        await request_with_retry(
            "GET",
            "https://example.com/catalog",
            timeout_seconds=3.0,
            response_kind="json",
            policy=HTTPRetryPolicy(max_attempts=2, base_backoff_seconds=0.2, max_backoff_seconds=2.0),
        )

    assert exc_info.value.error_code == "rate_limited"
    assert exc_info.value.http_status == 429
    assert exc_info.value.retry_after_seconds == 2.0
    assert exc_info.value.attempts == 2
