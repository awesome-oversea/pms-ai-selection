from __future__ import annotations

from typing import Any

import httpx

from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class CRMClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class CRMClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
        complaints_path: str | None = None,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.inbound_path = inbound_path
        self.outbound_path = outbound_path
        self.timeout_seconds = timeout_seconds
        self.complaints_path = complaints_path or inbound_path

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
            raise CRMClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise CRMClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise CRMClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise CRMClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise CRMClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise CRMClientError(str(e), error_code="transport_error", retryable=True)

    async def _fetch_items(self, path: str) -> list[dict[str, Any]]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                payload = read_json_artifact(self.api_endpoint, path)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(f"{self.api_endpoint}{path}", headers=self.build_headers())
                    response.raise_for_status()
                    payload = response.json()
            if isinstance(payload, dict):
                return list(payload.get("items", []))
            return list(payload)
        except FileNotFoundError as e:
            raise CRMClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise CRMClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise CRMClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise CRMClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise CRMClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise CRMClientError(str(e), error_code="transport_error", retryable=True)

    async def fetch_customer_feedbacks(self) -> list[dict[str, Any]]:
        return await self._fetch_items(self.inbound_path)

    async def fetch_complaints(self) -> list[dict[str, Any]]:
        return await self._fetch_items(self.complaints_path)

    async def push_followups(self, payload: dict[str, Any]) -> None:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                write_json_artifact(self.api_endpoint, self.outbound_path, payload)
                return
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.api_endpoint}{self.outbound_path}", headers=self.build_headers(), json=payload)
                response.raise_for_status()
        except FileNotFoundError as e:
            raise CRMClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise CRMClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise CRMClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise CRMClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise CRMClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise CRMClientError(str(e), error_code="transport_error", retryable=True)
