from __future__ import annotations

from typing import Any

from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact


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
        if self._is_local:
            return self._local_products(query, region, page_size)
        return await self._get("/open_api/v1.3/product/list/", params={"query": query, "region": region, "page_size": page_size})

    async def fetch_creators(self, *, niche: str, max_results: int = 10) -> dict[str, Any]:
        if self._is_local:
            return self._local_creators(niche, max_results)
        return await self._get("/open_api/v1.3/creator/search/", params={"query": niche, "page_size": max_results})

    def _local_products(self, query: str, region: str, page_size: int) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "products")
            items = artifact if isinstance(artifact, list) else artifact.get("products", []) if isinstance(artifact, dict) else []
            matched = [i for i in items if isinstance(i, dict) and (query.lower() in str(i.get("title", "")).lower() or query.lower() in str(i.get("description", "")).lower())] if query else items
            return {"products": matched[:page_size], "total": len(matched), "region": region}
        except FileNotFoundError:
            return {"products": [], "total": 0, "region": region}

    def _local_creators(self, niche: str, max_results: int) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "creators")
            items = artifact if isinstance(artifact, list) else artifact.get("creators", []) if isinstance(artifact, dict) else []
            matched = [i for i in items if isinstance(i, dict) and niche.lower() in str(i.get("niche", "")).lower()] if niche else items
            return {"creators": matched[:max_results], "total": len(matched)}
        except FileNotFoundError:
            return {"creators": [], "total": 0}
