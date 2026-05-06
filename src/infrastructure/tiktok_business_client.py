from __future__ import annotations

from typing import Any

from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry


class TikTokBusinessClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool,
        http_status: int | None = None,
        retry_after_seconds: float | None = None,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.attempts = attempts


class TikTokBusinessClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        timeout_seconds: float,
        retry_policy: HTTPRetryPolicy | None = None,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or HTTPRetryPolicy()

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Access-Token"] = self.api_key
        return headers

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await request_with_retry(
                "GET",
                f"{self.api_endpoint}{path}",
                headers=self.build_headers(),
                params=params,
                timeout_seconds=self.timeout_seconds,
                response_kind="json",
                policy=self.retry_policy,
            )
        except UpstreamHTTPError as e:
            raise TikTokBusinessClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    async def fetch_products(self, *, query: str, region: str, page_size: int = 10) -> dict[str, Any]:
        return await self._get("/open_api/v1.3/product/list/", params={"query": query, "region": region, "page_size": page_size})

    async def fetch_creators(self, *, niche: str, max_results: int = 10) -> dict[str, Any]:
        return await self._get("/open_api/v1.3/creator/search/", params={"query": niche, "page_size": max_results})
