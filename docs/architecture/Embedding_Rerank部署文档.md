# Embedding与Rerank服务部署文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: AI推理服务部署文档
> **子任务**: D10-D11 - Embedding/Rerank模型部署
> **文档版本**: v1.0
>
> **更新说明（2026-04-19）**: 当前本地默认部署基线已切换为 `bge-reranker-base (纯CPU)`，多模态默认切换为 `Qwen3.5-2B / TinyGPT-V (GGUF量化)`。本文中的 Triton GPU 路线保留为历史高配 / 扩展方案。

---

## 1. 概述

Embedding和Rerank服务是RAG检索管道的核心组件。Embedding服务将文本转化为1024维向量用于相似度检索，Rerank服务对初步检索结果进行精排序提升准确率。

| 组件 | 模型 | 推理服务器 | 功能 |
|------|------|-----------|------|
| Embedding | BAAI/bge-large-zh-v1.5 | Triton | 文本→1024维向量 |
| Rerank | BAAI/bge-reranker-v2-m3 | Triton | 查询-文档相关性排序 |

---

## 2. Embedding服务架构

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

---

## 3. Triton K8s部署配置

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

---

## 4. Embedding API封装

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
                "inputs": [{
                    "name": "input_ids",
                    "shape": [len(request.texts), 512],
                    "datatype": "INT32",
                    "data": await tokenize(request.texts)
                }]
            }
        )
        result = response.json()
        embeddings = result["outputs"][0]["data"]
        if request.normalize:
            embeddings = normalize_embeddings(embeddings)
        return EmbeddingResponse(
            embeddings=embeddings, dimension=1024, model="bge-large-zh-v1.5"
        )
```

---

## 5. Rerank服务

### 5.1 Rerank API

```python
from sentence_transformers import CrossEncoder

class RerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: int = 5

@app.post("/v1/rerank")
async def rerank(request: RerankRequest):
    model = CrossEncoder('BAAI/bge-reranker-v2-m3')
    pairs = [[request.query, doc] for doc in request.documents]
    scores = model.predict(pairs)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:request.top_k]
    return {"results": [{"index": idx, "score": float(score)} for idx, score in ranked]}
```

### 5.2 RerankPipeline

```python
class RerankPipeline:
    def __init__(self, rerank_service_url: str):
        self.rerank_url = rerank_service_url

    async def rerank(self, query: str, candidates: List[dict], top_k: int = 5):
        documents = [c["content"] for c in candidates]
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.rerank_url}/v1/rerank",
                json={"query": query, "documents": documents, "top_k": top_k}
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

## 6. 性能指标

| 指标 | Embedding | Rerank |
|------|-----------|--------|
| 单请求P50 | 10ms | 30ms |
| 单请求P99 | 25ms | 100ms |
| Batch(32) P50 | 50ms | - |
| 吞吐量 | 5000 QPS | 500 QPS |

---

## 7. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| Triton Server运行 | Pod Running, 端口8000/8001/8002 | ☐ |
| BGE模型加载 | /v2/models/bge → READY | ☐ |
| Embedding API | 1024维向量返回 | ☐ |
| Embedding P99<80ms | batch=32 | ☐ |
| Rerank模型加载 | /v2/models/rerank → READY | ☐ |
| Rerank API | score范围[0,1] | ☐ |
| Rerank P99<100ms | - | ☐ |

---

**文档状态**: ✅ 已完成
