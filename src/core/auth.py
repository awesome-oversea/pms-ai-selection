"""
JWT 认证中间件
==============

提供 JWT 令牌的生成、验证和 FastAPI 依赖注入:
- create_access_token:  生成 Access Token
- create_refresh_token: 生成 Refresh Token
- get_current_user:     FastAPI Depends 依赖，解析并验证请求中的 Bearer Token
- verify_password / get_password_hash: 密码哈希与验证工具

配置读取自 SecuritySettings (src/config/settings.py):
- secret_key, algorithm, access_token_expire_minutes, refresh_token_expire_days
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from src.config.settings import SecuritySettings
from src.core.exceptions import AuthenticationError
from src.core.oidc import decode_oidc_token_claims, map_oidc_claims_to_local_identity
from src.core.rbac import derive_roles, normalize_roles
from src.core.tenant import get_default_tenant_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置 & 工具
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _get_security_settings() -> SecuritySettings:
    return SecuritySettings()


# ---------------------------------------------------------------------------
# 密码工具
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配。"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """生成 bcrypt 密码哈希。"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# ---------------------------------------------------------------------------
# Token 生成
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    生成 JWT Access Token。

    Args:
        data: 要编码到 Token 中的数据 (必须包含 "sub" 字段)
        expires_delta: 自定义过期时间增量，默认取配置 access_token_expire_minutes

    Returns:
        str: 编码后的 JWT 字符串
    """
    security = _get_security_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=security.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    encoded = jwt.encode(to_encode, security.secret_key, algorithm=security.algorithm)
    return encoded


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    生成 JWT Refresh Token。

    Args:
        data: 要编码到 Token 中的数据 (必须包含 "sub" 字段)
        expires_delta: 自定义过期时间增量，默认取配置 refresh_token_expire_days

    Returns:
        str: 编码后的 JWT Refresh Token
    """
    security = _get_security_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=security.refresh_token_expire_days)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded = jwt.encode(to_encode, security.secret_key, algorithm=security.algorithm)
    return encoded


# ---------------------------------------------------------------------------
# Token 解析 & FastAPI 依赖
# ---------------------------------------------------------------------------

def _decode_local_token(token: str) -> dict[str, Any]:
    """
    解码并验证本地签发的 JWT Token。

    Args:
        token: JWT 字符串

    Returns:
        dict: 解码后的 payload

    Raises:
        AuthenticationError: Token 无效或已过期
    """
    try:
        security = _get_security_settings()
        payload = jwt.decode(
            token,
            security.secret_key,
            algorithms=[security.algorithm],
        )
        payload.setdefault("auth_source", "local_jwt")
        return payload
    except JWTError as e:
        raise AuthenticationError(f"Token 验证失败: {e}")


def decode_token(token: str) -> dict[str, Any]:
    """
    解码并验证认证 Token。

    优先验证本地签发 JWT；若 OIDC 已启用，则在本地 JWT 失败后回退到
    企业 IdP (Keycloak/Okta 等) 的 provider token 校验链路。
    """
    try:
        return _decode_local_token(token)
    except AuthenticationError as local_error:
        security = _get_security_settings()
        if not security.oidc_enabled:
            raise local_error
        try:
            provider_claims = decode_oidc_token_claims(token, security_settings=security)
            return map_oidc_claims_to_local_identity(
                provider_claims,
                security_settings=security,
            )
        except AuthenticationError as oidc_error:
            raise AuthenticationError(
                f"Token 验证失败: 本地 JWT 与 OIDC provider token 均未通过 ({oidc_error})"
            ) from oidc_error


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """
    FastAPI 依赖注入：从请求头中提取并验证 JWT Token，返回用户信息。

    用法:
        @router.post("/protected")
        async def protected_endpoint(current_user = Depends(get_current_user)):
            ...

    Returns:
        dict: 包含 sub(用户名), user_id 等字段的用户信息

    Raises:
        AuthenticationError: 无 Token、Token 无效或已过期
    """
    if token is None:
        raise AuthenticationError("未提供认证凭证")

    payload = decode_token(token)  # 内部处理 JWTError

    username: str | None = payload.get("sub")
    if username is None:
        raise AuthenticationError("Token 中缺少用户标识")

    security = _get_security_settings()
    default_tenant = get_default_tenant_context()
    has_tenant_id = payload.get("tenant_id") is not None
    if security.require_explicit_tenant and not has_tenant_id:
        raise AuthenticationError("当前环境要求显式提供 tenant_id")

    tenant_id = payload.get("tenant_id") if has_tenant_id else default_tenant.tenant_id
    tenant_key = payload.get("tenant_key")
    tenant_name = payload.get("tenant_name")
    if not security.require_explicit_tenant and not has_tenant_id:
        tenant_key = tenant_key or default_tenant.tenant_key
        tenant_name = tenant_name or default_tenant.tenant_name

    current_user = {
        "username": username,
        "user_id": payload.get("user_id"),
        "is_superuser": payload.get("is_superuser", False),
        "tenant_id": tenant_id,
        "tenant_key": tenant_key,
        "tenant_name": tenant_name,
        "token_type": payload.get("type", "access"),
        "roles": normalize_roles(payload.get("roles")),
        "authorization": f"Bearer {token}",
        "auth_source": payload.get("auth_source", "local_jwt"),
        "provider_issuer": payload.get("provider_issuer"),
        "provider_subject": payload.get("provider_subject"),
    }
    current_user["roles"] = derive_roles(current_user)
    return current_user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
) -> dict[str, Any] | None:
    """
    可选认证依赖：有 Token 时验证并返回用户，无 Token 时返回 None。

    适用于公开端点但需要区分登录/匿名用户的场景。
    """
    if token is None:
        return None
    try:
        return await get_current_user(token)
    except AuthenticationError:
        return None
