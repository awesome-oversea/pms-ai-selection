from __future__ import annotations

from typing import Any, NoReturn
from uuid import uuid4

import httpx

from src.core.pms_governance import AuditContext
from src.infrastructure.erp_client import BaseERPClient, ERPClientError
from src.infrastructure.object_store import is_local_artifact_endpoint, read_json_artifact, write_json_artifact


class ADSClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class ADSClient:
    _DOMAIN = "ads"

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
        trace_id = f"ads-{uuid4()}"
        return AuditContext(
            tenant_id="system",
            actor_type="service",
            actor_id="pms-ads-client",
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
        enriched.setdefault("source_system", audit_context.source_system)
        if audit_context.idempotency_key:
            enriched.setdefault("idempotency_key", audit_context.idempotency_key)
        return enriched

    @staticmethod
    def _raise_client_error(error: ERPClientError) -> NoReturn:
        raise ADSClientError(
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
                audit_context=self._resolve_audit_context(audit_context, purpose="ads_health_check"),
            )
            return {"status": "ok", "error_code": None, "retryable": False}
        except FileNotFoundError as e:
            raise ADSClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise ADSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise ADSClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise ADSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise ADSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise ADSClientError(str(e), error_code="transport_error", retryable=True)

    async def submit_ad_optimization_suggestion(
        self,
        payload: dict[str, Any],
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            enriched = dict(payload)
            enriched["owner_domain"] = "ads"
            enriched["write_object"] = "recommendation"
            if enriched.get("status") in {None, "created"}:
                enriched["status"] = "submitted"
            audit = self._resolve_audit_context(
                audit_context,
                purpose="submit_ad_optimization_suggestion",
                idempotency_key=(
                    str(enriched.get("idempotency_key"))
                    if enriched.get("idempotency_key") is not None
                    else f"ads-submit-{enriched.get('suggestion_id') or enriched.get('campaign_id') or uuid4()}"
                ),
            )
            enriched = self._attach_audit_context(enriched, audit)
            if is_local_artifact_endpoint(self.api_endpoint):
                write_json_artifact(self.api_endpoint, self.outbound_path, enriched)
                return {
                    "suggestion_id": enriched.get("suggestion_id") or f"ADS-{uuid4()}",
                    "status": enriched["status"],
                    "owner_domain": "ads",
                    "write_object": "recommendation",
                }
            body = await self._transport().request(
                "POST",
                self._normalize_resource_path(self.outbound_path),
                audit_context=audit,
                json_body=enriched,
            )
            if isinstance(body, dict):
                body.setdefault("owner_domain", "ads")
                body.setdefault("write_object", "recommendation")
                return body
            return {"status": "submitted", "owner_domain": "ads", "write_object": "recommendation"}
        except FileNotFoundError as e:
            raise ADSClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise ADSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in {401, 403}:
                raise ADSClientError(str(e), error_code="auth_failed", retryable=False)
            if status >= 500:
                raise ADSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise ADSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise ADSClientError(str(e), error_code="transport_error", retryable=True)

    async def get_campaign_metrics(
        self,
        campaign_id: str,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            audit = self._resolve_audit_context(audit_context, purpose="get_campaign_metrics")
            if is_local_artifact_endpoint(self.api_endpoint):
                data = read_json_artifact(self.api_endpoint, self.inbound_path)
                return data if isinstance(data, dict) else {"campaign_id": campaign_id, "metrics": data}
            body = await self._transport().request(
                "GET",
                self._normalize_resource_path(f"campaigns/{campaign_id}/metrics"),
                audit_context=audit,
            )
            return body if isinstance(body, dict) else {"campaign_id": campaign_id, "metrics": body}
        except FileNotFoundError as e:
            raise ADSClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise ADSClientError(str(e), error_code="timeout", retryable=True)
        except Exception as e:
            raise ADSClientError(str(e), error_code="transport_error", retryable=True)

    async def query_suggestion_status(
        self,
        suggestion_id: str,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            audit = self._resolve_audit_context(
                audit_context,
                purpose="query_suggestion_status",
                idempotency_key=f"ads-status-{suggestion_id}",
            )
            if is_local_artifact_endpoint(self.api_endpoint):
                artifact = read_json_artifact(self.api_endpoint, self.inbound_path)
                items = artifact if isinstance(artifact, list) else [artifact] if isinstance(artifact, dict) else []
                for item in items:
                    if isinstance(item, dict) and (item.get("suggestion_id") == suggestion_id or item.get("campaign_id") == suggestion_id):
                        return {
                            "suggestion_id": suggestion_id,
                            "domain": "ads",
                            "status": item.get("status", "unknown"),
                            "detail": item.get("detail"),
                            "updated_at": item.get("updated_at"),
                            "campaign_id": item.get("campaign_id"),
                        }
                return {"suggestion_id": suggestion_id, "domain": "ads", "status": "not_found"}
            body = await self._transport().request(
                "GET",
                f"suggestions/{suggestion_id}/status",
                audit_context=audit,
            )
            if isinstance(body, dict):
                body.setdefault("domain", "ads")
                body.setdefault("suggestion_id", suggestion_id)
                return body
            return {"suggestion_id": suggestion_id, "domain": "ads", "status": "unknown"}
        except FileNotFoundError:
            return {"suggestion_id": suggestion_id, "domain": "ads", "status": "not_found"}
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise ADSClientError(str(e), error_code="timeout", retryable=True)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                return {"suggestion_id": suggestion_id, "domain": "ads", "status": "not_found"}
            if status >= 500:
                raise ADSClientError(str(e), error_code="upstream_5xx", retryable=True)
            raise ADSClientError(str(e), error_code="upstream_4xx", retryable=False)
        except Exception as e:
            raise ADSClientError(str(e), error_code="transport_error", retryable=True)

    async def get_ad_performance(
        self,
        product_id: str | None = None,
        marketplace: str | None = None,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        try:
            audit = self._resolve_audit_context(audit_context, purpose="get_ad_performance")
            resource = "ad-performance"
            params: dict[str, str] = {}
            if product_id:
                params["product_id"] = product_id
            if marketplace:
                params["marketplace"] = marketplace
            if is_local_artifact_endpoint(self.api_endpoint):
                data = read_json_artifact(self.api_endpoint, self.inbound_path)
                return data if isinstance(data, dict) else {"performance": data}
            body = await self._transport().request(
                "GET",
                self._normalize_resource_path(resource),
                audit_context=audit,
                query_params=params,
            )
            return body if isinstance(body, dict) else {"performance": body}
        except FileNotFoundError as e:
            raise ADSClientError(str(e), error_code="artifact_missing", retryable=False)
        except ERPClientError as e:
            self._raise_client_error(e)
        except httpx.TimeoutException as e:
            raise ADSClientError(str(e), error_code="timeout", retryable=True)
        except Exception as e:
            raise ADSClientError(str(e), error_code="transport_error", retryable=True)
