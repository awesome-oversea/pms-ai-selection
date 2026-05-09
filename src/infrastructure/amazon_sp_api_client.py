from __future__ import annotations

from typing import Any

from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact


class AmazonSPAPIClientError(Exception):
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


class AmazonSPAPIClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        marketplace_id: str,
        timeout_seconds: float = 10.0,
        retry_policy: HTTPRetryPolicy | None = None,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.marketplace_id = marketplace_id
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or HTTPRetryPolicy()
        self._is_local = is_local_artifact_endpoint(api_endpoint)

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "x-amz-marketplace-id": self.marketplace_id}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
            raise AmazonSPAPIClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    async def fetch_catalog_items(self, *, keywords: list[str], page_size: int = 10) -> dict[str, Any]:
        if self._is_local:
            return self._local_catalog_items(keywords, page_size)
        return await self._get("/catalog/2022-04-01/items", params={"keywords": ",".join(keywords), "pageSize": page_size, "marketplaceIds": self.marketplace_id})

    async def fetch_item_offers(self, *, asin: str) -> dict[str, Any]:
        if self._is_local:
            return self._local_item_offers(asin)
        return await self._get(f"/products/pricing/v0/items/{asin}/offers", params={"MarketplaceId": self.marketplace_id, "ItemCondition": "New"})

    async def fetch_item_reviews(self, *, asin: str, page_size: int = 20) -> dict[str, Any]:
        if self._is_local:
            return self._local_item_reviews(asin, page_size)
        return await self._get(f"/reviews/2023-06-30/items/{asin}", params={"marketplaceIds": self.marketplace_id, "pageSize": page_size})

    def _local_catalog_items(self, keywords: list[str], page_size: int) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "catalog")
            items = artifact if isinstance(artifact, list) else artifact.get("items", []) if isinstance(artifact, dict) else []
            matched = [i for i in items if isinstance(i, dict) and any(kw.lower() in str(i.get("title", "")).lower() for kw in keywords)] if keywords else items
            return {"items": matched[:page_size], "totalItems": len(matched), "marketplaceId": self.marketplace_id}
        except FileNotFoundError:
            return {"items": [], "totalItems": 0, "marketplaceId": self.marketplace_id}

    def _local_item_offers(self, asin: str) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "offers")
            items = artifact if isinstance(artifact, list) else [artifact] if isinstance(artifact, dict) else []
            for item in items:
                if isinstance(item, dict) and item.get("asin") == asin:
                    return {"asin": asin, "offers": item.get("offers", []), "marketplaceId": self.marketplace_id}
            return {"asin": asin, "offers": [], "marketplaceId": self.marketplace_id}
        except FileNotFoundError:
            return {"asin": asin, "offers": [], "marketplaceId": self.marketplace_id}

    def _local_item_reviews(self, asin: str, page_size: int) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "reviews")
            items = artifact if isinstance(artifact, list) else [artifact] if isinstance(artifact, dict) else []
            reviews = [r for r in items if isinstance(r, dict) and r.get("asin") == asin]
            return {"reviews": reviews[:page_size], "totalReviews": len(reviews), "marketplaceId": self.marketplace_id}
        except FileNotFoundError:
            return {"reviews": [], "totalReviews": 0, "marketplaceId": self.marketplace_id}
