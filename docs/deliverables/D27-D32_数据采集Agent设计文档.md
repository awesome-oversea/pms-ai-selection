# 数据采集Agent设计文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D27-D32 数据采集Agent + 市场洞察Agent开发
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. Agent架构设计](#2-agent架构设计)
- [3. 数据采集工具设计](#3-数据采集工具设计)
- [4. 数据标准化处理](#4-数据标准化处理)
- [5. 市场洞察Agent设计](#5-市场洞察agent设计)
- [6. API接口设计](#6-api接口设计)

---

## 1. 概述

### 1.1 设计目标

数据采集Agent负责从多个数据源采集商品、市场、竞品等信息，为AI选品决策提供数据支撑。

### 1.2 数据源覆盖

| 数据源 | 数据类型 | 采集频率 | 优先级 |
|--------|---------|---------|--------|
| Amazon | BSR榜单、评论、价格 | 每日 | P0 |
| TikTok | 热门商品、视频数据 | 每日 | P0 |
| Google Trends | 搜索热度、趋势 | 每小时 | P1 |
| 1688 | 供应商、价格、库存 | 每日 | P1 |

---

## 2. Agent架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    DataCollectionAgent                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Tool Layer                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ Amazon   │ │ TikTok   │ │ Google   │ │  1688    │   │   │
│  │  │ Tool     │ │ Tool     │ │ Trends   │ │ Tool     │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Data Processing Layer                   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 数据清洗  │ │ 数据融合  │ │ 质量检查  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Output Layer                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 标准格式  │ │ 数据存储  │ │ 事件通知  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心类设计

```python
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel
import asyncio

class DataItem(BaseModel):
    source: str
    data_type: str
    raw_data: dict[str, Any]
    normalized_data: Optional[dict[str, Any]] = None
    quality_score: float = 0.0
    collected_at: str

class BaseTool(ABC):
    name: str
    description: str
    
    @abstractmethod
    async def run(self, query: str) -> list[DataItem]:
        pass
    
    @abstractmethod
    def validate_data(self, data: dict) -> bool:
        pass

class DataCollectionAgent:
    def __init__(self):
        self.tools: list[BaseTool] = []
        self.quality_checker = QualityChecker()
        self.data_merger = DataMerger()
    
    def register_tool(self, tool: BaseTool):
        self.tools.append(tool)
    
    async def collect(self, query: str) -> dict[str, Any]:
        tasks = [tool.run(query) for tool in self.tools]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for result in results:
            if isinstance(result, list):
                valid_results.extend(result)
        
        merged_data = self.data_merger.merge(valid_results)
        quality_report = self.quality_checker.check(merged_data)
        
        return {
            "data": merged_data,
            "quality": quality_report,
            "sources": [t.name for t in self.tools]
        }
```

---

## 3. 数据采集工具设计

### 3.1 Amazon Tool

```python
class AmazonTool(BaseTool):
    name = "amazon"
    description = "Amazon商品数据采集工具"
    
    def __init__(self, config: AmazonConfig):
        self.config = config
        self.bsr_tool = AmazonBSRTool(config)
        self.review_tool = AmazonReviewTool(config)
        self.price_tool = AmazonPriceTool(config)
    
    async def run(self, query: str) -> list[DataItem]:
        tasks = [
            self.bsr_tool.fetch(query),
            self.review_tool.fetch(query),
            self.price_tool.fetch(query)
        ]
        results = await asyncio.gather(*tasks)
        
        items = []
        for result in results:
            for item in result:
                items.append(DataItem(
                    source="amazon",
                    data_type=item["type"],
                    raw_data=item,
                    collected_at=datetime.now().isoformat()
                ))
        return items
    
    def validate_data(self, data: dict) -> bool:
        required_fields = ["asin", "title", "price"]
        return all(field in data for field in required_fields)

class AmazonBSRTool:
    async def fetch(self, category: str) -> list[dict]:
        return [
            {
                "type": "bsr",
                "asin": "B0XXXXX",
                "title": "Product Title",
                "bsr_rank": 1,
                "category": category,
                "price": 29.99,
                "rating": 4.5,
                "review_count": 1234
            }
        ]

class AmazonReviewTool:
    async def fetch(self, asin: str) -> list[dict]:
        return [
            {
                "type": "review",
                "asin": asin,
                "review_id": "RXXXXX",
                "rating": 5,
                "title": "Great product",
                "content": "Review content...",
                "verified_purchase": True,
                "helpful_votes": 10
            }
        ]

class AmazonPriceTool:
    async def fetch(self, asin: str) -> list[dict]:
        return [
            {
                "type": "price",
                "asin": asin,
                "current_price": 29.99,
                "original_price": 39.99,
                "discount": 0.25,
                "currency": "USD"
            }
        ]
```

### 3.2 TikTok Tool

```python
class TikTokTool(BaseTool):
    name = "tiktok"
    description = "TikTok商品和视频数据采集工具"
    
    async def run(self, query: str) -> list[DataItem]:
        async with TikTokAPIClient(self.config) as client:
            products = await client.search_products(query)
            videos = await client.search_videos(query)
            
        items = []
        for product in products:
            items.append(DataItem(
                source="tiktok",
                data_type="product",
                raw_data=product,
                collected_at=datetime.now().isoformat()
            ))
        
        for video in videos:
            items.append(DataItem(
                source="tiktok",
                data_type="video",
                raw_data=video,
                collected_at=datetime.now().isoformat()
            ))
        
        return items
    
    def validate_data(self, data: dict) -> bool:
        required_fields = ["product_id", "title"]
        return all(field in data for field in required_fields)
```

### 3.3 Google Trends Tool

```python
class GoogleTrendsTool(BaseTool):
    name = "google_trends"
    description = "Google Trends搜索趋势数据采集工具"
    
    async def run(self, query: str) -> list[DataItem]:
        async with TrendReq() as pytrends:
            pytrends.build_payload([query])
            
            interest_over_time = pytrends.interest_over_time()
            related_queries = pytrends.related_queries()
            interest_by_region = pytrends.interest_by_region()
        
        items = [
            DataItem(
                source="google_trends",
                data_type="interest_over_time",
                raw_data=interest_over_time.to_dict(),
                collected_at=datetime.now().isoformat()
            ),
            DataItem(
                source="google_trends",
                data_type="related_queries",
                raw_data=related_queries,
                collected_at=datetime.now().isoformat()
            ),
            DataItem(
                source="google_trends",
                data_type="interest_by_region",
                raw_data=interest_by_region.to_dict(),
                collected_at=datetime.now().isoformat()
            )
        ]
        
        return items
```

### 3.4 1688 Tool

```python
class Alibaba1688Tool(BaseTool):
    name = "1688"
    description = "1688供应商和商品数据采集工具"
    
    async def run(self, query: str) -> list[DataItem]:
        async with Alibaba1688Client(self.config) as client:
            products = await client.search_products(query)
            suppliers = await client.search_suppliers(query)
        
        items = []
        for product in products:
            items.append(DataItem(
                source="1688",
                data_type="product",
                raw_data=product,
                collected_at=datetime.now().isoformat()
            ))
        
        for supplier in suppliers:
            items.append(DataItem(
                source="1688",
                data_type="supplier",
                raw_data=supplier,
                collected_at=datetime.now().isoformat()
            ))
        
        return items
```

---

## 4. 数据标准化处理

### 4.1 数据标准化器

```python
class DataNormalizer:
    FIELD_MAPPINGS = {
        "amazon": {
            "asin": "product_id",
            "title": "name",
            "price": "price",
            "rating": "rating",
            "review_count": "review_count"
        },
        "tiktok": {
            "product_id": "product_id",
            "title": "name",
            "price": "price",
            "sales": "sales_count"
        },
        "1688": {
            "offer_id": "product_id",
            "subject": "name",
            "price": "price",
            "stock": "stock"
        }
    }
    
    def normalize(self, item: DataItem) -> dict[str, Any]:
        mapping = self.FIELD_MAPPINGS.get(item.source, {})
        normalized = {}
        
        for src_field, dst_field in mapping.items():
            if src_field in item.raw_data:
                normalized[dst_field] = item.raw_data[src_field]
        
        normalized["source"] = item.source
        normalized["collected_at"] = item.collected_at
        
        return normalized

class DataMerger:
    def merge(self, items: list[DataItem]) -> dict[str, Any]:
        normalizer = DataNormalizer()
        merged = {}
        
        for item in items:
            normalized = normalizer.normalize(item)
            key = normalized.get("product_id")
            
            if key:
                if key not in merged:
                    merged[key] = normalized
                else:
                    merged[key].update(normalized)
        
        return merged

class QualityChecker:
    RULES = {
        "required_fields": ["product_id", "name"],
        "price_range": (0, 10000),
        "rating_range": (0, 5),
    }
    
    def check(self, data: dict[str, Any]) -> dict[str, Any]:
        issues = []
        score = 100.0
        
        for field in self.RULES["required_fields"]:
            if field not in data or not data[field]:
                issues.append(f"Missing required field: {field}")
                score -= 20
        
        if "price" in data:
            min_price, max_price = self.RULES["price_range"]
            if not min_price <= data["price"] <= max_price:
                issues.append(f"Price out of range: {data['price']}")
                score -= 10
        
        return {
            "score": max(score, 0),
            "issues": issues,
            "is_valid": score >= 60
        }
```

---

## 5. 市场洞察Agent设计

### 5.1 架构设计

```python
class MarketInsightAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.data_collector = DataCollectionAgent()
    
    async def analyze(self, category: str) -> dict[str, Any]:
        data = await self.data_collector.collect(category)
        
        supply_demand = self._calc_supply_demand(data)
        lifecycle = self._analyze_lifecycle(data)
        trends = self._predict_trends(data)
        competition = self._analyze_competition(data)
        
        insight = await self._generate_insight(
            category, supply_demand, lifecycle, trends, competition
        )
        
        return {
            "category": category,
            "supply_demand": supply_demand,
            "lifecycle": lifecycle,
            "trends": trends,
            "competition": competition,
            "insight": insight
        }
    
    def _calc_supply_demand(self, data: dict) -> dict[str, Any]:
        supply = data.get("product_count", 0)
        demand = data.get("search_volume", 0)
        
        ratio = supply / max(demand, 1)
        
        if ratio < 0.5:
            market_type = "蓝海"
            opportunity = "高"
        elif ratio < 1.0:
            market_type = "成长期"
            opportunity = "中"
        else:
            market_type = "红海"
            opportunity = "低"
        
        return {
            "supply": supply,
            "demand": demand,
            "ratio": round(ratio, 2),
            "market_type": market_type,
            "opportunity": opportunity
        }
    
    def _analyze_lifecycle(self, data: dict) -> dict[str, Any]:
        trend_data = data.get("trend_data", [])
        
        if len(trend_data) < 2:
            return {"stage": "unknown", "confidence": 0}
        
        recent_trend = trend_data[-7:]
        earlier_trend = trend_data[-30:-7]
        
        recent_avg = sum(recent_trend) / len(recent_trend)
        earlier_avg = sum(earlier_trend) / len(earlier_trend)
        
        growth_rate = (recent_avg - earlier_avg) / max(earlier_avg, 1)
        
        if growth_rate > 0.2:
            stage = "成长期"
        elif growth_rate > 0:
            stage = "成熟期"
        elif growth_rate > -0.2:
            stage = "饱和期"
        else:
            stage = "衰退期"
        
        return {
            "stage": stage,
            "growth_rate": round(growth_rate, 2),
            "confidence": 0.8
        }
    
    def _predict_trends(self, data: dict) -> dict[str, Any]:
        from prophet import Prophet
        import pandas as pd
        
        trend_data = data.get("trend_data", [])
        if len(trend_data) < 30:
            return {"prediction": [], "confidence": 0}
        
        df = pd.DataFrame({
            "ds": pd.date_range(start="2024-01-01", periods=len(trend_data)),
            "y": trend_data
        })
        
        model = Prophet()
        model.fit(df)
        
        future = model.make_future_dataframe(periods=30)
        forecast = model.predict(future)
        
        return {
            "prediction": forecast["yhat"].tail(30).tolist(),
            "confidence": 0.75
        }
    
    async def _generate_insight(
        self, category: str, supply_demand: dict,
        lifecycle: dict, trends: dict, competition: dict
    ) -> str:
        prompt = f"""
        作为市场分析专家，请基于以下数据分析{category}品类的市场机会：
        
        供需分析：
        - 供应量：{supply_demand['supply']}
        - 需求量：{supply_demand['demand']}
        - 市场类型：{supply_demand['market_type']}
        
        生命周期：
        - 当前阶段：{lifecycle['stage']}
        - 增长率：{lifecycle['growth_rate']}
        
        请给出：
        1. 市场机会评估
        2. 进入建议
        3. 风险提示
        """
        
        response = await self.llm.generate(prompt)
        return response.text
```

---

## 6. API接口设计

### 6.1 数据采集接口

```python
from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/api/v1/data", tags=["data-collection"])

@router.post("/collect")
async def collect_data(
    query: str,
    sources: list[str] = ["amazon", "tiktok", "google_trends", "1688"],
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(run_collection, query, sources)
    return {"status": "started", "query": query, "sources": sources}

@router.get("/collect/{task_id}")
async def get_collection_result(task_id: str):
    result = await get_task_result(task_id)
    return result

@router.post("/market-insight")
async def analyze_market(category: str):
    agent = MarketInsightAgent(get_llm_client())
    result = await agent.analyze(category)
    return result
```

### 6.2 数据查询接口

```python
@router.get("/products")
async def list_products(
    category: Optional[str] = None,
    source: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    page: int = 1,
    size: int = 20
):
    products = await query_products(
        category=category,
        source=source,
        price_range=(min_price, max_price),
        offset=(page - 1) * size,
        limit=size
    )
    return {"products": products, "page": page, "size": size}

@router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
```

---

## 附录

### A. 配置示例

```yaml
data_collection:
  amazon:
    api_endpoint: "https://api.amazon.com"
    access_key: "${AMAZON_ACCESS_KEY}"
    rate_limit: 100
  
  tiktok:
    api_endpoint: "https://api.tiktok.com"
    app_id: "${TIKTOK_APP_ID}"
    app_secret: "${TIKTOK_APP_SECRET}"
  
  google_trends:
    rate_limit: 50
  
  alibaba_1688:
    api_endpoint: "https://api.1688.com"
    app_key: "${ALIBABA_APP_KEY}"
    app_secret: "${ALIBABA_APP_SECRET}"
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
