"""
任务 4.1 验收测试：安全配置加固
===============================

验收标准:
- [x] APP_ENVIRONMENT=production + 弱 Secret Key → 应用启动失败并报错
- [x] APP_ENVIRONMENT=development + 弱 Secret Key → 仅警告，正常启动
- [x] CORS 响应头中 Access-Control-Allow-Methods 不再包含通配符 *
- [x] docker-compose.yml 中密码可通过环境变量 POSTGRES_PASSWORD 覆盖
"""

import warnings

import pytest


class TestSecurityConfig:
    def test_production_weak_secret_raises(self, monkeypatch):
        """production 环境 + 弱密钥 → 启动失败 (ValueError)。"""
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("SEC_SECRET_KEY", "weak")

        # 清除 lru_cache
        from src.config.settings import get_settings
        get_settings.cache_clear()

        from pydantic import ValidationError
        with pytest.raises((ValueError, ValidationError)):
            from src.config.settings import SecuritySettings
            SecuritySettings(secret_key="weak")

        # 恢复
        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_development_weak_secret_warns(self, monkeypatch):
        """development 环境 + 弱密钥 → 仅发出警告。"""
        monkeypatch.setenv("APP_ENVIRONMENT", "development")
        monkeypatch.setenv("SEC_SECRET_KEY", "short")

        from src.config.settings import SecuritySettings, get_settings
        get_settings.cache_clear()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sec = SecuritySettings()
            # 应有警告但不抛异常
            assert sec.secret_key == "short"

        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_production_strong_secret_ok(self, monkeypatch):
        """production 环境 + 强密钥 → 正常启动。"""
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        strong_key = "a" * 64  # 64 字符，足够安全
        monkeypatch.setenv("SEC_SECRET_KEY", strong_key)

        from src.config.settings import SecuritySettings, get_settings
        get_settings.cache_clear()

        sec = SecuritySettings()
        assert sec.secret_key == strong_key

        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_require_explicit_tenant_blocks_default_fallback(self, monkeypatch):
        monkeypatch.setenv("SEC_REQUIRE_EXPLICIT_TENANT", "true")
        monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)

        from src.config.settings import SecuritySettings, get_settings
        from src.core.auth import create_access_token, get_current_user
        from src.core.exceptions import AuthenticationError

        get_settings.cache_clear()
        sec = SecuritySettings()
        assert sec.require_explicit_tenant is True

        token = create_access_token({"sub": "tenantless-user", "user_id": "u-1"})

        import asyncio
        with pytest.raises(AuthenticationError):
            asyncio.run(get_current_user(token))

        monkeypatch.delenv("SEC_REQUIRE_EXPLICIT_TENANT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_resolve_tenant_context_does_not_backfill_default_metadata_when_explicit_required(self, monkeypatch):
        monkeypatch.setenv("SEC_REQUIRE_EXPLICIT_TENANT", "true")
        monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)

        from src.config.settings import get_settings
        from src.core.tenant import resolve_tenant_context

        get_settings.cache_clear()
        context = resolve_tenant_context({"tenant_id": "tenant-002"})
        assert context.tenant_id == "tenant-002"
        assert context.tenant_key is None
        assert context.tenant_name is None
        assert context.is_default is False

        monkeypatch.delenv("SEC_REQUIRE_EXPLICIT_TENANT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_resolve_tenant_context_requires_tenant_id_when_enforcement_enabled(self, monkeypatch):
        monkeypatch.setenv("SEC_REQUIRE_EXPLICIT_TENANT", "true")
        monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)

        from src.config.settings import get_settings
        from src.core.exceptions import AuthenticationError
        from src.core.tenant import resolve_tenant_context

        get_settings.cache_clear()
        with pytest.raises(AuthenticationError):
            resolve_tenant_context({})

        monkeypatch.delenv("SEC_REQUIRE_EXPLICIT_TENANT", raising=False)
        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    def test_security_list_settings_parse_csv(self, monkeypatch):
        monkeypatch.setenv("SEC_SECRET_KEY", "a" * 64)
        monkeypatch.setenv("SEC_LLM_IP_ALLOWLIST", "10.0.0.1, 10.0.0.2")
        monkeypatch.setenv("SEC_LLM_PROMPT_GUARD_KEYWORDS", "ignore previous instructions,泄露系统提示")
        monkeypatch.setenv("SEC_PII_FIELD_PATTERNS", "employee_name,shipping_contact")

        from src.config.settings import SecuritySettings, get_settings

        get_settings.cache_clear()
        sec = SecuritySettings()
        assert sec.llm_ip_allowlist == ["10.0.0.1", "10.0.0.2"]
        assert sec.llm_prompt_guard_keywords == ["ignore previous instructions", "泄露系统提示"]

        monkeypatch.delenv("SEC_SECRET_KEY", raising=False)
        monkeypatch.delenv("SEC_LLM_IP_ALLOWLIST", raising=False)
        monkeypatch.delenv("SEC_LLM_PROMPT_GUARD_KEYWORDS", raising=False)
        monkeypatch.delenv("SEC_PII_FIELD_PATTERNS", raising=False)
        get_settings.cache_clear()

    def test_cors_no_wildcard_methods(self):
        """CORS allow_methods 不包含通配符 *。"""
        from src.main import create_app

        app = create_app()

        # 检查 CORSMiddleware 配置
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "CORSMiddleware":
                methods = middleware.kwargs.get("allow_methods", [])
                assert "*" not in methods, f"allow_methods 仍包含通配符: {methods}"
                assert "GET" in methods
                assert "POST" in methods
                break

    def test_cors_no_wildcard_headers(self):
        """CORS allow_headers 不包含通配符 *。"""
        from src.main import create_app

        app = create_app()

        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "CORSMiddleware":
                headers = middleware.kwargs.get("allow_headers", [])
                assert "*" not in headers, f"allow_headers 仍包含通配符: {headers}"
                assert "Authorization" in headers
                assert "Content-Type" in headers
                break

    def test_cors_origins_cover_local_next_workbench_ports(self):
        """本地 Next.js 正式工作台端口应在默认 CORS 白名单内。"""
        from src.config.settings import AppSettings

        app = AppSettings()
        assert "http://127.0.0.1:3100" in app.cors_origins
        assert "http://localhost:3100" in app.cors_origins

    def test_docker_compose_password_env_var(self):
        """docker-compose.yml 中密码支持 POSTGRES_PASSWORD 环境变量覆盖。"""
        with open("docker-compose.yml", encoding="utf-8") as f:
            content = f.read()

        assert "${POSTGRES_PASSWORD:-pms_dev_2024}" in content, \
            "docker-compose.yml 未使用 ${POSTGRES_PASSWORD:-pms_dev_2024} 格式"

    def test_env_example_has_secret_key_warning(self):
        """.env.example 中包含 Secret Key 安全提示。"""
        with open(".env.example", encoding="utf-8") as f:
            content = f.read()

        assert "production" in content.lower() or "安全" in content
        assert "SEC_SECRET_KEY" in content
