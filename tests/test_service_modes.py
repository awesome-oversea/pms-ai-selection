from __future__ import annotations

import contextlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import pytest
from fastapi.testclient import TestClient
from src.config.settings import get_settings
from src.core.auth import create_access_token
from src.main import create_app
from src.services import service_gateway as service_gateway_module


@pytest.fixture
def client(monkeypatch):
    get_settings.cache_clear()
    service_gateway_module._service_gateway_singleton = None

    monkeypatch.setattr("src.infrastructure.database.get_engine", _noop_client)
    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_dependency)
    monkeypatch.setattr("src.infrastructure.database.close_db", _noop_close)
    monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", _noop_client)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_dependency)
    monkeypatch.setattr("src.infrastructure.redis.close_redis", _noop_close)
    monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", _noop_client)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_dependency)
    monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", _noop_close)
    monkeypatch.setattr(
        "src.api.v1.endpoints.llm.get_async_session_factory",
        lambda: (lambda: _DummySession()),
    )
    monkeypatch.setattr("src.api.v1.endpoints.llm.PromptPolicyService", _FakePromptPolicyService)
    monkeypatch.setattr("src.api.v1.endpoints.llm.TenantQuotaRepository", _FakeTenantQuotaRepository)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    get_settings.cache_clear()
    service_gateway_module._service_gateway_singleton = None


@pytest.fixture
def auth_headers():
    token = create_access_token(
        {
            "sub": "testuser",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "is_superuser": True,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


class _FakeRemoteRAGGateway:
    last_kwargs = None

    def __init__(self, mode: str = "success"):
        self.mode = mode

    async def route_rag_query(self, **kwargs):
        _FakeRemoteRAGGateway.last_kwargs = kwargs
        if self.mode == "fallback":
            return await kwargs["fallback"]()
        return {
            "query": kwargs["query"],
            "results": [{"content": "remote result", "score": 1.0}],
            "total_found": 1,
            "processing_time_ms": 1.0,
        }


class _FakeRemoteLLMGateway:
    last_kwargs = None

    def __init__(self, mode: str = "success"):
        self.mode = mode

    async def route_llm_request(self, **kwargs):
        _FakeRemoteLLMGateway.last_kwargs = kwargs
        if self.mode == "fallback":
            return await kwargs["fallback"]()
        return {
            "selected_node": "remote-llm",
            "model_name": "remote-model",
            "tier": "light",
            "response": "remote ok",
            "tokens_used": 11,
            "latency_ms": 2.0,
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


def _stable_llm_route(monkeypatch, tier="light"):
    class _StableResult:
        def to_dict(self):
            return {
                "selected_node": "mock-node",
                "model_name": "mock-model",
                "tier": tier,
                "response": "ok",
                "tokens_used": 12,
                "latency_ms": 1.0,
                "cost_usd": 0.0001,
                "degraded": False,
                "provider_mode": "mock",
                "primary_provider": "vllm",
                "actual_provider": "ollama",
                "fallback_provider": "ollama",
            }

    async def _stable_route(self, prompt, force_tier=None):
        return _StableResult()

    monkeypatch.setattr("src.api.v1.endpoints.llm.LLMGateway.route", _stable_route)


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


class _StableLocalGateway:
    def __init__(self, config: Any) -> None:
        self.config = config

    async def route(self, prompt: str, force_tier: Any = None):
        class _StableResult:
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

        return _StableResult()

    def get_cluster_status(self) -> dict[str, Any]:
        return {"cluster_status": "healthy", "nodes": [{"name": "mock-node", "status": "healthy"}]}


class _RemoteHTTPState:
    def __init__(self) -> None:
        self.mode = "success"
        self.requests: list[dict[str, Any]] = []


class _RemoteHTTPHandler(BaseHTTPRequestHandler):
    state: _RemoteHTTPState | None = None

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed_path = self.path.split("?", 1)[0]
        if parsed_path == "/api/v1/health":
            self._send_json(200, {"status": "healthy"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed_path = self.path.split("?", 1)[0]
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        payload = json.loads(raw_body.decode("utf-8") or "{}")
        state = self.state or _RemoteHTTPState()
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


async def _noop_init_db() -> None:
    return None


async def _healthy_dependency() -> dict[str, str]:
    return {"status": "healthy"}


async def _noop_close() -> None:
    return None


def _noop_client() -> object:
    return object()


def _healthy_sync_status(self) -> dict[str, str]:
    return {"status": "healthy"}


async def _healthy_async_status(self) -> dict[str, str]:
    return {"status": "healthy"}


@contextlib.contextmanager
def _remote_llm_http_server():
    state = _RemoteHTTPState()
    handler = type("BoundRemoteHTTPHandler", (_RemoteHTTPHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def remote_llm_http_client(monkeypatch):
    with _remote_llm_http_server() as (server, state):
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        monkeypatch.setenv("SERVICE_MODE_LLM_MODE", "remote-service")
        monkeypatch.setenv("SERVICE_MODE_LLM_BASE_URL", base_url)
        monkeypatch.setenv("SERVICE_MODE_ENABLE_FALLBACK", "true")
        monkeypatch.setenv("SERVICE_MODE_LLM_TIMEOUT_SECONDS", "3")
        get_settings.cache_clear()
        service_gateway_module._service_gateway_singleton = None

        monkeypatch.setattr("src.infrastructure.database.get_engine", _noop_client)
        monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
        monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_dependency)
        monkeypatch.setattr("src.infrastructure.database.close_db", _noop_close)
        monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", _noop_client)
        monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_dependency)
        monkeypatch.setattr("src.infrastructure.redis.close_redis", _noop_close)
        monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", _noop_client)
        monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_dependency)
        monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", _noop_close)
        monkeypatch.setattr(
            "src.api.v1.endpoints.llm.get_async_session_factory",
            lambda: (lambda: _DummySession()),
        )
        monkeypatch.setattr("src.api.v1.endpoints.llm.PromptPolicyService", _FakePromptPolicyService)
        monkeypatch.setattr("src.api.v1.endpoints.llm.TenantQuotaRepository", _FakeTenantQuotaRepository)
        monkeypatch.setattr("src.api.v1.endpoints.llm.LLMGateway", _StableLocalGateway)
        monkeypatch.setattr("src.api.v1.endpoints.llm.VLLMStatusService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.GPUResourcePoolService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.CudaTensorRTStatusService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.TritonStatusService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.OllamaStatusService.build_status", _healthy_async_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.MultimodalInferenceService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.CPUModelStatusService.build_status", _healthy_sync_status)
        monkeypatch.setattr("src.api.v1.endpoints.llm.InferenceHealthService.build_status", _healthy_async_status)

        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, state, base_url

        get_settings.cache_clear()
        service_gateway_module._service_gateway_singleton = None


def test_knowledge_service_mode_returns_config(client, auth_headers):
    resp = client.get("/api/v1/knowledge/service-mode", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] in {"in-process", "remote-service"}
    assert "gateway" in data
    assert "fallback_enabled" in data
    assert data["gateway"]["status_endpoint"].endswith("/status")


def test_llm_status_returns_service_mode(client, auth_headers):
    resp = client.get("/api/v1/llm/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_mode"]["mode"] in {"in-process", "remote-service"}
    assert "fallback_enabled" in data


def test_remote_rag_query_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr("src.api.v1.endpoints.knowledge.get_service_gateway", lambda: _FakeRemoteRAGGateway("success"))
    resp = client.post("/api/v1/knowledge/query", headers=auth_headers, json={"query": "蓝牙耳机", "top_k": 3, "threshold": 0.1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] == 1
    assert data["results"][0]["content"] == "remote result"
    assert _FakeRemoteRAGGateway.last_kwargs["token"] == auth_headers["Authorization"]


def test_remote_rag_query_fallback_to_local(client, auth_headers, monkeypatch, tmp_path):
    async def _no_db_session():
        return None

    monkeypatch.setattr("src.api.v1.endpoints.knowledge.get_service_gateway", lambda: _FakeRemoteRAGGateway("fallback"))
    monkeypatch.setattr("src.api.v1.endpoints.knowledge._get_db_session", _no_db_session)
    monkeypatch.setattr("src.services.local_knowledge_service._DB_PATH", tmp_path / "remote_fallback_knowledge.db")

    upload_resp = client.post(
        "/api/v1/knowledge/documents",
        headers=auth_headers,
        files={"file": ("demo.txt", "蓝牙耳机适合跨境电商".encode(), "text/plain")},
    )
    assert upload_resp.status_code == 200

    query_resp = client.post("/api/v1/knowledge/query", json={"query": "蓝牙耳机", "top_k": 3, "threshold": 0.1})
    assert query_resp.status_code == 200
    data = query_resp.json()
    assert data["total_found"] >= 1


def test_remote_llm_route_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr("src.api.v1.endpoints.llm.get_service_gateway", lambda: _FakeRemoteLLMGateway("success"))
    resp = client.post(
        "/api/v1/llm/route",
        headers=auth_headers,
        json={"prompt": "远程LLM测试", "use_mock": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_mode"] == "remote-service"
    assert data["response"] == "remote ok"
    assert _FakeRemoteLLMGateway.last_kwargs["token"].startswith("Bearer ")


def test_remote_llm_route_fallback_to_in_process(client, auth_headers, monkeypatch):
    _stable_llm_route(monkeypatch, tier="light")
    monkeypatch.setattr("src.api.v1.endpoints.llm.get_service_gateway", lambda: _FakeRemoteLLMGateway("fallback"))
    resp = client.post(
        "/api/v1/llm/route",
        headers=auth_headers,
        json={"prompt": "LLM fallback 测试", "use_mock": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_mode"] == "mock"


def test_remote_llm_status_exposes_route_endpoint(remote_llm_http_client, auth_headers):
    client, _state, base_url = remote_llm_http_client
    resp = client.get("/api/v1/llm/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_mode"]["mode"] == "remote-service"
    assert data["service_mode"]["route_endpoint"] == f"{base_url}/llm/route"
    assert data["fallback_enabled"] is True


def test_remote_llm_route_real_http_success(remote_llm_http_client, auth_headers):
    client, state, _base_url = remote_llm_http_client
    resp = client.post(
        "/api/v1/llm/route",
        headers=auth_headers,
        json={"prompt": "remote success validation", "use_mock": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_mode"] == "remote-service"
    assert data["actual_provider"] == "remote"
    assert data["response"] == "remote service ok"
    assert state.requests[0]["authorization"] == auth_headers["Authorization"]


def test_remote_llm_route_real_http_fallback_to_in_process(remote_llm_http_client, auth_headers):
    client, state, _base_url = remote_llm_http_client
    state.mode = "error"
    resp = client.post(
        "/api/v1/llm/route",
        headers=auth_headers,
        json={"prompt": "remote failure fallback validation", "use_mock": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_mode"] == "mock"
    assert data["actual_provider"] == "ollama"
    assert data["response"] == "local fallback ok"
    assert state.requests[0]["authorization"] == auth_headers["Authorization"]
