# Embedding与数据采集方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D10-D12 Embedding与数据采集
> **文档版本**: v1.0
>
> **更新说明（2026-04-19）**: 当前本地默认方案已切换为 `bge-reranker-base (纯CPU)`、`Whisper tiny / base (纯CPU)` 与 `Qwen3.5-2B / TinyGPT-V (GGUF量化)`。本文中的 Triton GPU 路线保留为历史高配 / 扩展方案。

---

## 目录

- [1. 概述](#1-概述)
- [2. Embedding服务](#2-embedding服务)
- [3. Rerank服务](#3-rerank服务)
- [4. 数据采集爬虫](#4-数据采集爬虫)
- [5. Flink实时处理](#5-flink实时处理)

---

## 1. 概述

### 1.1 部署目标

完成Embedding/Rerank模型部署、数据采集爬虫开发和实时处理引擎搭建，为RAG检索和数据分析提供基础能力。

### 1.2 组件规划

| 组件 | 规格 | 用途 |
|------|------|------|
| BGE-large-zh | Triton GPU | 文本向量化 |
| bge-reranker-v2 | Triton GPU | 重排序 |
| Amazon爬虫 | Python | 数据采集 |
| Flink | 集群 | 实时处理 |

---

## 2. Embedding服务

### 2.1 服务架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Embedding服务架构                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    API层                                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ REST API │ │ gRPC API │ │ Batch API│               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Triton推理服务器                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 模型加载  │ │ 批处理   │ │ 动态批处理│               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    模型层                                │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │           BAAI/bge-large-zh-v1.5                  │  │   │
│  │  │           (1024维向量)                            │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Triton部署配置

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: triton-embedding
  namespace: pms-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: triton-embedding
  template:
    metadata:
      labels:
        app: triton-embedding
    spec:
      nodeSelector:
        node-role.kubernetes.io/worker-gpu: ""
      containers:
        - name: triton
          image: nvcr.io/nvidia/tritonserver:23.10-py3
          ports:
            - containerPort: 8000
              name: http
            - containerPort: 8001
              name: grpc
            - containerPort: 8002
              name: metrics
          args:
            - tritonserver
            - --model-repository=/models
            - --enable-gpu-metrics=true
          resources:
            limits:
              nvidia.com/gpu: 1
          volumeMounts:
            - name: model-repository
              mountPath: /models
      volumes:
        - name: model-repository
          persistentVolumeClaim:
            claimName: triton-models-pvc
```

### 2.3 Embedding服务封装

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import httpx

app = FastAPI()

class EmbeddingRequest(BaseModel):
    texts: List[str]
    normalize: bool = True

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    dimension: int
    model: str

TRITON_URL = "http://triton-embedding:8000"

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TRITON_URL}/v2/models/bge-large-zh/infer",
            json={
                "inputs": [
                    {
                        "name": "input_ids",
                        "shape": [len(request.texts), 512],
                        "datatype": "INT32",
                        "data": await tokenize(request.texts)
                    }
                ]
            }
        )
        
        result = response.json()
        embeddings = result["outputs"][0]["data"]
        
        if request.normalize:
            embeddings = normalize_embeddings(embeddings)
        
        return EmbeddingResponse(
            embeddings=embeddings,
            dimension=1024,
            model="bge-large-zh-v1.5"
        )

async def tokenize(texts: List[str]) -> List[List[int]]:
    pass

def normalize_embeddings(embeddings: List[List[float]]) -> List[List[float]]:
    import numpy as np
    normalized = []
    for emb in embeddings:
        arr = np.array(emb)
        norm = np.linalg.norm(arr)
        if norm > 0:
            normalized.append((arr / norm).tolist())
        else:
            normalized.append(emb)
    return normalized
```

### 2.4 性能指标

```yaml
embedding_performance:
  single_request:
    latency_p50: 10ms
    latency_p99: 25ms
  
  batch_request:
    batch_size: 32
    latency_p50: 50ms
    throughput: 5000 QPS
```

---

## 3. Rerank服务

### 3.1 服务架构

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: int = 5

class RerankResult(BaseModel):
    index: int
    document: str
    score: float

class RerankResponse(BaseModel):
    results: List[RerankResult]

@app.post("/v1/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    from sentence_transformers import CrossEncoder
    
    model = CrossEncoder('BAAI/bge-reranker-v2-m3')
    
    pairs = [[request.query, doc] for doc in request.documents]
    scores = model.predict(pairs)
    
    ranked = sorted(
        enumerate(scores),
        key=lambda x: x[1],
        reverse=True
    )[:request.top_k]
    
    results = [
        RerankResult(
            index=idx,
            document=request.documents[idx],
            score=float(score)
        )
        for idx, score in ranked
    ]
    
    return RerankResponse(results=results)
```

### 3.2 Rerank Pipeline

```python
class RerankPipeline:
    def __init__(self, rerank_service_url: str):
        self.rerank_url = rerank_service_url
    
    async def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int = 5
    ) -> List[dict]:
        documents = [c["content"] for c in candidates]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.rerank_url}/v1/rerank",
                json={
                    "query": query,
                    "documents": documents,
                    "top_k": top_k
                }
            )
        
        result = response.json()
        
        reranked = []
        for r in result["results"]:
            candidate = candidates[r["index"]].copy()
            candidate["rerank_score"] = r["score"]
            reranked.append(candidate)
        
        return reranked
```

---

## 4. 数据采集爬虫

### 4.1 爬虫架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    数据采集爬虫架构                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    调度层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 任务队列  │ │ 代理管理  │ │ 限流控制  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    采集层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │Amazon BSR│ │ 评论采集  │ │ 商品详情  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    输出层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Kafka    │ │ 数据库   │ │ 文件存储  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Amazon BSR爬虫

```python
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict
import random

class AmazonBSRCrawler:
    def __init__(self, proxy_pool: List[str], kafka_producer):
        self.proxy_pool = proxy_pool
        self.kafka_producer = kafka_producer
        self.base_url = "https://www.amazon.com/Best-Sellers/zgbs"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
    
    async def crawl_category(self, category: str) -> List[Dict]:
        url = f"{self.base_url}/{category}"
        proxy = random.choice(self.proxy_pool)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self.headers,
                proxy=proxy,
                timeout=30
            ) as response:
                html = await response.text()
        
        products = self._parse_bsr_page(html, category)
        
        for product in products:
            await self.kafka_producer.send(
                "amazon-data",
                product
            )
        
        return products
    
    def _parse_bsr_page(self, html: str, category: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        products = []
        
        items = soup.select("#zg-ordered-list li")
        
        for rank, item in enumerate(items, 1):
            try:
                product = {
                    "asin": self._extract_asin(item),
                    "title": self._extract_title(item),
                    "price": self._extract_price(item),
                    "rating": self._extract_rating(item),
                    "review_count": self._extract_review_count(item),
                    "rank": rank,
                    "category": category,
                    "source": "amazon_bsr",
                    "timestamp": datetime.now().isoformat()
                }
                products.append(product)
            except Exception as e:
                print(f"Parse error: {e}")
        
        return products
    
    def _extract_asin(self, item) -> str:
        link = item.select_one("a.a-link-normal")
        if link:
            href = link.get("href", "")
            if "/dp/" in href:
                return href.split("/dp/")[1].split("/")[0]
        return ""
    
    def _extract_title(self, item) -> str:
        title_elem = item.select_one(".p13n-sc-truncated")
        return title_elem.text.strip() if title_elem else ""
    
    def _extract_price(self, item) -> float:
        price_elem = item.select_one(".p13n-sc-price")
        if price_elem:
            price_text = price_elem.text.replace("$", "").replace(",", "")
            return float(price_text)
        return 0.0
    
    def _extract_rating(self, item) -> float:
        rating_elem = item.select_one(".a-icon-star-small")
        if rating_elem:
            rating_text = rating_elem.text.split()[0]
            return float(rating_text)
        return 0.0
    
    def _extract_review_count(self, item) -> int:
        review_elem = item.select_one(".a-size-small")
        if review_elem:
            review_text = review_elem.text.replace(",", "")
            return int(review_text)
        return 0
```

### 4.3 评论爬虫

```python
class AmazonReviewCrawler:
    def __init__(self, proxy_pool: List[str], kafka_producer):
        self.proxy_pool = proxy_pool
        self.kafka_producer = kafka_producer
        self.base_url = "https://www.amazon.com/product-reviews/{asin}"
    
    async def crawl_reviews(
        self,
        asin: str,
        max_pages: int = 10
    ) -> List[Dict]:
        reviews = []
        
        for page in range(1, max_pages + 1):
            url = self.base_url.format(asin=asin)
            params = {"pageNumber": page}
            proxy = random.choice(self.proxy_pool)
            
            await asyncio.sleep(random.uniform(1, 3))
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    proxy=proxy,
                    timeout=30
                ) as response:
                    html = await response.text()
            
            page_reviews = self._parse_reviews(html, asin)
            
            if not page_reviews:
                break
            
            reviews.extend(page_reviews)
            
            for review in page_reviews:
                await self.kafka_producer.send(
                    "amazon-reviews",
                    review
                )
        
        return reviews
    
    def _parse_reviews(self, html: str, asin: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        reviews = []
        
        review_items = soup.select("[data-hook='review']")
        
        for item in review_items:
            review = {
                "review_id": item.get("id", ""),
                "asin": asin,
                "rating": self._extract_review_rating(item),
                "title": self._extract_review_title(item),
                "content": self._extract_review_content(item),
                "author": self._extract_review_author(item),
                "date": self._extract_review_date(item),
                "verified": self._is_verified(item),
                "helpful_votes": self._extract_helpful_votes(item),
                "timestamp": datetime.now().isoformat()
            }
            reviews.append(review)
        
        return reviews
    
    def _extract_review_rating(self, item) -> float:
        rating_elem = item.select_one(".a-icon-star-small")
        if rating_elem:
            rating_text = rating_elem.text.split()[0]
            return float(rating_text)
        return 0.0
    
    def _extract_review_title(self, item) -> str:
        title_elem = item.select_one("[data-hook='review-title']")
        return title_elem.text.strip() if title_elem else ""
    
    def _extract_review_content(self, item) -> str:
        content_elem = item.select_one("[data-hook='review-body']")
        return content_elem.text.strip() if content_elem else ""
```

### 4.4 反爬策略

```python
class AntiScrapingStrategy:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        ]
        
        self.request_interval = (1, 5)
        self.max_retries = 3
    
    def get_random_user_agent(self) -> str:
        return random.choice(self.user_agents)
    
    async def wait_random(self):
        wait_time = random.uniform(*self.request_interval)
        await asyncio.sleep(wait_time)
    
    async def request_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        **kwargs
    ) -> aiohttp.ClientResponse:
        for attempt in range(self.max_retries):
            try:
                await self.wait_random()
                
                kwargs["headers"] = kwargs.get("headers", {})
                kwargs["headers"]["User-Agent"] = self.get_random_user_agent()
                
                response = await session.get(url, **kwargs)
                
                if response.status == 200:
                    return response
                elif response.status == 429:
                    await asyncio.sleep(60)
                elif response.status == 403:
                    kwargs["proxy"] = self.rotate_proxy()
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("Max retries exceeded")
```

---

## 5. Flink实时处理

### 5.1 Flink集群部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flink-jobmanager
  namespace: pms-data
spec:
  replicas: 1
  selector:
    matchLabels:
      app: flink
      role: jobmanager
  template:
    metadata:
      labels:
        app: flink
        role: jobmanager
    spec:
      containers:
        - name: jobmanager
          image: flink:1.17.1
          ports:
            - containerPort: 8081
              name: webui
            - containerPort: 6123
              name: rpc
          env:
            - name: FLINK_PROPERTIES
              value: |
                jobmanager.rpc.address: flink-jobmanager
                jobmanager.rpc.port: 6123
                jobmanager.memory.process.size: 2048m
          command: ["jobmanager"]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flink-taskmanager
  namespace: pms-data
spec:
  replicas: 3
  selector:
    matchLabels:
      app: flink
      role: taskmanager
  template:
    metadata:
      labels:
        app: flink
        role: taskmanager
    spec:
      containers:
        - name: taskmanager
          image: flink:1.17.1
          env:
            - name: FLINK_PROPERTIES
              value: |
                jobmanager.rpc.address: flink-jobmanager
                jobmanager.rpc.port: 6123
                taskmanager.memory.process.size: 4096m
                taskmanager.numberOfTaskSlots: 4
          command: ["taskmanager"]
```

### 5.2 ETL处理作业

```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink
from pyflink.common.serialization import JsonRowDeserializationSchema, JsonRowSerializationSchema
from pyflink.datastream.functions import ProcessFunction

class DataCleaningETL:
    def __init__(self):
        self.env = StreamExecutionEnvironment.get_execution_environment()
        self.env.set_parallelism(4)
    
    def create_kafka_source(self):
        return KafkaSource.builder() \
            .set_bootstrap_servers("kafka:9092") \
            .set_topics("amazon-data") \
            .set_group_id("etl-consumer") \
            .set_starting_offsets(OffsetsInitializer.earliest()) \
            .set_value_only_deserializer(
                JsonRowDeserializationSchema.builder()
                .type_info(Types.ROW([Types.STRING(), Types.STRING(), Types.FLOAT()]))
                .build()
            ) \
            .build()
    
    def create_kafka_sink(self):
        return KafkaSink.builder() \
            .set_bootstrap_servers("kafka:9092") \
            .set_record_serializer(
                KafkaRecordSerializationSchema.builder()
                .set_topic("amazon-data-cleaned")
                .set_value_serialization_schema(
                    JsonRowSerializationSchema.builder()
                    .with_type_info(Types.ROW([Types.STRING(), Types.STRING(), Types.FLOAT()]))
                    .build()
                )
                .build()
            ) \
            .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE) \
            .build()
    
    def clean_data(self, row):
        cleaned = row.copy()
        
        if cleaned.price < 0 or cleaned.price > 99999:
            cleaned.price = None
        
        if cleaned.rating < 0 or cleaned.rating > 5:
            cleaned.rating = None
        
        cleaned.title = cleaned.title.strip() if cleaned.title else ""
        
        return cleaned
    
    def run(self):
        source = self.create_kafka_source()
        sink = self.create_kafka_sink()
        
        stream = self.env.from_source(
            source,
            WatermarkStrategy.no_watermarks(),
            "Kafka Source"
        )
        
        cleaned_stream = stream.process(self.clean_data)
        
        cleaned_stream.sink_to(sink)
        
        self.env.execute("Amazon Data ETL")
```

### 5.3 数据质量检查

```python
class DataQualityChecker:
    def __init__(self):
        self.rules = {
            "price": lambda x: x is None or (0 < x <= 99999),
            "rating": lambda x: x is None or (0 <= x <= 5),
            "title": lambda x: len(x) > 0 and len(x) <= 500,
            "asin": lambda x: len(x) == 10 and x.isalnum()
        }
    
    def check(self, data: dict) -> dict:
        result = {
            "valid": True,
            "errors": []
        }
        
        for field, rule in self.rules.items():
            value = data.get(field)
            if not rule(value):
                result["valid"] = False
                result["errors"].append({
                    "field": field,
                    "value": value,
                    "message": f"Invalid {field}"
                })
        
        return result
    
    def check_batch(self, data_list: list) -> dict:
        results = {
            "total": len(data_list),
            "valid": 0,
            "invalid": 0,
            "errors": []
        }
        
        for data in data_list:
            check_result = self.check(data)
            if check_result["valid"]:
                results["valid"] += 1
            else:
                results["invalid"] += 1
                results["errors"].extend(check_result["errors"])
        
        return results
```

---

## 附录

### A. 验收检查清单

```markdown
## D10-D12 验收检查清单

### Embedding服务
- [ ] Triton服务运行正常
- [ ] BGE模型加载成功
- [ ] API响应延迟<25ms
- [ ] 吞吐量>5000 QPS

### Rerank服务
- [ ] Rerank API可用
- [ ] 延迟<100ms
- [ ] 排序准确率验证

### 数据采集
- [ ] Amazon BSR爬虫可用
- [ ] 评论爬虫可用
- [ ] 数据入库正常
- [ ] 反爬策略生效

### Flink
- [ ] 集群运行正常
- [ ] ETL作业提交成功
- [ ] 数据质量达标
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
