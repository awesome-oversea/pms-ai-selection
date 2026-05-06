# ERP闭环集成设计方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D39-D44 ERP闭环集成(SCM/OMS/WMS)
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. 集成架构设计](#2-集成架构设计)
- [3. SCM集成设计](#3-scm集成设计)
- [4. OMS集成设计](#4-oms集成设计)
- [5. WMS集成设计](#5-wms集成设计)
- [6. 数据同步机制](#6-数据同步机制)
- [7. API接口设计](#7-api接口设计)

---

## 1. 概述

### 1.1 集成目标

实现AI选品系统与ERP系统的闭环集成，打通选品决策到供应链管理的全链路流程。

### 1.2 集成范围

| 系统 | 集成模块 | 数据流向 | 优先级 |
|------|---------|---------|--------|
| SCM | 供应商管理、采购订单 | 双向 | P0 |
| OMS | 订单管理、履约状态 | 双向 | P0 |
| WMS | 库存管理、出入库 | 双向 | P0 |
| CRM | 客户管理、反馈 | 单向读取 | P1 |
| FMS | 财务核算、成本 | 单向读取 | P1 |

### 1.3 集成原则

- **松耦合**: 通过API网关解耦，降低系统依赖
- **异步化**: 使用消息队列实现异步数据同步
- **幂等性**: 接口设计支持幂等，避免重复处理
- **可追溯**: 全链路日志记录，支持问题排查

---

## 2. 集成架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI选品系统 (PMS)                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    ERP Gateway                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ SCM      │ │ OMS      │ │ WMS      │ │ CRM/FMS  │   │   │
│  │  │ Adapter  │ │ Adapter  │ │ Adapter  │ │ Adapter  │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Message Queue (Kafka)                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ SCM      │ │ OMS      │ │ WMS      │ │ Event    │   │   │
│  │  │ Topic    │ │ Topic    │ │ Topic    │ │ Topic    │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ERP系统集群                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   SCM    │ │   OMS    │ │   WMS    │ │   CRM    │          │
│  │  System  │ │  System  │ │  System  │ │  System  │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 ERP Gateway设计

```python
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel

class ERPEvent(BaseModel):
    event_id: str
    event_type: str
    source: str
    target: str
    payload: dict[str, Any]
    timestamp: str
    correlation_id: Optional[str] = None

class BaseAdapter(ABC):
    system_name: str
    
    @abstractmethod
    async def send(self, event: ERPEvent) -> bool:
        pass
    
    @abstractmethod
    async def receive(self, event: ERPEvent) -> bool:
        pass
    
    @abstractmethod
    async def query(self, query: dict) -> dict:
        pass

class ERPGateway:
    def __init__(self):
        self.adapters: dict[str, BaseAdapter] = {}
        self.event_bus = KafkaEventBus()
    
    def register_adapter(self, adapter: BaseAdapter):
        self.adapters[adapter.system_name] = adapter
    
    async def send_event(self, event: ERPEvent) -> bool:
        adapter = self.adapters.get(event.target)
        if not adapter:
            raise ValueError(f"Unknown target system: {event.target}")
        
        success = await adapter.send(event)
        if success:
            await self.event_bus.publish(event)
        
        return success
    
    async def handle_event(self, event: ERPEvent):
        adapter = self.adapters.get(event.source)
        if adapter:
            await adapter.receive(event)
```

---

## 3. SCM集成设计

### 3.1 集成数据模型

```python
from enum import Enum
from datetime import datetime

class SupplierLevel(str, Enum):
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"

class Supplier(BaseModel):
    supplier_id: str
    name: str
    level: SupplierLevel
    contact: str
    phone: str
    email: str
    address: str
    categories: list[str]
    lead_time_days: int
    min_order_quantity: int
    payment_terms: str
    rating: float
    status: str

class PurchaseOrder(BaseModel):
    order_id: str
    supplier_id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_amount: float
    status: str
    order_date: datetime
    expected_delivery: datetime
    actual_delivery: Optional[datetime] = None
```

### 3.2 SCM Adapter实现

```python
class SCMAdapter(BaseAdapter):
    system_name = "scm"
    
    def __init__(self, config: SCMConfig):
        self.config = config
        self.client = SCMClient(config)
    
    async def send(self, event: ERPEvent) -> bool:
        if event.event_type == "create_purchase_order":
            return await self._create_purchase_order(event.payload)
        elif event.event_type == "update_supplier_score":
            return await self._update_supplier_score(event.payload)
        return False
    
    async def receive(self, event: ERPEvent) -> bool:
        if event.event_type == "order_status_changed":
            return await self._handle_order_status_change(event.payload)
        elif event.event_type == "supplier_updated":
            return await self._handle_supplier_update(event.payload)
        return False
    
    async def query(self, query: dict) -> dict:
        if query.get("type") == "supplier":
            return await self._query_supplier(query)
        elif query.get("type") == "purchase_order":
            return await self._query_purchase_order(query)
        return {}
    
    async def _create_purchase_order(self, data: dict) -> bool:
        order = PurchaseOrder(**data)
        result = await self.client.create_order(order)
        return result.get("success", False)
    
    async def _update_supplier_score(self, data: dict) -> bool:
        supplier_id = data.get("supplier_id")
        score = data.get("score")
        result = await self.client.update_score(supplier_id, score)
        return result.get("success", False)
    
    async def _query_supplier(self, query: dict) -> dict:
        supplier_id = query.get("supplier_id")
        supplier = await self.client.get_supplier(supplier_id)
        return supplier.dict() if supplier else {}
```

### 3.3 供应商推荐集成

```python
class SupplierRecommendation:
    def __init__(self, scm_adapter: SCMAdapter, llm_client: LLMClient):
        self.scm = scm_adapter
        self.llm = llm_client
    
    async def recommend(self, product_info: dict) -> list[dict]:
        suppliers = await self.scm.query({
            "type": "supplier",
            "category": product_info.get("category")
        })
        
        if not suppliers:
            return []
        
        scored_suppliers = []
        for supplier in suppliers:
            score = await self._calculate_score(supplier, product_info)
            scored_suppliers.append({
                **supplier,
                "recommendation_score": score
            })
        
        scored_suppliers.sort(key=lambda x: x["recommendation_score"], reverse=True)
        return scored_suppliers[:5]
    
    async def _calculate_score(self, supplier: dict, product_info: dict) -> float:
        weights = {
            "rating": 0.3,
            "lead_time": 0.2,
            "price_competitiveness": 0.25,
            "reliability": 0.25
        }
        
        rating_score = supplier.get("rating", 0) / 5.0
        
        lead_time = supplier.get("lead_time_days", 30)
        lead_time_score = max(0, 1 - lead_time / 60)
        
        price_score = await self._get_price_score(supplier, product_info)
        
        reliability_score = self._get_reliability_score(supplier)
        
        total_score = (
            weights["rating"] * rating_score +
            weights["lead_time"] * lead_time_score +
            weights["price_competitiveness"] * price_score +
            weights["reliability"] * reliability_score
        )
        
        return round(total_score, 2)
```

---

## 4. OMS集成设计

### 4.1 集成数据模型

```python
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"

class Order(BaseModel):
    order_id: str
    customer_id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_amount: float
    status: OrderStatus
    channel: str
    order_date: datetime
    ship_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    tracking_number: Optional[str] = None
```

### 4.2 OMS Adapter实现

```python
class OMSAdapter(BaseAdapter):
    system_name = "oms"
    
    def __init__(self, config: OMSConfig):
        self.config = config
        self.client = OMSClient(config)
    
    async def send(self, event: ERPEvent) -> bool:
        if event.event_type == "sync_product":
            return await self._sync_product(event.payload)
        return False
    
    async def receive(self, event: ERPEvent) -> bool:
        if event.event_type == "order_created":
            return await self._handle_order_created(event.payload)
        elif event.event_type == "order_status_changed":
            return await self._handle_order_status_changed(event.payload)
        return False
    
    async def query(self, query: dict) -> dict:
        if query.get("type") == "order":
            return await self._query_order(query)
        elif query.get("type") == "sales_stats":
            return await self._query_sales_stats(query)
        return {}
    
    async def _handle_order_created(self, data: dict) -> bool:
        order = Order(**data)
        await self._update_sales_metrics(order)
        return True
    
    async def _update_sales_metrics(self, order: Order):
        await update_product_sales(
            product_id=order.product_id,
            quantity=order.quantity,
            revenue=order.total_amount
        )
```

---

## 5. WMS集成设计

### 5.1 集成数据模型

```python
class InventoryStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    RESERVED = "reserved"

class Inventory(BaseModel):
    product_id: str
    warehouse_id: str
    quantity: int
    reserved_quantity: int
    available_quantity: int
    status: InventoryStatus
    last_updated: datetime

class StockMovement(BaseModel):
    movement_id: str
    product_id: str
    warehouse_id: str
    movement_type: str
    quantity: int
    reference_id: str
    timestamp: datetime
```

### 5.2 WMS Adapter实现

```python
class WMSAdapter(BaseAdapter):
    system_name = "wms"
    
    def __init__(self, config: WMSConfig):
        self.config = config
        self.client = WMSClient(config)
    
    async def send(self, event: ERPEvent) -> bool:
        if event.event_type == "reserve_inventory":
            return await self._reserve_inventory(event.payload)
        elif event.event_type == "release_inventory":
            return await self._release_inventory(event.payload)
        return False
    
    async def receive(self, event: ERPEvent) -> bool:
        if event.event_type == "inventory_updated":
            return await self._handle_inventory_update(event.payload)
        elif event.event_type == "stock_movement":
            return await self._handle_stock_movement(event.payload)
        return False
    
    async def query(self, query: dict) -> dict:
        if query.get("type") == "inventory":
            return await self._query_inventory(query)
        elif query.get("type") == "warehouse":
            return await self._query_warehouse(query)
        return {}
    
    async def check_availability(self, product_id: str, quantity: int) -> bool:
        inventory = await self.query({
            "type": "inventory",
            "product_id": product_id
        })
        
        available = inventory.get("available_quantity", 0)
        return available >= quantity
```

---

## 6. 数据同步机制

### 6.1 事件驱动同步

```python
class EventSynchronizer:
    def __init__(self, gateway: ERPGateway, kafka: KafkaClient):
        self.gateway = gateway
        self.kafka = kafka
    
    async def sync_supplier_data(self):
        event = ERPEvent(
            event_id=str(uuid.uuid4()),
            event_type="sync_request",
            source="pms",
            target="scm",
            payload={"entity": "supplier", "action": "full_sync"},
            timestamp=datetime.now().isoformat()
        )
        await self.gateway.send_event(event)
    
    async def sync_inventory_data(self):
        event = ERPEvent(
            event_id=str(uuid.uuid4()),
            event_type="sync_request",
            source="pms",
            target="wms",
            payload={"entity": "inventory", "action": "delta_sync"},
            timestamp=datetime.now().isoformat()
        )
        await self.gateway.send_event(event)
    
    async def handle_incoming_events(self):
        async for message in self.kafka.consume("erp-events"):
            event = ERPEvent(**message.value)
            await self.gateway.handle_event(event)
```

### 6.2 定时同步任务

```python
from apscheduler import AsyncScheduler

class SyncScheduler:
    def __init__(self, synchronizer: EventSynchronizer):
        self.sync = synchronizer
        self.scheduler = AsyncScheduler()
    
    async def start(self):
        self.scheduler.add_job(
            self.sync.sync_supplier_data,
            "cron",
            hour=2,
            minute=0
        )
        
        self.scheduler.add_job(
            self.sync.sync_inventory_data,
            "interval",
            minutes=30
        )
        
        await self.scheduler.start()
```

---

## 7. API接口设计

### 7.1 ERP集成接口

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/erp", tags=["erp-integration"])

@router.post("/sync/suppliers")
async def sync_suppliers():
    await sync_supplier_data()
    return {"status": "sync_started"}

@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str):
    adapter = get_scm_adapter()
    supplier = await adapter.query({
        "type": "supplier",
        "supplier_id": supplier_id
    })
    return supplier

@router.post("/purchase-orders")
async def create_purchase_order(order: PurchaseOrderCreate):
    event = ERPEvent(
        event_id=str(uuid.uuid4()),
        event_type="create_purchase_order",
        source="pms",
        target="scm",
        payload=order.dict(),
        timestamp=datetime.now().isoformat()
    )
    success = await get_gateway().send_event(event)
    return {"success": success, "order_id": order.order_id}

@router.get("/inventory/{product_id}")
async def get_inventory(product_id: str):
    adapter = get_wms_adapter()
    inventory = await adapter.query({
        "type": "inventory",
        "product_id": product_id
    })
    return inventory
```

---

## 附录

### A. 配置示例

```yaml
erp:
  scm:
    api_endpoint: "https://scm.example.com/api"
    api_key: "${SCM_API_KEY}"
    timeout: 30
  
  oms:
    api_endpoint: "https://oms.example.com/api"
    api_key: "${OMS_API_KEY}"
    timeout: 30
  
  wms:
    api_endpoint: "https://wms.example.com/api"
    api_key: "${WMS_API_KEY}"
    timeout: 30

kafka:
  bootstrap_servers: "kafka-1:9092,kafka-2:9092,kafka-3:9092"
  topics:
    erp_events: "erp-events"
    scm_events: "scm-events"
    oms_events: "oms-events"
    wms_events: "wms-events"
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
