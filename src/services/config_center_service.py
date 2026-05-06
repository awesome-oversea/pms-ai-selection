"""
配置中心与 Feature Flag 服务
============================

为 T7.6 提供最小可用能力：
- 动态配置发布/查询/回滚
- Feature Flag 发布/查询/解析/回滚
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from src.repositories.tenant_config_repository import TenantConfigRepository

_MEMORY_CONFIG_STORE: dict[tuple[str, str], dict[str, Any]] = {}


class ConfigCenterService:
    def __init__(self, session, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = TenantConfigRepository(session)

    def _store_key(self, config_key: str) -> tuple[str, str]:
        return str(self.tenant_id), config_key

    def _read_memory_payload(self, config_key: str) -> dict[str, Any] | None:
        payload = _MEMORY_CONFIG_STORE.get(self._store_key(config_key))
        return deepcopy(payload) if payload is not None else None

    def _write_memory_payload(self, config_key: str, payload: dict[str, Any]) -> None:
        _MEMORY_CONFIG_STORE[self._store_key(config_key)] = deepcopy(payload)

    def _memory_items(self) -> list[dict[str, Any]]:
        tenant_id = str(self.tenant_id)
        return [
            {"config_key": key, "config_value": deepcopy(payload)}
            for (store_tenant_id, key), payload in _MEMORY_CONFIG_STORE.items()
            if store_tenant_id == tenant_id
        ]

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
            rollback = getattr(self.session, "rollback", None)
            if rollback is not None:
                await rollback()
            return None

    async def build_operations_status(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        try:
            configs = await self.repo.list_configs(tenant_id=self.tenant_id, limit=200)
            items = [
                {
                    "config_key": item.config_key,
                    "config_value": deepcopy(item.config_value or {}),
                }
                for item in configs
            ]
        except Exception:
            items = []
        if not items:
            items = self._memory_items()

        config_items = [item for item in items if (item.get("config_key") or "").startswith("config:")]
        feature_flags = [item for item in items if (item.get("config_key") or "").startswith("config:feature_flag:")]
        recent_versions = []
        for item in items[:10]:
            current = (item.get("config_value") or {}).get("current", {})
            recent_versions.append(
                {
                    "config_key": item.get("config_key"),
                    "version": current.get("version", 0),
                    "description": current.get("description", ""),
                }
            )
        return {
            "tenant_id": self.tenant_id,
            "config_total": len(config_items),
            "feature_flag_total": len(feature_flags),
            "recent_versions": recent_versions,
            "environment_overrides": {
                "local": "default",
                "test": "config-map override",
                "preprod": "release config override",
                "prod": "strict change workflow",
            },
        }

    @staticmethod
    def _config_key(key: str) -> str:
        return f"config:{key}"

    @staticmethod
    def _flag_key(key: str) -> str:
        return f"feature_flag:{key}"

    async def publish_config(self, config_key: str, value: dict[str, Any], description: str = "") -> dict[str, Any]:
        full_key = self._config_key(config_key)
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
            "description": description,
            "value": value,
        }
        await self._persist_payload(full_key, {"current": current, "history": history[-20:]})
        return deepcopy(current)

    async def rollback_config(self, config_key: str) -> dict[str, Any] | None:
        full_key = self._config_key(config_key)
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

    async def get_config(self, config_key: str) -> dict[str, Any] | None:
        payload = await self._load_payload(self._config_key(config_key))
        if payload is None:
            return None
        current = payload.get("current")
        return deepcopy(current) if current else None

    async def publish_feature_flag(
        self,
        flag_key: str,
        *,
        enabled: bool,
        rollout_percent: int = 0,
        tenant_whitelist: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        payload = {
            "enabled": enabled,
            "rollout_percent": rollout_percent,
            "tenant_whitelist": tenant_whitelist or [],
        }
        return await self.publish_config(self._flag_key(flag_key), payload, description)

    async def rollback_feature_flag(self, flag_key: str) -> dict[str, Any] | None:
        return await self.rollback_config(self._flag_key(flag_key))

    async def get_feature_flag(self, flag_key: str) -> dict[str, Any] | None:
        return await self.get_config(self._flag_key(flag_key))

    async def resolve_feature_flag(self, flag_key: str) -> dict[str, Any]:
        current = await self.get_feature_flag(flag_key)
        if current is None:
            return {"enabled": False, "gray_hit": False, "version": 0}

        payload = current.get("value", {})
        whitelist = set(payload.get("tenant_whitelist", []))
        rollout_percent = int(payload.get("rollout_percent", 0))
        gray_hit = False
        if self.tenant_id in whitelist:
            gray_hit = True
        elif rollout_percent > 0:
            bucket = int(hashlib.md5(f"{self.tenant_id}:{flag_key}".encode()).hexdigest(), 16) % 100
            gray_hit = bucket < rollout_percent

        return {
            "version": current.get("version", 0),
            "enabled": bool(payload.get("enabled", False)) and (gray_hit or rollout_percent == 0 or self.tenant_id in whitelist),
            "gray_hit": gray_hit,
            "rollout_percent": rollout_percent,
            "tenant_whitelist": list(whitelist),
        }
