from __future__ import annotations

from typing import Any

import httpx

from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class PaaSClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class PaaSClient:
    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        health_path: str,
        trigger_path: str,
        status_path: str,
        timeout_seconds: float,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.health_path = health_path
        self.trigger_path = trigger_path
        self.status_path = status_path
        self.timeout_seconds = timeout_seconds

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    @staticmethod
    def _raise_as_client_error(exc: Exception) -> None:
        if isinstance(exc, httpx.TimeoutException):
            raise PaaSClientError(str(exc), error_code="timeout", retryable=True)
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {401, 403}:
                raise PaaSClientError(str(exc), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise PaaSClientError(str(exc), error_code="upstream_5xx", retryable=True)
            raise PaaSClientError(str(exc), error_code="upstream_4xx", retryable=False)
        raise PaaSClientError(str(exc), error_code="transport_error", retryable=True)

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
            raise PaaSClientError(str(e), error_code="artifact_missing", retryable=False)
        except Exception as e:
            self._raise_as_client_error(e)

    async def trigger_workflow(
        self,
        *,
        workflow_key: str,
        payload: dict[str, Any],
        callback: dict[str, Any],
        callback_context: dict[str, Any],
    ) -> dict[str, Any]:
        request_payload = {
            "workflow_key": workflow_key,
            "input": payload,
            "callback": callback,
            "callback_context": callback_context,
        }
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                data = read_json_artifact(self.api_endpoint, self.trigger_path)
                write_json_artifact(self.api_endpoint, self.status_path.format(run_id=str(data.get("run_id") or data.get("id") or callback_context.get("internal_run_id"))), {
                    "run_id": str(data.get("run_id") or data.get("id") or callback_context.get("internal_run_id")),
                    "status": data.get("status", "dispatched"),
                    "result": data.get("result"),
                    "workflow_key": workflow_key,
                    "accepted": bool(data.get("accepted", True)),
                    "request_payload": request_payload,
                })
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.api_endpoint}{self.trigger_path}",
                        headers=self.build_headers(),
                        json=request_payload,
                    )
                    response.raise_for_status()
                    data = response.json()
            return {
                "run_id": str(data.get("run_id") or data.get("id") or callback_context.get("internal_run_id")),
                "status": data.get("status", "dispatched"),
                "accepted": bool(data.get("accepted", True)),
            }
        except FileNotFoundError as e:
            raise PaaSClientError(str(e), error_code="artifact_missing", retryable=False)
        except Exception as e:
            self._raise_as_client_error(e)

    async def get_workflow_status(self, run_id: str) -> dict[str, Any]:
        path = self.status_path.format(run_id=run_id)
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                data = read_json_artifact(self.api_endpoint, path)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(f"{self.api_endpoint}{path}", headers=self.build_headers())
                    response.raise_for_status()
                    data = response.json()
            return {
                "run_id": str(data.get("run_id") or run_id),
                "status": data.get("status", "running"),
                "result": data.get("result"),
            }
        except FileNotFoundError as e:
            raise PaaSClientError(str(e), error_code="artifact_missing", retryable=False)
        except Exception as e:
            self._raise_as_client_error(e)
