from __future__ import annotations

from typing import Any

import httpx


class TritonClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class TritonClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _raise_as_client_error(exc: Exception) -> None:
        if isinstance(exc, httpx.TimeoutException):
            raise TritonClientError(str(exc), error_code="timeout", retryable=True)
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            raise TritonClientError(str(exc), error_code=f"http_{code}", retryable=code >= 500)
        raise TritonClientError(str(exc), error_code="transport_error", retryable=True)

    def healthcheck_sync(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(f"{self.base_url}/v2/health/ready")
                response.raise_for_status()
            return {"status": "ok", "endpoint": self.base_url}
        except Exception as e:
            self._raise_as_client_error(e)

    async def healthcheck(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/v2/health/ready")
                response.raise_for_status()
            return {"status": "ok", "endpoint": self.base_url}
        except Exception as e:
            self._raise_as_client_error(e)

    def rerank_sync(self, *, query: str, documents: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        payload = {"query": query, "documents": documents, "top_k": top_k}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}/v1/rerank", json=payload)
                response.raise_for_status()
                data = response.json()
            return list(data.get("results", []))
        except Exception as e:
            self._raise_as_client_error(e)

    async def rerank(self, *, query: str, documents: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        payload = {"query": query, "documents": documents, "top_k": top_k}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/v1/rerank", json=payload)
                response.raise_for_status()
                data = response.json()
            return list(data.get("results", []))
        except Exception as e:
            self._raise_as_client_error(e)
