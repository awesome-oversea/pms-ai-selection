from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from src.core.pms_governance import AuditContext
from src.infrastructure.erp_client import BaseERPClient, ERPClientError
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class SOMClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class SOMClient:
    _DOMAIN = "som"
    _DRAFT_STATUSES = {None, "draft", "draft_created", "pending_approval"}
    _FORBIDDEN_FORMAL_FIELDS = {"listing_id", "published_at", "go_live_at", "is_live", "asin_binding_status"}

    def __init__(
        self,
        *,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None = None,
        inbound_path: str,
        outbound_path: str,
        timeout_seconds: float,
    ) -> None:
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key or api_key or ""
        self.inbound_path = inbound_path
        self.outbound_path = outbound_path
        self.timeout_seconds = timeout_seconds

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    @classmethod
    def _normalize_resource_path(cls, path: str) -> str:
        normalized = f"/{str(path or '').lstrip('/')}"
        internal_prefix = f"/api/internal/v1/{cls._DOMAIN}/"
        if normalized.startswith(internal_prefix):
            return normalized[len(internal_prefix) :]
        return normalized.strip("/")

    def _transport(self) -> BaseERPClient:
        return BaseERPClient(
            base_url=self.api_endpoint,
            domain=self._DOMAIN,
            api_key=self.api_key or "",
            secret_key=self.secret_key,
            connect_timeout_seconds=min(self.timeout_seconds, 5.0),
            read_timeout_seconds=max(self.timeout_seconds, 5.0),
        )

    @staticmethod
    def _default_audit_context(*, purpose: str, idempotency_key: str | None = None) -> AuditContext:
        trace_id = f"som-{uuid4()}"
        return AuditContext(
            tenant_id="system",
            actor_type="service",
            actor_id="pms-som-client",
            scope="tenant",
            purpose=purpose,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    def _resolve_audit_context(
        self,
        audit_context: AuditContext | None,
        *,
        purpose: str,
        idempotency_key: str | None = None,
    ) -> AuditContext:
        return audit_context or self._default_audit_context(
            purpose=purpose,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _attach_audit_context(payload: dict[str, Any], audit_context: AuditContext) -> dict[str, Any]:
        enriched = dict(payload)
        enriched["audit_context"] = audit_context.to_filter()
        enriched.setdefault("tenant_id", audit_context.tenant_id)
        enriched.setdefault("actor_id", audit_context.actor_id)
        enriched.setdefault("actor_type", audit_context.actor_type)
        enriched.setdefault("scope", audit_context.scope)
        enriched.setdefault("purpose", audit_context.purpose)
        enriched.setdefault("trace_id", audit_context.trace_id)
        if audit_context.idempotency_key:
            enriched.setdefault("idempotency_key", audit_context.idempotency_key)
        return enriched

    @staticmethod
    def _raise_client_error(error: ERPClientError) -> None:
        raise SOMClientError(
            str(error),
            error_code=error.error_code,
            retryable=error.retryable,
        ) from error

    async def test_connection(self, audit_context: AuditContext | None = None) -> dict[str, Any]:
        try:
            if is_local_artifact_endpoint(self.api_endpoint):
                read_json_artifact(self.api_endpoint, self.inbound_path)
                return {"status": "ok", "error_code": None, "retryable": False}
            await self._transport().request(
                "GET",
                self._normalize_resource_path(self.inbound_path),
                audit_context=self._resolve_audit_context(
                    audit_context,
                    purpose="som_health_check",
                ),
            )
            return {"status": "ok", "error_code": None, "retryable": False}
        except FileNotFoundError as e:
            raise SOMClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise SOMClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise SOMClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise SOMClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise SOMClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise SOMClientError(str(e), error_code="transport_error", retryable=True)

    def _enrich_listing_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(payload)
        forbidden = sorted(field for field in self._FORBIDDEN_FORMAL_FIELDS if enriched.get(field) not in {None, ""})
        if forbidden:
            raise SOMClientError(f"formal listing fields are forbidden: {','.join(forbidden)}", error_code="write_boundary_violation", retryable=False)
        if enriched.get("write_object") not in {None, "draft"}:
            raise SOMClientError("SOM client only supports listing draft writes", error_code="write_boundary_violation", retryable=False)
        if enriched.get("status") not in self._DRAFT_STATUSES:
            raise SOMClientError("SOM client only supports draft or pending approval status", error_code="write_boundary_violation", retryable=False)
        enriched["owner_domain"] = "som"
        enriched["write_object"] = "draft"
        enriched["status"] = "pending_approval"
        return enriched

    async def create_listing_draft(
        self,
        payload: dict[str, Any],
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            enriched = self._enrich_listing_draft(payload)
            audit = self._resolve_audit_context(
                audit_context,
                purpose="submit_listing_draft",
                idempotency_key=(
                    str(enriched.get("idempotency_key"))
                    if enriched.get("idempotency_key") is not None
                    else f"som-submit-{enriched.get('listing_draft_id') or enriched.get('task_id') or uuid4()}"
                ),
            )
            enriched = self._attach_audit_context(enriched, audit)
            if is_local_artifact_endpoint(self.api_endpoint):
                write_json_artifact(self.api_endpoint, self.outbound_path, enriched)
                return {
                    "listing_draft_id": enriched.get("listing_draft_id") or f"LST-{enriched.get('task_id', 'LOCAL')}",
                    "status": enriched["status"],
                    "owner_domain": "som",
                    "write_object": "draft",
                }
            body = await self._transport().request(
                "POST",
                self._normalize_resource_path(self.outbound_path),
                audit_context=audit,
                json_body=enriched,
            )
            if isinstance(body, dict):
                body.setdefault("owner_domain", "som")
                body.setdefault("write_object", "draft")
                body["status"] = "pending_approval" if body.get("status") in self._DRAFT_STATUSES else body.get("status")
                return body
            return {"status": "pending_approval", "owner_domain": "som", "write_object": "draft"}
        except SOMClientError:
            raise
        except FileNotFoundError as e:
            raise SOMClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise SOMClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise SOMClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise SOMClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise SOMClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise SOMClientError(str(e), error_code="transport_error", retryable=True)
