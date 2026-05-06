# API文档与运维手册

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术文档
> **子任务**: D86-D90 文档完善(API文档/运维手册)
> **文档版本**: v1.0

---

## 目录

- [1. API文档](#1-api文档)
- [2. 运维手册](#2-运维手册)
- [3. 部署指南](#3-部署指南)
- [4. 故障处理手册](#4-故障处理手册)
- [5. 安全运维手册](#5-安全运维手册)

---

## 1. API文档

### 1.1 API概述

**Base URL**: `https://api.fms.example.com/v1`

**认证方式**: Bearer Token (JWT)

**请求格式**: JSON

**响应格式**: JSON

### 1.2 认证接口

#### 用户登录

```http
POST /auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

#### 刷新Token

```http
POST /auth/refresh
Authorization: Bearer {refresh_token}
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

### 1.3 商品接口

#### 搜索商品

```http
GET /products/search?keyword={keyword}&page={page}&size={size}
Authorization: Bearer {token}
```

**参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 搜索关键词 |
| page | int | 否 | 页码，默认1 |
| size | int | 否 | 每页数量，默认20 |

**响应**:
```json
{
  "products": [
    {
      "product_id": "prod_001",
      "name": "户外便携电源",
      "category": "户外用品",
      "price": 299.99,
      "rating": 4.5,
      "review_count": 1234,
      "source": "amazon",
      "image_url": "https://..."
    }
  ],
  "total": 100,
  "page": 1,
  "size": 20
}
```

#### 获取商品详情

```http
GET /products/{product_id}
Authorization: Bearer {token}
```

**响应**:
```json
{
  "product_id": "prod_001",
  "name": "户外便携电源",
  "description": "产品描述...",
  "category": "户外用品",
  "price": 299.99,
  "original_price": 399.99,
  "rating": 4.5,
  "review_count": 1234,
  "sales_count": 5000,
  "source": "amazon",
  "images": ["https://..."],
  "specifications": {
    "capacity": "500Wh",
    "weight": "5kg"
  },
  "trend_data": {
    "price_history": [...],
    "sales_trend": [...]
  }
}
```

### 1.4 选品分析接口

#### 创建选品任务

```http
POST /selection/tasks
Authorization: Bearer {token}
Content-Type: application/json

{
  "category": "户外用品",
  "budget": 10000,
  "target_market": "US",
  "requirements": {
    "min_rating": 4.0,
    "min_reviews": 100
  }
}
```

**响应**:
```json
{
  "task_id": "task_001",
  "status": "pending",
  "created_at": "2026-04-06T10:00:00Z"
}
```

#### 获取任务状态

```http
GET /selection/tasks/{task_id}
Authorization: Bearer {token}
```

**响应**:
```json
{
  "task_id": "task_001",
  "status": "completed",
  "progress": 100,
  "result": {
    "recommendations": [...],
    "analysis_report": "..."
  },
  "created_at": "2026-04-06T10:00:00Z",
  "completed_at": "2026-04-06T10:05:00Z"
}
```

### 1.5 Agent接口

#### 获取Agent状态

```http
GET /agents/status
Authorization: Bearer {token}
```

**响应**:
```json
{
  "agents": [
    {
      "agent_id": "agent_001",
      "type": "data_collection",
      "status": "running",
      "current_task": "Amazon数据采集",
      "metrics": {
        "tasks_completed": 100,
        "success_rate": 0.98
      }
    }
  ]
}
```

### 1.6 错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |

---

## 2. 运维手册

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        系统架构                                  │
├─────────────────────────────────────────────────────────────────┤
│  接入层: Nginx Ingress + Kong Gateway                          │
│  应用层: API服务 + Agent服务 + LLM服务                          │
│  数据层: PostgreSQL + Redis + Qdrant + Kafka                   │
│  监控层: Prometheus + Grafana + Jaeger + ELK                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 服务清单

| 服务名称 | 端口 | 说明 |
|---------|------|------|
| pms-api | 8000 | API服务 |
| pms-agent | 8001 | Agent服务 |
| pms-llm | 8002 | LLM推理服务 |
| postgres | 5432 | PostgreSQL数据库 |
| redis | 6379 | Redis缓存 |
| qdrant | 6333 | 向量数据库 |
| kafka | 9092 | 消息队列 |

### 2.3 日常运维操作

#### 查看服务状态

```bash
# 查看所有Pod状态
kubectl get pods -n fms-production

# 查看服务日志
kubectl logs -f deployment/pms-api -n fms-production

# 查看资源使用
kubectl top pods -n fms-production
```

#### 服务扩缩容

```bash
# 扩容API服务
kubectl scale deployment pms-api --replicas=5 -n fms-production

# 自动扩缩容
kubectl autoscale deployment pms-api --min=3 --max=10 --cpu-percent=70 -n fms-production
```

#### 配置更新

```bash
# 更新ConfigMap
kubectl create configmap pms-api-config --from-file=config.yaml --dry-run -o yaml | kubectl apply -f - -n fms-production

# 重启服务使配置生效
kubectl rollout restart deployment/pms-api -n fms-production
```

---

## 3. 部署指南

### 3.1 环境准备

```bash
# 检查K8s集群状态
kubectl cluster-info
kubectl get nodes

# 创建命名空间
kubectl create namespace fms-production

# 创建Secret
kubectl create secret generic fms-db-secret \
  --from-literal=url='postgresql://...' \
  -n fms-production
```

### 3.2 部署步骤

```bash
# 1. 部署基础设施
helm install fms-infra ./helm/fms-infra -n fms-production

# 2. 部署数据库
helm install postgres ./charts/postgresql -n fms-data

# 3. 部署缓存
helm install redis ./charts/redis -n fms-data

# 4. 部署应用
helm install fms ./helm/fms -n fms-production \
  --values values-production.yaml

# 5. 验证部署
kubectl get all -n fms-production
```

### 3.3 数据库迁移

```bash
# 执行迁移
kubectl exec -it deployment/pms-api -n fms-production -- \
  alembic upgrade head

# 回滚迁移
kubectl exec -it deployment/pms-api -n fms-production -- \
  alembic downgrade -1
```

---

## 4. 故障处理手册

### 4.1 常见故障

#### 服务无法启动

**现象**: Pod状态为CrashLoopBackOff

**排查步骤**:
```bash
# 查看Pod日志
kubectl logs <pod-name> -n fms-production

# 查看Pod事件
kubectl describe pod <pod-name> -n fms-production

# 检查资源限制
kubectl get pod <pod-name> -n fms-production -o yaml
```

**解决方案**:
- 检查配置是否正确
- 检查资源是否充足
- 检查依赖服务是否正常

#### 数据库连接失败

**现象**: 应用日志显示数据库连接错误

**排查步骤**:
```bash
# 检查数据库服务
kubectl get svc -n fms-data

# 检查数据库连接
kubectl exec -it <pod-name> -n fms-production -- \
  psql $DATABASE_URL -c "SELECT 1"

# 检查连接池
kubectl exec -it <pod-name> -n fms-production -- \
  curl localhost:8000/metrics | grep db_connections
```

**解决方案**:
- 检查数据库凭证
- 检查网络策略
- 调整连接池配置

#### 缓存命中率低

**现象**: 系统响应慢，缓存命中率<70%

**排查步骤**:
```bash
# 检查Redis状态
kubectl exec -it <redis-pod> -n fms-data -- redis-cli info

# 检查缓存键
kubectl exec -it <redis-pod> -n fms-data -- redis-cli keys "*"

# 检查内存使用
kubectl exec -it <redis-pod> -n fms-data -- redis-cli info memory
```

**解决方案**:
- 调整缓存策略
- 增加缓存容量
- 优化缓存键设计

### 4.2 故障处理流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 故障发现  │───→│ 故障确认  │───→│ 故障处理  │───→│ 故障恢复  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │
      ▼               ▼               ▼               ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 监控告警  │    │ 影响评估  │    │ 方案执行  │    │ 验证确认  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

---

## 5. 安全运维手册

### 5.1 安全检查清单

| 检查项 | 频率 | 说明 |
|--------|------|------|
| 安全补丁 | 每周 | 检查系统安全补丁 |
| 密钥轮换 | 每月 | 轮换敏感密钥 |
| 权限审计 | 每月 | 审计用户权限 |
| 日志审计 | 每周 | 检查异常日志 |
| 漏洞扫描 | 每月 | 执行安全扫描 |

### 5.2 安全加固操作

```bash
# 更新镜像
kubectl set image deployment/pms-api \
  pms-api=harbor.fms.example.com/fms/api:v1.0.1 \
  -n fms-production

# 轮换密钥
kubectl create secret generic fms-db-secret \
  --from-literal=url='new_connection_string' \
  --dry-run -o yaml | kubectl apply -f - -n fms-production

# 重启服务
kubectl rollout restart deployment/pms-api -n fms-production
```

### 5.3 安全事件响应

| 事件级别 | 响应时间 | 处理流程 |
|---------|---------|---------|
| P0-紧急 | 15分钟 | 立即隔离、调查、修复 |
| P1-高 | 1小时 | 快速响应、分析、处理 |
| P2-中 | 4小时 | 常规处理、跟踪 |
| P3-低 | 24小时 | 记录、计划处理 |

---

## 附录

### A. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
