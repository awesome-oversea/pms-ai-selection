from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import AIFeatureToggle
from src.models.models import AIFeatureConfig

logger = get_logger(__name__)


class AIFeatureToggleService:
    """
    AI功能开关服务。

    职责:
    - 管理AI功能开关(全局/租户级)
    - 支持灰度发布(按租户百分比)
    - 提供功能开关查询接口
    - 记录开关变更审计日志
    """

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}

    async def is_feature_enabled(
        self,
        feature_key: str | AIFeatureToggle,
        *,
        tenant_id: str | None = None,
        default: bool = False,
    ) -> bool:
        effective_tenant = tenant_id or self.tenant_id
        key = feature_key.value if isinstance(feature_key, AIFeatureToggle) else feature_key

        config = await self._find_config(key, tenant_id=effective_tenant)
        if config is None:
            config = await self._find_config(key, tenant_id=None)
        if config is None:
            return default

        if not config.is_enabled:
            return False

        if effective_tenant and config.rollout_percentage is not None:
            if config.rollout_percentage >= 100:
                return True
            if config.rollout_percentage <= 0:
                return False
            hash_val = hash(f"{key}:{effective_tenant}") % 100
            return hash_val < config.rollout_percentage

        return config.is_enabled

    async def get_feature_config(
        self,
        feature_key: str | AIFeatureToggle,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any] | None:
        effective_tenant = tenant_id or self.tenant_id
        key = feature_key.value if isinstance(feature_key, AIFeatureToggle) else feature_key

        config = await self._find_config(key, tenant_id=effective_tenant)
        if config is None:
            config = await self._find_config(key, tenant_id=None)
        if config is None:
            return None

        return self._serialize_config(config)

    async def set_feature_config(
        self,
        feature_key: str | AIFeatureToggle,
        *,
        is_enabled: bool | None = None,
        rollout_percentage: int | None = None,
        config_overrides: dict[str, Any] | None = None,
        description: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        effective_tenant = tenant_id or self.tenant_id
        key = feature_key.value if isinstance(feature_key, AIFeatureToggle) else feature_key

        config = await self._find_config(key, tenant_id=effective_tenant)
        if config is None:
            config = AIFeatureConfig(
                tenant_id=UUID(str(effective_tenant)) if effective_tenant else uuid4(),
                feature_key=key,
                is_enabled=is_enabled if is_enabled is not None else True,
                rollout_percentage=rollout_percentage,
                config_overrides=config_overrides,
                description=description,
                created_by=UUID(str(self.actor.get("user_id"))) if self.actor.get("user_id") else None,
            )
            self.session.add(config)
        else:
            if is_enabled is not None:
                config.is_enabled = is_enabled
            if rollout_percentage is not None:
                config.rollout_percentage = rollout_percentage
            if config_overrides is not None:
                config.config_overrides = config_overrides
            if description is not None:
                config.description = description

        await self.session.flush()
        return self._serialize_config(config)

    async def enable_feature(
        self,
        feature_key: str | AIFeatureToggle,
        *,
        tenant_id: str | None = None,
        rollout_percentage: int | None = None,
    ) -> dict[str, Any]:
        return await self.set_feature_config(
            feature_key,
            is_enabled=True,
            rollout_percentage=rollout_percentage,
            tenant_id=tenant_id,
        )

    async def disable_feature(
        self,
        feature_key: str | AIFeatureToggle,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.set_feature_config(
            feature_key,
            is_enabled=False,
            tenant_id=tenant_id,
        )

    async def list_features(
        self,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        effective_tenant = tenant_id or self.tenant_id
        query = select(AIFeatureConfig)

        if effective_tenant:
            query = query.where(
                (AIFeatureConfig.tenant_id == UUID(str(effective_tenant)))
                | (AIFeatureConfig.tenant_id.is_(None))
            )
        else:
            query = query.where(AIFeatureConfig.tenant_id.is_(None))

        result = await self.session.execute(query.order_by(AIFeatureConfig.feature_key))
        configs = result.scalars().all()

        return {
            "tenant_id": effective_tenant,
            "features": [self._serialize_config(c) for c in configs],
            "total": len(configs),
        }

    async def _find_config(self, feature_key: str, *, tenant_id: str | None = None) -> AIFeatureConfig | None:
        query = select(AIFeatureConfig).where(AIFeatureConfig.feature_key == feature_key)
        if tenant_id:
            query = query.where(AIFeatureConfig.tenant_id == UUID(str(tenant_id)))
        else:
            query = query.where(AIFeatureConfig.tenant_id.is_(None))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _serialize_config(config: AIFeatureConfig) -> dict[str, Any]:
        return {
            "id": str(config.id),
            "tenant_id": str(config.tenant_id) if config.tenant_id else None,
            "feature_key": config.feature_key,
            "is_enabled": config.is_enabled,
            "rollout_percentage": config.rollout_percentage,
            "config_overrides": config.config_overrides,
            "description": config.description,
            "created_by": str(config.created_by) if config.created_by else None,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }
