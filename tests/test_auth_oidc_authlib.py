from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt
from src.core.oidc import clear_oidc_provider_cache
from starlette.requests import Request


def _build_request(session: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/v1/auth/oidc",
        "raw_path": b"/api/v1/auth/oidc",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 8000),
        "server": ("testserver", 80),
        "scheme": "http",
        "session": session or {},
    }
    return Request(scope)


def _load_auth_module():
    auth_path = Path(__file__).resolve().parents[1] / "src" / "api" / "v1" / "endpoints" / "auth.py"
    module_name = f"_test_auth_module_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, auth_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load auth module from {auth_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _build_provider_signing_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-kid-001",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return private_pem, {"keys": [jwk]}


def test_oidc_authorize_url_uses_authlib_and_persists_state(monkeypatch):
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://sso.example.com")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-web")
    monkeypatch.setenv("SEC_OIDC_SCOPE", "openid profile email")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    clear_oidc_provider_cache()
    auth_module = _load_auth_module()

    class _Client:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def create_authorization_url(self, url, state=None, **kwargs):
            assert url == "https://sso.example.com/authorize"
            assert self.kwargs["client_id"] == "pms-web"
            return (f"{url}?client_id=pms-web&state={state}", state)

        async def aclose(self):
            return None

    monkeypatch.setattr(auth_module, "AsyncOAuth2Client", _Client)

    request = _build_request()
    payload = asyncio.run(
        auth_module.get_oidc_authorize_url(
            request=request,
            redirect_uri="https://app.example.com/callback",
            state="state-001",
            actor={},
        )
    )

    assert payload.authorize_url == "https://sso.example.com/authorize?client_id=pms-web&state=state-001"
    assert payload.scope == "openid profile email"
    assert request.session["oidc_state"] == "state-001"
    assert request.session["oidc_redirect_uri"] == "https://app.example.com/callback"

    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEC_OIDC_SCOPE", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()


def test_oidc_callback_uses_authlib_exchange_and_clears_state(monkeypatch):
    monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://sso.example.com")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-client")
    monkeypatch.setenv("SEC_OIDC_CLIENT_SECRET", "pms-secret")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    clear_oidc_provider_cache()
    auth_module = _load_auth_module()

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def fetch_token(self, url=None, grant_type=None, code=None, redirect_uri=None, **kwargs):
            assert url == "https://sso.example.com/token"
            assert grant_type == "authorization_code"
            assert code == "code-001"
            assert redirect_uri == "https://app.example.com/callback"
            return {"access_token": "provider-token", "token_type": "Bearer"}

        async def get(self, url, **kwargs):
            assert url == "https://sso.example.com/userinfo"
            return _Response(
                {
                    "sub": "oidc-user-001",
                    "email": "oidc@example.com",
                    "preferred_username": "oidc-user",
                }
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(auth_module, "AsyncOAuth2Client", _Client)

    request = _build_request(
        {
            "oidc_state": "state-001",
            "oidc_redirect_uri": "https://app.example.com/callback",
        }
    )

    payload = asyncio.run(
        auth_module.handle_oidc_callback(
            request=request,
            code="code-001",
            state="state-001",
            redirect_uri="https://app.example.com/callback",
            actor={"username": "tester"},
        )
    )

    assert payload["status"] == "exchanged"
    assert payload["provider_user"]["sub"] == "oidc-user-001"
    assert payload["local_access_token"]
    assert "oidc_state" not in request.session
    assert "oidc_redirect_uri" not in request.session

    monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_SECRET", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()


def test_oidc_callback_rejects_state_mismatch(monkeypatch):
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://sso.example.com")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-client")
    monkeypatch.setenv("SEC_OIDC_CLIENT_SECRET", "pms-secret")

    from fastapi import HTTPException
    from src.config.settings import get_settings

    get_settings.cache_clear()
    clear_oidc_provider_cache()
    auth_module = _load_auth_module()

    request = _build_request({"oidc_state": "state-expected"})

    try:
        asyncio.run(
            auth_module.handle_oidc_callback(
                request=request,
                code="code-001",
                state="state-actual",
                redirect_uri="https://app.example.com/callback",
                actor={},
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "OIDC state mismatch"
    else:
        raise AssertionError("Expected OIDC state mismatch to raise HTTPException")

    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_SECRET", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()


def test_oidc_discovery_prefers_well_known_metadata_for_okta_like_provider(monkeypatch):
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://example.okta.com/oauth2/default")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-client")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    clear_oidc_provider_cache()
    auth_module = _load_auth_module()
    monkeypatch.setattr(
        auth_module,
        "get_oidc_provider_metadata",
        lambda security_settings=None: {
            "issuer": "https://example.okta.com/oauth2/default",
            "authorization_endpoint": "https://example.okta.com/oauth2/default/v1/authorize",
            "token_endpoint": "https://example.okta.com/oauth2/default/v1/token",
            "userinfo_endpoint": "https://example.okta.com/oauth2/default/v1/userinfo",
            "jwks_uri": "https://example.okta.com/oauth2/default/v1/keys",
            "source": "well_known",
        },
    )

    payload = asyncio.run(auth_module.get_oidc_discovery(actor={}))

    assert payload["enabled"] is True
    assert payload["authorization_endpoint"] == "https://example.okta.com/oauth2/default/v1/authorize"
    assert payload["jwks_uri"] == "https://example.okta.com/oauth2/default/v1/keys"
    assert payload["discovery_source"] == "well_known"

    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()


def test_get_current_user_accepts_oidc_provider_token_and_maps_claims(monkeypatch):
    monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://sso.example.com/realms/pms")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-client")
    monkeypatch.setenv("SEC_OIDC_AUDIENCE", "api://pms")
    monkeypatch.setenv("SEC_OIDC_ROLE_MAPPING", "pms-admin=tenant_admin")

    from src.config.settings import get_settings
    from src.core.auth import get_current_user

    get_settings.cache_clear()
    clear_oidc_provider_cache()

    private_pem, jwks = _build_provider_signing_material()
    metadata = {
        "issuer": "https://sso.example.com/realms/pms",
        "jwks_uri": "https://sso.example.com/realms/pms/protocol/openid-connect/certs",
    }
    monkeypatch.setattr("src.core.oidc.get_oidc_provider_metadata", lambda security_settings=None: metadata)
    monkeypatch.setattr("src.core.oidc.get_oidc_jwks", lambda security_settings=None, metadata=None: jwks)

    token = jose_jwt.encode(
        {
            "iss": "https://sso.example.com/realms/pms",
            "sub": "user-001",
            "preferred_username": "oidc-user",
            "aud": ["api://pms"],
            "azp": "pms-client",
            "realm_access": {"roles": ["pms-admin"]},
            "tenant_id": "tenant-001",
            "tenant_key": "tenant-key-001",
            "tenant_name": "Tenant One",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-kid-001"},
    )

    current_user = asyncio.run(get_current_user(token))

    assert current_user["username"] == "oidc-user"
    assert current_user["user_id"] == "user-001"
    assert current_user["tenant_id"] == "tenant-001"
    assert current_user["tenant_key"] == "tenant-key-001"
    assert current_user["tenant_name"] == "Tenant One"
    assert current_user["roles"] == ["tenant_admin"]
    assert current_user["auth_source"] == "oidc"
    assert current_user["provider_issuer"] == "https://sso.example.com/realms/pms"

    monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("SEC_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("SEC_OIDC_ROLE_MAPPING", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()


def test_local_jwt_remains_compatible_when_oidc_enabled(monkeypatch):
    monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)
    monkeypatch.setenv("SEC_OIDC_ENABLED", "true")
    monkeypatch.setenv("SEC_OIDC_ISSUER_URL", "https://sso.example.com/realms/pms")
    monkeypatch.setenv("SEC_OIDC_CLIENT_ID", "pms-client")

    from src.config.settings import get_settings
    from src.core.auth import create_access_token, get_current_user

    get_settings.cache_clear()
    clear_oidc_provider_cache()

    token = create_access_token(
        {
            "sub": "local-user",
            "user_id": "local-user-001",
            "tenant_id": "tenant-local-001",
            "tenant_key": "local",
            "tenant_name": "Local Tenant",
            "roles": ["operator"],
        }
    )

    current_user = asyncio.run(get_current_user(token))

    assert current_user["username"] == "local-user"
    assert current_user["roles"] == ["operator"]
    assert current_user["auth_source"] == "local_jwt"

    monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
    monkeypatch.delenv("SEC_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("SEC_OIDC_ISSUER_URL", raising=False)
    monkeypatch.delenv("SEC_OIDC_CLIENT_ID", raising=False)
    clear_oidc_provider_cache()
    get_settings.cache_clear()
