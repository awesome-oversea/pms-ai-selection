from __future__ import annotations

from typing import Any

from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact


class GoogleTrendsClientError(Exception):
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


class GoogleTrendsClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        timeout_seconds: float = 10.0,
        retry_policy: HTTPRetryPolicy | None = None,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or HTTPRetryPolicy()
        self._is_local = is_local_artifact_endpoint(api_endpoint)

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def fetch_interest_over_time(self, *, keywords: list[str], geo: str, time_range: str) -> str:
        if self._is_local:
            return self._local_interest_over_time(keywords, geo, time_range)
        params = {"q": ",".join(keywords), "geo": geo, "date": time_range}
        try:
            return await request_with_retry(
                "GET",
                f"{self.api_endpoint}/trends/explore",
                headers=self.build_headers(),
                params=params,
                timeout_seconds=self.timeout_seconds,
                follow_redirects=True,
                response_kind="text",
                policy=self.retry_policy,
            )
        except UpstreamHTTPError as e:
            raise GoogleTrendsClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    async def fetch_interest_by_region(self, *, keywords: list[str], geo: str, resolution: str = "COUNTRY") -> dict[str, Any]:
        if self._is_local:
            return self._local_interest_by_region(keywords, geo, resolution)
        params = {"q": ",".join(keywords), "geo": geo, "resolution": resolution}
        try:
            return await request_with_retry(
                "GET",
                f"{self.api_endpoint}/trends/interest_by_region",
                headers=self.build_headers(),
                params=params,
                timeout_seconds=self.timeout_seconds,
                response_kind="json",
                policy=self.retry_policy,
            )
        except UpstreamHTTPError as e:
            raise GoogleTrendsClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    def _local_interest_over_time(self, keywords: list[str], geo: str, time_range: str) -> str:
        try:
            artifact = read_json_artifact(self.api_endpoint, "interest_over_time")
            if isinstance(artifact, dict):
                return artifact.get("timeline_data", "")
            return str(artifact)
        except FileNotFoundError:
            return ""

    def _local_interest_by_region(self, keywords: list[str], geo: str, resolution: str) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "interest_by_region")
            if isinstance(artifact, dict):
                return artifact
            return {"geo": geo, "resolution": resolution, "regions": []}
        except FileNotFoundError:
            return {"geo": geo, "resolution": resolution, "regions": []}
