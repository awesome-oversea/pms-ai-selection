from __future__ import annotations

from typing import Any

from src.infrastructure.http_retry import HTTPRetryPolicy, UpstreamHTTPError, request_with_retry
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact


class Ali1688OpenClientError(Exception):
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


class Ali1688OpenClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        timeout_seconds: float = 10.0,
        retry_policy: HTTPRetryPolicy | None = None,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or HTTPRetryPolicy()
        self._is_local = is_local_artifact_endpoint(api_endpoint)

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.secret_key:
            headers["X-API-Secret"] = self.secret_key
        return headers

    async def fetch_suppliers(self, *, keyword: str, page_size: int = 10) -> dict[str, Any]:
        if self._is_local:
            return self._local_suppliers(keyword, page_size)
        try:
            return await request_with_retry(
                "GET",
                f"{self.api_endpoint}/openapi/offer/search",
                headers=self.build_headers(),
                params={"keywords": keyword, "pageSize": page_size},
                timeout_seconds=self.timeout_seconds,
                response_kind="json",
                policy=self.retry_policy,
            )
        except UpstreamHTTPError as e:
            raise Ali1688OpenClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    async def fetch_product_detail(self, *, product_id: str) -> dict[str, Any]:
        if self._is_local:
            return self._local_product_detail(product_id)
        try:
            return await request_with_retry(
                "GET",
                f"{self.api_endpoint}/openapi/offer/detail",
                headers=self.build_headers(),
                params={"offerId": product_id},
                timeout_seconds=self.timeout_seconds,
                response_kind="json",
                policy=self.retry_policy,
            )
        except UpstreamHTTPError as e:
            raise Ali1688OpenClientError(
                str(e),
                error_code=e.error_code,
                retryable=e.retryable,
                http_status=e.http_status,
                retry_after_seconds=e.retry_after_seconds,
                attempts=e.attempts,
            ) from e

    def _local_suppliers(self, keyword: str, page_size: int) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "suppliers")
            items = artifact if isinstance(artifact, list) else artifact.get("offers", artifact.get("suppliers", [])) if isinstance(artifact, dict) else []
            matched = [i for i in items if isinstance(i, dict) and (keyword.lower() in str(i.get("subject", "")).lower() or keyword.lower() in str(i.get("title", "")).lower())] if keyword else items
            return {"offers": matched[:page_size], "total": len(matched)}
        except FileNotFoundError:
            return {"offers": [], "total": 0}

    def _local_product_detail(self, product_id: str) -> dict[str, Any]:
        try:
            artifact = read_json_artifact(self.api_endpoint, "products")
            items = artifact if isinstance(artifact, list) else [artifact] if isinstance(artifact, dict) else []
            for item in items:
                if isinstance(item, dict) and str(item.get("offerId", item.get("product_id"))) == product_id:
                    return item
            return {"offerId": product_id, "status": "not_found"}
        except FileNotFoundError:
            return {"offerId": product_id, "status": "not_found"}
