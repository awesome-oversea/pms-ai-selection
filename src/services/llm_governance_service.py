from __future__ import annotations

from typing import Any

from src.repositories.tenant_config_repository import TenantConfigRepository
from src.repositories.tenant_quota_repository import TenantQuotaRepository


class LLMGovernanceService:
    def __init__(self, session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.config_repo = TenantConfigRepository(session)
        self.quota_repo = TenantQuotaRepository(session)

    async def build_status(self) -> dict[str, Any]:
        quota_status = await self.quota_repo.list_quota_status(tenant_id=self.tenant_id)
        llm_quota = next((item for item in quota_status if item.get("quota_type") == "llm_cost_usd"), None)

        prompt_configs = await self.config_repo.list_configs(tenant_id=self.tenant_id, limit=200)
        prompt_items = [item for item in prompt_configs if (item.config_key or "").startswith("llm_prompt:")]
        route_policy = await self.config_repo.get_config(tenant_id=self.tenant_id, config_key="llm_route_policy")
        current_policy = ((route_policy.config_value or {}).get("current", {})) if route_policy and route_policy.config_value else {}

        prompt_versions = []
        for item in prompt_items[:20]:
            current = (item.config_value or {}).get("current", {}) if item.config_value else {}
            prompt_versions.append(
                {
                    "prompt_key": (item.config_key or "").replace("llm_prompt:", "", 1),
                    "version": current.get("version", 0),
                    "description": current.get("description", ""),
                }
            )

        return {
            "tenant_id": self.tenant_id,
            "quota": {
                "quota_type": "llm_cost_usd",
                "configured": llm_quota is not None,
                "limit_value": llm_quota.get("limit_value", 0.0) if llm_quota else 0.0,
                "used_value": llm_quota.get("used_value", 0.0) if llm_quota else 0.0,
                "remaining": llm_quota.get("remaining", 0.0) if llm_quota else 0.0,
                "reset_period": llm_quota.get("reset_period", "monthly") if llm_quota else "monthly",
                "is_active": llm_quota.get("is_active", False) if llm_quota else False,
            },
            "prompt_governance": {
                "prompt_total": len(prompt_items),
                "recent_versions": prompt_versions,
            },
            "route_policy": {
                "configured": route_policy is not None,
                "version": current_policy.get("version", 0),
                "default_force_tier": current_policy.get("default_force_tier"),
                "default_use_mock": current_policy.get("default_use_mock"),
                "default_api_model_name": current_policy.get("default_api_model_name"),
                "gray_rollout_percent": current_policy.get("gray_rollout_percent", 0),
                "gray_tenant_whitelist": current_policy.get("gray_tenant_whitelist", []),
            },
            "audit": {
                "prompt_audit_ready": True,
                "cost_trace_ready": True,
                "quota_enforcement_ready": True,
            },
        }
