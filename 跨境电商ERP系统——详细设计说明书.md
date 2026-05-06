# 跨境电商ERP系统——详细设计说明书

> **版本**：v1.0
> **创建日期**：2026-04-23
> **项目代号**：Project Aegis - ERP Module
> **文档状态**：正式版
> **参考文档**：
>
> - AI选品系统PMS详细设计说明书 v1.0
> - 架构设计方案 v3.0
> - 微服务接口清单 v1.0

------

## 目录

1. **ERP系统概述**
   - 1.1 系统定位
   - 1.2 系统边界
   - 1.3 与AI选品系统的关系
   - 1.4 核心业务流程
2. **ERP领域模型设计**
   - 2.1 订单域 (OMS)
   - 2.2 仓储域 (WMS)
   - 2.3 供应链域 (SCM)
   - 2.4 客户域 (CRM)
   - 2.5 财务域 (FMS)
   - 2.6 商业智能域 (BI)
3. **数据库详细设计**
   - 3.1 OMS数据库
   - 3.2 WMS数据库
   - 3.3 SCM数据库
   - 3.4 CRM数据库
   - 3.5 FMS数据库
   - 3.6 BI数据库
4. **API接口详细设计**
   - 4.1 OMS接口
   - 4.2 WMS接口
   - 4.3 SCM接口
   - 4.4 CRM接口
   - 4.5 FMS接口
   - 4.6 BI接口
5. **CDC数据同步设计**
   - 5.1 CDC架构
   - 5.2 OMS CDC配置
   - 5.3 CRM CDC配置
   - 5.4 数据格式规范
6. **与AI选品系统集成设计**
   - 6.1 集成架构
   - 6.2 数据输入（AI感知）
   - 6.3 数据输出（AI驱动）
   - 6.4 闭环反馈设计
7. **部署与运维**
   - 7.1 部署架构
   - 7.2 高可用配置
   - 7.3 监控告警

------

## 1. ERP系统概述

### 1.1 系统定位

ERP系统是跨境电商企业的核心业务操作系统，负责订单管理、仓储物流、供应链协同、客户关系、财务核算和商业智能分析。

在AI选品系统PMS的整体架构中，ERP系统扮演着**执行层**和**数据源**的双重角色：





| 角色       | 说明                                                         |
| :--------- | :----------------------------------------------------------- |
| **执行层** | 接收AI选品系统的决策指令，执行采购、仓储、上架等业务操作     |
| **数据源** | 为AI选品系统提供历史销售、库存、成本、客户反馈等真实业务数据 |

### 1.2 系统边界

text

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          ERP系统边界                                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              AI选品系统 (PMS)                                                 │  │
│  │                                                                                              │  │
│  │  选品决策 → 产品定义 → 采购建议 → 定价策略 → 风险评估                                            │  │
│  └───────────────────────────────┬─────────────────────────────────────────────────────────────┘  │
│                                  │ 采纳执行                                                       │
│                                  ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              ERP系统                                                         │  │
│  │                                                                                              │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │  │
│  │  │   OMS    │───▶│   WMS    │───▶│   SCM    │───▶│   CRM    │───▶│   FMS    │───▶│    BI    │ │  │
│  │  │ (订单)   │    │ (仓储)   │    │ (供应链) │    │ (客户)   │    │ (财务)   │    │ (智能)   │ │  │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘ │  │
│  │       │               │               │               │               │               │       │  │
│  └───────┼───────────────┼───────────────┼───────────────┼───────────────┼───────────────┼───────┘  │
│          │               │               │               │               │               │          │
│          ▼               ▼               ▼               ▼               ▼               ▼          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              数据回流 (CDC)                                                  │  │
│  │                                                                                              │  │
│  │  OMS订单数据 → CRM评价数据 → FMS成本利润数据 → BI KPI数据                                        │  │
│  └───────────────────────────────────────────────┬─────────────────────────────────────────────┘  │
│                                                  │                                                │
│                                                  ▼                                                │
│                                          ┌─────────────┐                                         │
│                                          │    Kafka    │                                         │
│                                          │  (消息总线) │                                         │
│                                          └─────────────┘                                         │
│                                                  │                                                │
│                                                  ▼                                                │
│                                    ┌───────────────────────┐                                    │
│                                    │   AI选品系统 (PMS)    │                                    │
│                                    │   数据中台 → 特征工程  │                                    │
│                                    └───────────────────────┘                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```



### 1.3 与AI选品系统的关系





| ERP模块 | 为AI选品提供的数据                       | 接收AI选品的指令     |
| :------ | :--------------------------------------- | :------------------- |
| **OMS** | 历史销量、订单明细、转化率、退款数据     | 创建Listing草稿      |
| **WMS** | 实时库存、库龄、周转率、库容利用率       | 预留库容             |
| **SCM** | 供应商交期、质量评分、采购价格趋势       | 创建采购单、触发询价 |
| **CRM** | 客户评价、客诉文本、退换货原因、用户画像 | -                    |
| **FMS** | 头程运费、关税、FBA费用、广告费、毛利率  | -                    |
| **BI**  | 历史选品KPI、广告转化率、销售趋势报表    | -                    |

### 1.4 核心业务流程

text

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ERP核心业务流程                                                    │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  1. 选品采纳                                                                                        │
│     AI选品系统输出选品建议 ──▶ 运营人员采纳 ──▶ 触发ERP执行                                            │
│                                                                                                    │
│  2. 采购执行                                                                                        │
│     SCM创建采购单 ──▶ 供应商确认 ──▶ 物流跟踪 ──▶ WMS入库                                             │
│                                                                                                    │
│  3. 上架销售                                                                                        │
│     WMS库存就绪 ──▶ OMS创建Listing ──▶ 平台销售 ──▶ OMS订单记录                                       │
│                                                                                                    │
│  4. 履约交付                                                                                        │
│     OMS订单 ──▶ WMS拣货出库 ──▶ 物流发货 ──▶ 客户签收                                                 │
│                                                                                                    │
│  5. 售后服务                                                                                        │
│     CRM客户反馈 ──▶ 评价分析 ──▶ 客诉处理 ──▶ 退换货管理                                               │
│                                                                                                    │
│  6. 财务核算                                                                                        │
│     FMS成本归集 ──▶ 利润计算 ──▶ BI报表 ──▶ 反哺AI选品                                                │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```



------

## 2. ERP领域模型设计

### 2.1 订单域 (OMS)

#### 2.1.1 领域概述

**职责**：管理订单全生命周期，包括订单创建、支付、履约、退款等。

**核心实体**：Order、OrderItem、Listing、Refund、Promotion

#### 2.1.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Listing      │────▶│     Order       │────▶│   OrderItem     │
│                 │     │                 │     │                 │
│ • listing_id(PK)│     │ • order_id (PK) │     │ • item_id (PK)  │
│ • asin          │     │ • listing_id(FK)│     │ • order_id (FK) │
│ • title         │     │ • customer_id   │     │ • asin          │
│ • price         │     │ • total_amount  │     │ • quantity      │
│ • quantity      │     │ • currency      │     │ • unit_price    │
│ • status        │     │ • status        │     │ • total_price   │
│ • platform      │     │ • order_date    │     │ • tax_amount    │
│ • created_at    │     │ • created_at    │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   Refund    │ │  Shipment   │ │  Promotion  │
            │             │ │             │ │             │
            │ • refund_id │ │ • shipment  │ │ • promo_id  │
            │ • order_id  │ │   _id(PK)   │ │ • name      │
            │ • amount    │ │ • order_id  │ │ • type      │
            │ • reason    │ │ • carrier   │ │ • discount  │
            │ • status    │ │ • tracking  │ │ • start_date│
            └─────────────┘ │ • status    │ │ • end_date  │
                            └─────────────┘ └─────────────┘
```



#### 2.1.3 核心聚合

python

```
@dataclass
class Order:
    """订单聚合根"""
    order_id: str
    listing_id: str
    customer_id: str
    tenant_id: str
    platform: str  # Amazon, TikTok, Shopee
    marketplace: str  # US, EU, JP
    items: List[OrderItem]
    total_amount: Decimal
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    order_date: datetime
    shipment: Optional[Shipment]
    refund: Optional[Refund]
    created_at: datetime
    updated_at: datetime
    
    def calculate_total(self) -> Decimal:
        """计算订单总额"""
        return sum(item.total_price for item in self.items) + self.tax_amount
    
    def can_refund(self) -> bool:
        """是否可退款"""
        return self.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]
    
    def can_cancel(self) -> bool:
        """是否可取消"""
        return self.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]

@dataclass
class OrderItem:
    """订单项"""
    item_id: str
    order_id: str
    asin: str
    sku: str
    title: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    tax_amount: Decimal
    fulfillment_type: str  # FBA, FBM
```



#### 2.1.4 状态机

text

```
                    ┌─────────┐
                    │ pending │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
                    │confirmed│
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │cancelled│    │processing│    │  on_hold│
    └─────────┘    └────┬────┘    └─────────┘
                         │
                         ▼
                    ┌─────────┐
                    │ shipped │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
                    │delivered│
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │completed│    │refunding│    │ returned│
    └─────────┘    └────┬────┘    └─────────┘
                         │
                         ▼
                    ┌─────────┐
                    │refunded │
                    └─────────┘
```



### 2.2 仓储域 (WMS)

#### 2.2.1 领域概述

**职责**：管理仓库库存、入库出库、库位管理、库存盘点。

**核心实体**：Warehouse、Inventory、InboundOrder、OutboundOrder、StorageLocation

#### 2.2.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Warehouse     │────▶│ StorageLocation │────▶│   Inventory     │
│                 │     │                 │     │                 │
│ • warehouse_id  │     │ • location_id   │     │ • inventory_id  │
│ • name          │     │ • warehouse_id  │     │ • location_id   │
│ • address       │     │ • zone          │     │ • asin          │
│ • capacity      │     │ • aisle         │     │ • sku           │
│ • utilization   │     │ • shelf         │     │ • quantity      │
│ • status        │     │ • bin           │     │ • available_qty │
└─────────────────┘     │ • capacity      │     │ • reserved_qty  │
                        └─────────────────┘     │ • damaged_qty   │
                                                 │ • last_updated  │
                                                 └────────┬────────┘
                                                          │
                            ┌─────────────────────────────┼─────────────────────────────┐
                            │                             │                             │
                            ▼                             ▼                             ▼
                    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
                    │  InboundOrder   │     │  OutboundOrder  │     │InventoryMovement│
                    │                 │     │                 │     │                 │
                    │ • inbound_id    │     │ • outbound_id   │     │ • movement_id   │
                    │ • warehouse_id  │     │ • warehouse_id  │     │ • inventory_id  │
                    │ • supplier_id   │     │ • order_id      │     │ • type          │
                    │ • expected_date │     │ • customer_id   │     │ • quantity      │
                    │ • status        │     │ • carrier       │     │ • before_qty    │
                    │ • items         │     │ • tracking_no   │     │ • after_qty     │
                    └─────────────────┘     │ • status        │     │ • reference     │
                                            └─────────────────┘     │ • created_at    │
                                                                    └─────────────────┘
```



#### 2.2.3 核心聚合

python

```
@dataclass
class Inventory:
    """库存聚合根"""
    inventory_id: str
    tenant_id: str
    warehouse_id: str
    location_id: str
    asin: str
    sku: str
    fnsku: str
    quantity: int
    available_quantity: int
    reserved_quantity: int
    damaged_quantity: int
    inbound_quantity: int
    unit_cost: Decimal
    total_value: Decimal
    last_received_date: datetime
    last_shipped_date: datetime
    days_in_stock: int
    turnover_rate: float
    status: InventoryStatus
    created_at: datetime
    updated_at: datetime
    
    def can_fulfill(self, requested_qty: int) -> bool:
        """是否可满足订单"""
        return self.available_quantity >= requested_qty
    
    def reserve(self, quantity: int) -> None:
        """预留库存"""
        if not self.can_fulfill(quantity):
            raise InsufficientInventoryError()
        self.reserved_quantity += quantity
        self.available_quantity -= quantity
    
    def release(self, quantity: int) -> None:
        """释放预留"""
        self.reserved_quantity -= quantity
        self.available_quantity += quantity
    
    def is_low_stock(self, threshold: int = 10) -> bool:
        """是否低库存"""
        return self.available_quantity <= threshold
    
    def is_overstock(self, threshold: int = 90) -> bool:
        """是否滞销（库龄超过阈值）"""
        return self.days_in_stock >= threshold

@dataclass
class Warehouse:
    """仓库聚合根"""
    warehouse_id: str
    tenant_id: str
    name: str
    type: str  # FBA, 海外仓, 自建仓
    country: str
    address: str
    total_capacity: int  # 立方米
    used_capacity: int
    utilization_rate: float
    status: str
    locations: List[StorageLocation]
    
    def can_accept_inbound(self, volume: int) -> bool:
        """是否可接收入库"""
        return (self.used_capacity + volume) <= self.total_capacity * 0.9
```



### 2.3 供应链域 (SCM)

#### 2.3.1 领域概述

**职责**：管理供应商、采购订单、采购询价、供应商评估。

**核心实体**：Supplier、PurchaseOrder、Quote、SupplierScore

#### 2.3.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Supplier     │────▶│ PurchaseOrder   │────▶│    POItem       │
│                 │     │                 │     │                 │
│ • supplier_id   │     │ • po_id (PK)    │     │ • item_id (PK)  │
│ • name          │     │ • supplier_id   │     │ • po_id (FK)    │
│ • country       │     │ • tenant_id     │     │ • asin          │
│ • contact       │     │ • status        │     │ • quantity      │
│ • credit_rating │     │ • total_amount  │     │ • unit_price    │
│ • lead_time     │     │ • currency      │     │ • total_price   │
│ • moq           │     │ • order_date    │     │ • expected_date │
│ • status        │     │ • expected_date │     │ • received_qty  │
└────────┬────────┘     │ • created_at    │     └─────────────────┘
         │              └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│     Quote       │     │ SupplierScore   │
│                 │     │                 │
│ • quote_id      │     │ • score_id      │
│ • supplier_id   │     │ • supplier_id   │
│ • product_spec  │     │ • quality_score │
│ • unit_price    │     │ • delivery_score│
│ • moq           │     │ • price_score   │
│ • lead_time     │     │ • overall_score │
│ • valid_until   │     │ • evaluated_at  │
└─────────────────┘     └─────────────────┘
```



#### 2.3.3 核心聚合

python

```
@dataclass
class PurchaseOrder:
    """采购单聚合根"""
    po_id: str
    supplier_id: str
    tenant_id: str
    po_number: str
    items: List[POItem]
    total_amount: Decimal
    currency: str
    status: POStatus
    payment_terms: str
    shipping_terms: str
    expected_delivery_date: datetime
    actual_delivery_date: Optional[datetime]
    notes: str
    created_by: str
    approved_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    def calculate_total(self) -> Decimal:
        """计算总额"""
        return sum(item.total_price for item in self.items)
    
    def can_approve(self) -> bool:
        """是否可审批"""
        return self.status == POStatus.DRAFT
    
    def can_receive(self) -> bool:
        """是否可收货"""
        return self.status in [POStatus.APPROVED, POStatus.IN_TRANSIT]
    
    def receive_item(self, item_id: str, quantity: int) -> None:
        """收货"""
        item = next(i for i in self.items if i.item_id == item_id)
        item.received_quantity += quantity
        
        if all(i.received_quantity >= i.quantity for i in self.items):
            self.status = POStatus.RECEIVED
            self.actual_delivery_date = datetime.utcnow()

@dataclass
class Supplier:
    """供应商聚合根"""
    supplier_id: str
    tenant_id: str
    name: str
    company_name: str
    country: str
    city: str
    address: str
    contact_person: str
    contact_phone: str
    contact_email: str
    credit_rating: str  # A, B, C, D
    lead_time_days: int
    moq: int
    payment_terms: str
    qualification_docs: List[str]
    product_categories: List[str]
    status: str
    scores: List[SupplierScore]
    created_at: datetime
    updated_at: datetime
    
    def get_overall_score(self) -> float:
        """获取综合评分"""
        if not self.scores:
            return 0.0
        return sum(s.overall_score for s in self.scores) / len(self.scores)
```



### 2.4 客户域 (CRM)

#### 2.4.1 领域概述

**职责**：管理客户信息、评价、客诉、退换货。

**核心实体**：Customer、Review、Complaint、Return

#### 2.4.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Customer     │────▶│     Review      │────▶│   ReviewImage   │
│                 │     │                 │     │                 │
│ • customer_id   │     │ • review_id     │     │ • image_id      │
│ • platform_id   │     │ • customer_id   │     │ • review_id     │
│ • name          │     │ • asin          │     │ • url           │
│ • email         │     │ • order_id      │     │ • type          │
│ • country       │     │ • rating        │     └─────────────────┘
│ • segments      │     │ • title         │
│ • total_orders  │     │ • text          │
│ • total_spent   │     │ • sentiment     │
│ • created_at    │     │ • verified      │
└────────┬────────┘     │ • helpful_votes │
         │              │ • created_at    │
         │              └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│   Complaint     │     │    Return       │
│                 │     │                 │
│ • complaint_id  │     │ • return_id     │
│ • customer_id   │     │ • order_id      │
│ • order_id      │     │ • customer_id   │
│ • asin          │     │ • asin          │
│ • type          │     │ • reason        │
│ • description   │     │ • status        │
│ • severity      │     │ • refund_amount │
│ • status        │     │ • created_at    │
│ • resolution    │     └─────────────────┘
└─────────────────┘
```



#### 2.4.3 核心聚合

python

```
@dataclass
class Review:
    """评价聚合根"""
    review_id: str
    tenant_id: str
    customer_id: str
    order_id: str
    asin: str
    platform: str
    rating: int  # 1-5
    title: str
    text: str
    sentiment_score: float  # -1 到 1
    sentiment_label: str  # positive, neutral, negative
    pain_points: List[str]
    keywords: List[str]
    verified_purchase: bool
    helpful_votes: int
    images: List[str]
    reply_text: Optional[str]
    reply_date: Optional[datetime]
    created_at: datetime
    
    def is_negative(self) -> bool:
        """是否差评"""
        return self.rating <= 2 or self.sentiment_label == "negative"
    
    def is_positive(self) -> bool:
        """是否好评"""
        return self.rating >= 4 and self.sentiment_label == "positive"
    
    def extract_pain_points(self) -> List[str]:
        """提取痛点"""
        pain_keywords = {
            "充电": ["充电慢", "充电口", "续航短"],
            "质量": ["坏了", "故障", "质量差", "做工"],
            "噪音": ["噪音", "声音大", "吵"],
            "重量": ["重", "笨重", "不便携"],
            "发热": ["发热", "烫", "过热"],
            "售后": ["客服", "售后", "退货慢"]
        }
        
        points = []
        for category, keywords in pain_keywords.items():
            for keyword in keywords:
                if keyword in self.text:
                    points.append({"category": category, "keyword": keyword})
                    break
        
        return points

@dataclass
class Complaint:
    """客诉聚合根"""
    complaint_id: str
    tenant_id: str
    customer_id: str
    order_id: str
    asin: str
    complaint_type: str  # quality, delivery, description, service
    description: str
    severity: str  # low, medium, high, critical
    status: str  # open, investigating, resolved, closed
    resolution: Optional[str]
    resolution_date: Optional[datetime]
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    def escalate(self) -> None:
        """升级"""
        if self.severity == "critical":
            self.severity = "critical"
        else:
            severity_map = {"low": "medium", "medium": "high", "high": "critical"}
            self.severity = severity_map.get(self.severity, "critical")
```



### 2.5 财务域 (FMS)

#### 2.5.1 领域概述

**职责**：管理成本核算、利润分析、费用管理、财务报表。

**核心实体**：CostBreakdown、ProfitStatement、Expense、Budget

#### 2.5.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  CostBreakdown  │────▶│ ProfitStatement │────▶│    Expense      │
│                 │     │                 │     │                 │
│ • cost_id       │     │ • statement_id  │     │ • expense_id    │
│ • asin          │     │ • asin          │     │ • tenant_id     │
│ • bom_cost      │     │ • period        │     │ • type          │
│ • shipping_cost │     │ • revenue       │     │ • amount        │
│ • fba_fees      │     │ • total_cost    │     │ • currency      │
│ • tariff        │     │ • gross_profit  │     │ • period        │
│ • advertising   │     │ • gross_margin  │     │ • status        │
│ • other_costs   │     │ • net_profit    │     │ • created_at    │
│ • total_cost    │     │ • net_margin    │     └─────────────────┘
│ • period        │     │ • roi           │
│ • created_at    │     │ • created_at    │
└─────────────────┘     └─────────────────┘
```



#### 2.5.3 核心聚合

python

```
@dataclass
class CostBreakdown:
    """成本分解聚合根"""
    cost_id: str
    tenant_id: str
    asin: str
    sku: str
    period: str  # YYYY-MM
    bom_cost: Decimal  # 物料成本
    shipping_cost: Decimal  # 头程运费
    fba_fees: Decimal  # FBA费用
    tariff: Decimal  # 关税
    advertising_cost: Decimal  # 广告费
    storage_cost: Decimal  # 仓储费
    return_cost: Decimal  # 退货成本
    other_costs: Decimal  # 其他费用
    total_cost: Decimal
    currency: str
    created_at: datetime
    
    def calculate_total(self) -> Decimal:
        """计算总成本"""
        return (self.bom_cost + self.shipping_cost + self.fba_fees + 
                self.tariff + self.advertising_cost + self.storage_cost + 
                self.return_cost + self.other_costs)

@dataclass
class ProfitStatement:
    """利润表聚合根"""
    statement_id: str
    tenant_id: str
    asin: str
    period: str
    revenue: Decimal  # 销售收入
    refund_amount: Decimal  # 退款金额
    net_revenue: Decimal  # 净收入
    total_cost: Decimal  # 总成本
    gross_profit: Decimal  # 毛利
    gross_margin: float  # 毛利率
    operating_expenses: Decimal  # 运营费用
    net_profit: Decimal  # 净利润
    net_margin: float  # 净利率
    roi: float  # 投资回报率
    units_sold: int
    avg_selling_price: Decimal
    currency: str
    created_at: datetime
    
    def calculate_metrics(self) -> None:
        """计算指标"""
        self.net_revenue = self.revenue - self.refund_amount
        self.gross_profit = self.net_revenue - self.total_cost
        self.gross_margin = float(self.gross_profit / self.net_revenue) if self.net_revenue > 0 else 0
        self.net_profit = self.gross_profit - self.operating_expenses
        self.net_margin = float(self.net_profit / self.net_revenue) if self.net_revenue > 0 else 0
        self.roi = float(self.net_profit / self.total_cost) if self.total_cost > 0 else 0
```



### 2.6 商业智能域 (BI)

#### 2.6.1 领域概述

**职责**：提供KPI指标、销售趋势报表、选品绩效分析。

**核心实体**：KPI、SalesTrend、SelectionPerformance、Dashboard

#### 2.6.2 实体关系图

text

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│      KPI        │     │  SalesTrend     │     │SelectionPerformance│
│                 │     │                 │     │                 │
│ • kpi_id        │     │ • trend_id      │     │ • perf_id       │
│ • metric_name   │     │ • asin          │     │ • task_id       │
│ • metric_value  │     │ • category      │     │ • hit_rate      │
│ • target_value  │     │ • period        │     │ • adoption_rate │
│ • period        │     │ • sales_qty     │     │ • avg_roi       │
│ • dimension     │     │ • revenue       │     │ • accuracy      │
│ • created_at    │     │ • growth_rate   │     │ • period        │
└─────────────────┘     │ • trend         │     │ • created_at    │
                        └─────────────────┘     └─────────────────┘
```



#### 2.6.3 核心聚合

python

```
@dataclass
class SelectionPerformance:
    """选品绩效聚合根"""
    perf_id: str
    tenant_id: str
    task_id: str
    period: str
    total_recommendations: int
    adopted_count: int
    adoption_rate: float
    hit_count: int  # 达到ROI目标的商品数
    hit_rate: float
    avg_actual_roi: float
    avg_predicted_roi: float
    prediction_accuracy: float
    total_revenue: Decimal
    total_profit: Decimal
    created_at: datetime
    
    def calculate_accuracy(self) -> float:
        """计算预测准确度"""
        if self.avg_predicted_roi == 0:
            return 0.0
        return 1 - abs(self.avg_actual_roi - self.avg_predicted_roi) / self.avg_predicted_roi

@dataclass
class KPI:
    """KPI聚合根"""
    kpi_id: str
    tenant_id: str
    metric_name: str
    metric_value: float
    target_value: float
    period: str
    dimension: Dict[str, str]  # 维度：品类、市场、时间等
    trend: List[float]  # 历史趋势
    created_at: datetime
    
    def achievement_rate(self) -> float:
        """达成率"""
        return self.metric_value / self.target_value if self.target_value > 0 else 0
    
    def trend_direction(self) -> str:
        """趋势方向"""
        if len(self.trend) < 2:
            return "stable"
        return "up" if self.trend[-1] > self.trend[0] else "down"
```



------

## 3. 数据库详细设计

### 3.1 OMS数据库

sql

```
-- 订单表
CREATE TABLE oms.orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    listing_id UUID REFERENCES oms.listings(listing_id),
    customer_id VARCHAR(100) NOT NULL,
    platform VARCHAR(20) NOT NULL,
    marketplace VARCHAR(10) NOT NULL,
    order_number VARCHAR(100) UNIQUE NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0,
    shipping_amount DECIMAL(12,2) DEFAULT 0,
    discount_amount DECIMAL(12,2) DEFAULT 0,
    currency VARCHAR(10) DEFAULT 'USD',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payment_status VARCHAR(20) DEFAULT 'pending',
    fulfillment_status VARCHAR(20) DEFAULT 'pending',
    order_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_tenant ON oms.orders(tenant_id);
CREATE INDEX idx_orders_customer ON oms.orders(customer_id);
CREATE INDEX idx_orders_status ON oms.orders(status);
CREATE INDEX idx_orders_date ON oms.orders(order_date DESC);
CREATE INDEX idx_orders_platform ON oms.orders(platform, marketplace);

-- 订单项表
CREATE TABLE oms.order_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES oms.orders(order_id) ON DELETE CASCADE,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    title VARCHAR(500),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    total_price DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0,
    fulfillment_type VARCHAR(10) DEFAULT 'FBA',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_items_order ON oms.order_items(order_id);
CREATE INDEX idx_order_items_asin ON oms.order_items(asin);

-- Listing表
CREATE TABLE oms.listings (
    listing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    asin VARCHAR(20),
    sku VARCHAR(100),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    bullet_points TEXT[],
    price DECIMAL(12,2) NOT NULL,
    quantity INTEGER DEFAULT 0,
    images TEXT[],
    category VARCHAR(100),
    platform VARCHAR(20) NOT NULL,
    marketplace VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_listings_tenant ON oms.listings(tenant_id);
CREATE INDEX idx_listings_asin ON oms.listings(asin);
CREATE INDEX idx_listings_status ON oms.listings(status);

-- 退款表
CREATE TABLE oms.refunds (
    refund_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES oms.orders(order_id),
    refund_amount DECIMAL(12,2) NOT NULL,
    reason VARCHAR(200),
    status VARCHAR(20) DEFAULT 'pending',
    approved_by UUID,
    processed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_refunds_order ON oms.refunds(order_id);

-- 发货表
CREATE TABLE oms.shipments (
    shipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES oms.orders(order_id),
    carrier VARCHAR(50),
    tracking_number VARCHAR(100),
    shipping_method VARCHAR(50),
    estimated_delivery TIMESTAMP,
    actual_delivery TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_shipments_order ON oms.shipments(order_id);
CREATE INDEX idx_shipments_tracking ON oms.shipments(tracking_number);
```



### 3.2 WMS数据库

sql

```
-- 仓库表
CREATE TABLE wms.warehouses (
    warehouse_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,
    country VARCHAR(10) NOT NULL,
    address TEXT,
    total_capacity DECIMAL(10,2),
    used_capacity DECIMAL(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 库存表
CREATE TABLE wms.inventory (
    inventory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id UUID NOT NULL REFERENCES wms.warehouses(warehouse_id),
    tenant_id UUID NOT NULL,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    fnsku VARCHAR(100),
    quantity INTEGER NOT NULL DEFAULT 0,
    available_quantity INTEGER DEFAULT 0,
    reserved_quantity INTEGER DEFAULT 0,
    damaged_quantity INTEGER DEFAULT 0,
    inbound_quantity INTEGER DEFAULT 0,
    unit_cost DECIMAL(12,2),
    last_received_date TIMESTAMP,
    last_shipped_date TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(warehouse_id, asin)
);

CREATE INDEX idx_inventory_warehouse ON wms.inventory(warehouse_id);
CREATE INDEX idx_inventory_asin ON wms.inventory(asin);
CREATE INDEX idx_inventory_tenant ON wms.inventory(tenant_id);

-- 入库单表
CREATE TABLE wms.inbound_orders (
    inbound_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id UUID NOT NULL REFERENCES wms.warehouses(warehouse_id),
    tenant_id UUID NOT NULL,
    supplier_id UUID,
    po_id UUID,
    expected_date TIMESTAMP,
    actual_date TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 入库单项表
CREATE TABLE wms.inbound_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbound_id UUID NOT NULL REFERENCES wms.inbound_orders(inbound_id) ON DELETE CASCADE,
    asin VARCHAR(20) NOT NULL,
    expected_quantity INTEGER NOT NULL,
    received_quantity INTEGER DEFAULT 0,
    unit_cost DECIMAL(12,2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 出库单表
CREATE TABLE wms.outbound_orders (
    outbound_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id UUID NOT NULL REFERENCES wms.warehouses(warehouse_id),
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    carrier VARCHAR(50),
    tracking_number VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    shipped_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 库存移动记录表
CREATE TABLE wms.inventory_movements (
    movement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID NOT NULL REFERENCES wms.inventory(inventory_id),
    type VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    before_quantity INTEGER NOT NULL,
    after_quantity INTEGER NOT NULL,
    reference_type VARCHAR(20),
    reference_id UUID,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_movements_inventory ON wms.inventory_movements(inventory_id);
CREATE INDEX idx_movements_created ON wms.inventory_movements(created_at DESC);
```



### 3.3 SCM数据库

sql

```
-- 供应商表
CREATE TABLE scm.suppliers (
    supplier_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    company_name VARCHAR(500),
    country VARCHAR(10),
    city VARCHAR(100),
    address TEXT,
    contact_person VARCHAR(100),
    contact_phone VARCHAR(50),
    contact_email VARCHAR(200),
    credit_rating VARCHAR(5),
    lead_time_days INTEGER,
    moq INTEGER,
    payment_terms VARCHAR(100),
    product_categories TEXT[],
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_suppliers_tenant ON scm.suppliers(tenant_id);
CREATE INDEX idx_suppliers_status ON scm.suppliers(status);

-- 采购单表
CREATE TABLE scm.purchase_orders (
    po_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL REFERENCES scm.suppliers(supplier_id),
    tenant_id UUID NOT NULL,
    po_number VARCHAR(100) UNIQUE NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'draft',
    payment_terms VARCHAR(100),
    shipping_terms VARCHAR(100),
    expected_delivery_date TIMESTAMP,
    actual_delivery_date TIMESTAMP,
    notes TEXT,
    created_by UUID,
    approved_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_po_supplier ON scm.purchase_orders(supplier_id);
CREATE INDEX idx_po_status ON scm.purchase_orders(status);
CREATE INDEX idx_po_tenant ON scm.purchase_orders(tenant_id);

-- 采购单项表
CREATE TABLE scm.po_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id UUID NOT NULL REFERENCES scm.purchase_orders(po_id) ON DELETE CASCADE,
    asin VARCHAR(20),
    product_name VARCHAR(500),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    total_price DECIMAL(12,2) NOT NULL,
    received_quantity INTEGER DEFAULT 0,
    expected_date TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 报价表
CREATE TABLE scm.quotes (
    quote_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL REFERENCES scm.suppliers(supplier_id),
    product_spec JSONB,
    unit_price DECIMAL(12,2) NOT NULL,
    moq INTEGER,
    lead_time_days INTEGER,
    valid_until TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 供应商评分表
CREATE TABLE scm.supplier_scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id UUID NOT NULL REFERENCES scm.suppliers(supplier_id),
    quality_score DECIMAL(5,2),
    delivery_score DECIMAL(5,2),
    price_score DECIMAL(5,2),
    service_score DECIMAL(5,2),
    overall_score DECIMAL(5,2),
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```



### 3.4 CRM数据库

sql

```
-- 客户表
CREATE TABLE crm.customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    platform_id VARCHAR(100),
    platform VARCHAR(20),
    name VARCHAR(200),
    email VARCHAR(200),
    country VARCHAR(10),
    total_orders INTEGER DEFAULT 0,
    total_spent DECIMAL(12,2) DEFAULT 0,
    avg_rating DECIMAL(3,2),
    segments TEXT[],
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customers_tenant ON crm.customers(tenant_id);

-- 评价表
CREATE TABLE crm.reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    customer_id UUID REFERENCES crm.customers(customer_id),
    order_id UUID,
    asin VARCHAR(20) NOT NULL,
    platform VARCHAR(20),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title VARCHAR(500),
    text TEXT,
    sentiment_score DECIMAL(5,4),
    sentiment_label VARCHAR(20),
    pain_points TEXT[],
    keywords TEXT[],
    verified_purchase BOOLEAN DEFAULT FALSE,
    helpful_votes INTEGER DEFAULT 0,
    images TEXT[],
    reply_text TEXT,
    reply_date TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reviews_asin ON crm.reviews(asin);
CREATE INDEX idx_reviews_tenant ON crm.reviews(tenant_id);
CREATE INDEX idx_reviews_sentiment ON crm.reviews(sentiment_label);
CREATE INDEX idx_reviews_rating ON crm.reviews(rating);
CREATE INDEX idx_reviews_created ON crm.reviews(created_at DESC);

-- 客诉表
CREATE TABLE crm.complaints (
    complaint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    customer_id UUID,
    order_id UUID,
    asin VARCHAR(20),
    complaint_type VARCHAR(50),
    description TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'open',
    resolution TEXT,
    resolution_date TIMESTAMP,
    assigned_to UUID,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_complaints_status ON crm.complaints(status);
CREATE INDEX idx_complaints_type ON crm.complaints(complaint_type);

-- 退货表
CREATE TABLE crm.returns (
    return_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    customer_id UUID,
    order_id UUID,
    asin VARCHAR(20),
    return_reason VARCHAR(100),
    return_type VARCHAR(50),
    quantity INTEGER DEFAULT 1,
    refund_amount DECIMAL(12,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```



### 3.5 FMS数据库

sql

```
-- 成本分解表
CREATE TABLE fms.cost_breakdown (
    cost_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    period VARCHAR(7) NOT NULL,
    bom_cost DECIMAL(12,2) DEFAULT 0,
    shipping_cost DECIMAL(12,2) DEFAULT 0,
    fba_fees DECIMAL(12,2) DEFAULT 0,
    tariff DECIMAL(12,2) DEFAULT 0,
    advertising_cost DECIMAL(12,2) DEFAULT 0,
    storage_cost DECIMAL(12,2) DEFAULT 0,
    return_cost DECIMAL(12,2) DEFAULT 0,
    other_costs DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,
    currency VARCHAR(10) DEFAULT 'USD',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, asin, period)
);

CREATE INDEX idx_cost_asin ON fms.cost_breakdown(asin);
CREATE INDEX idx_cost_period ON fms.cost_breakdown(period);

-- 利润表
CREATE TABLE fms.profit_statements (
    statement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    asin VARCHAR(20) NOT NULL,
    period VARCHAR(7) NOT NULL,
    revenue DECIMAL(12,2) DEFAULT 0,
    refund_amount DECIMAL(12,2) DEFAULT 0,
    net_revenue DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,
    gross_profit DECIMAL(12,2) DEFAULT 0,
    gross_margin DECIMAL(5,4) DEFAULT 0,
    operating_expenses DECIMAL(12,2) DEFAULT 0,
    net_profit DECIMAL(12,2) DEFAULT 0,
    net_margin DECIMAL(5,4) DEFAULT 0,
    roi DECIMAL(5,4) DEFAULT 0,
    units_sold INTEGER DEFAULT 0,
    avg_selling_price DECIMAL(12,2) DEFAULT 0,
    currency VARCHAR(10) DEFAULT 'USD',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, asin, period)
);

CREATE INDEX idx_profit_asin ON fms.profit_statements(asin);
CREATE INDEX idx_profit_period ON fms.profit_statements(period);

-- 费用表
CREATE TABLE fms.expenses (
    expense_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    expense_type VARCHAR(50) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    period VARCHAR(7) NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_expenses_type ON fms.expenses(expense_type);
CREATE INDEX idx_expenses_period ON fms.expenses(period);
```



### 3.6 BI数据库

sql

```
-- KPI表
CREATE TABLE bi.kpis (
    kpi_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(15,4) NOT NULL,
    target_value DECIMAL(15,4),
    period VARCHAR(7) NOT NULL,
    dimension JSONB,
    trend DECIMAL(15,4)[],
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_kpis_metric ON bi.kpis(metric_name);
CREATE INDEX idx_kpis_period ON bi.kpis(period);

-- 销售趋势表
CREATE TABLE bi.sales_trends (
    trend_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    asin VARCHAR(20),
    category VARCHAR(100),
    period VARCHAR(10) NOT NULL,
    sales_quantity INTEGER DEFAULT 0,
    revenue DECIMAL(12,2) DEFAULT 0,
    growth_rate DECIMAL(5,4),
    trend_direction VARCHAR(10),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trends_asin ON bi.sales_trends(asin);
CREATE INDEX idx_trends_period ON bi.sales_trends(period);

-- 选品绩效表
CREATE TABLE bi.selection_performance (
    perf_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    task_id UUID NOT NULL,
    period VARCHAR(7) NOT NULL,
    total_recommendations INTEGER DEFAULT 0,
    adopted_count INTEGER DEFAULT 0,
    adoption_rate DECIMAL(5,4) DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    hit_rate DECIMAL(5,4) DEFAULT 0,
    avg_actual_roi DECIMAL(5,4),
    avg_predicted_roi DECIMAL(5,4),
    prediction_accuracy DECIMAL(5,4),
    total_revenue DECIMAL(15,2),
    total_profit DECIMAL(15,2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_perf_task ON bi.selection_performance(task_id);
CREATE INDEX idx_perf_period ON bi.selection_performance(period);
```



------

## 4. API接口详细设计

### 4.1 OMS接口





| 方法            | 路径                                  | 说明            | 请求体               | 响应                               |
| :-------------- | :------------------------------------ | :-------------- | :------------------- | :--------------------------------- |
| **订单管理**    |                                       |                 |                      |                                    |
| GET             | `/api/v1/oms/orders`                  | 查询订单列表    | QueryParams          | PaginatedResponse<OrderResponse>   |
| GET             | `/api/v1/oms/orders/{orderId}`        | 获取订单详情    | -                    | OrderDetailResponse                |
| GET             | `/api/v1/oms/orders/{orderId}/items`  | 获取订单项      | -                    | List<OrderItemResponse>            |
| POST            | `/api/v1/oms/orders/{orderId}/cancel` | 取消订单        | CancelRequest        | SuccessResponse                    |
| POST            | `/api/v1/oms/orders/{orderId}/refund` | 申请退款        | RefundRequest        | RefundResponse                     |
| **Listing管理** |                                       |                 |                      |                                    |
| GET             | `/api/v1/oms/listings`                | 查询Listing列表 | QueryParams          | PaginatedResponse<ListingResponse> |
| GET             | `/api/v1/oms/listings/{listingId}`    | 获取Listing详情 | -                    | ListingDetailResponse              |
| POST            | `/api/v1/oms/listings`                | 创建Listing草稿 | CreateListingRequest | ListingResponse                    |
| PUT             | `/api/v1/oms/listings/{listingId}`    | 更新Listing     | UpdateListingRequest | ListingResponse                    |
| DELETE          | `/api/v1/oms/listings/{listingId}`    | 删除Listing     | -                    | SuccessResponse                    |
| **销售数据**    |                                       |                 |                      |                                    |
| GET             | `/api/v1/oms/sales/{asin}`            | 获取销售历史    | QueryParams          | SalesHistoryResponse               |
| GET             | `/api/v1/oms/sales/{asin}/elasticity` | 获取价格弹性    | -                    | PriceElasticityResponse            |
| GET             | `/api/v1/oms/sales/statistics`        | 获取销售统计    | QueryParams          | SalesStatisticsResponse            |

### 4.2 WMS接口





| 方法         | 路径                                      | 说明           | 请求体                 | 响应                                 |
| :----------- | :---------------------------------------- | :------------- | :--------------------- | :----------------------------------- |
| **库存管理** |                                           |                |                        |                                      |
| GET          | `/api/v1/wms/inventory/{asin}`            | 获取库存信息   | -                      | InventoryResponse                    |
| GET          | `/api/v1/wms/inventory`                   | 查询库存列表   | QueryParams            | PaginatedResponse<InventoryResponse> |
| GET          | `/api/v1/wms/inventory/{asin}/turnover`   | 获取库存周转率 | -                      | TurnoverResponse                     |
| GET          | `/api/v1/wms/inventory/alerts`            | 获取库存预警   | -                      | List<InventoryAlertResponse>         |
| **库容管理** |                                           |                |                        |                                      |
| GET          | `/api/v1/wms/capacity`                    | 获取仓库容量   | -                      | List<CapacityResponse>               |
| POST         | `/api/v1/wms/capacity/reserve`            | 预留库容       | ReserveCapacityRequest | CapacityResponse                     |
| POST         | `/api/v1/wms/capacity/release`            | 释放库容       | ReleaseCapacityRequest | SuccessResponse                      |
| **入库管理** |                                           |                |                        |                                      |
| GET          | `/api/v1/wms/inbound`                     | 查询入库单     | QueryParams            | PaginatedResponse<InboundResponse>   |
| POST         | `/api/v1/wms/inbound`                     | 创建入库单     | CreateInboundRequest   | InboundResponse                      |
| POST         | `/api/v1/wms/inbound/{inboundId}/receive` | 确认收货       | ReceiveRequest         | SuccessResponse                      |
| **出库管理** |                                           |                |                        |                                      |
| GET          | `/api/v1/wms/outbound`                    | 查询出库单     | QueryParams            | PaginatedResponse<OutboundResponse>  |
| POST         | `/api/v1/wms/outbound`                    | 创建出库单     | CreateOutboundRequest  | OutboundResponse                     |
| POST         | `/api/v1/wms/outbound/{outboundId}/ship`  | 确认发货       | ShipRequest            | SuccessResponse                      |

### 4.3 SCM接口





| 方法           | 路径                                             | 说明           | 请求体                | 响应                                |
| :------------- | :----------------------------------------------- | :------------- | :-------------------- | :---------------------------------- |
| **供应商管理** |                                                  |                |                       |                                     |
| GET            | `/api/v1/scm/suppliers`                          | 查询供应商列表 | QueryParams           | PaginatedResponse<SupplierResponse> |
| GET            | `/api/v1/scm/suppliers/{supplierId}`             | 获取供应商详情 | -                     | SupplierDetailResponse              |
| POST           | `/api/v1/scm/suppliers`                          | 创建供应商     | CreateSupplierRequest | SupplierResponse                    |
| PUT            | `/api/v1/scm/suppliers/{supplierId}`             | 更新供应商     | UpdateSupplierRequest | SupplierResponse                    |
| GET            | `/api/v1/scm/suppliers/{supplierId}/scores`      | 获取供应商评分 | -                     | SupplierScoreResponse               |
| GET            | `/api/v1/scm/suppliers/{supplierId}/performance` | 获取供应商绩效 | QueryParams           | PerformanceResponse                 |
| **采购管理**   |                                                  |                |                       |                                     |
| GET            | `/api/v1/scm/purchase-orders`                    | 查询采购单     | QueryParams           | PaginatedResponse<POResponse>       |
| GET            | `/api/v1/scm/purchase-orders/{poId}`             | 获取采购单详情 | -                     | PODetailResponse                    |
| POST           | `/api/v1/scm/purchase-orders`                    | 创建采购单     | CreatePORequest       | POResponse                          |
| PUT            | `/api/v1/scm/purchase-orders/{poId}`             | 更新采购单     | UpdatePORequest       | POResponse                          |
| POST           | `/api/v1/scm/purchase-orders/{poId}/approve`     | 审批采购单     | ApproveRequest        | SuccessResponse                     |
| POST           | `/api/v1/scm/purchase-orders/{poId}/receive`     | 确认收货       | ReceiveRequest        | SuccessResponse                     |
| **询价管理**   |                                                  |                |                       |                                     |
| POST           | `/api/v1/scm/quotes/request`                     | 请求报价       | QuoteRequest          | QuoteResponse                       |
| GET            | `/api/v1/scm/quotes`                             | 查询报价列表   | QueryParams           | PaginatedResponse<QuoteResponse>    |

### 4.4 CRM接口





| 方法         | 路径                                           | 说明         | 请求体                 | 响应                                 |
| :----------- | :--------------------------------------------- | :----------- | :--------------------- | :----------------------------------- |
| **客户管理** |                                                |              |                        |                                      |
| GET          | `/api/v1/crm/customers`                        | 查询客户列表 | QueryParams            | PaginatedResponse<CustomerResponse>  |
| GET          | `/api/v1/crm/customers/{customerId}`           | 获取客户详情 | -                      | CustomerDetailResponse               |
| GET          | `/api/v1/crm/customers/{customerId}/profile`   | 获取客户画像 | -                      | CustomerProfileResponse              |
| **评价管理** |                                                |              |                        |                                      |
| GET          | `/api/v1/crm/reviews/{asin}`                   | 获取商品评价 | QueryParams            | PaginatedResponse<ReviewResponse>    |
| GET          | `/api/v1/crm/reviews/{asin}/statistics`        | 获取评价统计 | -                      | ReviewStatisticsResponse             |
| GET          | `/api/v1/crm/reviews/{asin}/sentiment`         | 获取情感分析 | -                      | SentimentResponse                    |
| POST         | `/api/v1/crm/reviews/{reviewId}/reply`         | 回复评价     | ReplyRequest           | SuccessResponse                      |
| **客诉管理** |                                                |              |                        |                                      |
| GET          | `/api/v1/crm/complaints`                       | 查询客诉列表 | QueryParams            | PaginatedResponse<ComplaintResponse> |
| GET          | `/api/v1/crm/complaints/{complaintId}`         | 获取客诉详情 | -                      | ComplaintDetailResponse              |
| POST         | `/api/v1/crm/complaints`                       | 创建客诉记录 | CreateComplaintRequest | ComplaintResponse                    |
| PUT          | `/api/v1/crm/complaints/{complaintId}/resolve` | 解决客诉     | ResolveRequest         | SuccessResponse                      |
| **退货管理** |                                                |              |                        |                                      |
| GET          | `/api/v1/crm/returns`                          | 查询退货列表 | QueryParams            | PaginatedResponse<ReturnResponse>    |
| POST         | `/api/v1/crm/returns`                          | 创建退货记录 | CreateReturnRequest    | ReturnResponse                       |

### 4.5 FMS接口





| 方法         | 路径                                  | 说明         | 请求体               | 响应                               |
| :----------- | :------------------------------------ | :----------- | :------------------- | :--------------------------------- |
| **成本管理** |                                       |              |                      |                                    |
| GET          | `/api/v1/fms/costs/{asin}`            | 获取成本明细 | QueryParams          | CostDetailResponse                 |
| GET          | `/api/v1/fms/costs/{asin}/breakdown`  | 获取成本分解 | QueryParams          | CostBreakdownResponse              |
| GET          | `/api/v1/fms/costs/{asin}/trend`      | 获取成本趋势 | QueryParams          | CostTrendResponse                  |
| **利润管理** |                                       |              |                      |                                    |
| GET          | `/api/v1/fms/profit/{asin}`           | 获取利润数据 | QueryParams          | ProfitResponse                     |
| GET          | `/api/v1/fms/profit/{asin}/trend`     | 获取利润趋势 | QueryParams          | ProfitTrendResponse                |
| GET          | `/api/v1/fms/profit/statistics`       | 获取利润统计 | QueryParams          | ProfitStatisticsResponse           |
| **费用管理** |                                       |              |                      |                                    |
| GET          | `/api/v1/fms/expenses`                | 查询费用列表 | QueryParams          | PaginatedResponse<ExpenseResponse> |
| POST         | `/api/v1/fms/expenses`                | 创建费用记录 | CreateExpenseRequest | ExpenseResponse                    |
| **广告费用** |                                       |              |                      |                                    |
| GET          | `/api/v1/fms/advertising/{asin}`      | 获取广告费用 | QueryParams          | AdCostResponse                     |
| GET          | `/api/v1/fms/advertising/{asin}/acos` | 获取ACOS     | QueryParams          | ACOSResponse                       |

### 4.6 BI接口





| 方法         | 路径                                        | 说明           | 请求体      | 响应                         |
| :----------- | :------------------------------------------ | :------------- | :---------- | :--------------------------- |
| **KPI管理**  |                                             |                |             |                              |
| GET          | `/api/v1/bi/kpi/{metric}`                   | 获取KPI数据    | QueryParams | KPIResponse                  |
| GET          | `/api/v1/bi/kpi/dashboard`                  | 获取仪表板数据 | QueryParams | DashboardResponse            |
| GET          | `/api/v1/bi/kpi/trends`                     | 获取KPI趋势    | QueryParams | KPITrendResponse             |
| **销售趋势** |                                             |                |             |                              |
| GET          | `/api/v1/bi/trends/category/{category}`     | 获取品类趋势   | QueryParams | CategoryTrendResponse        |
| GET          | `/api/v1/bi/trends/market/{market}`         | 获取市场趋势   | QueryParams | MarketTrendResponse          |
| GET          | `/api/v1/bi/trends/product/{asin}`          | 获取商品趋势   | QueryParams | ProductTrendResponse         |
| **选品绩效** |                                             |                |             |                              |
| GET          | `/api/v1/bi/selection/{taskId}/performance` | 获取选品绩效   | -           | SelectionPerformanceResponse |
| GET          | `/api/v1/bi/selection/statistics`           | 获取选品统计   | QueryParams | SelectionStatisticsResponse  |

------

## 5. CDC数据同步设计

### 5.1 CDC架构

text

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    CDC数据同步架构                                                    │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              ERP数据库 (PostgreSQL)                                           │  │
│  │                                                                                              │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐               │  │
│  │  │   OMS    │    │   WMS    │    │   SCM    │    │   CRM    │    │   FMS    │               │  │
│  │  │ (订单)   │    │ (库存)   │    │ (采购)   │    │ (评价)   │    │ (成本)   │               │  │
│  │  └────┬─────┘    └──────────┘    └──────────┘    └────┬─────┘    └──────────┘               │  │
│  │       │                                               │                                     │  │
│  │       │ WAL日志                                       │ WAL日志                             │  │
│  └───────┼───────────────────────────────────────────────┼─────────────────────────────────────┘  │
│          │                                               │                                        │
│          ▼                                               ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Debezium Connect                                               │  │
│  │                                                                                              │  │
│  │  ┌─────────────────────┐          ┌─────────────────────┐                                   │  │
│  │  │  OMS Connector      │          │  CRM Connector      │                                   │  │
│  │  │  (订单/退款)         │          │  (评价/客诉)         │                                   │  │
│  │  └──────────┬──────────┘          └──────────┬──────────┘                                   │  │
│  └─────────────┼────────────────────────────────┼──────────────────────────────────────────────┘  │
│                │                                │                                                  │
│                ▼                                ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Kafka Topics                                                   │  │
│  │                                                                                              │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                              │  │
│  │  │ cdc_oms_orders  │  │ cdc_oms_refunds │  │ cdc_crm_reviews │                              │  │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                              │  │
│  └───────────┼────────────────────┼────────────────────┼────────────────────────────────────────┘  │
│              │                    │                    │                                            │
│              ▼                    ▼                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              AI选品系统 (PMS)                                                │  │
│  │                                                                                              │  │
│  │  Flink消费 ──► 数据湖(Iceberg) ──► 特征平台(Feast) ──► Agent决策                               │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```



### 5.2 OMS CDC配置

json

```
{
  "name": "oms-orders-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "oms-postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${DEBEZIUM_PASSWORD}",
    "database.dbname": "oms",
    "database.server.name": "oms_server",
    "schema.include.list": "oms",
    "table.include.list": "oms.orders,oms.order_items,oms.refunds",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_oms_slot",
    "publication.autocreate.mode": "filtered",
    "transforms": "route,unwrap",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "oms_server.oms.(.*)",
    "transforms.route.replacement": "cdc_oms_$1",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "transforms.unwrap.drop.tombstones": "false",
    "transforms.unwrap.delete.handling.mode": "rewrite",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
```



### 5.3 CRM CDC配置

json

```
{
  "name": "crm-reviews-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "crm-postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${DEBEZIUM_PASSWORD}",
    "database.dbname": "crm",
    "database.server.name": "crm_server",
    "schema.include.list": "crm",
    "table.include.list": "crm.reviews,crm.complaints,crm.returns",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_crm_slot",
    "transforms": "route,unwrap",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "crm_server.crm.(.*)",
    "transforms.route.replacement": "cdc_crm_$1",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState"
  }
}
```



### 5.4 数据格式规范

json

```
{
  "schema": {
    "type": "struct",
    "fields": [
      {"field": "order_id", "type": "string"},
      {"field": "tenant_id", "type": "string"},
      {"field": "status", "type": "string"},
      {"field": "total_amount", "type": "double"},
      {"field": "order_date", "type": "string"}
    ]
  },
  "payload": {
    "order_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "tenant_001",
    "status": "confirmed",
    "total_amount": 199.99,
    "order_date": "2026-01-01T00:00:00Z",
    "__op": "c",
    "__source_ts_ms": 1704067200000
  }
}
```



------

## 6. 与AI选品系统集成设计

### 6.1 集成架构

text

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              AI选品系统与ERP集成架构                                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              AI选品系统 (PMS)                                                 │  │
│  │                                                                                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │  │
│  │  │市场洞察Agent │  │产品规划Agent │  │商业化Agent  │  │风险评估Agent │  │数据采集Agent │        │  │
│  │  │             │  │             │  │             │  │             │  │             │        │  │
│  │  │ 查询OMS销量  │  │ 查询CRM评价  │  │ 查询FMS成本  │  │ 查询SCM供应  │  │ 调用ERP API │        │  │
│  │  │ 查询BI趋势  │  │ 查询CRM客诉  │  │ 查询SCM报价  │  │ 查询WMS库存  │  │             │        │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │  │
│  └─────────┼────────────────┼────────────────┼────────────────┼────────────────┼────────────────┘  │
│            │                │                │                │                │                   │
│            ▼                ▼                ▼                ▼                ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Integration Service                                             │  │
│  │                                                                                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │  │
│  │  │OMS Client│  │WMS Client│  │SCM Client│  │CRM Client│  │FMS Client│  │BI Client │        │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │  │
│  └───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┼──────────────┘  │
│          │             │             │             │             │             │                  │
│          ▼             ▼             ▼             ▼             ▼             ▼                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              ERP系统                                                         │  │
│  │                                                                                              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │  │
│  │  │   OMS    │  │   WMS    │  │   SCM    │  │   CRM    │  │   FMS    │  │    BI    │        │  │
│  │  │ :8001    │  │ :8002    │  │ :8003    │  │ :8004    │  │ :8005    │  │ :8006    │        │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```



### 6.2 数据输入（AI感知）





| Agent             | 查询的ERP数据 | 调用接口                                     | 用途                       |
| :---------------- | :------------ | :------------------------------------------- | :------------------------- |
| **市场洞察Agent** | OMS历史销量   | `GET /api/v1/oms/sales/{asin}`               | 分析品类趋势和市场规模     |
| **市场洞察Agent** | BI品类趋势    | `GET /api/v1/bi/trends/category/{category}`  | 获取品类增长趋势           |
| **产品规划Agent** | CRM评价数据   | `GET /api/v1/crm/reviews/{asin}`             | 挖掘用户痛点和产品改进方向 |
| **产品规划Agent** | CRM客诉数据   | `GET /api/v1/crm/complaints`                 | 识别产品质量问题           |
| **商业化Agent**   | FMS成本数据   | `GET /api/v1/fms/costs/{asin}`               | 计算全链路成本             |
| **商业化Agent**   | SCM供应商报价 | `GET /api/v1/scm/quotes`                     | 获取采购成本               |
| **商业化Agent**   | OMS价格弹性   | `GET /api/v1/oms/sales/{asin}/elasticity`    | 制定定价策略               |
| **风险评估Agent** | SCM供应商绩效 | `GET /api/v1/scm/suppliers/{id}/performance` | 评估供应稳定性             |
| **风险评估Agent** | WMS库存数据   | `GET /api/v1/wms/inventory/{asin}`           | 评估库存风险               |
| **数据采集Agent** | 所有ERP API   | 各接口                                       | 采集内部业务数据           |

### 6.3 数据输出（AI驱动）





| 输出动作            | 调用的ERP接口                            | 触发时机     | 说明                     |
| :------------------ | :--------------------------------------- | :----------- | :----------------------- |
| **创建采购单**      | `POST /api/v1/scm/purchase-orders`       | 选品采纳后   | 自动创建SCM采购单        |
| **预留库容**        | `POST /api/v1/wms/capacity/reserve`      | 选品采纳后   | 为新品预留仓储空间       |
| **创建Listing草稿** | `POST /api/v1/oms/listings`              | 选品采纳后   | 自动生成Listing          |
| **请求供应商报价**  | `POST /api/v1/scm/quotes/request`        | 选品分析中   | 获取最新报价用于成本测算 |
| **更新产品状态**    | `PUT /api/v1/scm/purchase-orders/{poId}` | 采购进度变更 | 跟踪采购执行状态         |

### 6.4 闭环反馈设计

text

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              闭环反馈流程                                                           │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  1. AI选品系统生成选品建议                                                                            │
│     │                                                                                              │
│     ▼                                                                                              │
│  2. 运营人员采纳选品建议                                                                              │
│     │                                                                                              │
│     ▼                                                                                              │
│  3. 触发ERP执行                                                                                      │
│     ├── SCM: 创建采购单                                                                              │
│     ├── WMS: 预留库容                                                                                │
│     └── OMS: 创建Listing草稿                                                                         │
│     │                                                                                              │
│     ▼                                                                                              │
│  4. 商品上架销售                                                                                      │
│     │                                                                                              │
│     ▼                                                                                              │
│  5. ERP产生业务数据                                                                                   │
│     ├── OMS: 订单数据                                                                                │
│     ├── CRM: 评价数据                                                                                │
│     └── FMS: 成本利润数据                                                                            │
│     │                                                                                              │
│     ▼                                                                                              │
│  6. CDC实时同步到Kafka                                                                               │
│     │                                                                                              │
│     ▼                                                                                              │
│  7. Flink消费处理                                                                                    │
│     ├── 实时特征计算                                                                                 │
│     ├── 情感分析                                                                                    │
│     └── 异常检测                                                                                    │
│     │                                                                                              │
│     ▼                                                                                              │
│  8. 更新AI选品系统                                                                                    │
│     ├── 特征平台 (Feast): 更新特征值                                                                  │
│     ├── 知识库 (Qdrant): 更新评价知识                                                                │
│     └── BI: 更新选品绩效KPI                                                                          │
│     │                                                                                              │
│     ▼                                                                                              │
│  9. 下次选品更精准                                                                                    │
│     └── 模型微调 (LoRA): 基于反馈数据优化模型                                                          │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```



------

## 7. 部署与运维

### 7.1 部署架构

yaml

```
# docker-compose.yml
version: '3.8'

services:
  oms-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: oms
      POSTGRES_USER: oms_user
      POSTGRES_PASSWORD: ${OMS_DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - oms_data:/var/lib/postgresql/data
      - ./init/oms:/docker-entrypoint-initdb.d
    command: |
      -c wal_level=logical
      -c max_wal_senders=10
      -c max_replication_slots=10

  wms-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: wms
    ports:
      - "5433:5432"
    volumes:
      - wms_data:/var/lib/postgresql/data

  scm-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: scm
    ports:
      - "5434:5432"
    volumes:
      - scm_data:/var/lib/postgresql/data

  crm-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: crm
    ports:
      - "5435:5432"
    volumes:
      - crm_data:/var/lib/postgresql/data
    command: |
      -c wal_level=logical
      -c max_wal_senders=10
      -c max_replication_slots=10

  fms-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: fms
    ports:
      - "5436:5432"
    volumes:
      - fms_data:/var/lib/postgresql/data

  bi-postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: bi
    ports:
      - "5437:5432"
    volumes:
      - bi_data:/var/lib/postgresql/data

  oms-service:
    build: ./services/oms
    ports:
      - "8001:8001"
    depends_on:
      - oms-postgres
    environment:
      DB_URL: postgresql://oms_user:${OMS_DB_PASSWORD}@oms-postgres:5432/oms

  wms-service:
    build: ./services/wms
    ports:
      - "8002:8002"
    depends_on:
      - wms-postgres

  scm-service:
    build: ./services/scm
    ports:
      - "8003:8003"
    depends_on:
      - scm-postgres

  crm-service:
    build: ./services/crm
    ports:
      - "8004:8004"
    depends_on:
      - crm-postgres

  fms-service:
    build: ./services/fms
    ports:
      - "8005:8005"
    depends_on:
      - fms-postgres

  bi-service:
    build: ./services/bi
    ports:
      - "8006:8006"
    depends_on:
      - bi-postgres

  debezium:
    image: debezium/connect:2.5
    ports:
      - "8083:8083"
    environment:
      BOOTSTRAP_SERVERS: kafka:9092
      GROUP_ID: debezium
      CONFIG_STORAGE_TOPIC: debezium_configs
      OFFSET_STORAGE_TOPIC: debezium_offsets
      STATUS_STORAGE_TOPIC: debezium_status

volumes:
  oms_data:
  wms_data:
  scm_data:
  crm_data:
  fms_data:
  bi_data:
```



### 7.2 高可用配置





| 组件               | 高可用方案       | 配置                   |
| :----------------- | :--------------- | :--------------------- |
| **OMS PostgreSQL** | Patroni + etcd   | 1主2从，自动故障转移   |
| **CRM PostgreSQL** | Patroni + etcd   | 1主2从，自动故障转移   |
| **WMS/SCM/FMS/BI** | PostgreSQL流复制 | 1主1从，手动切换       |
| **Debezium**       | 多Worker         | 3 Worker，任务自动分配 |
| **应用服务**       | K8s多副本        | 2副本，HPA自动扩缩容   |

### 7.3 监控告警





| 指标                       | 告警阈值     | 说明           |
| :------------------------- | :----------- | :------------- |
| `oms_order_creation_rate`  | 异常下降>50% | 订单创建量异常 |
| `wms_inventory_available`  | < 安全库存   | 库存不足预警   |
| `scm_po_approval_time`     | > 24小时     | 采购审批超时   |
| `crm_negative_review_rate` | > 30%        | 差评率过高     |
| `fms_profit_margin`        | < 目标值     | 利润率不达标   |
| `cdc_lag_seconds`          | > 60秒       | CDC同步延迟    |
| `api_response_time_p95`    | > 500ms      | API响应过慢    |

------

**文档版本**: v1.0
**创建日期**: 2026-04-23
**项目代号**: Project Aegis - ERP Module
**文档状态**: 正式版