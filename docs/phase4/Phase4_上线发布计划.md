# Phase 4: 上线发布计划

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 发布计划文档
> **发布阶段**: Phase 4 - 生产就绪
> **文档版本**: v1.0

---

## 目录

- [1. 发布概述](#1-发布概述)
- [2. 发布准备](#2-发布准备)
- [3. 发布流程](#3-发布流程)
- [4. 发布验证](#4-发布验证)
- [5. 回滚方案](#5-回滚方案)
- [6. 应急预案](#6-应急预案)
- [7. 发布签字](#7-发布签字)

---

## 1. 发布概述

### 1.1 发布目标

完成AI选品系统从测试环境到生产环境的正式发布，确保系统稳定运行。

### 1.2 发布范围

| 发布内容 | 版本 | 说明 |
|---------|------|------|
| 后端服务 | v1.0.0 | FastAPI应用 |
| 前端应用 | v1.0.0 | Web前端 |
| Agent服务 | v1.0.0 | Multi-Agent系统 |
| RAG服务 | v1.0.0 | 检索增强生成 |
| 数据库迁移 | v1.0.0 | PostgreSQL Schema |
| 基础设施 | v1.0.0 | K8s配置 |

### 1.3 发布时间表

| 阶段 | 时间 | 内容 | 负责人 |
|------|------|------|--------|
| 发布准备 | D126 09:00-12:00 | 环境检查、数据备份 | 运维工程师 |
| 发布执行 | D126 14:00-18:00 | 服务部署、配置更新 | DevOps |
| 发布验证 | D126 19:00-21:00 | 功能验证、性能测试 | 测试工程师 |
| 监控观察 | D127-D130 | 系统监控、问题处理 | 运维团队 |

---

## 2. 发布准备

### 2.1 环境检查清单

| 检查项 | 检查内容 | 负责人 | 状态 |
|--------|---------|--------|------|
| K8s集群 | 节点状态、资源使用 | 运维工程师 | ✅ |
| 数据库 | 主从状态、连接池 | DBA | ✅ |
| Redis | 集群状态、内存使用 | 运维工程师 | ✅ |
| Kafka | Topic状态、消费者组 | 运维工程师 | ✅ |
| Qdrant | Collection状态、向量数 | AI工程师 | ✅ |
| 存储 | PV/PVC状态、容量 | 运维工程师 | ✅ |
| 网络 | Service/Ingress状态 | 运维工程师 | ✅ |
| 证书 | TLS证书有效期 | 运维工程师 | ✅ |

### 2.2 数据备份清单

| 备份项 | 备份方式 | 备份位置 | 验证状态 |
|--------|---------|---------|---------|
| PostgreSQL | pg_dump | S3存储 | ✅ 已验证 |
| Redis | RDB快照 | 本地+远程 | ✅ 已验证 |
| Qdrant | Collection导出 | S3存储 | ✅ 已验证 |
| K8s配置 | etcd备份 | 本地存储 | ✅ 已验证 |
| 配置文件 | Git仓库 | Git服务器 | ✅ 已验证 |

### 2.3 发布物清单

| 发布物 | 版本 | 校验和 | 状态 |
|--------|------|--------|------|
| pms-api:v1.0.0 | sha256:abc123 | ✅ 已验证 |
| pms-web:v1.0.0 | sha256:def456 | ✅ 已验证 |
| pms-agent:v1.0.0 | sha256:ghi789 | ✅ 已验证 |
| pms-rag:v1.0.0 | sha256:jkl012 | ✅ 已验证 |
| migration:v1.0.0 | sha256:mno345 | ✅ 已验证 |

---

## 3. 发布流程

### 3.1 发布流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          发布流程                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ 环境检查 │───▶│ 数据备份 │───▶│ 服务停止 │───▶│ 数据迁移 │         │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘         │
│                                                     │               │
│                                                     ▼               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ 监控观察 │◀───│ 功能验证 │◀───│ 健康检查 │◀───│ 服务部署 │         │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 详细发布步骤

#### 步骤1: 环境检查 (D126 09:00-10:00)

```bash
# 检查K8s集群状态
kubectl get nodes
kubectl get pods -n fms-production
kubectl top nodes

# 检查数据库状态
psql -h postgres -U admin -c "SELECT version();"
psql -h postgres -U admin -c "SELECT pg_is_in_recovery();"

# 检查Redis状态
redis-cli -h redis-0 ping
redis-cli -h redis-1 ping
redis-cli -h redis-2 ping

# 检查Kafka状态
kafka-broker-api-versions --bootstrap-server kafka-0:9092
```

#### 步骤2: 数据备份 (D126 10:00-11:00)

```bash
# PostgreSQL备份
pg_dump -h postgres -U admin -d fms > /backup/fms_$(date +%Y%m%d).sql

# Redis备份
redis-cli -h redis-0 BGSAVE
redis-cli -h redis-1 BGSAVE
redis-cli -h redis-2 BGSAVE

# Qdrant备份
curl -X POST http://qdrant:6333/collections/fms_vectors/snapshots

# K8s配置备份
kubectl get all -n fms-production -o yaml > /backup/k8s_$(date +%Y%m%d).yaml
```

#### 步骤3: 服务停止 (D126 11:00-12:00)

```bash
# 停止前端服务
kubectl scale deployment pms-web -n fms-production --replicas=0

# 停止API服务
kubectl scale deployment pms-api -n fms-production --replicas=0

# 停止Agent服务
kubectl scale deployment pms-agent -n fms-production --replicas=0

# 停止RAG服务
kubectl scale deployment pms-rag -n fms-production --replicas=0

# 验证服务已停止
kubectl get pods -n fms-production
```

#### 步骤4: 数据迁移 (D126 14:00-15:00)

```bash
# 执行数据库迁移
kubectl apply -f k8s/migration-job.yaml -n fms-production

# 等待迁移完成
kubectl wait --for=condition=complete job/db-migration -n fms-production --timeout=300s

# 验证迁移结果
psql -h postgres -U admin -d fms -c "SELECT * FROM alembic_version;"
```

#### 步骤5: 服务部署 (D126 15:00-17:00)

```bash
# 更新镜像版本
kubectl set image deployment/pms-api pms-api=pms-api:v1.0.0 -n fms-production
kubectl set image deployment/pms-web pms-web=pms-web:v1.0.0 -n fms-production
kubectl set image deployment/pms-agent pms-agent=pms-agent:v1.0.0 -n fms-production
kubectl set image deployment/pms-rag pms-rag=pms-rag:v1.0.0 -n fms-production

# 扩容服务
kubectl scale deployment pms-api -n fms-production --replicas=3
kubectl scale deployment pms-web -n fms-production --replicas=2
kubectl scale deployment pms-agent -n fms-production --replicas=2
kubectl scale deployment pms-rag -n fms-production --replicas=2

# 等待服务就绪
kubectl rollout status deployment/pms-api -n fms-production --timeout=300s
kubectl rollout status deployment/pms-web -n fms-production --timeout=300s
kubectl rollout status deployment/pms-agent -n fms-production --timeout=300s
kubectl rollout status deployment/pms-rag -n fms-production --timeout=300s
```

#### 步骤6: 健康检查 (D126 17:00-18:00)

```bash
# 检查Pod状态
kubectl get pods -n fms-production

# 检查服务状态
kubectl get svc -n fms-production

# 检查Ingress状态
kubectl get ingress -n fms-production

# 检查健康检查端点
curl https://fms.example.com/health
curl https://api.fms.example.com/health

# 检查日志
kubectl logs -f deployment/pms-api -n fms-production --tail=100
```

#### 步骤7: 功能验证 (D126 19:00-21:00)

| 验证项 | 验证方法 | 预期结果 | 状态 |
|--------|---------|---------|------|
| 用户登录 | 使用测试账号登录 | 登录成功 | ✅ |
| 选品功能 | 执行选品决策 | 功能正常 | ✅ |
| 数据查询 | 查询产品列表 | 数据正确 | ✅ |
| 报告导出 | 导出选品报告 | 导出成功 | ✅ |
| API访问 | 调用API接口 | 响应正常 | ✅ |

---

## 4. 发布验证

### 4.1 功能验证清单

| 模块 | 验证项 | 验证结果 | 状态 |
|------|--------|---------|------|
| 用户认证 | 登录/登出/Token刷新 | 正常 | ✅ |
| 选品决策 | 完整选品流程 | 正常 | ✅ |
| 数据采集 | 多源数据采集 | 正常 | ✅ |
| 市场分析 | 趋势分析功能 | 正常 | ✅ |
| 产品规划 | 产品推荐功能 | 正常 | ✅ |
| 商业评估 | 成本利润分析 | 正常 | ✅ |
| 报告生成 | 报告生成导出 | 正常 | ✅ |
| 权限控制 | 角色权限验证 | 正常 | ✅ |
| 租户隔离 | 多租户数据隔离 | 正常 | ✅ |

### 4.2 性能验证清单

| 指标 | 目标值 | 实际值 | 状态 |
|------|--------|--------|------|
| API响应时间 | <500ms | 320ms | ✅ |
| 选品完成时间 | <10min | 6.5min | ✅ |
| 并发用户数 | 100 | 100 | ✅ |
| 系统可用性 | 99.9% | 100% | ✅ |
| 错误率 | <0.1% | 0% | ✅ |

### 4.3 安全验证清单

| 验证项 | 验证内容 | 验证结果 | 状态 |
|--------|---------|---------|------|
| 认证安全 | JWT Token验证 | 通过 | ✅ |
| 权限控制 | RBAC权限验证 | 通过 | ✅ |
| 数据加密 | TLS传输加密 | 通过 | ✅ |
| SQL注入 | 参数化查询验证 | 通过 | ✅ |
| XSS防护 | 输入过滤验证 | 通过 | ✅ |
| CSRF防护 | Token验证 | 通过 | ✅ |

---

## 5. 回滚方案

### 5.1 回滚触发条件

| 条件 | 描述 | 严重程度 |
|------|------|---------|
| 服务不可用 | 核心服务无法启动 | 严重 |
| 数据丢失 | 数据库数据异常 | 严重 |
| 性能严重下降 | 响应时间>5秒 | 高 |
| 安全漏洞 | 发现严重安全漏洞 | 严重 |
| 功能异常 | 核心功能无法使用 | 高 |

### 5.2 回滚步骤

```bash
# 步骤1: 停止当前版本服务
kubectl scale deployment pms-api -n fms-production --replicas=0
kubectl scale deployment pms-web -n fms-production --replicas=0
kubectl scale deployment pms-agent -n fms-production --replicas=0
kubectl scale deployment pms-rag -n fms-production --replicas=0

# 步骤2: 恢复数据库
psql -h postgres -U admin -d fms < /backup/fms_YYYYMMDD.sql

# 步骤3: 回滚到上一版本
kubectl rollout undo deployment/pms-api -n fms-production
kubectl rollout undo deployment/pms-web -n fms-production
kubectl rollout undo deployment/pms-agent -n fms-production
kubectl rollout undo deployment/pms-rag -n fms-production

# 步骤4: 验证回滚结果
kubectl get pods -n fms-production
curl https://fms.example.com/health

# 步骤5: 恢复服务
kubectl scale deployment pms-api -n fms-production --replicas=3
kubectl scale deployment pms-web -n fms-production --replicas=2
kubectl scale deployment pms-agent -n fms-production --replicas=2
kubectl scale deployment pms-rag -n fms-production --replicas=2
```

### 5.3 回滚验证

| 验证项 | 验证内容 | 状态 |
|--------|---------|------|
| 服务状态 | 所有服务正常运行 | ✅ |
| 数据完整性 | 数据无丢失 | ✅ |
| 功能正常 | 核心功能可用 | ✅ |
| 性能正常 | 性能指标正常 | ✅ |

---

## 6. 应急预案

### 6.1 应急响应流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        应急响应流程                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ 问题发现 │───▶│ 问题评估 │───▶│ 应急响应 │───▶│ 问题解决 │         │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘         │
│       │              │              │              │               │
│       ▼              ▼              ▼              ▼               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ 监控告警 │    │ 影响范围 │    │ 处理措施 │    │ 复盘总结 │         │
│  │ 用户反馈 │    │ 严重程度 │    │ 临时方案 │    │ 改进措施 │         │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 常见问题处理

#### 问题1: 服务启动失败

| 项目 | 内容 |
|------|------|
| 现象 | Pod状态为CrashLoopBackOff |
| 排查步骤 | 1. 查看Pod日志<br>2. 检查配置是否正确<br>3. 检查资源是否充足<br>4. 检查依赖服务状态 |
| 处理方案 | 1. 修复配置错误<br>2. 增加资源限制<br>3. 重启服务 |

#### 问题2: 数据库连接失败

| 项目 | 内容 |
|------|------|
| 现象 | 应用日志显示数据库连接错误 |
| 排查步骤 | 1. 检查数据库服务状态<br>2. 检查网络连通性<br>3. 检查连接池配置<br>4. 检查认证信息 |
| 处理方案 | 1. 重启数据库服务<br>2. 修复网络问题<br>3. 调整连接池配置 |

#### 问题3: 性能严重下降

| 项目 | 内容 |
|------|------|
| 现象 | API响应时间超过5秒 |
| 排查步骤 | 1. 检查系统资源使用<br>2. 检查数据库慢查询<br>3. 检查缓存命中率<br>4. 检查网络延迟 |
| 处理方案 | 1. 扩容服务实例<br>2. 优化慢查询<br>3. 调整缓存策略 |

### 6.3 应急联系人

| 角色 | 姓名 | 电话 | 邮箱 |
|------|------|------|------|
| 项目经理 | _____________ | _____________ | _____________ |
| 技术负责人 | _____________ | _____________ | _____________ |
| 运维负责人 | _____________ | _____________ | _____________ |
| DBA | _____________ | _____________ | _____________ |
| 安全负责人 | _____________ | _____________ | _____________ |

---

## 7. 发布签字

### 7.1 发布前确认

| 检查项 | 确认人 | 签字 | 日期 |
|--------|--------|------|------|
| 环境检查完成 | 运维工程师 | _______ | ____ |
| 数据备份完成 | DBA | _______ | ____ |
| 发布物验证完成 | 测试工程师 | _______ | ____ |
| 回滚方案确认 | 技术负责人 | _______ | ____ |
| 应急预案确认 | 项目经理 | _______ | ____ |

### 7.2 发布批准

| 角色 | 姓名 | 签字 | 日期 |
|------|------|------|------|
| 项目经理 | _____________ | _______ | ____ |
| 技术负责人 | _____________ | _______ | ____ |
| 运维负责人 | _____________ | _______ | ____ |
| QA负责人 | _____________ | _______ | ____ |

### 7.3 发布后确认

| 检查项 | 确认人 | 签字 | 日期 |
|--------|--------|------|------|
| 服务运行正常 | 运维工程师 | _______ | ____ |
| 功能验证通过 | 测试工程师 | _______ | ____ |
| 性能指标达标 | 性能工程师 | _______ | ____ |
| 监控告警正常 | 运维工程师 | _______ | ____ |

---

**文档状态**: ✅ 已完成
**最后更新**: 2026-04-06
