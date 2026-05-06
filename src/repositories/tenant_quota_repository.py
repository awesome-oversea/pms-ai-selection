"""
租户配额 Repository
===================

提供 T6.4 最小模型预算与配额治理能力：
- 获取或创建租户配额
- 检查余额
- 扣减额度
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TenantQuotaRepository:
    COST_QUOTA_SCALE = Decimal("1000000")

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _upgrade_legacy_cost_quota(self, quota: Any) -> Any:
        if getattr(quota, "quota_type", None) != "llm_cost_usd":
            return quota
        limit_value = int(quota.limit_value or 0)
        used_value = int(quota.used_value or 0)
        if 0 < limit_value <= 1000 and used_value <= 1000:
            quota.limit_value = limit_value * int(self.COST_QUOTA_SCALE)
            quota.used_value = used_value * int(self.COST_QUOTA_SCALE)
            await self.session.flush()
        return quota

    @classmethod
    def _encode_amount(cls, quota_type: str, amount: float | int) -> int:
        value = Decimal(str(amount))
        if quota_type == "llm_cost_usd":
            return int((value * cls.COST_QUOTA_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @classmethod
    def _decode_amount(cls, quota_type: str, amount: float | int | None) -> float:
        value = Decimal(str(amount or 0))
        if quota_type == "llm_cost_usd":
            return float(value / cls.COST_QUOTA_SCALE)
        return float(value)

    async def list_quota_status(self, *, tenant_id: str) -> list[dict[str, Any]]:
        from src.models.models import TenantQuota

        tenant_uuid = UUID(str(tenant_id))
        result = await self.session.execute(
            select(TenantQuota).where(TenantQuota.tenant_id == tenant_uuid).order_by(TenantQuota.quota_type.asc())
        )
        items = list(result.scalars().all())
        return [
            {
                'quota_type': item.quota_type,
                'limit_value': self._decode_amount(item.quota_type, item.limit_value),
                'used_value': self._decode_amount(item.quota_type, item.used_value),
                'remaining': self._decode_amount(item.quota_type, (item.limit_value or 0) - (item.used_value or 0)),
                'reset_period': item.reset_period,
                'is_active': item.is_active,
            }
            for item in items
        ]

    async def get_or_create_quota(
        self,
        *,
        tenant_id: str,
        quota_type: str,
        default_limit: int = 100,
        reset_period: str = "monthly",
    ) -> Any:
        from src.models.models import TenantQuota

        tenant_uuid = UUID(str(tenant_id))
        result = await self.session.execute(
            select(TenantQuota).where(
                TenantQuota.tenant_id == tenant_uuid,
                TenantQuota.quota_type == quota_type,
                TenantQuota.is_active == True,  # noqa: E712
            )
        )
        quota = result.scalar_one_or_none()
        if quota is not None:
            return await self._upgrade_legacy_cost_quota(quota)

        quota = TenantQuota(
            tenant_id=tenant_uuid,
            quota_type=quota_type,
            limit_value=self._encode_amount(quota_type, default_limit),
            used_value=0,
            reset_period=reset_period,
            is_active=True,
        )
        self.session.add(quota)
        await self.session.flush()
        return quota

    async def check_quota(self, *, tenant_id: str, quota_type: str, amount: float, default_limit: int = 100) -> tuple[bool, Any, float]:
        quota = await self.get_or_create_quota(
            tenant_id=tenant_id,
            quota_type=quota_type,
            default_limit=default_limit,
        )
        requested_amount = self._encode_amount(quota_type, amount)
        remaining = int(quota.limit_value or 0) - int(quota.used_value or 0)
        return remaining >= requested_amount, quota, self._decode_amount(quota_type, remaining)

    async def consume_quota(self, *, tenant_id: str, quota_type: str, amount: float, default_limit: int = 100) -> Any:
        quota = await self.get_or_create_quota(
            tenant_id=tenant_id,
            quota_type=quota_type,
            default_limit=default_limit,
        )
        quota.used_value = int(quota.used_value or 0) + self._encode_amount(quota_type, amount)
        await self.session.flush()
        return quota
