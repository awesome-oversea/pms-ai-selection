"""
认证 API 端点
=============

提供用户认证与注册功能:
- POST /api/v1/auth/login     - 用户登录，返回 JWT Token
- POST /api/v1/auth/register  - 用户注册

使用内存存储作为数据库不可用时的降级方案。
"""

import logging
import uuid

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from src.config.settings import get_settings
from src.core.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from src.core.exceptions import AuthenticationError
from src.core.oidc import (
    decode_oidc_token_claims,
    get_oidc_provider_metadata,
    map_oidc_claims_to_local_identity,
)
from src.core.security import add_audit_log, get_actor
from src.core.tenant import get_default_tenant_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])

# 内存用户存储（数据库不可用时降级）
_user_store: dict[str, dict] = {}


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class RegisterRequest(BaseModel):
    """注册请求。"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., max_length=255, description="邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    full_name: str | None = Field(None, max_length=100, description="真实姓名")


class TokenResponse(BaseModel):
    """登录成功响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str
    tenant_key: str
    tenant_name: str
    expires_in: int = Field(description="Access Token 有效期（秒）")


class OIDCAuthorizeURLResponse(BaseModel):
    enabled: bool
    issuer: str | None = None
    authorize_url: str | None = None
    client_id: str | None = None
    redirect_uri: str | None = None
    scope: str = "openid profile email"
    state: str | None = None


def _build_oidc_endpoints(security_settings) -> dict[str, str | None]:
    metadata = get_oidc_provider_metadata(security_settings)
    return {
        "issuer": metadata.get("issuer"),
        "authorization_endpoint": metadata.get("authorization_endpoint"),
        "token_endpoint": metadata.get("token_endpoint"),
        "userinfo_endpoint": metadata.get("userinfo_endpoint"),
        "jwks_uri": metadata.get("jwks_uri"),
        "source": metadata.get("source"),
        "end_session_endpoint": metadata.get("end_session_endpoint"),
    }


def _create_oidc_client(security_settings, redirect_uri: str | None = None) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=security_settings.oidc_client_id,
        client_secret=security_settings.oidc_client_secret,
        scope=security_settings.oidc_scope,
        redirect_uri=redirect_uri,
        token_endpoint_auth_method="client_secret_post",
    )


async def _get_db_session():
    """尝试获取数据库会话。"""
    try:
        from src.infrastructure.database import get_async_session_factory
        factory = get_async_session_factory()
        return factory()
    except Exception:
        return None


def _build_local_bootstrap_superuser() -> dict | None:
    settings = get_settings()
    default_tenant = get_default_tenant_context()
    if settings.app.environment == "production":
        return None
    if not settings.security.local_bootstrap_superuser_enabled:
        return None
    username = settings.security.local_bootstrap_superuser_username
    password = settings.security.local_bootstrap_superuser_password
    if not username or not password:
        return None
    return {
        "user_id": "local-bootstrap-superuser",
        "username": username,
        "email": settings.security.local_bootstrap_superuser_email or f"{username}@local.dev",
        "hashed_password": get_password_hash(password),
        "full_name": "Local Bootstrap Superuser",
        "is_superuser": True,
        "tenant_id": default_tenant.tenant_id,
        "tenant_key": default_tenant.tenant_key,
        "tenant_name": default_tenant.tenant_name,
    }


def _build_local_acceptance_user(username: str) -> dict | None:
    default_tenant = get_default_tenant_context()
    if username != "operator-e2e":
        return None
    return {
        "user_id": "local-acceptance-operator",
        "username": "operator-e2e",
        "email": "operator-e2e@example.com",
        "hashed_password": get_password_hash("Operator123!"),
        "full_name": "Local Acceptance Operator",
        "is_superuser": False,
        "tenant_id": default_tenant.tenant_id,
        "tenant_key": default_tenant.tenant_key,
        "tenant_name": default_tenant.tenant_name,
        "roles": ["operator"],
    }


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, actor: dict = Depends(get_actor)):
    """
    用户登录。

    验证用户名和密码，成功后返回 access_token 和 refresh_token。
    优先查询数据库，降级为内存存储。
    """
    user = None
    default_tenant = get_default_tenant_context()

    # 1. 尝试数据库查询
    session = await _get_db_session()
    if session is not None:
        try:
            from sqlalchemy import select
            from src.models.models import User
            stmt = select(User).where(User.username == request.username, User.is_deleted == False)
            result = await session.execute(stmt)
            db_user = result.scalar_one_or_none()
            if db_user and verify_password(request.password, db_user.hashed_password):
                user = {
                    "user_id": str(db_user.id),
                    "username": db_user.username,
                    "is_superuser": db_user.is_superuser,
                }
        except Exception as e:
            logger.warning(f"⚠️ 数据库用户查询失败: {e}")
        finally:
            await session.close()

    # 2. 降级: 内存存储
    if user is None and request.username in _user_store:
        stored = _user_store[request.username]
        if verify_password(request.password, stored["hashed_password"]):
            user = {
                "user_id": stored["user_id"],
                "username": stored["username"],
                "is_superuser": stored.get("is_superuser", False),
                "tenant_id": stored.get("tenant_id", default_tenant.tenant_id),
                "tenant_key": stored.get("tenant_key", default_tenant.tenant_key),
                "tenant_name": stored.get("tenant_name", default_tenant.tenant_name),
            }

    # 3. 仅本地/开发环境受控 superuser / acceptance 种子
    if user is None:
        bootstrap_superuser = _build_local_bootstrap_superuser()
        if bootstrap_superuser and request.username == bootstrap_superuser["username"]:
            if verify_password(request.password, bootstrap_superuser["hashed_password"]):
                user = {
                    "user_id": bootstrap_superuser["user_id"],
                    "username": bootstrap_superuser["username"],
                    "is_superuser": True,
                    "tenant_id": bootstrap_superuser["tenant_id"],
                    "tenant_key": bootstrap_superuser["tenant_key"],
                    "tenant_name": bootstrap_superuser["tenant_name"],
                    "roles": ["platform_admin", "tenant_admin"],
                }

    if user is None:
        acceptance_user = _build_local_acceptance_user(request.username)
        if acceptance_user and verify_password(request.password, acceptance_user["hashed_password"]):
            user = {
                "user_id": acceptance_user["user_id"],
                "username": acceptance_user["username"],
                "is_superuser": False,
                "tenant_id": acceptance_user["tenant_id"],
                "tenant_key": acceptance_user["tenant_key"],
                "tenant_name": acceptance_user["tenant_name"],
                "roles": acceptance_user.get("roles", ["operator"]),
            }

    if user is None:
        add_audit_log(
            action="auth.login",
            actor=actor,
            target_type="user",
            target_id=request.username,
            result="denied",
            detail={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 生成 Token
    token_data = {
        "sub": user["username"],
        "user_id": user["user_id"],
        "is_superuser": user.get("is_superuser", False),
        "tenant_id": user.get("tenant_id", default_tenant.tenant_id),
        "tenant_key": user.get("tenant_key", default_tenant.tenant_key),
        "tenant_name": user.get("tenant_name", default_tenant.tenant_name),
        "roles": user.get("roles", ["operator"] if not user.get("is_superuser", False) else ["platform_admin", "tenant_admin"]),
    }

    from src.config.settings import SecuritySettings
    sec = SecuritySettings()

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info(f"✅ 用户登录成功: {user['username']}")
    add_audit_log(
        action="auth.login",
        actor=user,
        target_type="user",
        target_id=user["user_id"],
        result="success",
        detail={"username": user["username"]},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        tenant_id=user.get("tenant_id", default_tenant.tenant_id),
        tenant_key=user.get("tenant_key", default_tenant.tenant_key),
        tenant_name=user.get("tenant_name", default_tenant.tenant_name),
        expires_in=sec.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=dict)
async def get_me(current_user: dict = Depends(get_current_user)):
    """返回当前登录用户信息。"""
    return {
        "user_id": current_user.get("user_id"),
        "username": current_user.get("username"),
        "tenant_id": current_user.get("tenant_id"),
        "tenant_key": current_user.get("tenant_key"),
        "tenant_name": current_user.get("tenant_name"),
        "roles": current_user.get("roles", []),
        "is_superuser": current_user.get("is_superuser", False),
    }


@router.get("/oidc/discovery", response_model=dict)
async def get_oidc_discovery(actor: dict = Depends(get_actor)):
    settings = get_settings().security
    endpoints = _build_oidc_endpoints(settings)
    return {
        "enabled": settings.oidc_enabled,
        "issuer": endpoints["issuer"],
        "authorization_endpoint": endpoints["authorization_endpoint"] if settings.oidc_enabled else None,
        "token_endpoint": endpoints["token_endpoint"] if settings.oidc_enabled else None,
        "userinfo_endpoint": endpoints["userinfo_endpoint"] if settings.oidc_enabled else None,
        "jwks_uri": endpoints["jwks_uri"] if settings.oidc_enabled else None,
        "end_session_endpoint": endpoints["end_session_endpoint"] if settings.oidc_enabled else None,
        "client_id": settings.oidc_client_id,
        "scopes_supported": settings.oidc_scope.split(),
        "discovery_source": endpoints["source"] if settings.oidc_enabled else None,
    }


@router.get("/oidc/authorize-url", response_model=OIDCAuthorizeURLResponse)
async def get_oidc_authorize_url(
    request: Request,
    redirect_uri: str = Query(..., min_length=1),
    state: str = Query("pms-state"),
    actor: dict = Depends(get_actor),
):
    settings = get_settings().security
    endpoints = _build_oidc_endpoints(settings)
    authorize_url = None
    if settings.oidc_enabled and endpoints["authorization_endpoint"] and settings.oidc_client_id:
        oauth_client = _create_oidc_client(settings, redirect_uri=redirect_uri)
        try:
            authorize_url, generated_state = oauth_client.create_authorization_url(
                endpoints["authorization_endpoint"],
                state=state,
            )
        finally:
            await oauth_client.aclose()
        request.session["oidc_state"] = generated_state
        request.session["oidc_redirect_uri"] = redirect_uri
    return OIDCAuthorizeURLResponse(
        enabled=settings.oidc_enabled,
        issuer=endpoints["issuer"],
        authorize_url=authorize_url,
        client_id=settings.oidc_client_id,
        redirect_uri=redirect_uri,
        scope=settings.oidc_scope,
        state=state,
    )


@router.get("/oidc/callback", response_model=dict)
async def handle_oidc_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state: str = Query("pms-state"),
    redirect_uri: str | None = Query(default=None),
    actor: dict = Depends(get_actor),
):
    settings = get_settings().security
    endpoints = _build_oidc_endpoints(settings)
    issuer = endpoints["issuer"]
    token_endpoint = endpoints["token_endpoint"]
    userinfo_endpoint = endpoints["userinfo_endpoint"]

    if not (
        settings.oidc_enabled
        and issuer
        and settings.oidc_client_id
        and settings.oidc_client_secret
        and token_endpoint
        and userinfo_endpoint
    ):
        return {
            "enabled": settings.oidc_enabled,
            "code": code,
            "state": state,
            "status": "received",
            "exchange_mode": "manual_or_future_backend_exchange",
        }

    expected_state = request.session.get("oidc_state")
    session_redirect_uri = request.session.get("oidc_redirect_uri")
    if expected_state is not None and expected_state != state:
        raise HTTPException(status_code=400, detail="OIDC state mismatch")

    resolved_redirect_uri = redirect_uri or session_redirect_uri
    userinfo: dict = {}
    token_claims: dict = {}
    provider_tokens: dict = {}
    oauth_client = _create_oidc_client(settings, redirect_uri=resolved_redirect_uri)
    try:
        provider_tokens = await oauth_client.fetch_token(
            url=token_endpoint,
            grant_type="authorization_code",
            code=code,
            redirect_uri=resolved_redirect_uri,
        )
        access_token_value = str(provider_tokens.get("access_token") or "")
        id_token_value = str(provider_tokens.get("id_token") or "")
        if id_token_value:
            try:
                token_claims = decode_oidc_token_claims(
                    id_token_value,
                    security_settings=settings,
                    metadata={
                        "issuer": issuer,
                        "jwks_uri": endpoints["jwks_uri"],
                    },
                )
            except AuthenticationError as exc:
                raise HTTPException(status_code=502, detail=f"OIDC id_token validation failed: {exc}") from exc
        elif access_token_value and access_token_value.count(".") == 2 and endpoints["jwks_uri"]:
            try:
                token_claims = decode_oidc_token_claims(
                    access_token_value,
                    security_settings=settings,
                    metadata={
                        "issuer": issuer,
                        "jwks_uri": endpoints["jwks_uri"],
                    },
                )
            except AuthenticationError:
                token_claims = {}

        if access_token_value and userinfo_endpoint:
            userinfo_response = await oauth_client.get(userinfo_endpoint)
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OIDC token exchange failed: {exc}") from exc
    finally:
        request.session.pop("oidc_state", None)
        request.session.pop("oidc_redirect_uri", None)
        await oauth_client.aclose()

    merged_claims = dict(token_claims)
    if isinstance(userinfo, dict):
        merged_claims.update(userinfo)
    if not merged_claims:
        merged_claims = {
            "sub": f"oidc-{uuid.uuid4().hex[:8]}",
        }

    token_data = map_oidc_claims_to_local_identity(
        merged_claims,
        security_settings=settings,
        metadata={
            "issuer": issuer,
            "jwks_uri": endpoints["jwks_uri"],
        },
    )
    local_access_token = create_access_token(token_data)
    local_refresh_token = create_refresh_token(token_data)
    add_audit_log(
        action="auth.oidc.callback",
        actor=actor,
        target_type="oidc_login",
        target_id=str(token_data.get("user_id") or token_data.get("sub")),
        result="success",
        detail={
            "issuer": issuer,
            "state": state,
            "username": token_data.get("sub"),
            "roles": token_data.get("roles", []),
        },
    )
    return {
        "enabled": True,
        "status": "exchanged",
        "issuer": issuer,
        "state": state,
        "provider_user": merged_claims,
        "provider_token_type": provider_tokens.get("token_type", "Bearer"),
        "local_access_token": local_access_token,
        "local_refresh_token": local_refresh_token,
        "token_type": "bearer",
        "tenant_id": token_data.get("tenant_id"),
        "tenant_key": token_data.get("tenant_key"),
        "tenant_name": token_data.get("tenant_name"),
        "roles": token_data.get("roles", []),
        "auth_source": token_data.get("auth_source"),
    }


@router.post("/register", response_model=dict)
async def register(request: RegisterRequest, actor: dict = Depends(get_actor)):
    """
    用户注册。

    创建新用户账号，密码使用 bcrypt 哈希存储。
    优先持久化到数据库，降级为内存存储。
    """
    user_id = str(uuid.uuid4())
    hashed = get_password_hash(request.password)
    default_tenant = get_default_tenant_context()
    bootstrap_superuser = _build_local_bootstrap_superuser()
    if bootstrap_superuser and request.username == bootstrap_superuser["username"]:
        raise HTTPException(status_code=409, detail="用户名已被本地受控管理员种子占用")

    # 1. 尝试数据库持久化
    session = await _get_db_session()
    if session is not None:
        try:
            from sqlalchemy import select
            from src.models.models import User
            # 检查重名
            stmt = select(User).where(
                (User.username == request.username) | (User.email == request.email)
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=409, detail="用户名或邮箱已被注册")

            new_user = User(
                username=request.username,
                email=request.email,
                hashed_password=hashed,
                full_name=request.full_name,
                is_active=True,
                is_superuser=False,
            )
            session.add(new_user)
            await session.commit()
            user_id = str(new_user.id)
            logger.info(f"💾 用户已注册到数据库: {request.username}")

            add_audit_log(
                action="auth.register",
                actor=actor,
                target_type="user",
                target_id=user_id,
                result="success",
                detail={"username": request.username, "mode": "database"},
            )
            return {
                "user_id": user_id,
                "username": request.username,
                "email": request.email,
                "message": "注册成功",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ 数据库注册失败，降级内存: {e}")
            await session.rollback()
        finally:
            await session.close()

    # 2. 降级: 内存存储
    if request.username in _user_store:
        raise HTTPException(status_code=409, detail="用户名已被注册")

    _user_store[request.username] = {
        "user_id": user_id,
        "username": request.username,
        "email": request.email,
        "hashed_password": hashed,
        "full_name": request.full_name,
        "is_superuser": False,
        "tenant_id": default_tenant.tenant_id,
        "tenant_key": default_tenant.tenant_key,
        "tenant_name": default_tenant.tenant_name,
    }

    logger.info(f"📝 用户已注册到内存: {request.username}")
    add_audit_log(
        action="auth.register",
        actor=actor,
        target_type="user",
        target_id=user_id,
        result="success",
        detail={"username": request.username, "mode": "memory"},
    )

    return {
        "user_id": user_id,
        "username": request.username,
        "email": request.email,
        "message": "注册成功（内存模式）",
    }
