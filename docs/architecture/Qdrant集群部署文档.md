# Qdrant集群部署文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 基础设施部署文档
> **子任务**: D7 - Qdrant向量数据库部署
> **文档版本**: v1.0

---

## 1. 概述

Qdrant是系统的核心向量数据库，负责存储和检索商品知识向量、市场洞察向量等，为RAG检索提供高性能相似度搜索能力。

| 项目 | 规格 |
|------|------|
| 集群模式 | Raft共识集群 |
| 节点数量 | 3节点 (1 Leader + 2 Follower) |
| 单节点规格 | 4核8G |
| 存储引擎 | HNSW索引 + Payload存储 |
| 向量维度 | 1024维 (BGE-large-zh) |

---

## 2. 集群架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Qdrant Raft集群                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Raft共识层                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Leader   │ │ Follower │ │ Follower │               │   │
│  │  │ Node-1   │ │ Node-2   │ │ Node-3   │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    存储层                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ HNSW索引 │ │ Payload  │ │ Snapshot │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**数据流说明**:
- **Raft共识层**: 3节点通过Raft协议保证数据一致性，Leader负责写入，Follower同步复制
- **HNSW索引**: 近似最近邻搜索索引，m=16, ef_construct=100
- **Payload存储**: 非向量元数据存储（商品ASIN、标题、分类等）
- **Snapshot**: 集群快照备份，支持增量备份与恢复

---

## 3. K8s StatefulSet部署配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  namespace: pms-data
spec:
  serviceName: qdrant-headless
  replicas: 3
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
        - name: qdrant
          image: qdrant/qdrant:v1.7.0
          ports:
            - containerPort: 6333
              name: http
            - containerPort: 6334
              name: grpc
          env:
            - name: QDRANT__CLUSTER__ENABLED
              value: "true"
            - name: QDRANT__CLUSTER__P2P__PORT
              value: "6335"
          volumeMounts:
            - name: qdrant-storage
              mountPath: /qdrant/storage
          livenessProbe:
            httpGet:
              path: /health
              port: 6333
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 6333
            initialDelaySeconds: 10
            periodSeconds: 5
      volumes:
        - name: qdrant-storage
          persistentVolumeClaim:
            claimName: qdrant-pvc
```

---

## 4. Collection配置

### 4.1 product_knowledge集合（核心）

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, HnswConfig

client = QdrantClient(host="qdrant", port=6333)

client.create_collection(
    collection_name="product_knowledge",
    vectors_config=VectorParams(
        size=1024,
        distance=Distance.COSINE,
        hnsw_config=HnswConfig(
            m=16,
            ef_construct=100
        )
    )
)
```

### 4.2 market_insights集合

```python
client.create_collection(
    collection_name="market_insights",
    vectors_config=VectorParams(
        size=1024,
        distance=Distance.COSINE
    )
)
```

---

## 5. 集群初始化命令

```bash
# 步骤1: 初始化Raft集群（在Leader节点执行）
curl -X POST "http://qdrant-0.qdrant-headless:6333/cluster" \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "http://qdrant-0.qdrant-headless:6333"
  }'

# 步骤2: 添加Follower节点
curl -X POST "http://qdrant-0.qdrant-headless:6333/cluster/peer" \
  -H "Content-Type: application/json" \
  -d '{"uri": "http://qdrant-1.qdrant-headless:6333"}'

curl -X POST "http://qdrant-0.qdrant-headless:6333/cluster/peer" \
  -H "Content-Type: application/json" \
  -d '{"uri": "http://qdrant-2.qdrant-headless:6333"}'

# 步骤3: 验证集群状态
curl -s http://qdrant-0.qdrant-headless:6333/cluster | jq .
# 预期: status="enabled", peer_count=3
```

---

## 6. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| 3节点Raft集群健康 | cluster_status=green, peer_count=3 | ☐ |
| product_knowledge集合创建 | vector_size=1024, HNSW(m=16) | ☐ |
| market_insights集合创建 | vector_size=1024 | ☐ |
| 向量插入/检索正常 | 写入测试向量→查询返回正确结果 | ☐ |
| 数据一致性 | 任一节点写入，其他节点可读 | ☐ |
| API响应正常 | GET / 返回200 | ☐ |

---

**文档状态**: ✅ 已完成
