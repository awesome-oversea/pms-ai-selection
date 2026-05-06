from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import ERPSystemType


class ErpIntegrationRepository:
    def __init__(self, session: AsyncSession, tenant_id: str | None = None):
        self.session = session
        self.tenant_id = tenant_id

    def _matches_tenant(self, config: Any) -> bool:
        if not self.tenant_id:
            return True
        extra = config.extra_config or {}
        return extra.get("tenant_id") in (None, self.tenant_id)

    async def get_config(self, system_type: ERPSystemType, name: str = "default") -> Any | None:
        from src.models.models import ErpConfig

        result = await self.session.execute(
            select(ErpConfig)
            .where(
                ErpConfig.system_type == system_type,
                ErpConfig.name == name,
                ErpConfig.is_active == True,  # noqa: E712
            )
            .order_by(ErpConfig.created_at.desc())
        )
        for config in result.scalars().all():
            if self._matches_tenant(config):
                return config
        return None

    async def create_or_update_config(
        self,
        *,
        system_type: ERPSystemType,
        name: str,
        api_endpoint: str,
        api_key: str | None,
        secret_key: str | None,
        extra_config: dict[str, Any] | None = None,
    ) -> Any:
        from src.models.models import ErpConfig

        config = await self.get_config(system_type=system_type, name=name)
        merged_extra = dict(extra_config or {})
        if self.tenant_id:
            merged_extra["tenant_id"] = self.tenant_id
        if config is None:
            config = ErpConfig(
                system_type=system_type,
                name=name,
                api_endpoint=api_endpoint,
                api_key=api_key,
                secret_key=secret_key,
                extra_config=merged_extra,
                is_active=True,
            )
            self.session.add(config)
        else:
            config.api_endpoint = api_endpoint
            config.api_key = api_key
            config.secret_key = secret_key
            config.extra_config = merged_extra
            config.is_active = True
        await self.session.flush()
        return config

    async def create_sync_log(self, *, config_id: str, sync_type: str, entity_type: str) -> Any:
        from src.models.models import ErpSyncLog

        now = datetime.now(UTC)
        log = ErpSyncLog(
            config_id=UUID(str(config_id)),
            sync_type=sync_type,
            entity_type=entity_type,
            status="running",
            items_total=0,
            items_success=0,
            items_failed=0,
            started_at=now,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def update_sync_log(self, log_id: str, **fields: Any) -> Any:
        log = await self.get_sync_log(log_id)
        if log is None:
            raise ValueError(f"同步日志不存在: {log_id}")
        for key, value in fields.items():
            setattr(log, key, value)
        await self.session.flush()
        return log

    async def get_sync_log(self, log_id: str) -> Any | None:
        from src.models.models import ErpSyncLog

        result = await self.session.execute(select(ErpSyncLog).where(ErpSyncLog.id == UUID(str(log_id))))
        return result.scalar_one_or_none()

    async def get_sync_log_with_config(self, log_id: str) -> tuple[Any | None, Any | None]:
        from src.models.models import ErpConfig, ErpSyncLog

        result = await self.session.execute(
            select(ErpSyncLog, ErpConfig)
            .join(ErpConfig, ErpSyncLog.config_id == ErpConfig.id)
            .where(ErpSyncLog.id == UUID(str(log_id)))
        )
        row = result.first()
        if row is None:
            return None, None
        log, config = row
        if not self._matches_tenant(config):
            return None, None
        return log, config

    async def list_sync_logs(self, system_type: ERPSystemType, limit: int = 20, name: str | None = None) -> list[tuple[Any, Any]]:
        from src.models.models import ErpConfig, ErpSyncLog

        stmt = (
            select(ErpSyncLog, ErpConfig)
            .join(ErpConfig, ErpSyncLog.config_id == ErpConfig.id)
            .where(ErpConfig.system_type == system_type)
            .order_by(ErpSyncLog.created_at.desc())
            .limit(limit)
        )
        if name is not None:
            stmt = stmt.where(ErpConfig.name == name)

        result = await self.session.execute(stmt)
        rows = []
        for log, config in result.all():
            if self._matches_tenant(config):
                rows.append((log, config))
        return rows

    async def upsert_product_by_external_id(self, data: dict[str, Any]) -> tuple[Any, bool]:
        from src.models.models import Product

        platform = data.get("platform", "oms")
        external_product_id = str(data["external_product_id"])
        result = await self.session.execute(
            select(Product).where(
                Product.platform == platform,
                Product.external_product_id == external_product_id,
                Product.is_deleted == False,  # noqa: E712
            )
        )
        product = result.scalar_one_or_none()
        created = False
        if product is None:
            product = Product(
                name=data.get("name") or f"OMS-{external_product_id}",
                brand=data.get("brand"),
                platform=platform,
                external_product_id=external_product_id,
                asin=data.get("asin"),
                price=data.get("price"),
                rating=data.get("rating"),
                review_count=data.get("review_count"),
                sales_rank=data.get("sales_rank"),
                image_url=data.get("image_url"),
                product_url=data.get("product_url"),
                attributes=data.get("attributes") or {},
            )
            self.session.add(product)
            created = True
        else:
            product.name = data.get("name") or product.name
            product.brand = data.get("brand")
            product.asin = data.get("asin")
            product.price = data.get("price")
            product.rating = data.get("rating")
            product.review_count = data.get("review_count")
            product.sales_rank = data.get("sales_rank")
            product.image_url = data.get("image_url")
            product.product_url = data.get("product_url")
            product.attributes = data.get("attributes") or product.attributes
        await self.session.flush()
        return product, created

    async def list_products_for_export(self, limit: int = 100) -> list[Any]:
        from src.models.models import Product

        result = await self.session.execute(
            select(Product)
            .where(Product.is_deleted == False)  # noqa: E712
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
