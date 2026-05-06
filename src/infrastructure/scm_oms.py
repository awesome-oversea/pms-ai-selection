"""
SCM供应链管理 + OMS订单管理
===========================

提供供应链和订单管理能力(D66-D70):
    - 供应商CRUD与评分
    - 1688 API模拟对接
    - 采购订单管理
    - 订单状态机
    - 物流轨迹追踪

使用方式:
    from src.infrastructure.scm_oms import SCMManager, OMSManager

    scm = SCMManager()
    supplier = await scm.create_supplier(...)

    oms = OMSManager()
    order = await oms.create_order(...)
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class SupplierLevel(StrEnum):
    """供应商等级。"""
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    NEW = "new"


class PriceLevel(StrEnum):
    """价格等级。"""
    LOW = "low"
    MID = "mid"
    HIGH = "high"


class OrderStatus(StrEnum):
    """订单状态(D69)。"""
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    WAREHOUSED = "warehoused"
    CANCELLED = "cancelled"


@dataclass
class Supplier:
    """供应商(D68)。"""
    supplier_id: str
    name: str
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    moq: int = 10
    lead_time_days: int = 7
    quality_score: float = 0.0
    price_level: PriceLevel = PriceLevel.MID
    level: SupplierLevel = SupplierLevel.NEW
    total_orders: int = 0
    on_time_rate: float = 0.0
    categories: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def calculate_level(self) -> SupplierLevel:
        """计算供应商等级。"""
        score = self.quality_score * 0.4 + self.on_time_rate * 0.3 + min(self.total_orders / 100, 1) * 0.3
        if score >= 0.8:
            return SupplierLevel.GOLD
        elif score >= 0.6:
            return SupplierLevel.SILVER
        elif score >= 0.4:
            return SupplierLevel.BRONZE
        return SupplierLevel.NEW

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "moq": self.moq,
            "lead_time_days": self.lead_time_days,
            "quality_score": round(self.quality_score, 2),
            "price_level": self.price_level.value,
            "level": self.level.value,
            "total_orders": self.total_orders,
            "on_time_rate": round(self.on_time_rate, 2),
            "categories": self.categories,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PurchaseOrder:
    """采购订单(D69)。"""
    order_id: str
    supplier_id: str
    product_name: str
    sku: str
    quantity: int
    unit_price: float
    total_amount: float
    status: OrderStatus = OrderStatus.PENDING_PAYMENT
    payment_deadline: str | None = None
    paid_at: str | None = None
    shipped_at: str | None = None
    delivered_at: str | None = None
    tracking_number: str | None = None
    logistics_company: str | None = None
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "supplier_id": self.supplier_id,
            "product_name": self.product_name,
            "sku": self.sku,
            "quantity": self.quantity,
            "unit_price": round(self.unit_price, 2),
            "total_amount": round(self.total_amount, 2),
            "status": self.status.value,
            "payment_deadline": self.payment_deadline,
            "paid_at": self.paid_at,
            "shipped_at": self.shipped_at,
            "delivered_at": self.delivered_at,
            "tracking_number": self.tracking_number,
            "logistics_company": self.logistics_company,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class LogisticsTrack:
    """物流轨迹。"""
    tracking_number: str
    logistics_company: str
    status: str
    current_location: str
    estimated_delivery: str
    timeline: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracking_number": self.tracking_number,
            "logistics_company": self.logistics_company,
            "status": self.status,
            "current_location": self.current_location,
            "estimated_delivery": self.estimated_delivery,
            "timeline": self.timeline,
        }


class API1688Mock:
    """
    1688 API模拟(D67)。

    提供的接口:
        - product_search: 商品搜索
        - supplier_info: 供应商详情
        - order_create: 创建采购单
        - order_status: 订单状态查询
    """

    def __init__(self, app_key: str = "", app_secret: str = ""):
        self._app_key = app_key
        self._app_secret = app_secret
        self._products: dict[str, dict] = {}
        self._suppliers: dict[str, dict] = {}
        self._init_mock_data()
        logger.info("1688 API模拟初始化完成")

    def _init_mock_data(self) -> None:
        """初始化模拟数据。"""
        for i in range(10):
            pid = f"1688_PROD_{i:04d}"
            self._products[pid] = {
                "product_id": pid,
                "title": f"户外储能电源{i+1}号",
                "price": round(500 + random.uniform(-100, 200), 2),
                "moq": random.randint(5, 50),
                "supplier_id": f"SUP_{random.randint(1000, 9999)}",
                "category": "储能设备",
                "images": [f"https://img.1688.com/{pid}.jpg"],
            }

        for i in range(5):
            sid = f"SUP_{1000 + i * 100}"
            self._suppliers[sid] = {
                "supplier_id": sid,
                "name": f"供应商{chr(65 + i)}",
                "contact": f"联系人{chr(65 + i)}",
                "phone": f"138{random.randint(10000000, 99999999)}",
                "rating": round(random.uniform(3.5, 5.0), 1),
                "trade_count": random.randint(100, 10000),
                "response_rate": round(random.uniform(0.8, 1.0), 2),
            }

    async def product_search(self, keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """商品搜索。"""
        await asyncio.sleep(random.uniform(0.05, 0.15))
        results = [
            p for p in self._products.values()
            if keyword.lower() in p["title"].lower()
        ]
        total = len(results)
        start = (page - 1) * page_size
        return {
            "success": True,
            "total": total,
            "page": page,
            "page_size": page_size,
            "products": results[start : start + page_size],
        }

    async def supplier_info(self, supplier_id: str) -> dict[str, Any]:
        """供应商详情。"""
        await asyncio.sleep(random.uniform(0.03, 0.08))
        supplier = self._suppliers.get(supplier_id)
        if supplier:
            return {"success": True, "supplier": supplier}
        return {"success": False, "error": "供应商不存在"}

    async def order_create(self, order_data: dict[str, Any]) -> dict[str, Any]:
        """创建采购单。"""
        await asyncio.sleep(random.uniform(0.1, 0.2))
        order_id = f"PO_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        return {
            "success": True,
            "order_id": order_id,
            "status": "created",
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def order_status(self, order_id: str) -> dict[str, Any]:
        """订单状态查询。"""
        await asyncio.sleep(random.uniform(0.02, 0.05))
        return {
            "success": True,
            "order_id": order_id,
            "status": random.choice(list(OrderStatus)).value,
            "updated_at": datetime.now(UTC).isoformat(),
        }


class SCMManager:
    """
    SCM供应链管理器(D66-D68)。

    功能:
        1. 供应商CRUD
        2. 供应商评分算法
        3. 采购询价/比价
        4. 采购订单管理
    """

    def __init__(self, api_1688: API1688Mock | None = None):
        self._api = api_1688 or API1688Mock()
        self._suppliers: dict[str, Supplier] = {}
        self._orders: dict[str, PurchaseOrder] = {}
        self._stats = {
            "suppliers_count": 0,
            "orders_count": 0,
            "total_purchase_amount": 0.0,
        }
        logger.info("SCMManager初始化完成")

    async def create_supplier(
        self,
        name: str,
        contact_person: str = "",
        moq: int = 10,
        lead_time_days: int = 7,
        price_level: PriceLevel = PriceLevel.MID,
        categories: list[str] | None = None,
    ) -> Supplier:
        """创建供应商。"""
        supplier_id = f"SUP_{uuid.uuid4().hex[:8].upper()}"
        supplier = Supplier(
            supplier_id=supplier_id,
            name=name,
            contact_person=contact_person,
            moq=moq,
            lead_time_days=lead_time_days,
            price_level=price_level,
            categories=categories or [],
        )
        self._suppliers[supplier_id] = supplier
        self._stats["suppliers_count"] = len(self._suppliers)
        logger.info(f"创建供应商: {supplier_id} - {name}")
        return supplier

    async def get_supplier(self, supplier_id: str) -> Supplier | None:
        return self._suppliers.get(supplier_id)

    async def list_suppliers(
        self,
        category: str | None = None,
        level: SupplierLevel | None = None,
        min_score: float | None = None,
    ) -> list[Supplier]:
        """列出供应商。"""
        results = list(self._suppliers.values())
        if category:
            results = [s for s in results if category in s.categories]
        if level:
            results = [s for s in results if s.level == level]
        if min_score is not None:
            results = [s for s in results if s.quality_score >= min_score]
        return sorted(results, key=lambda x: x.quality_score, reverse=True)

    async def update_supplier_score(
        self,
        supplier_id: str,
        quality_score: float | None = None,
        on_time_rate: float | None = None,
    ) -> Supplier | None:
        """更新供应商评分。"""
        supplier = self._suppliers.get(supplier_id)
        if not supplier:
            return None
        if quality_score is not None:
            supplier.quality_score = min(max(quality_score, 0), 1)
        if on_time_rate is not None:
            supplier.on_time_rate = min(max(on_time_rate, 0), 1)
        supplier.level = supplier.calculate_level()
        supplier.updated_at = datetime.now(UTC).isoformat()
        return supplier

    async def create_purchase_order(
        self,
        supplier_id: str,
        product_name: str,
        sku: str,
        quantity: int,
        unit_price: float,
        notes: str = "",
    ) -> PurchaseOrder:
        """创建采购订单。"""
        order_id = f"PO_{uuid.uuid4().hex[:8].upper()}"
        total_amount = quantity * unit_price
        payment_deadline = (datetime.now(UTC) + timedelta(days=3)).isoformat()

        order = PurchaseOrder(
            order_id=order_id,
            supplier_id=supplier_id,
            product_name=product_name,
            sku=sku,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            payment_deadline=payment_deadline,
            notes=notes,
        )

        self._orders[order_id] = order
        self._stats["orders_count"] = len(self._orders)
        self._stats["total_purchase_amount"] += total_amount

        supplier = self._suppliers.get(supplier_id)
        if supplier:
            supplier.total_orders += 1

        logger.info(f"创建采购订单: {order_id}")
        return order

    async def get_order(self, order_id: str) -> PurchaseOrder | None:
        return self._orders.get(order_id)

    async def list_orders(
        self,
        supplier_id: str | None = None,
        status: OrderStatus | None = None,
    ) -> list[PurchaseOrder]:
        """列出订单。"""
        results = list(self._orders.values())
        if supplier_id:
            results = [o for o in results if o.supplier_id == supplier_id]
        if status:
            results = [o for o in results if o.status == status]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    async def search_products(self, keyword: str) -> dict[str, Any]:
        """搜索1688商品。"""
        return await self._api.product_search(keyword)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "total_purchase_amount": round(self._stats["total_purchase_amount"], 2),
        }


class OMSManager:
    """
    OMS订单管理器(D69)。

    功能:
        1. 订单状态机
        2. 物流轨迹追踪
        3. 订单状态同步
    """

    STATUS_TRANSITIONS = {
        OrderStatus.PENDING_PAYMENT: [OrderStatus.PAID, OrderStatus.CANCELLED],
        OrderStatus.PAID: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
        OrderStatus.SHIPPED: [OrderStatus.IN_TRANSIT],
        OrderStatus.IN_TRANSIT: [OrderStatus.DELIVERED],
        OrderStatus.DELIVERED: [OrderStatus.WAREHOUSED],
        OrderStatus.WAREHOUSED: [],
        OrderStatus.CANCELLED: [],
    }

    def __init__(self):
        self._orders: dict[str, PurchaseOrder] = {}
        self._tracks: dict[str, LogisticsTrack] = {}
        self._status_history: dict[str, list[dict]] = {}
        logger.info("OMSManager初始化完成")

    def register_order(self, order: PurchaseOrder) -> None:
        """注册订单到OMS。"""
        self._orders[order.order_id] = order
        self._status_history[order.order_id] = [{
            "status": order.status.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "note": "订单创建",
        }]

    async def update_order_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        note: str = "",
    ) -> PurchaseOrder | None:
        """更新订单状态(状态机)。"""
        order = self._orders.get(order_id)
        if not order:
            return None

        allowed = self.STATUS_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            logger.warning(f"状态转换不允许: {order.status} -> {new_status}")
            return None

        old_status = order.status
        order.status = new_status
        order.updated_at = datetime.now(UTC).isoformat()

        if new_status == OrderStatus.PAID:
            order.paid_at = datetime.now(UTC).isoformat()
        elif new_status == OrderStatus.SHIPPED:
            order.shipped_at = datetime.now(UTC).isoformat()
            order.tracking_number = f"SF{random.randint(1000000000, 9999999999)}"
            order.logistics_company = "顺丰速运"
        elif new_status == OrderStatus.DELIVERED:
            order.delivered_at = datetime.now(UTC).isoformat()

        self._status_history[order_id].append({
            "status": new_status.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "note": note or f"状态从 {old_status.value} 更新为 {new_status.value}",
        })

        logger.info(f"订单状态更新: {order_id} {old_status.value} -> {new_status.value}")
        return order

    async def get_tracking(self, order_id: str) -> LogisticsTrack | None:
        """获取物流轨迹。"""
        order = self._orders.get(order_id)
        if not order or not order.tracking_number:
            return None

        if order_id in self._tracks:
            return self._tracks[order_id]

        track = LogisticsTrack(
            tracking_number=order.tracking_number,
            logistics_company=order.logistics_company or "未知",
            status="运输中",
            current_location=random.choice(["深圳", "广州", "上海", "北京"]),
            estimated_delivery=(datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%d"),
            timeline=[
                {
                    "time": (datetime.now(UTC) - timedelta(hours=i * 6)).strftime("%Y-%m-%d %H:%M"),
                    "location": random.choice(["深圳集散中心", "广州转运中心", "上海分拨中心"]),
                    "status": random.choice(["已揽收", "运输中", "到达分拨中心"]),
                }
                for i in range(5)
            ],
        )
        self._tracks[order_id] = track
        return track

    async def get_status_history(self, order_id: str) -> list[dict]:
        """获取状态历史。"""
        return self._status_history.get(order_id, [])

    def get_stats(self) -> dict[str, Any]:
        status_counts = {}
        for order in self._orders.values():
            status = order.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "total_orders": len(self._orders),
            "status_distribution": status_counts,
        }
