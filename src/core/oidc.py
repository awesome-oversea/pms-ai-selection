from __future__ import annotations

import time
from typing import Any

import httpx
from authlib.jose import JoseError, JsonWebKey
from authlib.jose import jwt as authlib_jwt

from src.config.settings import SecuritySettings
from src.core.exceptions import AuthenticationError
from src.core.tenant import get_default_tenant_context

_METADATA_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_oidc_provider_cache() -> None:
    _METADATA_CACHE.clear()
    _JWKS_CACHE.clear()


def _cache_get(
    cache: dict[str, tuple[float, dict[str, Any]]],
    cache_key: str,
    ttl_seconds: int,
) -> dict[str, Any] | None:
    if ttl_seconds <= 0:
        return None
    cached = cache.get(cache_key)
    if cached is None:
        return None
    cached_at, payload = cached
    if (time.monotonic() - cached_at) >= ttl_seconds:
        cache.pop(cache_key, None)
        return None
    return dict(payload)


def _cache_put(
    cache: dict[str, tuple[float, dict[str, Any]]],
    cache_key: str,
    value: dict[str, Any],
    ttl_seconds: int,
) -> None:
    if ttl_seconds <= 0:
        return
    cache[cache_key] = (time.monotonic(), dict(value))


def _resolve_discovery_url(security_settings: SecuritySettings) -> str | None:
    explicit_url = (security_settings.oidc_discovery_url or "").strip()
    if explicit_url:
        return explicit_url
    issuer = (security_settings.oidc_issuer_url or "").strip().rstrip("/")
    if not issuer:
        return None
    return f"{issuer}/.well-known/openid-configuration"


def _build_static_metadata(security_settings: SecuritySettings) -> dict[str, Any]:
    issuer = (security_settings.oidc_issuer_url or "").strip().rstrip("/")
    metadata = {
        "issuer": issuer or None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "userinfo_endpoint": None,
        "jwks_uri": (security_settings.oidc_jwks_uri or "").strip() or None,
        "source": "static",
    }
    if issuer:
        metadata["authorization_endpoint"] = f"{issuer}{security_settings.oidc_authorize_path}"
        metadata["token_endpoint"] = f"{issuer}{security_settings.oidc_token_path}"
        metadata["userinfo_endpoint"] = f"{issuer}{security_settings.oidc_userinfo_path}"
    return metadata


def get_oidc_provider_metadata(
    security_settings: SecuritySettings | None = None,
) -> dict[str, Any]:
    security = security_settings or SecuritySettings()
    static_metadata = _build_static_metadata(security)
    if not security.oidc_enabled:
        return static_metadata

    discovery_url = _resolve_discovery_url(security)
    if not discovery_url:
        return static_metadata

    cache_key = f"{discovery_url}|{security.oidc_jwks_uri or ''}"
    cached = _cache_get(_METADATA_CACHE, cache_key, security.oidc_cache_ttl_seconds)
    if cached is not None:
        return cached

    try:
        with httpx.Client(
            timeout=security.oidc_http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.get(discovery_url)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return static_metadata

    if not isinstance(payload, dict):
        return static_metadata

    metadata = dict(static_metadata)
    metadata.update(payload)
    metadata["source"] = "well_known"
    if not metadata.get("issuer"):
        metadata["issuer"] = static_metadata.get("issuer")
    if security.oidc_jwks_uri:
        metadata["jwks_uri"] = security.oidc_jwks_uri

    _cache_put(_METADATA_CACHE, cache_key, metadata, security.oidc_cache_ttl_seconds)
    return metadata


def get_oidc_jwks(
    security_settings: SecuritySettings | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    security = security_settings or SecuritySettings()
    provider_metadata = metadata or get_oidc_provider_metadata(security)
    jwks_uri = (security.oidc_jwks_uri or provider_metadata.get("jwks_uri") or "").strip()
    if not jwks_uri:
        raise AuthenticationError("OIDC 未配置 JWKS URI，无法校验 provider token")

    cached = _cache_get(_JWKS_CACHE, jwks_uri, security.oidc_cache_ttl_seconds)
    if cached is not None:
        return cached

    try:
        with httpx.Client(
            timeout=security.oidc_http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = client.get(jwks_uri)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise AuthenticationError(f"OIDC JWKS 获取失败: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise AuthenticationError("OIDC JWKS 响应格式无效")

    _cache_put(_JWKS_CACHE, jwks_uri, payload, security.oidc_cache_ttl_seconds)
    return payload


def _normalize_audience(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _get_claim_by_path(claims: dict[str, Any], path: str, client_id: str | None = None) -> Any:
    normalized_path = (path or "").replace("{client_id}", client_id or "")
    parts = [part for part in normalized_path.split(".") if part]
    current: Any = claims
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _collect_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        return [str(key).strip() for key, enabled in value.items() if enabled and str(key).strip()]
    if isinstance(value, (list, tuple, set)):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_collect_strings(item))
        return flattened
    cleaned = str(value).strip()
    return [cleaned] if cleaned else []


def extract_oidc_roles(
    claims: dict[str, Any],
    security_settings: SecuritySettings | None = None,
) -> list[str]:
    security = security_settings or SecuritySettings()
    roles: list[str] = []
    for path in security.oidc_role_claim_paths:
        roles.extend(_collect_strings(_get_claim_by_path(claims, path, security.oidc_client_id)))

    mapping = {
        str(key).strip(): str(value).strip()
        for key, value in security.oidc_role_mapping.items()
        if str(key).strip() and str(value).strip()
    }
    normalized: list[str] = []
    for role in roles:
        resolved = mapping.get(role) or mapping.get(role.lower()) or role
        if resolved not in normalized:
            normalized.append(resolved)
    return normalized


def _first_claim_value(
    claims: dict[str, Any],
    claim_paths: list[str],
    client_id: str | None = None,
) -> str | None:
    for path in claim_paths:
        value = _get_claim_by_path(claims, path, client_id)
        values = _collect_strings(value)
        if values:
            return values[0]
    return None


def map_oidc_claims_to_local_identity(
    claims: dict[str, Any],
    security_settings: SecuritySettings | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    security = security_settings or SecuritySettings()
    provider_metadata = metadata or get_oidc_provider_metadata(security)
    default_tenant = get_default_tenant_context()
    username = _first_claim_value(claims, security.oidc_username_claims, security.oidc_client_id)
    subject = _first_claim_value(claims, ["sub"], security.oidc_client_id)
    if not username:
        username = subject or "oidc-user"
    if not subject:
        subject = username

    tenant_id = (
        _first_claim_value(claims, [security.oidc_tenant_id_claim], security.oidc_client_id)
        or security.oidc_default_tenant_id
        or default_tenant.tenant_id
    )
    tenant_key = (
        _first_claim_value(claims, [security.oidc_tenant_key_claim], security.oidc_client_id)
        or security.oidc_default_tenant_key
    )
    tenant_name = (
        _first_claim_value(claims, [security.oidc_tenant_name_claim], security.oidc_client_id)
        or security.oidc_default_tenant_name
    )
    if tenant_id == default_tenant.tenant_id:
        tenant_key = tenant_key or default_tenant.tenant_key
        tenant_name = tenant_name or default_tenant.tenant_name

    roles = extract_oidc_roles(claims, security)
    is_superuser = bool(claims.get("is_superuser")) or "platform_admin" in roles

    return {
        "sub": username,
        "user_id": subject,
        "email": _first_claim_value(claims, ["email"], security.oidc_client_id),
        "name": _first_claim_value(claims, ["name"], security.oidc_client_id),
        "preferred_username": _first_claim_value(claims, ["preferred_username"], security.oidc_client_id),
        "is_superuser": is_superuser,
        "tenant_id": tenant_id,
        "tenant_key": tenant_key,
        "tenant_name": tenant_name,
        "roles": roles,
        "auth_source": "oidc",
        "provider_issuer": provider_metadata.get("issuer"),
        "provider_subject": subject,
    }


def decode_oidc_token_claims(
    token: str,
    security_settings: SecuritySettings | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    security = security_settings or SecuritySettings()
    if not security.oidc_enabled:
        raise AuthenticationError("OIDC 未启用")

    provider_metadata = metadata or get_oidc_provider_metadata(security)
    issuer = str(provider_metadata.get("issuer") or security.oidc_issuer_url or "").strip()
    if not issuer:
        raise AuthenticationError("OIDC issuer 未配置")

    jwks = get_oidc_jwks(security, provider_metadata)
    try:
        key_set = JsonWebKey.import_key_set(jwks)
        claims = authlib_jwt.decode(token, key_set)
        claims.validate()
    except JoseError as exc:
        raise AuthenticationError(f"OIDC provider token 校验失败: {exc}") from exc
    except Exception as exc:
        raise AuthenticationError(f"OIDC provider token 解析失败: {exc}") from exc

    payload = dict(claims)
    if payload.get("iss") != issuer:
        raise AuthenticationError("OIDC token issuer 不匹配")

    audiences = _normalize_audience(payload.get("aud"))
    authorized_party = str(payload.get("azp") or "").strip()
    expected_audience = str(security.oidc_audience or "").strip()
    if expected_audience:
        if expected_audience not in audiences and authorized_party != expected_audience:
            raise AuthenticationError("OIDC token audience 不匹配")
    elif security.oidc_client_id and authorized_party:  # noqa: SIM102
        if authorized_party != security.oidc_client_id and security.oidc_client_id not in audiences:
            raise AuthenticationError("OIDC token client_id 不匹配")

    return payload
