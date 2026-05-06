from __future__ import annotations

from typing import Any

import httpx

from src.core.permission_filter import filter_items_by_permission
from src.core.pms_governance import PermissionContext
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class OMSClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class OMSClient:
    def __init__(self, *, api_endpoint: str, api_key: str | None, inbound_path: str, outbound_path: str, timeout_seconds: float) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.inbound_path = inbound_path
        self.outbound_path = outbound_path
        self.timeout_seconds = timeout_seconds

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def test_connection(self) -> dict[str, Any]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                read_json_artifact(self.api_endpoint, self.inbound_path)
                return {"status": "ok", "error_code": None, "retryable": False}
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.api_endpoint}{self.inbound_path}", headers=self.build_headers())
                response.raise_for_status()
            return {"status": "ok", "error_code": None, "retryable": False}
        except FileNotFoundError as e:
            raise OMSClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise OMSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise OMSClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise OMSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise OMSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise OMSClientError(str(e), error_code="transport_error", retryable=True)

    async def fetch_products(self, permission_context: PermissionContext | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                payload = read_json_artifact(self.api_endpoint, self.inbound_path)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(f"{self.api_endpoint}{self.inbound_path}", headers=self.build_headers())
                    response.raise_for_status()
                    payload = response.json()
            if isinstance(payload, dict):
                return filter_items_by_permission(list(payload.get("items", [])), permission_context)
            return filter_items_by_permission(list(payload), permission_context)
        except FileNotFoundError as e:
            raise OMSClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise OMSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise OMSClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise OMSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise OMSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise OMSClientError(str(e), error_code="transport_error", retryable=True)

    async def push_products(self, payload: dict[str, Any]) -> None:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                write_json_artifact(self.api_endpoint, self.outbound_path, payload)
                return
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.api_endpoint}{self.outbound_path}", headers=self.build_headers(), json=payload)
                response.raise_for_status()
        except FileNotFoundError as e:
            raise OMSClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise OMSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise OMSClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise OMSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise OMSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise OMSClientError(str(e), error_code="transport_error", retryable=True)

    async def fetch_orders(self, permission_context: PermissionContext | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self.fetch_products(permission_context=permission_context)

    async def fetch_sales_metrics(self, permission_context: PermissionContext | dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return await self.fetch_products(permission_context=permission_context)

    async def push_listing_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise OMSClientError(
            "Listing draft belongs to ERP SOM; OMS is read-only for order, fulfillment, refund, and risk feedback in PMS/ERP V11.",
            error_code="boundary_violation",
            retryable=False,
        )
