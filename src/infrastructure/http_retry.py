from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx


@dataclass(frozen=True)
class HTTPRetryPolicy:
    max_attempts: int = 3
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 3.0


class UpstreamHTTPError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool,
        http_status: int | None = None,
        retry_after_seconds: float | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.attempts = attempts


def _parse_retry_after(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delta = (retry_at - datetime.now(UTC)).total_seconds()
    return max(delta, 0.0)


def _build_error(exc: Exception, *, attempts: int) -> UpstreamHTTPError:
    if isinstance(exc, httpx.TimeoutException):
        return UpstreamHTTPError(str(exc), error_code="timeout", retryable=True, attempts=attempts)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        retry_after_seconds = _parse_retry_after(exc.response.headers.get("Retry-After") if exc.response is not None else None)
        if status in {401, 403}:
            error_code = "auth_failed"
        elif status == 429:
            error_code = "rate_limited"
        elif status is not None and status >= 500:
            error_code = "upstream_5xx"
        else:
            error_code = "upstream_4xx"
        retryable = bool(status in {408, 409, 425, 429} or (status is not None and status >= 500))
        return UpstreamHTTPError(
            str(exc),
            error_code=error_code,
            retryable=retryable,
            http_status=status,
            retry_after_seconds=retry_after_seconds,
            attempts=attempts,
        )
    if isinstance(exc, httpx.TransportError):
        return UpstreamHTTPError(str(exc), error_code="transport_error", retryable=True, attempts=attempts)
    return UpstreamHTTPError(str(exc), error_code="transport_error", retryable=False, attempts=attempts)


def _compute_backoff_seconds(policy: HTTPRetryPolicy, *, attempts: int, retry_after_seconds: float | None) -> float:
    exponential_backoff = min(
        policy.base_backoff_seconds * (2 ** max(attempts - 1, 0)),
        policy.max_backoff_seconds,
    )
    if retry_after_seconds is None:
        return exponential_backoff
    return min(max(retry_after_seconds, exponential_backoff), policy.max_backoff_seconds)


async def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout_seconds: float,
    follow_redirects: bool = False,
    response_kind: Literal["json", "text", "bytes"] = "json",
    policy: HTTPRetryPolicy | None = None,
) -> Any:
    resolved_policy = policy or HTTPRetryPolicy()
    last_error: UpstreamHTTPError | None = None

    for attempts in range(1, resolved_policy.max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=follow_redirects) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                if response_kind == "text":
                    return response.text
                if response_kind == "bytes":
                    return response.content
                return response.json() if response.content else {}
        except Exception as exc:  # pragma: no cover - non-httpx branches are still wrapped for callers
            last_error = exc if isinstance(exc, UpstreamHTTPError) else _build_error(exc, attempts=attempts)
            if not last_error.retryable or attempts >= resolved_policy.max_attempts:
                raise last_error
            await asyncio.sleep(
                _compute_backoff_seconds(
                    resolved_policy,
                    attempts=attempts,
                    retry_after_seconds=last_error.retry_after_seconds,
                )
            )

    raise last_error or UpstreamHTTPError(
        "request failed without response",
        error_code="transport_error",
        retryable=False,
    )
