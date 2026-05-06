# Phase 4: 上线前数据准备

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 数据准备文档
> **准备阶段**: Phase 4 - 生产就绪
> **文档版本**: v1.0

---

## 目录

- [1. 数据准备概述](#1-数据准备概述)
- [2. 初始化数据准备](#2-初始化数据准备)
- [3. 初始化配置准备](#3-初始化配置准备)
- [4. 模拟数据准备](#4-模拟数据准备)
- [5. 多租户权限系统数据初始化](#5-多租户权限系统数据初始化)
- [6. 数据导入脚本](#6-数据导入脚本)
- [7. 数据验证清单](#7-数据验证清单)

---

## 1. 数据准备概述

### 1.1 数据准备目标

确保生产环境上线前所有必要数据已准备就绪，包括：
- 基础配置数据
- 初始业务数据
- 多租户权限数据
- 测试验证数据

### 1.2 数据准备范围

| 数据类型 | 数据量 | 准备方式 | 负责人 |
|---------|--------|---------|--------|
| 系统配置数据 | 50+项 | 手工配置 | 运维工程师 |
| 多租户数据 | 5个租户 | 脚本导入 | 后端开发 |
| 用户权限数据 | 50+用户 | 脚本导入 | 后端开发 |
| 基础业务数据 | 1000+条 | 脚本导入 | 数据工程师 |
| 模拟测试数据 | 10000+条 | 脚本生成 | 测试工程师 |

### 1.3 数据准备时间表

| 阶段 | 时间 | 内容 | 状态 |
|------|------|------|------|
| 准备阶段 | D115-D118 | 编写数据准备脚本 | ✅ 已完成 |
| 验证阶段 | D119-D120 | 测试环境验证 | ✅ 已完成 |
| 执行阶段 | D121-D122 | 生产环境导入 | ✅ 已完成 |
| 校验阶段 | D123 | 数据完整性校验 | ✅ 已完成 |

---

## 2. 初始化数据准备

### 2.1 系统配置数据

#### 2.1.1 全局配置项

| 配置分类 | 配置项 | 配置值 | 说明 |
|---------|--------|--------|------|
| 系统设置 | system.name | AI选品系统 | 系统名称 |
| 系统设置 | system.version | 1.0.0 | 系统版本 |
| 系统设置 | system.timezone | Asia/Shanghai | 系统时区 |
| 系统设置 | system.language | zh-CN | 默认语言 |
| 选品设置 | selection.max_retries | 3 | 最大重试次数 |
| 选品设置 | selection.timeout | 300 | 超时时间(秒) |
| 选品设置 | selection.default_market | US | 默认市场 |
| Agent设置 | agent.max_parallel | 4 | 最大并行Agent数 |
| Agent设置 | agent.llm_model | Qwen2.5-1.5B | 默认LLM模型 |
| Agent设置 | agent.temperature | 0.7 | 生成温度 |
| RAG设置 | rag.chunk_size | 512 | 文档切片大小 |
| RAG设置 | rag.chunk_overlap | 50 | 切片重叠 |
| RAG设置 | rag.top_k | 10 | 检索Top-K |
| RAG设置 | rag.rerank_enabled | true | 启用Rerank |
| 监控设置 | monitor.alert_email | alert@example.com | 告警邮箱 |
| 监控设置 | monitor.alert_webhook | https://hooks.example.com | 告警Webhook |

#### 2.1.2 LLM模型配置

| 模型名称 | 模型类型 | 用途 | 节点数 | 状态 |
|---------|---------|------|--------|------|
| Qwen2.5-1.5B | 主LLM | Agent推理、报告生成 | 1 | ✅ 已部署（Ollama） |
| Qwen2.5-7B | 轻量LLM | 简单查询、分类 | 2 | ✅ 已部署 |
| Phi-3-mini | 边缘LLM | 敏感词过滤、降级 | 2 | ✅ 已部署 |
| BGE-large-zh | Embedding | 文本向量化 | 1 | ✅ 已部署 |
| bge-reranker-base | Rerank | 检索精排 | 1 | 🔧 已切换为 CPU 路线，待实机验收 |
| Qwen3.5-2B | 多模态 | 图像分析 / 视频帧分析 | 1 | 🔧 WSL 路线已具备，待实机验收 |
| Whisper tiny | 语音转录 | 音频转录 | 1 | 🔧 CPU 路线已具备，待实机验收 |

#### 2.1.3 数据库配置

```sql
-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- 创建Schema
CREATE SCHEMA IF NOT EXISTS selection;
CREATE SCHEMA IF NOT EXISTS agent;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS erp;

-- 创建枚举类型
CREATE TYPE tenant_status AS ENUM ('active', 'suspended', 'trial', 'expired');
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'locked');
CREATE TYPE selection_phase AS ENUM ('start', 'data_collection', 'market_analysis', 'product_planning', 'commercial_evaluation', 'completed', 'failed');
```

### 2.2 基础业务数据

#### 2.2.1 产品类目数据

| 类目ID | 类目名称 | 父类目 | 层级 | 状态 |
|--------|---------|--------|------|------|
| CAT001 | 电子产品 | - | 1 | ✅ |
| CAT002 | 手机配件 | CAT001 | 2 | ✅ |
| CAT003 | 蓝牙耳机 | CAT002 | 3 | ✅ |
| CAT004 | 手机壳 | CAT002 | 3 | ✅ |
| CAT005 | 充电器 | CAT002 | 3 | ✅ |
| CAT006 | 家居用品 | - | 1 | ✅ |
| CAT007 | 厨房用品 | CAT006 | 2 | ✅ |
| CAT008 | 收纳整理 | CAT006 | 2 | ✅ |
| CAT009 | 运动户外 | - | 1 | ✅ |
| CAT010 | 健身器材 | CAT009 | 2 | ✅ |

#### 2.2.2 市场区域数据

| 区域ID | 区域名称 | 区域代码 | 货币 | 语言 | 状态 |
|--------|---------|---------|------|------|------|
| REG001 | 美国 | US | USD | en-US | ✅ |
| REG002 | 英国 | UK | GBP | en-GB | ✅ |
| REG003 | 德国 | DE | EUR | de-DE | ✅ |
| REG004 | 日本 | JP | JPY | ja-JP | ✅ |
| REG005 | 加拿大 | CA | CAD | en-CA | ✅ |
| REG006 | 澳大利亚 | AU | AUD | en-AU | ✅ |
| REG007 | 法国 | FR | EUR | fr-FR | ✅ |
| REG008 | 意大利 | IT | EUR | it-IT | ✅ |

#### 2.2.3 数据源配置

| 数据源ID | 数据源名称 | 数据源类型 | API端点 | 状态 |
|---------|-----------|-----------|---------|------|
| SRC001 | Amazon BSR | 电商平台 | api.amazon.com | ✅ |
| SRC002 | TikTok Shop | 电商平台 | api.tiktok.com | ✅ |
| SRC003 | Google Trends | 趋势数据 | trends.google.com | ✅ |
| SRC004 | 1688 | 供应链平台 | api.1688.com | ✅ |
| SRC005 | 媒体资讯 | 新闻数据 | api.news.com | ✅ |

---

## 3. 初始化配置准备

### 3.1 K8s配置

#### 3.1.1 Namespace配置

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: fms-production
  labels:
    environment: production
    project: pms-ai-selection
---
apiVersion: v1
kind: Namespace
metadata:
  name: pms-monitoring
  labels:
    environment: production
    project: pms-ai-selection
```

#### 3.1.2 ConfigMap配置

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pms-config
  namespace: pms-production
data:
  APP_NAME: "pms-ai-selection"
  APP_ENVIRONMENT: "production"
  APP_LOG_LEVEL: "INFO"
  DB_POOL_SIZE: "20"
  REDIS_CLUSTER_NODES: "redis-0:6379,redis-1:6379,redis-2:6379"
  KAFKA_BOOTSTRAP_SERVERS: "kafka-0:9092,kafka-1:9092,kafka-2:9092"
  QDRANT_HOST: "qdrant"
  QDRANT_PORT: "6333"
```

#### 3.1.3 Secret配置

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: pms-secrets
  namespace: pms-production
type: Opaque
stringData:
  DB_URL: "postgresql+asyncpg://user:password@postgres:5432/fms"
  REDIS_PASSWORD: "redis_password"
  SEC_SECRET_KEY: "jwt_secret_key"
  API_KEY: "api_key_for_external_services"
```

### 3.2 监控配置

#### 3.2.1 Prometheus告警规则

```yaml
groups:
  - name: fms-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: ServiceDown
        expr: up{job="pms-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service is down"
          
      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes > 10737418240
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
```

#### 3.2.2 Grafana Dashboard配置

| Dashboard名称 | 面板数 | 数据源 | 状态 |
|--------------|--------|--------|------|
| 系统概览 | 12 | Prometheus | ✅ |
| API性能 | 8 | Prometheus | ✅ |
| Agent监控 | 10 | Prometheus | ✅ |
| 数据库监控 | 6 | PostgreSQL | ✅ |
| Redis监控 | 5 | Redis | ✅ |
| Kafka监控 | 6 | Kafka | ✅ |

---

## 4. 模拟数据准备

### 4.1 产品模拟数据

```python
import random
from datetime import datetime, timedelta

def generate_mock_products(count: int = 1000):
    """生成模拟产品数据"""
    products = []
    categories = ["蓝牙耳机", "手机壳", "充电器", "厨房用品", "健身器材"]
    markets = ["US", "UK", "DE", "JP", "CA"]
    
    for i in range(count):
        product = {
            "product_id": f"PROD_{i+1:05d}",
            "name": f"测试产品 {i+1}",
            "category": random.choice(categories),
            "market": random.choice(markets),
            "price": round(random.uniform(10, 500), 2),
            "rating": round(random.uniform(3.0, 5.0), 1),
            "reviews": random.randint(0, 10000),
            "sales_30d": random.randint(0, 5000),
            "created_at": datetime.now() - timedelta(days=random.randint(1, 365)),
            "updated_at": datetime.now(),
        }
        products.append(product)
    return products
```

### 4.2 市场趋势模拟数据

```python
def generate_mock_trends(count: int = 500):
    """生成模拟市场趋势数据"""
    trends = []
    keywords = ["wireless earbuds", "phone case", "fast charger", "kitchen organizer", "yoga mat"]
    
    for i in range(count):
        trend = {
            "trend_id": f"TREND_{i+1:05d}",
            "keyword": random.choice(keywords),
            "market": random.choice(["US", "UK", "DE"]),
            "search_volume": random.randint(1000, 100000),
            "growth_rate": round(random.uniform(-50, 100), 2),
            "competition_level": random.choice(["low", "medium", "high"]),
            "date": datetime.now() - timedelta(days=random.randint(1, 30)),
        }
        trends.append(trend)
    return trends
```

### 4.3 竞品模拟数据

```python
def generate_mock_competitors(count: int = 200):
    """生成模拟竞品数据"""
    competitors = []
    
    for i in range(count):
        competitor = {
            "competitor_id": f"COMP_{i+1:05d}",
            "name": f"竞品商家 {i+1}",
            "platform": random.choice(["Amazon", "TikTok", "eBay"]),
            "product_count": random.randint(10, 500),
            "avg_rating": round(random.uniform(3.5, 5.0), 1),
            "avg_price": round(random.uniform(20, 300), 2),
            "monthly_sales": random.randint(100, 50000),
            "main_category": random.choice(["电子产品", "家居用品", "运动户外"]),
        }
        competitors.append(competitor)
    return competitors
```

### 4.4 模拟数据统计

| 数据类型 | 数量 | 用途 | 状态 |
|---------|------|------|------|
| 产品数据 | 10,000条 | 选品分析测试 | ✅ 已生成 |
| 趋势数据 | 5,000条 | 趋势分析测试 | ✅ 已生成 |
| 竞品数据 | 2,000条 | 竞品分析测试 | ✅ 已生成 |
| 向量数据 | 100,000条 | RAG检索测试 | ✅ 已生成 |
| 用户行为数据 | 50,000条 | 推荐算法测试 | ✅ 已生成 |

---

## 5. 多租户权限系统数据初始化

### 5.1 租户数据初始化

#### 5.1.1 初始租户列表

| 租户ID | 租户名称 | 租户代码 | 套餐 | 状态 | 最大用户数 |
|--------|---------|---------|------|------|-----------|
| TENANT_001 | 演示租户 | demo | enterprise | active | 100 |
| TENANT_002 | 测试租户A | test_a | professional | active | 50 |
| TENANT_003 | 测试租户B | test_b | professional | active | 50 |
| TENANT_004 | 试用租户 | trial | trial | trial | 5 |
| TENANT_005 | 企业客户A | enterprise_a | enterprise | active | 200 |

#### 5.1.2 租户配置数据

```sql
INSERT INTO tenants (tenant_id, name, slug, status, plan, contact_email, max_users, max_products, features) VALUES
('TENANT_001', '演示租户', 'demo', 'active', 'enterprise', 'demo@example.com', 100, 10000, '["ai_selection", "market_analysis", "report_export", "api_access"]'),
('TENANT_002', '测试租户A', 'test_a', 'active', 'professional', 'test_a@example.com', 50, 5000, '["ai_selection", "market_analysis", "report_export"]'),
('TENANT_003', '测试租户B', 'test_b', 'active', 'professional', 'test_b@example.com', 50, 5000, '["ai_selection", "market_analysis", "report_export"]'),
('TENANT_004', '试用租户', 'trial', 'trial', 'trial', 'trial@example.com', 5, 100, '["ai_selection"]'),
('TENANT_005', '企业客户A', 'enterprise_a', 'active', 'enterprise', 'enterprise_a@example.com', 200, 20000, '["ai_selection", "market_analysis", "report_export", "api_access", "white_label"]');
```

### 5.2 角色权限数据初始化

#### 5.2.1 系统角色定义

| 角色ID | 角色名称 | 角色代码 | 角色类型 | 说明 |
|--------|---------|---------|---------|------|
| ROLE_001 | 超级管理员 | super_admin | 系统角色 | 系统最高权限 |
| ROLE_002 | 租户管理员 | tenant_admin | 租户角色 | 租户管理权限 |
| ROLE_003 | 选品经理 | selection_manager | 业务角色 | 选品决策权限 |
| ROLE_004 | 数据分析师 | data_analyst | 业务角色 | 数据分析权限 |
| ROLE_005 | 运营人员 | operator | 业务角色 | 日常操作权限 |
| ROLE_006 | 普通用户 | user | 业务角色 | 基础查看权限 |

#### 5.2.2 权限定义

| 权限ID | 权限名称 | 权限代码 | 资源类型 | 操作 |
|--------|---------|---------|---------|------|
| PERM_001 | 选品决策 | selection:decide | selection | create,read,update |
| PERM_002 | 市场分析 | market:analyze | market | read,analyze |
| PERM_003 | 报告查看 | report:view | report | read |
| PERM_004 | 报告导出 | report:export | report | export |
| PERM_005 | 用户管理 | user:manage | user | create,read,update,delete |
| PERM_006 | 租户管理 | tenant:manage | tenant | create,read,update,delete |
| PERM_007 | 系统配置 | system:config | system | read,update |
| PERM_008 | 数据查看 | data:view | data | read |
| PERM_009 | API访问 | api:access | api | access |
| PERM_010 | 审计日志 | audit:view | audit | read |

#### 5.2.3 角色权限映射

```sql
-- 超级管理员权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_001', 'PERM_001'), ('ROLE_001', 'PERM_002'), ('ROLE_001', 'PERM_003'),
('ROLE_001', 'PERM_004'), ('ROLE_001', 'PERM_005'), ('ROLE_001', 'PERM_006'),
('ROLE_001', 'PERM_007'), ('ROLE_001', 'PERM_008'), ('ROLE_001', 'PERM_009'),
('ROLE_001', 'PERM_010');

-- 租户管理员权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_002', 'PERM_001'), ('ROLE_002', 'PERM_002'), ('ROLE_002', 'PERM_003'),
('ROLE_002', 'PERM_004'), ('ROLE_002', 'PERM_005'), ('ROLE_002', 'PERM_008');

-- 选品经理权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_003', 'PERM_001'), ('ROLE_003', 'PERM_002'), ('ROLE_003', 'PERM_003'),
('ROLE_003', 'PERM_004'), ('ROLE_003', 'PERM_008');

-- 数据分析师权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_004', 'PERM_002'), ('ROLE_004', 'PERM_003'), ('ROLE_004', 'PERM_004'),
('ROLE_004', 'PERM_008');

-- 运营人员权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_005', 'PERM_003'), ('ROLE_005', 'PERM_008');

-- 普通用户权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
('ROLE_006', 'PERM_003'), ('ROLE_006', 'PERM_008');
```

### 5.3 用户数据初始化

#### 5.3.1 初始用户列表

| 用户ID | 用户名 | 邮箱 | 角色 | 租户 | 状态 |
|--------|--------|------|------|------|------|
| USER_001 | admin | admin@system.com | super_admin | - | active |
| USER_002 | demo_admin | admin@demo.com | tenant_admin | TENANT_001 | active |
| USER_003 | demo_manager | manager@demo.com | selection_manager | TENANT_001 | active |
| USER_004 | demo_analyst | analyst@demo.com | data_analyst | TENANT_001 | active |
| USER_005 | demo_operator | operator@demo.com | operator | TENANT_001 | active |
| USER_006 | test_a_admin | admin@test_a.com | tenant_admin | TENANT_002 | active |
| USER_007 | test_a_manager | manager@test_a.com | selection_manager | TENANT_002 | active |
| USER_008 | test_b_admin | admin@test_b.com | tenant_admin | TENANT_003 | active |
| USER_009 | trial_user | user@trial.com | selection_manager | TENANT_004 | active |
| USER_010 | enterprise_admin | admin@enterprise_a.com | tenant_admin | TENANT_005 | active |

#### 5.3.2 用户数据SQL

```sql
INSERT INTO users (user_id, username, email, password_hash, role_id, tenant_id, status) VALUES
('USER_001', 'admin', 'admin@system.com', '$2b$12$...', 'ROLE_001', NULL, 'active'),
('USER_002', 'demo_admin', 'admin@demo.com', '$2b$12$...', 'ROLE_002', 'TENANT_001', 'active'),
('USER_003', 'demo_manager', 'manager@demo.com', '$2b$12$...', 'ROLE_003', 'TENANT_001', 'active'),
('USER_004', 'demo_analyst', 'analyst@demo.com', '$2b$12$...', 'ROLE_004', 'TENANT_001', 'active'),
('USER_005', 'demo_operator', 'operator@demo.com', '$2b$12$...', 'ROLE_005', 'TENANT_001', 'active'),
('USER_006', 'test_a_admin', 'admin@test_a.com', '$2b$12$...', 'ROLE_002', 'TENANT_002', 'active'),
('USER_007', 'test_a_manager', 'manager@test_a.com', '$2b$12$...', 'ROLE_003', 'TENANT_002', 'active'),
('USER_008', 'test_b_admin', 'admin@test_b.com', '$2b$12$...', 'ROLE_002', 'TENANT_003', 'active'),
('USER_009', 'trial_user', 'user@trial.com', '$2b$12$...', 'ROLE_003', 'TENANT_004', 'active'),
('USER_010', 'enterprise_admin', 'admin@enterprise_a.com', '$2b$12$...', 'ROLE_002', 'TENANT_005', 'active');
```

### 5.4 多端接入配置

#### 5.4.1 Web端配置

| 配置项 | 配置值 | 说明 |
|--------|--------|------|
| 域名 | https://fms.example.com | 主域名 |
| API端点 | https://api.fms.example.com | API地址 |
| WebSocket | wss://ws.fms.example.com | WebSocket地址 |
| CDN | https://cdn.fms.example.com | 静态资源CDN |

#### 5.4.2 移动端配置

| 配置项 | iOS | Android | 说明 |
|--------|-----|---------|------|
| App ID | com.fms.selection | com.fms.selection | 应用标识 |
| 最低版本 | iOS 14.0 | Android 8.0 | 系统要求 |
| API端点 | https://api.fms.example.com | https://api.fms.example.com | API地址 |
| 推送服务 | APNs | FCM | 推送服务 |

#### 5.4.3 API接入配置

| 接入方式 | 认证方式 | 限流 | 说明 |
|---------|---------|------|------|
| REST API | OAuth2 + JWT | 1000 req/min | 标准API |
| GraphQL | API Key | 500 req/min | GraphQL接口 |
| Webhook | HMAC签名 | - | 事件回调 |
| SDK | API Key | 2000 req/min | SDK接入 |

---

## 6. 数据导入脚本

### 6.1 数据导入脚本清单

| 脚本名称 | 功能 | 执行顺序 | 状态 |
|---------|------|---------|------|
| init_database.py | 初始化数据库结构 | 1 | ✅ |
| init_tenant.py | 初始化租户数据 | 2 | ✅ |
| init_role_permission.py | 初始化角色权限 | 3 | ✅ |
| init_user.py | 初始化用户数据 | 4 | ✅ |
| init_config.py | 初始化系统配置 | 5 | ✅ |
| import_category.py | 导入类目数据 | 6 | ✅ |
| import_market.py | 导入市场数据 | 7 | ✅ |
| import_mock_data.py | 导入模拟数据 | 8 | ✅ |
| init_vector.py | 初始化向量数据 | 9 | ✅ |
| verify_data.py | 数据完整性验证 | 10 | ✅ |

### 6.2 主执行脚本

```python
#!/usr/bin/env python3
"""
数据初始化主脚本
执行顺序: 1-10
"""

import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    scripts = [
        ("init_database.py", "初始化数据库结构"),
        ("init_tenant.py", "初始化租户数据"),
        ("init_role_permission.py", "初始化角色权限"),
        ("init_user.py", "初始化用户数据"),
        ("init_config.py", "初始化系统配置"),
        ("import_category.py", "导入类目数据"),
        ("import_market.py", "导入市场数据"),
        ("import_mock_data.py", "导入模拟数据"),
        ("init_vector.py", "初始化向量数据"),
        ("verify_data.py", "数据完整性验证"),
    ]
    
    for script, desc in scripts:
        logger.info(f"执行: {desc} ({script})")
        try:
            exec(open(script).read())
            logger.info(f"完成: {desc}")
        except Exception as e:
            logger.error(f"失败: {desc} - {e}")
            raise
    
    logger.info("所有数据初始化完成!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. 数据验证清单

### 7.1 数据完整性验证

| 验证项 | 验证方法 | 预期结果 | 状态 |
|--------|---------|---------|------|
| 数据库连接 | SELECT 1 | 连接成功 | ✅ |
| 租户数据 | SELECT COUNT(*) FROM tenants | ≥5条 | ✅ |
| 用户数据 | SELECT COUNT(*) FROM users | ≥10条 | ✅ |
| 角色数据 | SELECT COUNT(*) FROM roles | ≥6条 | ✅ |
| 权限数据 | SELECT COUNT(*) FROM permissions | ≥10条 | ✅ |
| 类目数据 | SELECT COUNT(*) FROM categories | ≥10条 | ✅ |
| 市场数据 | SELECT COUNT(*) FROM markets | ≥8条 | ✅ |
| 向量数据 | Qdrant Collection检查 | ≥100000条 | ✅ |

### 7.2 功能验证

| 验证项 | 验证内容 | 验证结果 | 状态 |
|--------|---------|---------|------|
| 用户登录 | 使用初始用户登录系统 | 登录成功 | ✅ |
| 权限验证 | 验证角色权限是否正确 | 权限正确 | ✅ |
| 租户隔离 | 验证租户数据隔离 | 隔离正确 | ✅ |
| API访问 | 验证API接口可访问 | 访问正常 | ✅ |
| 选品功能 | 执行选品决策流程 | 功能正常 | ✅ |

### 7.3 签字确认

| 角色 | 姓名 | 签字 | 日期 |
|------|------|------|------|
| 数据工程师 | _____________ | _______ | ____ |
| 后端开发 | _____________ | _______ | ____ |
| 运维工程师 | _____________ | _______ | ____ |
| 测试工程师 | _____________ | _______ | ____ |
| 项目经理 | _____________ | _______ | ____ |

---

**文档状态**: ✅ 已完成
**最后更新**: 2026-04-06
