"""
Prompt / Route Policy 服务
==========================

基于 TenantConfig 提供 T6.5 最小治理能力：
- Prompt 模板版本管理
- Route Policy 配置、灰度与回滚
- 模型注册中心（版本/灰度/回滚）
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from src.repositories.tenant_config_repository import TenantConfigRepository

_MEMORY_POLICY_STORE: dict[tuple[str, str], dict[str, Any]] = {}


class PromptPolicyService:
    def __init__(self, session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = TenantConfigRepository(session)

    def _store_key(self, config_key: str) -> tuple[str, str]:
        return str(self.tenant_id), config_key

    def _read_memory_payload(self, config_key: str) -> dict[str, Any] | None:
        payload = _MEMORY_POLICY_STORE.get(self._store_key(config_key))
        return deepcopy(payload) if payload is not None else None

    def _write_memory_payload(self, config_key: str, payload: dict[str, Any]) -> None:
        _MEMORY_POLICY_STORE[self._store_key(config_key)] = deepcopy(payload)

    async def _load_payload(self, config_key: str) -> dict[str, Any] | None:
        try:
            config = await self.repo.get_config(tenant_id=self.tenant_id, config_key=config_key)
        except Exception:
            return self._read_memory_payload(config_key)
        if config is not None and config.config_value:
            return deepcopy(config.config_value)
        return self._read_memory_payload(config_key)

    async def _persist_payload(self, config_key: str, payload: dict[str, Any]) -> None:
        self._write_memory_payload(config_key, payload)
        try:
            await self.repo.upsert_config(
                tenant_id=self.tenant_id,
                config_key=config_key,
                config_value=payload,
            )
        except Exception:
            return None

    @staticmethod
    def _prompt_key(key: str) -> str:
        return f"llm_prompt:{key}"

    @staticmethod
    def _policy_key() -> str:
        return "llm_route_policy"

    @staticmethod
    def _model_registry_key(registry_key: str = "default") -> str:
        return f"llm_model_registry:{registry_key}"

    async def publish_prompt(self, prompt_key: str, template: str, description: str = "") -> dict[str, Any]:
        full_key = self._prompt_key(prompt_key)
        existing = await self._load_payload(full_key)
        history = []
        current_version = 0
        if existing:
            history = list(existing.get("history", []))
            current = existing.get("current", {})
            if current:
                history.append(current)
                current_version = int(current.get("version", 0))

        version = current_version + 1
        payload = {
            "current": {
                "version": version,
                "template": template,
                "description": description,
            },
            "history": history[-20:],
        }
        await self._persist_payload(full_key, payload)
        return deepcopy(payload["current"])

    async def rollback_prompt(self, prompt_key: str) -> dict[str, Any] | None:
        full_key = self._prompt_key(prompt_key)
        payload = await self._load_payload(full_key)
        if payload is None:
            return None
        history = list(payload.get("history", []))
        if not history:
            current = payload.get("current")
            return deepcopy(current) if current else None
        current = history.pop()
        await self._persist_payload(full_key, {"current": current, "history": history})
        return deepcopy(current)

    async def resolve_prompt(self, prompt_key: str, prompt_vars: dict[str, Any] | None = None) -> dict[str, Any] | None:
        payload = await self._load_payload(self._prompt_key(prompt_key))
        if payload is None:
            return None
        current = payload.get("current", {})
        template = current.get("template", "")
        rendered = template.format(**(prompt_vars or {})) if template else ""
        return {
            "prompt_key": prompt_key,
            "version": current.get("version"),
            "template": template,
            "rendered_prompt": rendered,
        }

    async def publish_route_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        full_key = self._policy_key()
        existing = await self._load_payload(full_key)
        history = []
        current_version = 0
        if existing:
            history = list(existing.get("history", []))
            current = existing.get("current", {})
            if current:
                history.append(current)
                current_version = int(current.get("version", 0))

        current = {
            "version": current_version + 1,
            **policy,
        }
        await self._persist_payload(full_key, {"current": current, "history": history[-20:]})
        return deepcopy(current)

    async def publish_model_registry(self, registry_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        full_key = self._model_registry_key(registry_key)
        existing = await self._load_payload(full_key)
        history = []
        current_version = 0
        if existing:
            history = list(existing.get("history", []))
            current = existing.get("current", {})
            if current:
                history.append(current)
                current_version = int(current.get("version", 0))

        current = {
            "version": current_version + 1,
            **payload,
        }
        await self._persist_payload(full_key, {"current": current, "history": history[-20:]})
        return deepcopy(current)

    async def rollback_model_registry(self, registry_key: str) -> dict[str, Any] | None:
        full_key = self._model_registry_key(registry_key)
        payload = await self._load_payload(full_key)
        if payload is None:
            return None
        history = list(payload.get("history", []))
        if not history:
            current = payload.get("current")
            return deepcopy(current) if current else None
        current = history.pop()
        await self._persist_payload(full_key, {"current": current, "history": history})
        return deepcopy(current)

    async def get_model_registry(self, registry_key: str = "default") -> dict[str, Any] | None:
        payload = await self._load_payload(self._model_registry_key(registry_key))
        if payload is None:
            return None
        current = payload.get("current")
        return deepcopy(current) if current else None

    async def resolve_route_policy(self, prompt: str) -> dict[str, Any]:
        payload = await self._load_payload(self._policy_key())
        if payload is None:
            policy = {"version": 0, "gray_hit": False}
        else:
            current = payload.get("current", {})
            whitelist = set(current.get("gray_tenant_whitelist", []))
            rollout_percent = int(current.get("gray_rollout_percent", 0))
            gray_hit = False
            if self.tenant_id in whitelist:
                gray_hit = True
            elif rollout_percent > 0:
                bucket = int(hashlib.md5(f"{self.tenant_id}:{prompt}".encode()).hexdigest(), 16) % 100
                gray_hit = bucket < rollout_percent

            policy = {
                "version": current.get("version", 0),
                "force_tier": current.get("force_tier") if gray_hit else current.get("default_force_tier"),
                "use_mock": current.get("use_mock") if gray_hit else current.get("default_use_mock"),
                "api_model_name": current.get("api_model_name") if gray_hit else current.get("default_api_model_name"),
                "gray_hit": gray_hit,
            }

        registry = await self.get_model_registry("default")
        if registry:
            policy["model_registry_version"] = registry.get("version", 0)
            policy["active_model_version"] = registry.get("active_model_version")
            if registry.get("active_api_model_name") and not policy.get("api_model_name"):
                policy["api_model_name"] = registry.get("active_api_model_name")
            policy["registered_models"] = registry.get("models", [])
        else:
            policy["model_registry_version"] = 0
            policy["active_model_version"] = None
            policy["registered_models"] = []
        return policy
