# 产品规划Agent与商业化Agent设计方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D33-D38 产品规划Agent + 商业化Agent + vLLM扩展
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. 产品规划Agent设计](#2-产品规划agent设计)
- [3. 商业化Agent设计](#3-商业化agent设计)
- [4. vLLM四节点集群](#4-vllm四节点集群)
- [5. LLM Gateway智能路由](#5-llm-gateway智能路由)

---

## 1. 概述

### 1.1 设计目标

构建产品规划Agent和商业化Agent，实现从市场分析到商业决策的完整链路，同时扩展vLLM推理集群。

### 1.2 核心能力

| Agent | 核心能力 | 输出 |
|-------|---------|------|
| ProductPlanner | 多模态分析、评论聚类、竞品差异化 | 产品定义报告 |
| Commercializer | 成本计算、利润分析、定价建议、ROI预测 | 商业化分析报告 |

---

## 2. 产品规划Agent设计

### 2.1 Agent架构

```python
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    HOME_GARDEN = "home_garden"
    SPORTS_OUTDOORS = "sports_outdoors"
    BEAUTY = "beauty"
    TOYS = "toys"

@dataclass
class ProductDefinition:
    product_id: str
    name: str
    category: ProductCategory
    target_market: str
    key_features: List[str]
    differentiators: List[str]
    swot: Dict[str, List[str]]
    recommended_price_range: tuple
    estimated_demand: int
    risk_level: str

class ProductPlanningAgent:
    def __init__(
        self,
        llm_client,
        llava_client,
        embedding_service,
        qdrant_client
    ):
        self.llm = llm_client
        self.llava = llava_client
        self.embedding = embedding_service
        self.qdrant = qdrant_client
        
        self.tools = {
            "image_analysis": LLaVATool(llava_client),
            "review_clustering": ReviewClusterTool(embedding_service),
            "competitor_diff": CompetitorDiffTool(qdrant_client),
            "swot_generator": SWOTGeneratorTool(llm_client)
        }
    
    async def analyze(
        self,
        market_data: Dict[str, Any],
        product_images: List[str] = None,
        reviews: List[Dict] = None
    ) -> ProductDefinition:
        image_features = await self._analyze_images(product_images)
        
        pain_points = await self._cluster_reviews(reviews)
        
        competitor_matrix = await self._analyze_competitors(market_data)
        
        swot = await self._generate_swot(
            image_features,
            pain_points,
            competitor_matrix
        )
        
        product_def = await self._synthesize_definition(
            market_data,
            image_features,
            pain_points,
            competitor_matrix,
            swot
        )
        
        return product_def
```

### 2.2 LLaVA多模态工具

```python
class LLaVATool:
    def __init__(self, llava_client):
        self.client = llava_client
    
    async def analyze_product_image(self, image_url: str) -> Dict[str, Any]:
        prompt = """分析这张商品图片，提取以下信息：
        1. 产品类型和类别
        2. 主要颜色和外观特征
        3. 材质推断
        4. 功能特征
        5. 目标用户群体
        6. 潜在卖点
        """
        
        response = await self.client.generate(
            image=image_url,
            prompt=prompt
        )
        
        return self._parse_response(response)
    
    async def batch_analyze(
        self,
        image_urls: List[str]
    ) -> List[Dict[str, Any]]:
        tasks = [
            self.analyze_product_image(url)
            for url in image_urls
        ]
        return await asyncio.gather(*tasks)
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        return {
            "product_type": self._extract_type(response),
            "visual_features": self._extract_features(response),
            "materials": self._extract_materials(response),
            "target_users": self._extract_users(response),
            "selling_points": self._extract_selling_points(response)
        }
```

### 2.3 评论聚类工具

```python
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

class ReviewClusterTool:
    def __init__(self, embedding_service):
        self.embedding = embedding_service
        self.vectorizer = TfidfVectorizer(max_features=1000)
        self.n_clusters = 5
    
    async def cluster_reviews(
        self,
        reviews: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        texts = [r.get("content", "") for r in reviews]
        ratings = [r.get("rating", 3) for r in reviews]
        
        embeddings = await self.embedding.embed_batch(texts)
        embeddings_array = np.array(embeddings)
        
        kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=42
        )
        cluster_labels = kmeans.fit_predict(embeddings_array)
        
        clusters = self._organize_clusters(
            texts,
            ratings,
            cluster_labels
        )
        
        pain_points = self._extract_pain_points(clusters)
        highlights = self._extract_highlights(clusters)
        
        return {
            "clusters": clusters,
            "pain_points": pain_points,
            "highlights": highlights,
            "cluster_distribution": self._get_distribution(cluster_labels)
        }
    
    def _organize_clusters(
        self,
        texts: List[str],
        ratings: List[int],
        labels: np.ndarray
    ) -> Dict[int, Dict]:
        clusters = {}
        for i, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = {
                    "reviews": [],
                    "avg_rating": 0,
                    "keywords": []
                }
            clusters[label]["reviews"].append({
                "text": texts[i],
                "rating": ratings[i]
            })
        
        for label, cluster in clusters.items():
            ratings_list = [r["rating"] for r in cluster["reviews"]]
            cluster["avg_rating"] = np.mean(ratings_list)
            cluster["keywords"] = self._extract_keywords(
                [r["text"] for r in cluster["reviews"]]
            )
        
        return clusters
    
    def _extract_pain_points(
        self,
        clusters: Dict[int, Dict]
    ) -> List[Dict[str, Any]]:
        pain_points = []
        
        for label, cluster in clusters.items():
            if cluster["avg_rating"] < 3.5:
                pain_points.append({
                    "cluster_id": label,
                    "keywords": cluster["keywords"][:5],
                    "avg_rating": cluster["avg_rating"],
                    "sample_reviews": cluster["reviews"][:3],
                    "severity": self._calculate_severity(cluster)
                })
        
        return sorted(pain_points, key=lambda x: x["severity"], reverse=True)
    
    def _extract_highlights(
        self,
        clusters: Dict[int, Dict]
    ) -> List[Dict[str, Any]]:
        highlights = []
        
        for label, cluster in clusters.items():
            if cluster["avg_rating"] >= 4.0:
                highlights.append({
                    "cluster_id": label,
                    "keywords": cluster["keywords"][:5],
                    "avg_rating": cluster["avg_rating"],
                    "sample_reviews": cluster["reviews"][:3]
                })
        
        return sorted(highlights, key=lambda x: x["avg_rating"], reverse=True)
```

### 2.4 竞品差异化工具

```python
class CompetitorDiffTool:
    def __init__(self, qdrant_client):
        self.qdrant = qdrant_client
    
    async def analyze(
        self,
        market_data: Dict[str, Any],
        product_features: Dict[str, Any]
    ) -> Dict[str, Any]:
        competitors = market_data.get("competitors", [])
        
        competitor_matrix = []
        for comp in competitors:
            diff = await self._calculate_difference(
                product_features,
                comp
            )
            competitor_matrix.append(diff)
        
        differentiators = self._identify_differentiators(
            product_features,
            competitor_matrix
        )
        
        positioning = self._suggest_positioning(
            product_features,
            competitor_matrix
        )
        
        return {
            "competitor_matrix": competitor_matrix,
            "differentiators": differentiators,
            "positioning_suggestion": positioning,
            "market_gaps": self._find_market_gaps(competitor_matrix)
        }
    
    async def _calculate_difference(
        self,
        product: Dict,
        competitor: Dict
    ) -> Dict[str, Any]:
        return {
            "competitor_id": competitor.get("id"),
            "competitor_name": competitor.get("name"),
            "price_diff": product.get("price", 0) - competitor.get("price", 0),
            "feature_diff": self._compare_features(
                product.get("features", []),
                competitor.get("features", [])
            ),
            "rating_diff": product.get("rating", 0) - competitor.get("rating", 0),
            "advantages": [],
            "disadvantages": []
        }
    
    def _identify_differentiators(
        self,
        product: Dict,
        matrix: List[Dict]
    ) -> List[Dict[str, Any]]:
        differentiators = []
        
        for diff in matrix:
            if diff["price_diff"] < 0:
                differentiators.append({
                    "type": "price",
                    "description": f"价格低于{diff['competitor_name']}",
                    "advantage": True
                })
            
            if diff["rating_diff"] > 0.3:
                differentiators.append({
                    "type": "quality",
                    "description": f"评分高于{diff['competitor_name']}",
                    "advantage": True
                })
        
        return differentiators
```

### 2.5 SWOT分析生成器

```python
class SWOTGeneratorTool:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def generate(
        self,
        image_features: Dict,
        pain_points: List[Dict],
        competitor_matrix: List[Dict]
    ) -> Dict[str, List[str]]:
        prompt = f"""
        基于以下信息生成SWOT分析：
        
        产品特征：{json.dumps(image_features, ensure_ascii=False)}
        用户痛点：{json.dumps(pain_points[:5], ensure_ascii=False)}
        竞品对比：{json.dumps(competitor_matrix[:3], ensure_ascii=False)}
        
        请分别列出：
        1. Strengths（优势）：3-5条
        2. Weaknesses（劣势）：3-5条
        3. Opportunities（机会）：3-5条
        4. Threats（威胁）：3-5条
        """
        
        response = await self.llm.generate(prompt)
        
        return self._parse_swot(response)
    
    def _parse_swot(self, response: str) -> Dict[str, List[str]]:
        return {
            "strengths": self._extract_section(response, "Strengths", "优势"),
            "weaknesses": self._extract_section(response, "Weaknesses", "劣势"),
            "opportunities": self._extract_section(response, "Opportunities", "机会"),
            "threats": self._extract_section(response, "Threats", "威胁")
        }
```

---

## 3. 商业化Agent设计

### 3.1 Agent架构

```python
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class PricingStrategy(str, Enum):
    COST_PLUS = "cost_plus"
    COMPETITION_BASED = "competition_based"
    VALUE_BASED = "value_based"
    PENETRATION = "penetration"

@dataclass
class CostBreakdown:
    purchase_cost: float
    shipping_cost: float
    fba_fee: float
    platform_commission: float
    advertising_cost: float
    other_costs: float
    total_cost: float

@dataclass
class ProfitAnalysis:
    gross_margin: float
    net_margin: float
    break_even_units: int
    break_even_days: int
    monthly_profit: float
    annual_profit: float

@dataclass
class PricingRecommendation:
    suggested_price: float
    min_price: float
    max_price: float
    strategy: PricingStrategy
    reasoning: str

@dataclass
class ROIPrediction:
    initial_investment: float
    monthly_return: float
    payback_period_months: int
    annual_roi: float
    risk_level: str

class CommercialAgent:
    def __init__(
        self,
        scm_client,
        fms_client,
        logistics_api,
        amazon_api
    ):
        self.scm = scm_client
        self.fms = fms_client
        self.logistics = logistics_api
        self.amazon = amazon_api
    
    async def analyze(
        self,
        product_definition: ProductDefinition,
        market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        costs = await self._calculate_costs(product_definition)
        
        profit = await self._analyze_profit(costs, market_data)
        
        pricing = await self._recommend_pricing(
            costs,
            profit,
            market_data
        )
        
        roi = await self._predict_roi(costs, profit, market_data)
        
        return {
            "cost_breakdown": costs,
            "profit_analysis": profit,
            "pricing_recommendation": pricing,
            "roi_prediction": roi,
            "go_no_go": self._make_decision(profit, roi)
        }
```

### 3.2 成本计算引擎

```python
class CostEngine:
    def __init__(
        self,
        scm_client,
        logistics_api,
        amazon_api
    ):
        self.scm = scm_client
        self.logistics = logistics_api
        self.amazon = amazon_api
    
    async def calculate(
        self,
        product: ProductDefinition,
        supplier_id: str = None
    ) -> CostBreakdown:
        purchase_cost = await self._get_purchase_cost(
            product,
            supplier_id
        )
        
        shipping_cost = await self._calculate_shipping(product)
        
        fba_fee = await self._calculate_fba_fee(product)
        
        platform_commission = self._calculate_commission(
            product.recommended_price_range[0]
        )
        
        advertising_cost = await self._estimate_advertising(product)
        
        other_costs = self._calculate_other_costs(product)
        
        total = (
            purchase_cost +
            shipping_cost +
            fba_fee +
            platform_commission +
            advertising_cost +
            other_costs
        )
        
        return CostBreakdown(
            purchase_cost=purchase_cost,
            shipping_cost=shipping_cost,
            fba_fee=fba_fee,
            platform_commission=platform_commission,
            advertising_cost=advertising_cost,
            other_costs=other_costs,
            total_cost=total
        )
    
    async def _get_purchase_cost(
        self,
        product: ProductDefinition,
        supplier_id: str = None
    ) -> float:
        if supplier_id:
            supplier = await self.scm.get_supplier(supplier_id)
            return supplier.get("unit_price", 0)
        
        suppliers = await self.scm.search_suppliers(
            product.category,
            product.key_features
        )
        
        if suppliers:
            return min(s.get("unit_price", float("inf")) for s in suppliers)
        
        return 0
    
    async def _calculate_shipping(
        self,
        product: ProductDefinition
    ) -> float:
        weight = product.weight or 0.5
        volume = product.volume or 0.01
        
        quote = await self.logistics.get_quote(
            origin="CN",
            destination="US",
            weight=weight,
            volume=volume
        )
        
        return quote.get("cost", 0)
    
    async def _calculate_fba_fee(
        self,
        product: ProductDefinition
    ) -> float:
        fee = await self.amazon.calculate_fba_fee(
            category=product.category,
            dimensions=product.dimensions,
            weight=product.weight
        )
        
        return fee
    
    def _calculate_commission(self, price: float) -> float:
        commission_rate = 0.15
        return price * commission_rate
    
    async def _estimate_advertising(
        self,
        product: ProductDefinition
    ) -> float:
        base_ad_spend = 0.05
        
        competition_factor = 1.0 + (product.risk_level == "high" and 0.5 or 0)
        
        return product.recommended_price_range[0] * base_ad_spend * competition_factor
```

### 3.3 利润分析器

```python
class ProfitAnalyzer:
    def __init__(self):
        self.target_margin = 0.25
    
    def analyze(
        self,
        costs: CostBreakdown,
        market_data: Dict[str, Any]
    ) -> ProfitAnalysis:
        avg_price = market_data.get("avg_price", 0)
        estimated_sales = market_data.get("estimated_monthly_sales", 0)
        
        gross_profit = avg_price - costs.total_cost
        gross_margin = gross_profit / avg_price if avg_price > 0 else 0
        
        net_profit = gross_profit * 0.9
        net_margin = net_profit / avg_price if avg_price > 0 else 0
        
        monthly_profit = net_profit * estimated_sales
        
        break_even_units = int(costs.total_cost / gross_profit) if gross_profit > 0 else 0
        break_even_days = int(break_even_units / (estimated_sales / 30)) if estimated_sales > 0 else 0
        
        return ProfitAnalysis(
            gross_margin=gross_margin,
            net_margin=net_margin,
            break_even_units=break_even_units,
            break_even_days=break_even_days,
            monthly_profit=monthly_profit,
            annual_profit=monthly_profit * 12
        )
    
    def evaluate_profitability(
        self,
        analysis: ProfitAnalysis
    ) -> Dict[str, Any]:
        if analysis.gross_margin >= self.target_margin:
            rating = "excellent"
        elif analysis.gross_margin >= self.target_margin * 0.8:
            rating = "good"
        elif analysis.gross_margin >= self.target_margin * 0.6:
            rating = "acceptable"
        else:
            rating = "poor"
        
        return {
            "rating": rating,
            "meets_target": analysis.gross_margin >= self.target_margin,
            "margin_gap": self.target_margin - analysis.gross_margin
        }
```

### 3.4 定价建议器

```python
class PricingRecommender:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def recommend(
        self,
        costs: CostBreakdown,
        profit: ProfitAnalysis,
        market_data: Dict[str, Any]
    ) -> PricingRecommendation:
        cost_plus_price = self._cost_plus_pricing(costs)
        
        competition_price = self._competition_pricing(market_data)
        
        value_price = await self._value_pricing(costs, market_data)
        
        final_price = self._select_optimal_price(
            cost_plus_price,
            competition_price,
            value_price,
            market_data
        )
        
        return PricingRecommendation(
            suggested_price=final_price,
            min_price=costs.total_cost * 1.1,
            max_price=competition_price * 1.3,
            strategy=self._determine_strategy(market_data),
            reasoning=await self._generate_reasoning(
                final_price,
                costs,
                market_data
            )
        )
    
    def _cost_plus_pricing(self, costs: CostBreakdown) -> float:
        target_margin = 0.30
        return costs.total_cost / (1 - target_margin)
    
    def _competition_pricing(self, market_data: Dict) -> float:
        competitor_prices = market_data.get("competitor_prices", [])
        if competitor_prices:
            return sum(competitor_prices) / len(competitor_prices)
        return 0
    
    async def _value_pricing(
        self,
        costs: CostBreakdown,
        market_data: Dict
    ) -> float:
        prompt = f"""
        基于以下信息，计算价值导向定价：
        - 成本：{costs.total_cost}
        - 市场平均价：{market_data.get('avg_price', 0)}
        - 产品差异化：{market_data.get('differentiators', [])}
        - 目标利润率：30%
        
        请给出建议价格和理由。
        """
        
        response = await self.llm.generate(prompt)
        return self._parse_price(response)
```

### 3.5 ROI预测器

```python
class ROIPredictor:
    def __init__(self):
        self.min_acceptable_roi = 0.20
        self.max_payback_months = 12
    
    def predict(
        self,
        costs: CostBreakdown,
        profit: ProfitAnalysis,
        market_data: Dict[str, Any]
    ) -> ROIPrediction:
        initial_investment = self._calculate_initial_investment(
            costs,
            market_data
        )
        
        monthly_return = profit.monthly_profit
        
        if monthly_return > 0:
            payback_period = int(initial_investment / monthly_return)
        else:
            payback_period = 999
        
        annual_return = profit.annual_profit
        annual_roi = (annual_return - initial_investment) / initial_investment
        
        risk_level = self._assess_risk(
            payback_period,
            annual_roi,
            market_data
        )
        
        return ROIPrediction(
            initial_investment=initial_investment,
            monthly_return=monthly_return,
            payback_period_months=payback_period,
            annual_roi=annual_roi,
            risk_level=risk_level
        )
    
    def _calculate_initial_investment(
        self,
        costs: CostBreakdown,
        market_data: Dict
    ) -> float:
        first_order_qty = market_data.get("initial_order_quantity", 100)
        return costs.purchase_cost * first_order_qty + costs.shipping_cost
    
    def _assess_risk(
        self,
        payback_months: int,
        roi: float,
        market_data: Dict
    ) -> str:
        risk_score = 0
        
        if payback_months > self.max_payback_months:
            risk_score += 2
        elif payback_months > self.max_payback_months * 0.7:
            risk_score += 1
        
        if roi < self.min_acceptable_roi:
            risk_score += 2
        elif roi < self.min_acceptable_roi * 1.5:
            risk_score += 1
        
        competition = market_data.get("competition_level", "medium")
        if competition == "high":
            risk_score += 1
        
        if risk_score >= 4:
            return "high"
        elif risk_score >= 2:
            return "medium"
        else:
            return "low"
```

---

## 4. vLLM四节点集群

### 4.1 集群架构

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-cluster
  namespace: pms-ai
spec:
  replicas: 4
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          ports:
            - containerPort: 8000
          resources:
            limits:
              nvidia.com/gpu: 2
          env:
            - name: MODEL_NAME
              value: "Qwen/Qwen2.5-72B-Instruct"
            - name: TENSOR_PARALLEL_SIZE
              value: "2"
            - name: PIPELINE_PARALLEL_SIZE
              value: "2"
          volumeMounts:
            - name: model-cache
              mountPath: /root/.cache
      volumes:
        - name: model-cache
          persistentVolumeClaim:
            claimName: model-cache-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-service
  namespace: pms-ai
spec:
  selector:
    app: vllm
  ports:
    - port: 8000
      targetPort: 8000
```

### 4.2 负载均衡配置

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vllm-lb-config
  namespace: pms-ai
data:
  nginx.conf: |
    upstream vllm_backend {
        least_conn;
        server vllm-0.vllm-headless:8000;
        server vllm-1.vllm-headless:8000;
        server vllm-2.vllm-headless:8000;
        server vllm-3.vllm-headless:8000;
    }
    
    server {
        listen 8000;
        
        location / {
            proxy_pass http://vllm_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 300s;
        }
    }
```

---

## 5. LLM Gateway智能路由

### 5.1 路由策略

```python
from enum import Enum
from typing import Dict, Any, Optional
import asyncio

class ModelTier(str, Enum):
    PREMIUM = "premium"
    STANDARD = "standard"
    ECONOMY = "economy"

class TaskComplexity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class LLMGateway:
    def __init__(self):
        self.models = {
            ModelTier.PREMIUM: {
                "endpoint": "http://vllm-premium:8000",
                "model": "Qwen/Qwen2.5-72B-Instruct",
                "max_tokens": 8192
            },
            ModelTier.STANDARD: {
                "endpoint": "http://vllm-standard:8000",
                "model": "Qwen/Qwen2.5-32B-Instruct",
                "max_tokens": 4096
            },
            ModelTier.ECONOMY: {
                "endpoint": "http://ollama:11434",
                "model": "phi-3-mini",
                "max_tokens": 2048
            }
        }
        
        self.circuit_breakers = {
            tier: CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60
            )
            for tier in ModelTier
        }
    
    async def route(
        self,
        prompt: str,
        task_type: str = "general",
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        complexity = self._assess_complexity(prompt, task_type)
        
        tier = self._select_tier(complexity, max_tokens)
        
        model_config = self.models[tier]
        
        if not self.circuit_breakers[tier].allow_request():
            tier = self._fallback_tier(tier)
            model_config = self.models[tier]
        
        try:
            response = await self._call_model(
                model_config,
                prompt,
                max_tokens
            )
            self.circuit_breakers[tier].record_success()
            return response
        except Exception as e:
            self.circuit_breakers[tier].record_failure()
            raise
    
    def _assess_complexity(
        self,
        prompt: str,
        task_type: str
    ) -> TaskComplexity:
        high_complexity_tasks = [
            "market_analysis",
            "product_planning",
            "commercial_analysis"
        ]
        
        low_complexity_tasks = [
            "summarization",
            "translation",
            "classification"
        ]
        
        if task_type in high_complexity_tasks:
            return TaskComplexity.HIGH
        elif task_type in low_complexity_tasks:
            return TaskComplexity.LOW
        
        if len(prompt) > 2000:
            return TaskComplexity.HIGH
        elif len(prompt) > 500:
            return TaskComplexity.MEDIUM
        
        return TaskComplexity.LOW
    
    def _select_tier(
        self,
        complexity: TaskComplexity,
        max_tokens: int
    ) -> ModelTier:
        if complexity == TaskComplexity.HIGH or max_tokens > 4096:
            return ModelTier.PREMIUM
        elif complexity == TaskComplexity.MEDIUM:
            return ModelTier.STANDARD
        else:
            return ModelTier.ECONOMY
    
    def _fallback_tier(self, failed_tier: ModelTier) -> ModelTier:
        fallback_map = {
            ModelTier.PREMIUM: ModelTier.STANDARD,
            ModelTier.STANDARD: ModelTier.ECONOMY,
            ModelTier.ECONOMY: ModelTier.ECONOMY
        }
        return fallback_map[failed_tier]
```

### 5.2 熔断器实现

```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0
    
    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        return True
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
        self.failure_count = 0
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

---

## 附录

### A. 验收检查清单

```markdown
## D33-D38 验收检查清单

### 产品规划Agent
- [ ] LLaVA多模态分析可用
- [ ] 评论聚类功能正常
- [ ] 竞品差异化分析正确
- [ ] SWOT分析输出完整
- [ ] 产品定义报告生成

### 商业化Agent
- [ ] 成本计算准确
- [ ] 利润分析正确
- [ ] 定价建议合理
- [ ] ROI预测可信
- [ ] Go/No-Go决策输出

### vLLM集群
- [ ] 四节点全部运行
- [ ] 负载均衡生效
- [ ] 推理延迟达标

### LLM Gateway
- [ ] 智能路由正确
- [ ] 熔断器工作正常
- [ ] 降级策略有效
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
