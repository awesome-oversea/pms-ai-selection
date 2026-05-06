"""
WMS仓储 + CRM客户 + FMS财务管理系统
===================================

提供仓储、客户、财务管理能力(D71-D75):
    - WMS: 库存查询/入库出库/预警
    - CRM: 客户管理/RFM模型/分群
    - FMS: 成本核算/利润计算/发票

使用方式:
    from src.infrastructure.wms_crm_fms import WMSManager, CRMManager, FMSManager

    wms = WMSManager()
    inventory = await wms.get_inventory("SKU_001")

    crm = CRMManager()
    segment = await crm.segment_customers()

    fms = FMSManager()
    profit = await fms.calculate_profit("P001")
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class AlertLevel(StrEnum):
    """预警等级。"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertType(StrEnum):
    """预警类型。"""
    LOW_STOCK = "low_stock"
    OVERSTOCK = "overstock"
    SLOW_MOVING = "slow_moving"
    OUT_OF_STOCK = "out_of_stock"


class CustomerTier(StrEnum):
    """客户等级。"""
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class CustomerSegment(StrEnum):
    """客户分群。"""
    HIGH_VALUE = "high_value"
    MEDIUM_VALUE = "medium_value"
    LOW_VALUE = "low_value"
    ACTIVE = "active"
    DORMANT = "dormant"
    CHURNED = "churned"
    PRICE_SENSITIVE = "price_sensitive"
    QUALITY_FIRST = "quality_first"
    BRAND_LOYAL = "brand_loyal"


@dataclass
class Inventory:
    """库存(D71)。"""
    sku: str
    product_name: str
    warehouse_id: str
    total_quantity: int = 0
    available_quantity: int = 0
    in_transit_quantity: int = 0
    safety_stock: int = 10
    max_stock: int = 1000
    last_restock_date: str | None = None
    last_sale_date: str | None = None
    days_no_sale: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "product_name": self.product_name,
            "warehouse_id": self.warehouse_id,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "in_transit_quantity": self.in_transit_quantity,
            "safety_stock": self.safety_stock,
            "max_stock": self.max_stock,
            "last_restock_date": self.last_restock_date,
            "last_sale_date": self.last_sale_date,
            "days_no_sale": self.days_no_sale,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Alert:
    """库存预警(D72)。"""
    alert_id: str
    alert_type: AlertType
    alert_level: AlertLevel
    sku: str
    product_name: str
    message: str
    current_value: float
    threshold: float
    suggestion: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "alert_level": self.alert_level.value,
            "sku": self.sku,
            "product_name": self.product_name,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "suggestion": self.suggestion,
            "created_at": self.created_at,
            "acknowledged": self.acknowledged,
        }


@dataclass
class Customer:
    """客户(D73)。"""
    customer_id: str
    name: str
    email: str = ""
    phone: str = ""
    tier: CustomerTier = CustomerTier.BRONZE
    total_orders: int = 0
    total_spend: float = 0.0
    last_order_date: str | None = None
    tags: list[str] = field(default_factory=list)
    recency_days: int = 0
    frequency: int = 0
    monetary: float = 0.0
    rfm_score: float = 0.0
    segment: CustomerSegment = CustomerSegment.LOW_VALUE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def calculate_rfm(self) -> None:
        """计算RFM分数。"""
        r_score = max(5 - self.recency_days // 30, 1)
        f_score = min(self.frequency // 5 + 1, 5)
        m_score = min(int(self.monetary / 1000) + 1, 5)
        self.rfm_score = (r_score + f_score + m_score) / 3

    def determine_tier(self) -> CustomerTier:
        """确定客户等级。"""
        if self.total_spend >= 50000:
            return CustomerTier.PLATINUM
        elif self.total_spend >= 20000:
            return CustomerTier.GOLD
        elif self.total_spend >= 5000:
            return CustomerTier.SILVER
        return CustomerTier.BRONZE

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "tier": self.tier.value,
            "total_orders": self.total_orders,
            "total_spend": round(self.total_spend, 2),
            "last_order_date": self.last_order_date,
            "tags": self.tags,
            "recency_days": self.recency_days,
            "frequency": self.frequency,
            "monetary": round(self.monetary, 2),
            "rfm_score": round(self.rfm_score, 2),
            "segment": self.segment.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class FinancialRecord:
    """财务记录(D75)。"""
    record_id: str
    record_type: str
    product_id: str
    order_id: str | None
    amount: float
    category: str
    description: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "product_id": self.product_id,
            "order_id": self.order_id,
            "amount": round(self.amount, 2),
            "category": self.category,
            "description": self.description,
            "created_at": self.created_at,
        }


@dataclass
class ProfitSummary:
    """利润汇总。"""
    product_id: str
    product_name: str
    total_revenue: float = 0.0
    total_cost: float = 0.0
    gross_profit: float = 0.0
    profit_margin: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)

    def calculate(self) -> None:
        self.gross_profit = self.total_revenue - self.total_cost
        if self.total_revenue > 0:
            self.profit_margin = self.gross_profit / self.total_revenue

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "total_revenue": round(self.total_revenue, 2),
            "total_cost": round(self.total_cost, 2),
            "gross_profit": round(self.gross_profit, 2),
            "profit_margin": round(self.profit_margin, 4),
            "cost_breakdown": {k: round(v, 2) for k, v in self.cost_breakdown.items()},
        }


class WMSManager:
    """
    WMS仓储管理器(D71-D72)。

    功能:
        1. 库存查询(实时/可用/在途)
        2. 入库管理(采购/退货)
        3. 出库管理(销售/调拨)
        4. 库存预警(低库存/超储/滞销)
    """

    ALERT_RULES = [
        {"type": AlertType.LOW_STOCK, "condition": "available < safety_stock", "level": AlertLevel.HIGH},
        {"type": AlertType.OVERSTOCK, "condition": "available > max_stock * 1.5", "level": AlertLevel.MEDIUM},
        {"type": AlertType.SLOW_MOVING, "condition": "days_no_sale > 90", "level": AlertLevel.LOW},
        {"type": AlertType.OUT_OF_STOCK, "condition": "available == 0", "level": AlertLevel.HIGH},
    ]

    def __init__(self):
        self._inventory: dict[str, Inventory] = {}
        self._alerts: dict[str, Alert] = {}
        self._transactions: list[dict[str, Any]] = []
        self._stats = {
            "total_skus": 0,
            "total_quantity": 0,
            "alerts_count": 0,
        }
        logger.info("WMSManager初始化完成")

    async def create_inventory(
        self,
        sku: str,
        product_name: str,
        warehouse_id: str = "WH_001",
        total_quantity: int = 0,
        safety_stock: int = 10,
        max_stock: int = 1000,
    ) -> Inventory:
        """创建库存记录。"""
        inventory = Inventory(
            sku=sku,
            product_name=product_name,
            warehouse_id=warehouse_id,
            total_quantity=total_quantity,
            available_quantity=total_quantity,
            safety_stock=safety_stock,
            max_stock=max_stock,
        )
        self._inventory[sku] = inventory
        self._stats["total_skus"] = len(self._inventory)
        self._stats["total_quantity"] = sum(i.total_quantity for i in self._inventory.values())
        logger.info(f"创建库存: {sku} - {product_name}")
        return inventory

    async def get_inventory(self, sku: str) -> Inventory | None:
        return self._inventory.get(sku)

    async def list_inventory(self, warehouse_id: str | None = None) -> list[Inventory]:
        """列出库存。"""
        results = list(self._inventory.values())
        if warehouse_id:
            results = [i for i in results if i.warehouse_id == warehouse_id]
        return results

    async def stock_in(self, sku: str, quantity: int, reason: str = "采购入库") -> dict[str, Any]:
        """入库。"""
        inventory = self._inventory.get(sku)
        if not inventory:
            return {"success": False, "error": "SKU不存在"}

        inventory.total_quantity += quantity
        inventory.available_quantity += quantity
        inventory.last_restock_date = datetime.now(UTC).isoformat()
        inventory.updated_at = datetime.now(UTC).isoformat()

        transaction = {
            "transaction_id": f"TXN_{uuid.uuid4().hex[:8].upper()}",
            "sku": sku,
            "type": "stock_in",
            "quantity": quantity,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._transactions.append(transaction)
        self._stats["total_quantity"] = sum(i.total_quantity for i in self._inventory.values())

        logger.info(f"入库: {sku} +{quantity}")
        return {"success": True, "transaction": transaction}

    async def stock_out(self, sku: str, quantity: int, reason: str = "销售出库") -> dict[str, Any]:
        """出库。"""
        inventory = self._inventory.get(sku)
        if not inventory:
            return {"success": False, "error": "SKU不存在"}

        if inventory.available_quantity < quantity:
            return {"success": False, "error": "库存不足"}

        inventory.total_quantity -= quantity
        inventory.available_quantity -= quantity
        inventory.last_sale_date = datetime.now(UTC).isoformat()
        inventory.days_no_sale = 0
        inventory.updated_at = datetime.now(UTC).isoformat()

        transaction = {
            "transaction_id": f"TXN_{uuid.uuid4().hex[:8].upper()}",
            "sku": sku,
            "type": "stock_out",
            "quantity": -quantity,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._transactions.append(transaction)
        self._stats["total_quantity"] = sum(i.total_quantity for i in self._inventory.values())

        logger.info(f"出库: {sku} -{quantity}")
        return {"success": True, "transaction": transaction}

    async def check_alerts(self) -> list[Alert]:
        """检查库存预警(D72)。"""
        alerts = []
        for sku, inv in self._inventory.items():
            if inv.available_quantity == 0:
                alert = Alert(
                    alert_id=f"ALT_{uuid.uuid4().hex[:8].upper()}",
                    alert_type=AlertType.OUT_OF_STOCK,
                    alert_level=AlertLevel.HIGH,
                    sku=sku,
                    product_name=inv.product_name,
                    message=f"缺货: {inv.product_name}",
                    current_value=0,
                    threshold=inv.safety_stock,
                    suggestion="立即补货",
                )
                alerts.append(alert)
                self._alerts[alert.alert_id] = alert

            elif inv.available_quantity < inv.safety_stock:
                alert = Alert(
                    alert_id=f"ALT_{uuid.uuid4().hex[:8].upper()}",
                    alert_type=AlertType.LOW_STOCK,
                    alert_level=AlertLevel.HIGH,
                    sku=sku,
                    product_name=inv.product_name,
                    message=f"低库存: {inv.product_name} (当前{inv.available_quantity}, 安全库存{inv.safety_stock})",
                    current_value=inv.available_quantity,
                    threshold=inv.safety_stock,
                    suggestion=f"建议补货{inv.safety_stock - inv.available_quantity + 50}件",
                )
                alerts.append(alert)
                self._alerts[alert.alert_id] = alert

            elif inv.available_quantity > inv.max_stock * 1.5:
                alert = Alert(
                    alert_id=f"ALT_{uuid.uuid4().hex[:8].upper()}",
                    alert_type=AlertType.OVERSTOCK,
                    alert_level=AlertLevel.MEDIUM,
                    sku=sku,
                    product_name=inv.product_name,
                    message=f"超储: {inv.product_name}",
                    current_value=inv.available_quantity,
                    threshold=inv.max_stock,
                    suggestion="考虑促销清仓",
                )
                alerts.append(alert)
                self._alerts[alert.alert_id] = alert

            elif inv.days_no_sale > 90:
                alert = Alert(
                    alert_id=f"ALT_{uuid.uuid4().hex[:8].upper()}",
                    alert_type=AlertType.SLOW_MOVING,
                    alert_level=AlertLevel.LOW,
                    sku=sku,
                    product_name=inv.product_name,
                    message=f"滞销: {inv.product_name} ({inv.days_no_sale}天无销售)",
                    current_value=inv.days_no_sale,
                    threshold=90,
                    suggestion="考虑降价促销",
                )
                alerts.append(alert)
                self._alerts[alert.alert_id] = alert

        self._stats["alerts_count"] = len(self._alerts)
        return alerts

    async def acknowledge_alert(self, alert_id: str) -> Alert | None:
        """确认预警。"""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.acknowledged = True
        return alert

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "transactions_count": len(self._transactions),
        }


class CRMManager:
    """
    CRM客户管理器(D73-D74)。

    功能:
        1. 客户CRUD
        2. RFM模型计算
        3. 客户分群(K-Means简化版)
        4. 客户标签管理
    """

    def __init__(self):
        self._customers: dict[str, Customer] = {}
        self._stats = {
            "total_customers": 0,
            "by_tier": defaultdict(int),
            "by_segment": defaultdict(int),
        }
        logger.info("CRMManager初始化完成")

    async def create_customer(
        self,
        name: str,
        email: str = "",
        phone: str = "",
    ) -> Customer:
        """创建客户。"""
        customer_id = f"CUST_{uuid.uuid4().hex[:8].upper()}"
        customer = Customer(
            customer_id=customer_id,
            name=name,
            email=email,
            phone=phone,
        )
        self._customers[customer_id] = customer
        self._stats["total_customers"] = len(self._customers)
        self._stats["by_tier"][CustomerTier.BRONZE.value] += 1
        logger.info(f"创建客户: {customer_id} - {name}")
        return customer

    async def get_customer(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    async def update_customer_metrics(
        self,
        customer_id: str,
        recency_days: int | None = None,
        frequency: int | None = None,
        monetary: float | None = None,
    ) -> Customer | None:
        """更新客户指标。"""
        customer = self._customers.get(customer_id)
        if not customer:
            return None

        old_tier = customer.tier
        if recency_days is not None:
            customer.recency_days = recency_days
        if frequency is not None:
            customer.frequency = frequency
        if monetary is not None:
            customer.monetary = monetary
            customer.total_spend = monetary

        customer.calculate_rfm()
        customer.tier = customer.determine_tier()
        customer.updated_at = datetime.now(UTC).isoformat()

        if old_tier != customer.tier:
            self._stats["by_tier"][old_tier.value] -= 1
            self._stats["by_tier"][customer.tier.value] += 1

        return customer

    async def segment_customers(self) -> dict[str, list[str]]:
        """客户分群(D74)。"""
        segments: dict[str, list[str]] = defaultdict(list)

        for customer in self._customers.values():
            if customer.rfm_score >= 4:
                customer.segment = CustomerSegment.HIGH_VALUE
                customer.tags.append("高价值")
            elif customer.rfm_score >= 2.5:
                customer.segment = CustomerSegment.MEDIUM_VALUE
                customer.tags.append("中价值")
            else:
                customer.segment = CustomerSegment.LOW_VALUE
                customer.tags.append("低价值")

            if customer.recency_days <= 30:
                customer.tags.append("活跃")
            elif customer.recency_days <= 90:
                customer.tags.append("沉睡")
            else:
                customer.tags.append("流失风险")

            segments[customer.segment.value].append(customer.customer_id)
            self._stats["by_segment"][customer.segment.value] += 1

        return dict(segments)

    async def list_customers(
        self,
        tier: CustomerTier | None = None,
        segment: CustomerSegment | None = None,
        min_spend: float | None = None,
    ) -> list[Customer]:
        """列出客户。"""
        results = list(self._customers.values())
        if tier:
            results = [c for c in results if c.tier == tier]
        if segment:
            results = [c for c in results if c.segment == segment]
        if min_spend is not None:
            results = [c for c in results if c.total_spend >= min_spend]
        return sorted(results, key=lambda x: x.rfm_score, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_tier": dict(self._stats["by_tier"]),
            "by_segment": dict(self._stats["by_segment"]),
        }


class FMSManager:
    """
    FMS财务管理器(D75)。

    功能:
        1. 成本记录(采购/物流/平台)
        2. 收入记录
        3. 利润计算
        4. 发票管理
    """

    def __init__(self):
        self._records: dict[str, FinancialRecord] = {}
        self._invoices: dict[str, dict] = {}
        self._product_financials: dict[str, dict[str, float]] = defaultdict(lambda: {
            "revenue": 0.0,
            "purchase_cost": 0.0,
            "logistics_cost": 0.0,
            "platform_cost": 0.0,
            "other_cost": 0.0,
        })
        self._stats = {
            "total_revenue": 0.0,
            "total_cost": 0.0,
            "total_profit": 0.0,
            "records_count": 0,
        }
        logger.info("FMSManager初始化完成")

    async def record_cost(
        self,
        product_id: str,
        amount: float,
        category: str,
        description: str = "",
        order_id: str | None = None,
    ) -> FinancialRecord:
        """记录成本。"""
        record_id = f"COST_{uuid.uuid4().hex[:8].upper()}"
        record = FinancialRecord(
            record_id=record_id,
            record_type="cost",
            product_id=product_id,
            order_id=order_id,
            amount=amount,
            category=category,
            description=description,
        )
        self._records[record_id] = record

        pf = self._product_financials[product_id]
        if category == "purchase":
            pf["purchase_cost"] += amount
        elif category == "logistics":
            pf["logistics_cost"] += amount
        elif category == "platform":
            pf["platform_cost"] += amount
        else:
            pf["other_cost"] += amount

        self._stats["total_cost"] += amount
        self._stats["records_count"] = len(self._records)

        logger.info(f"记录成本: {product_id} {category} {amount}")
        return record

    async def record_revenue(
        self,
        product_id: str,
        amount: float,
        description: str = "",
        order_id: str | None = None,
    ) -> FinancialRecord:
        """记录收入。"""
        record_id = f"REV_{uuid.uuid4().hex[:8].upper()}"
        record = FinancialRecord(
            record_id=record_id,
            record_type="revenue",
            product_id=product_id,
            order_id=order_id,
            amount=amount,
            category="revenue",
            description=description,
        )
        self._records[record_id] = record

        self._product_financials[product_id]["revenue"] += amount
        self._stats["total_revenue"] += amount
        self._stats["records_count"] = len(self._records)

        logger.info(f"记录收入: {product_id} {amount}")
        return record

    async def calculate_profit(self, product_id: str, product_name: str = "") -> ProfitSummary:
        """计算利润。"""
        pf = self._product_financials[product_id]

        summary = ProfitSummary(
            product_id=product_id,
            product_name=product_name or product_id,
            total_revenue=pf["revenue"],
            total_cost=pf["purchase_cost"] + pf["logistics_cost"] + pf["platform_cost"] + pf["other_cost"],
            cost_breakdown={
                "purchase": pf["purchase_cost"],
                "logistics": pf["logistics_cost"],
                "platform": pf["platform_cost"],
                "other": pf["other_cost"],
            },
        )
        summary.calculate()

        self._stats["total_profit"] = self._stats["total_revenue"] - self._stats["total_cost"]

        return summary

    async def get_financial_records(
        self,
        product_id: str | None = None,
        record_type: str | None = None,
        category: str | None = None,
    ) -> list[FinancialRecord]:
        """获取财务记录。"""
        results = list(self._records.values())
        if product_id:
            results = [r for r in results if r.product_id == product_id]
        if record_type:
            results = [r for r in results if r.record_type == record_type]
        if category:
            results = [r for r in results if r.category == category]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "profit_margin": round(
                self._stats["total_profit"] / max(self._stats["total_revenue"], 1), 4
            ),
        }
