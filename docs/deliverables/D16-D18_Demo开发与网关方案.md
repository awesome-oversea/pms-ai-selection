# Demo开发与网关方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D16-D18 Demo开发与网关
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. Demo后端接口](#2-demo后端接口)
- [3. Demo前端开发](#3-demo前端开发)
- [4. Kong网关配置](#4-kong网关配置)
- [5. Elasticsearch部署](#5-elasticsearch部署)

---

## 1. 概述

### 1.1 开发目标

开发"商品趋势问答"Demo系统，完成API网关和全文检索引擎部署，验证RAG框架端到端能力。

### 1.2 组件规划

| 组件 | 技术 | 用途 |
|------|------|------|
| Demo后端 | FastAPI | RAG接口服务 |
| Demo前端 | Streamlit | Web界面 |
| API网关 | Kong | 路由/认证/限流 |
| 搜索引擎 | Elasticsearch | 全文检索 |

---

## 2. Demo后端接口

### 2.1 API设计

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio

app = FastAPI(
    title="FMS Demo API",
    description="AI选品系统Demo接口",
    version="1.0.0"
)

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    use_rerank: bool = True
    filters: Optional[dict] = None

class Source(BaseModel):
    chunk_id: str
    content: str
    score: float
    metadata: dict

class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    confidence: float
    latency_ms: float

@app.post("/api/demo/query", response_model=QueryResponse)
async def product_query(request: QueryRequest):
    import time
    start_time = time.time()
    
    rag_service = get_rag_service()
    
    result = await rag_service.query(
        query=request.query,
        top_k=request.top_k,
        use_rerank=request.use_rerank,
        filters=request.filters
    )
    
    latency_ms = (time.time() - start_time) * 1000
    
    sources = [
        Source(
            chunk_id=chunk.chunk_id,
            content=chunk.content[:200] + "...",
            score=score,
            metadata=chunk.metadata
        )
        for chunk, score in zip(result.sources, result.metadata.get("retrieval_scores", []))
    ]
    
    return QueryResponse(
        answer=result.answer,
        sources=sources,
        confidence=result.confidence,
        latency_ms=latency_ms
    )

@app.get("/api/demo/health")
async def health_check():
    return {"status": "healthy", "service": "demo-api"}
```

### 2.2 服务依赖注入

```python
from functools import lru_cache

@lru_cache()
def get_embedding_service():
    from services.embedding import EmbeddingService
    return EmbeddingService(
        triton_url="http://triton-embedding:8000"
    )

@lru_cache()
def get_qdrant_client():
    from qdrant_client import QdrantClient
    return QdrantClient(host="qdrant", port=6333)

@lru_cache()
def get_es_client():
    from elasticsearch import AsyncElasticsearch
    return AsyncElasticsearch(["http://elasticsearch:9200"])

@lru_cache()
def get_llm_client():
    from services.llm import LLMClient
    return LLMClient(
        base_url="http://vllm:8000",
        model="Qwen/Qwen2.5-72B-Instruct"
    )

@lru_cache()
def get_rag_service():
    from services.rag import RAGService
    
    embedding_service = get_embedding_service()
    qdrant_client = get_qdrant_client()
    es_client = get_es_client()
    llm_client = get_llm_client()
    
    vector_retriever = VectorRetriever(qdrant_client, embedding_service)
    keyword_retriever = KeywordRetriever(es_client)
    hybrid_retriever = HybridRetriever(vector_retriever, keyword_retriever)
    
    rerank_pipeline = RerankPipeline("http://rerank:8000")
    prompt_manager = PromptTemplateManager()
    
    return RAGService(
        retriever=hybrid_retriever,
        rerank_pipeline=rerank_pipeline,
        llm_client=llm_client,
        prompt_manager=prompt_manager
    )
```

### 2.3 异常处理

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class RAGException(Exception):
    def __init__(self, message: str, code: str = "RAG_ERROR"):
        self.message = message
        self.code = code

@app.exception_handler(RAGException)
async def rag_exception_handler(request: Request, exc: RAGException):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        }
    )
```

---

## 3. Demo前端开发

### 3.1 Streamlit应用

```python
import streamlit as st
import httpx
import time

st.set_page_config(
    page_title="AI选品系统 - 商品趋势问答",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 AI选品系统 - 商品趋势问答")
st.markdown("---")

API_URL = "http://demo-api:8000"

def query_api(query: str, top_k: int = 5):
    try:
        response = httpx.post(
            f"{API_URL}/api/demo/query",
            json={
                "query": query,
                "top_k": top_k,
                "use_rerank": True
            },
            timeout=60.0
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}

with st.sidebar:
    st.header("⚙️ 设置")
    top_k = st.slider("返回结果数量", 1, 10, 5)
    show_sources = st.checkbox("显示来源", value=True)
    
    st.markdown("---")
    st.markdown("### 📝 示例问题")
    examples = [
        "户外储能电源在欧洲市场的趋势如何？",
        "哪些品类的太阳能产品销量增长最快？",
        "便携式充电器的主要竞争对手有哪些？"
    ]
    for example in examples:
        if st.button(example, key=example):
            st.session_state.query = example

col1, col2 = st.columns([2, 1])

with col1:
    query = st.text_area(
        "请输入您的问题：",
        height=100,
        value=st.session_state.get("query", "")
    )
    
    if st.button("🔍 查询", type="primary"):
        if not query.strip():
            st.warning("请输入问题")
        else:
            with st.spinner("正在分析..."):
                start_time = time.time()
                result = query_api(query, top_k)
                elapsed = time.time() - start_time
            
            if "error" in result:
                st.error(f"查询失败: {result['error']}")
            else:
                st.success(f"✅ 查询完成 (耗时: {elapsed:.2f}秒)")
                
                st.markdown("### 📊 回答")
                st.markdown(result["answer"])
                
                if show_sources and result.get("sources"):
                    st.markdown("---")
                    st.markdown("### 📚 参考来源")
                    
                    for i, source in enumerate(result["sources"], 1):
                        with st.expander(f"来源 {i} (相关度: {source['score']:.3f})"):
                            st.markdown(source["content"])
                            if source.get("metadata"):
                                st.json(source["metadata"])

with col2:
    st.markdown("### 📈 查询统计")
    
    if "confidence" in st.session_state:
        st.metric("置信度", f"{st.session_state.confidence:.2%}")
    
    if "latency" in st.session_state:
        st.metric("响应时间", f"{st.session_state.latency:.0f}ms")
    
    st.markdown("---")
    st.markdown("### 💡 使用提示")
    st.info("""
    1. 输入具体的商品或品类问题
    2. 系统会从知识库检索相关信息
    3. AI会基于检索结果生成回答
    4. 可以查看参考来源验证信息
    """)
```

### 3.2 Docker部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY demo_frontend.py .

EXPOSE 8501

CMD ["streamlit", "run", "demo_frontend.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

## 4. Kong网关配置

### 4.1 Kong部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kong
  namespace: pms-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kong
  template:
    metadata:
      labels:
        app: kong
    spec:
      containers:
        - name: kong
          image: kong:3.4
          ports:
            - containerPort: 8000
              name: proxy
            - containerPort: 8443
              name: proxy-ssl
            - containerPort: 8001
              name: admin
          env:
            - name: KONG_DATABASE
              value: "off"
            - name: KONG_DECLARATIVE_CONFIG
              value: /etc/kong/kong.yml
            - name: KONG_PROXY_ACCESS_LOG
              value: /dev/stdout
            - name: KONG_ADMIN_ACCESS_LOG
              value: /dev/stdout
            - name: KONG_PROXY_ERROR_LOG
              value: /dev/stderr
            - name: KONG_ADMIN_ERROR_LOG
              value: /dev/stderr
          volumeMounts:
            - name: kong-config
              mountPath: /etc/kong
      volumes:
        - name: kong-config
          configMap:
            name: kong-config
---
apiVersion: v1
kind: Service
metadata:
  name: kong
  namespace: pms-gateway
spec:
  selector:
    app: kong
  ports:
    - name: proxy
      port: 8000
      targetPort: 8000
    - name: admin
      port: 8001
      targetPort: 8001
```

### 4.2 Kong声明式配置

```yaml
_format_version: "3.0"

services:
  - name: demo-api
    url: http://demo-api:8000
    routes:
      - name: demo-route
        paths:
          - /api/demo
    plugins:
      - name: rate-limiting
        config:
          minute: 100
          policy: local
      - name: jwt
        config:
          secret_is_base64: false

  - name: rag-api
    url: http://rag-api:8000
    routes:
      - name: rag-route
        paths:
          - /api/v1/rag
    plugins:
      - name: rate-limiting
        config:
          minute: 50
          policy: local

  - name: frontend
    url: http://demo-frontend:8501
    routes:
      - name: frontend-route
        paths:
          - /

consumers:
  - username: api-user
    jwt_secrets:
      - secret: your-jwt-secret-key
        key: api-key

plugins:
  - name: cors
    config:
      origins:
        - "*"
      methods:
        - GET
        - POST
        - PUT
        - DELETE
      headers:
        - Accept
        - Authorization
        - Content-Type
      exposed_headers:
        - X-Auth-Token
      credentials: true
      max_age: 3600
```

### 4.3 JWT认证

```python
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

JWT_SECRET = "your-jwt-secret-key"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 3600

def create_jwt_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXPIRATION)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

## 5. Elasticsearch部署

### 5.1 ES集群配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: elasticsearch
  namespace: pms-data
spec:
  serviceName: elasticsearch-headless
  replicas: 3
  selector:
    matchLabels:
      app: elasticsearch
  template:
    metadata:
      labels:
        app: elasticsearch
    spec:
      containers:
        - name: elasticsearch
          image: docker.elastic.co/elasticsearch/elasticsearch:8.10.0
          ports:
            - containerPort: 9200
              name: http
            - containerPort: 9300
              name: transport
          env:
            - name: cluster.name
              value: "fms-es-cluster"
            - name: node.name
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: discovery.seed_hosts
              value: "elasticsearch-0.elasticsearch-headless,elasticsearch-1.elasticsearch-headless,elasticsearch-2.elasticsearch-headless"
            - name: cluster.initial_master_nodes
              value: "elasticsearch-0,elasticsearch-1,elasticsearch-2"
            - name: ES_JAVA_OPTS
              value: "-Xms4g -Xmx4g"
            - name: xpack.security.enabled
              value: "false"
          volumeMounts:
            - name: es-data
              mountPath: /usr/share/elasticsearch/data
      volumes:
        - name: es-data
          persistentVolumeClaim:
            claimName: es-pvc
```

### 5.2 索引模板

```python
from elasticsearch import AsyncElasticsearch

async def create_index_templates(es_client: AsyncElasticsearch):
    await es_client.indices.put_index_template(
        name="product_knowledge_template",
        body={
            "index_patterns": ["product_knowledge*"],
            "template": {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1,
                    "analysis": {
                        "analyzer": {
                            "ik_smart_analyzer": {
                                "type": "custom",
                                "tokenizer": "ik_smart"
                            },
                            "ik_max_word_analyzer": {
                                "type": "custom",
                                "tokenizer": "ik_max_word"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "content": {
                            "type": "text",
                            "analyzer": "ik_max_word_analyzer",
                            "search_analyzer": "ik_smart_analyzer"
                        },
                        "doc_id": {"type": "keyword"},
                        "chunk_index": {"type": "integer"},
                        "metadata": {
                            "properties": {
                                "title": {"type": "text", "analyzer": "ik_max_word_analyzer"},
                                "category": {"type": "keyword"},
                                "source": {"type": "keyword"},
                                "created_at": {"type": "date"}
                            }
                        }
                    }
                }
            }
        }
    )
```

### 5.3 数据同步

```python
class ESSyncService:
    def __init__(self, es_client: AsyncElasticsearch, qdrant_client):
        self.es = es_client
        self.qdrant = qdrant_client
    
    async def sync_chunk(self, chunk: Chunk):
        doc = {
            "doc_id": chunk.doc_id,
            "chunk_id": chunk.chunk_id,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "metadata": chunk.metadata
        }
        
        await self.es.index(
            index="product_knowledge",
            id=chunk.chunk_id,
            document=doc
        )
    
    async def sync_batch(self, chunks: List[Chunk]):
        bulk_body = []
        
        for chunk in chunks:
            bulk_body.append({
                "index": {
                    "_index": "product_knowledge",
                    "_id": chunk.chunk_id
                }
            })
            bulk_body.append({
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "metadata": chunk.metadata
            })
        
        await self.es.bulk(body=bulk_body)
```

---

## 附录

### A. 验收检查清单

```markdown
## D16-D18 验收检查清单

### Demo后端
- [ ] FastAPI项目搭建
- [ ] /api/demo/query接口可用
- [ ] RAG检索流程跑通
- [ ] LLM调用正常

### Demo前端
- [ ] Streamlit界面可用
- [ ] 查询功能正常
- [ ] 结果展示正确
- [ ] 来源引用显示

### Kong网关
- [ ] Kong集群运行
- [ ] 路由转发正常
- [ ] JWT认证生效
- [ ] 限流规则生效

### Elasticsearch
- [ ] ES集群健康
- [ ] 索引创建成功
- [ ] IK分词器可用
- [ ] BM25检索正常
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
