from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict
from typing import Any

import httpx

from src.core.pms_governance import AuditContext, validate_erp_api_path


class ERPClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class BaseERPClient:
    def __init__(
        self,
        *,
        base_url: str,
        domain: str,
        api_key: str,
        secret_key: str,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.domain = domain.strip("/").lower()
        self.api_key = api_key
        self.secret_key = secret_key
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.max_retries = max_retries
        self.audit_log: list[dict[str, Any]] = []

    def build_path(self, resource: str) -> str:
        normalized_resource = resource.strip("/")
        path = f"/api/internal/v1/{self.domain}/{normalized_resource}"
        validate_erp_api_path(path)
        return path

    def build_url(self, resource: str) -> str:
        return f"{self.base_url}{self.build_path(resource)}"

    def build_signature(self, *, method: str, path: str, audit_context: AuditContext, body: Any | None = None) -> str:
        canonical_body = "" if body is None else json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload = "\n".join(
            [
                method.upper(),
                path,
                audit_context.tenant_id,
                audit_context.actor_type,
                audit_context.actor_id,
                audit_context.trace_id,
                audit_context.idempotency_key or "",
                canonical_body,
            ]
        )
        return hmac.new(self.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def build_headers(self, *, method: str, path: str, audit_context: AuditContext, body: Any | None = None) -> dict[str, str]:
        context = audit_context.to_filter()
        required = ["tenant_id", "actor_type", "actor_id", "scope", "purpose", "trace_id"]
        missing = [field for field in required if not context.get(field)]
        if missing:
            raise ValueError(f"missing audit context fields: {','.join(missing)}")
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-PMS-Source-System": "pms",
            "X-PMS-Tenant-ID": audit_context.tenant_id,
            "X-PMS-Actor-Type": audit_context.actor_type,
            "X-PMS-Actor-ID": audit_context.actor_id,
            "X-PMS-Scope": audit_context.scope,
            "X-PMS-Purpose": audit_context.purpose,
            "X-Trace-ID": audit_context.trace_id,
            "X-PMS-Signature": self.build_signature(method=method, path=path, audit_context=audit_context, body=body),
        }
        if audit_context.idempotency_key:
            headers["X-Idempotency-Key"] = audit_context.idempotency_key
        optional_header_fields = {
            "org_id": "X-PMS-Org-ID",
            "department_id": "X-PMS-Department-ID",
            "store_id": "X-PMS-Store-ID",
            "marketplace": "X-PMS-Marketplace",
            "channel": "X-PMS-Channel",
            "warehouse_id": "X-PMS-Warehouse-ID",
            "supplier_id": "X-PMS-Supplier-ID",
            "category_id": "X-PMS-Category-ID",
            "data_level": "X-PMS-Data-Level",
        }
        for field, header in optional_header_fields.items():
            value = getattr(audit_context, field)
            if value is not None:
                headers[header] = str(value)
        return headers

    def record_audit(self, *, method: str, path: str, audit_context: AuditContext, result: str, attempt: int, status_code: int | None = None, error_code: str | None = None) -> None:
        self.audit_log.append(
            {
                "method": method.upper(),
                "path": path,
                "tenant_id": audit_context.tenant_id,
                "actor_type": audit_context.actor_type,
                "actor_id": audit_context.actor_id,
                "trace_id": audit_context.trace_id,
                "idempotency_key": audit_context.idempotency_key,
                "result": result,
                "attempt": attempt,
                "status_code": status_code,
                "error_code": error_code,
                "context": asdict(audit_context),
            }
        )

    async def request(self, method: str, resource: str, *, audit_context: AuditContext, json_body: Any | None = None) -> dict[str, Any]:
        path = self.build_path(resource)
        url = f"{self.base_url}{path}"
        headers = self.build_headers(method=method, path=path, audit_context=audit_context, body=json_body)
        timeout = httpx.Timeout(connect=self.connect_timeout_seconds, read=self.read_timeout_seconds, write=self.read_timeout_seconds, pool=self.connect_timeout_seconds)
        last_error: ERPClientError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(method.upper(), url, headers=headers, json=json_body)
                    response.raise_for_status()
                self.record_audit(method=method, path=path, audit_context=audit_context, result="success", attempt=attempt, status_code=response.status_code)
                if not response.content:
                    return {}
                payload = response.json()
                return payload if isinstance(payload, dict) else {"data": payload}
            except httpx.TimeoutException as exc:
                last_error = ERPClientError(str(exc), error_code="timeout", retryable=True)
                self.record_audit(method=method, path=path, audit_context=audit_context, result="retry" if attempt < self.max_retries else "failed", attempt=attempt, error_code=last_error.error_code)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status >= 500
                last_error = ERPClientError(str(exc), error_code="upstream_5xx" if retryable else "upstream_4xx", retryable=retryable)
                self.record_audit(method=method, path=path, audit_context=audit_context, result="retry" if retryable and attempt < self.max_retries else "failed", attempt=attempt, status_code=status, error_code=last_error.error_code)
                if not retryable:
                    raise last_error
            except Exception as exc:
                last_error = ERPClientError(str(exc), error_code="transport_error", retryable=True)
                self.record_audit(method=method, path=path, audit_context=audit_context, result="retry" if attempt < self.max_retries else "failed", attempt=attempt, error_code=last_error.error_code)
        if last_error is not None:
            raise last_error
        raise ERPClientError("ERP request failed", error_code="unknown", retryable=True)
