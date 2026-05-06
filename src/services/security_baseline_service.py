from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.core.rbac import ROLE_MATRIX
from src.services.prompt_guard_service import PromptGuardService


class SecurityBaselineService:
    def build_status(self) -> dict[str, Any]:
        settings = get_settings()
        security = settings.security
        prompt_guard_keywords = security.llm_prompt_guard_keywords
        llm_ip_allowlist = security.llm_ip_allowlist
        masking_fields = [
            "password",
            "passwd",
            "pwd",
            "email",
            "mail",
            "phone",
            "mobile",
            "tel",
            "id_card",
            "idcard",
            "identity",
            "bank_card",
            "bankcard",
            "card",
            "token",
            "secret",
            "key",
            "db_url",
            "database_url",
        ]
        prompt_guard_policy = PromptGuardService().build_status()
        prompt_guard_policy["mode"] = "config-plus-patterns"

        return {
            "oauth2_enabled": True,
            "token_url": "/api/v1/auth/login",
            "rbac_enabled": True,
            "rbac_roles": sorted(ROLE_MATRIX.keys()),
            "explicit_tenant_required": security.require_explicit_tenant,
            "audit_persistent_ready": True,
            "audit_trace_query_ready": True,
            "llm_protection": {
                "ip_allowlist_enabled": len(llm_ip_allowlist) > 0,
                "ip_allowlist_count": len(llm_ip_allowlist),
                "prompt_guard_enabled": security.llm_prompt_guard_enabled,
                "prompt_guard_keyword_count": len(prompt_guard_keywords),
                "prompt_guard_policy": prompt_guard_policy,
            },
            "data_protection": {
                "db_url_masked": True,
                "sensitive_config_exposed": False,
                "data_masking_enabled": True,
                "masking_fields_count": len(masking_fields),
                "masking_coverage": {
                    "enabled": True,
                    "field_count": len(masking_fields),
                    "covered_fields": masking_fields,
                },
            },
            "waf": {
                "ip_whitelist_enabled": len(llm_ip_allowlist) > 0,
                "ip_whitelist_count": len(llm_ip_allowlist),
                "middleware_enabled": True,
            },
            "controls": [
                "oauth2_jwt",
                "rbac",
                "tenant_context",
                "audit_log",
                "trace_query",
                "prompt_guard",
                "ip_allowlist",
                "db_url_masking",
                "data_masking",
                "waf_ip_whitelist",
            ],
        }
