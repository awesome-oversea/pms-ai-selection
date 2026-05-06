from __future__ import annotations

from typing import Any

import httpx

from src.core.permission_filter import filter_dataset_by_permission
from src.core.pms_governance import PermissionContext
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class BIClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class BIClient:
    def __init__(self, *, api_endpoint: str, api_key: str | None, health_path: str, dataset_path: str, timeout_seconds: float) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.health_path = health_path
        self.dataset_path = dataset_path
        self.timeout_seconds = timeout_seconds

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def test_connection(self) -> dict[str, Any]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                read_json_artifact(self.api_endpoint, self.health_path)
                return {"status": "ok", "error_code": None, "retryable": False}
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.api_endpoint}{self.health_path}", headers=self.build_headers())
                response.raise_for_status()
            return {"status": "ok", "error_code": None, "retryable": False}
        except FileNotFoundError as e:
            raise BIClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise BIClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise BIClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise BIClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise BIClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise BIClientError(str(e), error_code="transport_error", retryable=True)

    async def push_dataset(self, payload: dict[str, Any]) -> None:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                write_json_artifact(self.api_endpoint, self.dataset_path, payload)
                return
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.api_endpoint}{self.dataset_path}",
                    headers=self.build_headers(),
                    json=payload,
                )
                response.raise_for_status()
        except FileNotFoundError as e:
            raise BIClientError(str(e), error_code="artifact_missing", retryable=False)
        except httpx.TimeoutException as e:
            raise BIClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise BIClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise BIClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise BIClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise BIClientError(str(e), error_code="transport_error", retryable=True)

    async def read_dataset(self, permission_context: PermissionContext | dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                payload = read_json_artifact(self.api_endpoint, self.dataset_path)
                return filter_dataset_by_permission(payload if isinstance(payload, dict) else {"datasets": []}, permission_context)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.api_endpoint}{self.dataset_path}",
                    headers=self.build_headers(),
                )
                response.raise_for_status()
                payload = response.json()
                return filter_dataset_by_permission(payload if isinstance(payload, dict) else {"datasets": []}, permission_context)
        except FileNotFoundError:
            return {"datasets": []}
        except httpx.TimeoutException as e:
            raise BIClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                return {"datasets": []}
            if status in {401, 403}:
                raise BIClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise BIClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise BIClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise BIClientError(str(e), error_code="transport_error", retryable=True)
