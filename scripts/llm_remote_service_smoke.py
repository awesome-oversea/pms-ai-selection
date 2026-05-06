from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

from fastapi.testclient import TestClient

from src.config.settings import get_settings
from src.core.auth import create_access_token
from src.main import create_app
from src.services import service_gateway as service_gateway_module


class _DummySession:
    async def close(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakePromptPolicyService:
    def __init__(self, session: Any, tenant_id: str | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def resolve_route_policy(self, prompt: str) -> dict[str, Any]:
        return {
            "version": 1,
            "gray_hit": False,
            "model_registry_version": 1,
            "active_model_version": "local-last-mile",
            "force_tier": None,
            "use_mock": True,
            "api_model_name": None,
        }


class _FakeTenantQuotaRepository:
    def __init__(self, session: Any) -> None:
        self.session = session

    async def check_quota(
        self,
        *,
        tenant_id: str | None,
        quota_type: str,
        amount: float,
        default_limit: float,
    ) -> tuple[bool, None, float]:
        return True, None, default_limit


async def _noop_init_db() -> None:
    return None


async def _healthy_dependency() -> dict[str, str]:
    return {"status": "healthy"}


async def _noop_close() -> None:
    return None


def _noop_client() -> object:
    return object()


class _StableRouteResult:
    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_node": "mock-node",
            "model_name": "mock-model",
            "tier": "light",
            "response": "local fallback ok",
            "tokens_used": 9,
            "latency_ms": 1.0,
            "cost_usd": 0.0001,
            "degraded": False,
            "provider_mode": "mock",
            "primary_provider": "vllm",
            "actual_provider": "ollama",
            "fallback_provider": "ollama",
        }


class _StableLLMGateway:
    def __init__(self, config: Any) -> None:
        self.config = config

    async def route(self, prompt: str, force_tier: Any = None) -> _StableRouteResult:
        return _StableRouteResult()

    def get_cluster_status(self) -> dict[str, Any]:
        return {
            "cluster_status": "healthy",
            "nodes": [{"name": "mock-node", "status": "healthy"}],
        }


def _healthy_sync_status(self) -> dict[str, str]:
    return {"status": "healthy"}


async def _healthy_async_status(self) -> dict[str, str]:
    return {"status": "healthy"}


class _RemoteLLMState:
    def __init__(self) -> None:
        self.mode = "success"
        self.requests: list[dict[str, Any]] = []


class _RemoteLLMHandler(BaseHTTPRequestHandler):
    state: _RemoteLLMState | None = None

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed_path = self.path.split("?", 1)[0]
        if parsed_path == "/api/v1/health":
            self._send_json(200, {"status": "healthy", "service": "mock-remote-llm"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed_path = self.path.split("?", 1)[0]
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        payload = json.loads(raw_body.decode("utf-8") or "{}")
        state = self.state or _RemoteLLMState()
        state.requests.append(
            {
                "path": parsed_path,
                "authorization": self.headers.get("Authorization"),
                "trace_id": self.headers.get("X-Trace-ID"),
                "request_id": self.headers.get("X-Request-ID"),
                "payload": payload,
            }
        )

        if parsed_path != "/api/v1/llm/route":
            self._send_json(404, {"error": "not_found"})
            return

        if state.mode == "error":
            self._send_json(503, {"error": "remote_llm_unavailable"})
            return

        self._send_json(
            200,
            {
                "data": {
                    "selected_node": "remote-llm",
                    "model_name": "remote-model",
                    "tier": "light",
                    "response": "remote service ok",
                    "tokens_used": 13,
                    "latency_ms": 5.0,
                    "cost_usd": 0.0002,
                    "degraded": False,
                    "provider_mode": "remote-service",
                    "primary_provider": "remote",
                    "actual_provider": "remote",
                    "fallback_provider": "mock",
                    "prompt_key": None,
                    "prompt_version": None,
                    "policy_version": 0,
                    "gray_hit": False,
                }
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        return None


@contextlib.contextmanager
def _remote_llm_server() -> Any:
    state = _RemoteLLMState()
    handler = type("BoundRemoteLLMHandler", (_RemoteLLMHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextlib.contextmanager
def _temporary_service_mode(base_url: str) -> Any:
    original_values = {
        "SERVICE_MODE_LLM_MODE": os.environ.get("SERVICE_MODE_LLM_MODE"),
        "SERVICE_MODE_LLM_BASE_URL": os.environ.get("SERVICE_MODE_LLM_BASE_URL"),
        "SERVICE_MODE_ENABLE_FALLBACK": os.environ.get("SERVICE_MODE_ENABLE_FALLBACK"),
        "SERVICE_MODE_LLM_TIMEOUT_SECONDS": os.environ.get("SERVICE_MODE_LLM_TIMEOUT_SECONDS"),
    }
    os.environ["SERVICE_MODE_LLM_MODE"] = "remote-service"
    os.environ["SERVICE_MODE_LLM_BASE_URL"] = base_url
    os.environ["SERVICE_MODE_ENABLE_FALLBACK"] = "true"
    os.environ["SERVICE_MODE_LLM_TIMEOUT_SECONDS"] = "3"
    get_settings.cache_clear()
    service_gateway_module._service_gateway_singleton = None
    try:
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        service_gateway_module._service_gateway_singleton = None


def _auth_headers() -> dict[str, str]:
    token = create_access_token(
        {
            "sub": "smoke-user",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "tenant_id": "tenant-smoke",
            "is_superuser": True,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def run_smoke() -> dict[str, Any]:
    headers = _auth_headers()
    with _remote_llm_server() as (server, state):
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        with _temporary_service_mode(base_url):
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch("src.infrastructure.database.get_engine", new=_noop_client))
                stack.enter_context(patch("src.infrastructure.database.init_db", new=_noop_init_db))
                stack.enter_context(patch("src.infrastructure.database.check_db_health", new=_healthy_dependency))
                stack.enter_context(patch("src.infrastructure.database.close_db", new=_noop_close))
                stack.enter_context(patch("src.infrastructure.redis.get_redis_connection", new=_noop_client))
                stack.enter_context(patch("src.infrastructure.redis.check_redis_health", new=_healthy_dependency))
                stack.enter_context(patch("src.infrastructure.redis.close_redis", new=_noop_close))
                stack.enter_context(patch("src.infrastructure.qdrant.get_qdrant_client", new=_noop_client))
                stack.enter_context(patch("src.infrastructure.qdrant.check_qdrant_health", new=_healthy_dependency))
                stack.enter_context(patch("src.infrastructure.qdrant.close_qdrant", new=_noop_close))
                stack.enter_context(
                    patch(
                        "src.api.v1.endpoints.llm.get_async_session_factory",
                        new=lambda: (lambda: _DummySession()),
                    )
                )
                stack.enter_context(patch("src.api.v1.endpoints.llm.PromptPolicyService", new=_FakePromptPolicyService))
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.TenantQuotaRepository", new=_FakeTenantQuotaRepository)
                )
                stack.enter_context(patch("src.api.v1.endpoints.llm.LLMGateway", new=_StableLLMGateway))
                stack.enter_context(patch("src.api.v1.endpoints.llm.VLLMStatusService.build_status", new=_healthy_sync_status))
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.GPUResourcePoolService.build_status", new=_healthy_sync_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.CudaTensorRTStatusService.build_status", new=_healthy_sync_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.TritonStatusService.build_status", new=_healthy_sync_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.OllamaStatusService.build_status", new=_healthy_async_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.MultimodalInferenceService.build_status", new=_healthy_sync_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.CPUModelStatusService.build_status", new=_healthy_sync_status)
                )
                stack.enter_context(
                    patch("src.api.v1.endpoints.llm.InferenceHealthService.build_status", new=_healthy_async_status)
                )

                app = create_app()
                with TestClient(app, raise_server_exceptions=False) as client:
                    status_resp = client.get("/api/v1/llm/status", headers=headers)
                    success_resp = client.post(
                        "/api/v1/llm/route",
                        headers=headers,
                        json={"prompt": "remote success validation", "use_mock": True},
                    )

                    state.mode = "error"
                    fallback_resp = client.post(
                        "/api/v1/llm/route",
                        headers=headers,
                        json={"prompt": "remote failure fallback validation", "use_mock": True},
                    )

    status_payload = status_resp.json() if status_resp.headers.get("content-type", "").startswith("application/json") else {}
    success_payload = success_resp.json() if success_resp.headers.get("content-type", "").startswith("application/json") else {}
    fallback_payload = fallback_resp.json() if fallback_resp.headers.get("content-type", "").startswith("application/json") else {}

    return {
        "remote_service_base_url": base_url,
        "service_mode_status": {
            "http_status": status_resp.status_code,
            "mode": ((status_payload.get("service_mode") or {}).get("mode")),
            "route_endpoint": ((status_payload.get("service_mode") or {}).get("route_endpoint")),
            "fallback_enabled": status_payload.get("fallback_enabled"),
        },
        "remote_success": {
            "http_status": success_resp.status_code,
            "provider_mode": success_payload.get("provider_mode"),
            "actual_provider": success_payload.get("actual_provider"),
            "response": success_payload.get("response"),
        },
        "remote_failure_fallback": {
            "http_status": fallback_resp.status_code,
            "provider_mode": fallback_payload.get("provider_mode"),
            "actual_provider": fallback_payload.get("actual_provider"),
            "response": fallback_payload.get("response"),
        },
        "remote_requests": state.requests,
        "last_mile_validation": {
            "real_http_remote_success": success_resp.status_code == 200 and success_payload.get("provider_mode") == "remote-service",
            "remote_failure_fallback_to_in_process": fallback_resp.status_code == 200 and fallback_payload.get("provider_mode") == "mock",
            "authorization_forwarded": any(bool(item.get("authorization")) for item in state.requests),
        },
    }


def main() -> int:
    payload = run_smoke()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(payload["last_mile_validation"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
