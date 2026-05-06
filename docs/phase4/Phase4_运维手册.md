# Phase 4: 运维手册

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 运维手册
> **文档版本**: v1.0
> **最后更新**: 2026-04-06

---

## 目录

- [1. 系统概述](#1-系统概述)
- [2. 部署架构](#2-部署架构)
- [3. 服务管理](#3-服务管理)
- [4. 监控告警](#4-监控告警)
- [5. 日志管理](#5-日志管理)
- [6. 备份恢复](#6-备份恢复)
- [7. 故障处理](#7-故障处理)
- [8. 日常运维](#8-日常运维)

---

## 1. 系统概述

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户层                                    │
│    Web前端  │  移动端PWA  │  API调用                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        接入层                                     │
│    Kong Gateway  │  CDN  │  负载均衡                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        应用层                                     │
│  API Gateway │ LLM Service │ RAG Service │ Agent Service        │
│  Embedding Service │ Data Pipeline │ ERP Gateway │ Report       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        数据层                                     │
│  PostgreSQL │ Redis Cluster │ Qdrant │ Kafka │ Elasticsearch   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        基础设施层                                  │
│    Kubernetes  │  Istio  │  Prometheus  │  Grafana  │  ELK     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 服务清单

| 服务名称 | 副本数 | 资源配置 | 端口 | 说明 |
|---------|--------|---------|------|------|
| api-gateway | 3 | 4C/8G | 8000 | API网关 |
| llm-service | 4 | 8C/32G | 8001 | LLM推理服务 |
| rag-service | 3 | 4C/16G | 8002 | RAG检索服务 |
| agent-service | 3 | 4C/8G | 8003 | Agent服务 |
| embedding-service | 2 | 4C/16G | 8004 | 向量嵌入服务 |
| data-pipeline | 3 | 4C/8G | 8005 | 数据管道 |
| erp-gateway | 3 | 2C/4G | 8006 | ERP集成网关 |
| report-service | 2 | 2C/4G | 8007 | 报告服务 |

### 1.3 联系人信息

| 角色 | 姓名 | 电话 | 邮箱 |
|------|------|------|------|
| 项目经理 | ________ | ________ | ________ |
| 技术负责人 | ________ | ________ | ________ |
| DevOps | ________ | ________ | ________ |
| DBA | ________ | ________ | ________ |

---

## 2. 部署架构

### 2.1 Kubernetes集群

| 集群 | 节点数 | 配置 | 用途 |
|------|--------|------|------|
| 生产集群 | 8 Worker + 3 Master | 32C/128G | 应用服务 |
| GPU集群 | 4 GPU节点 | A100 80GB | 推理服务 |

### 2.2 多可用区部署

```
┌─────────────────────────────────────────────────────────────────┐
│                         Region                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │    AZ-A     │  │    AZ-B     │  │    AZ-C     │             │
│  │  ┌───────┐  │  │  ┌───────┐  │  │  ┌───────┐  │             │
│  │  │Master1│  │  │  │Master2│  │  │  │Master3│  │             │
│  │  └───────┘  │  │  └───────┘  │  │  └───────┘  │             │
│  │  ┌───────┐  │  │  ┌───────┐  │  │  ┌───────┐  │             │
│  │  │Worker │  │  │  │Worker │  │  │  │Worker │  │             │
│  │  └───────┘  │  │  └───────┘  │  │  └───────┘  │             │
│  │  ┌───────┐  │  │  ┌───────┐  │  │  ┌───────┐  │             │
│  │  │  GPU   │  │  │  │  GPU   │  │  │  │  GPU   │  │             │
│  │  └───────┘  │  │  └───────┘  │  │  └───────┘  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 网络规划

| 网段 | 用途 | 说明 |
|------|------|------|
| 10.0.0.0/16 | VPC主网段 | 整个VPC |
| 10.0.1.0/24 | AZ-A子网 | Master+Worker |
| 10.0.2.0/24 | AZ-B子网 | Master+Worker |
| 10.0.3.0/24 | AZ-C子网 | Master+Worker |
| 10.0.100.0/24 | GPU子网 | GPU节点 |
| 10.0.200.0/24 | 数据库子网 | PostgreSQL/Redis |

---

## 3. 服务管理

### 3.1 服务启停

**启动服务**
```bash
# 启动所有服务
kubectl apply -f k8s/deployments/

# 启动单个服务
kubectl scale deployment api-gateway --replicas=3 -n fms

# 滚动重启服务
kubectl rollout restart deployment api-gateway -n fms
```

**停止服务**
```bash
# 停止单个服务
kubectl scale deployment api-gateway --replicas=0 -n fms

# 停止所有服务（紧急情况）
kubectl delete -f k8s/deployments/
```

### 3.2 服务扩缩容

**手动扩缩容**
```bash
# 扩容API网关到5个副本
kubectl scale deployment api-gateway --replicas=5 -n fms

# 缩容LLM服务到2个副本
kubectl scale deployment llm-service --replicas=2 -n fms
```

**自动扩缩容（HPA）**
```bash
# 查看HPA状态
kubectl get hpa -n fms

# 创建HPA
kubectl autoscale deployment api-gateway --min=3 --max=10 --cpu-percent=70 -n fms
```

### 3.3 服务更新

**滚动更新**
```bash
# 更新镜像
kubectl set image deployment/api-gateway api-gateway=fms/api-gateway:v2.0.0 -n fms

# 查看更新状态
kubectl rollout status deployment/api-gateway -n fms

# 查看更新历史
kubectl rollout history deployment/api-gateway -n fms
```

**回滚操作**
```bash
# 回滚到上一版本
kubectl rollout undo deployment/api-gateway -n fms

# 回滚到指定版本
kubectl rollout undo deployment/api-gateway --to-revision=2 -n fms
```

### 3.4 灰度发布

**金丝雀发布**
```bash
# 创建金丝雀部署（10%流量）
kubectl apply -f k8s/canary/api-gateway-canary.yaml

# 调整流量比例
kubectl patch virtualservice api-gateway -n fms --type=json -p='[
  {"op": "replace", "path": "/spec/http/0/route/1/weight", "value": 30}
]'

# 完成发布
kubectl scale deployment api-gateway-canary --replicas=0 -n fms
```

---

## 4. 监控告警

### 4.1 监控访问

| 监控系统 | 访问地址 | 说明 |
|---------|---------|------|
| Grafana | https://grafana.fms.example.com | 可视化监控 |
| Prometheus | https://prometheus.fms.example.com | 指标存储 |
| AlertManager | https://alertmanager.fms.example.com | 告警管理 |
| Jaeger | https://jaeger.fms.example.com | 链路追踪 |
| Kibana | https://kibana.fms.example.com | 日志分析 |

### 4.2 关键指标

**服务健康指标**
| 指标名称 | 告警阈值 | 说明 |
|---------|---------|------|
| 服务可用性 | <99.9% | 服务健康检查 |
| 请求成功率 | <99% | HTTP 2xx比例 |
| P99延迟 | >200ms | 请求响应时间 |
| 错误率 | >1% | HTTP 5xx比例 |

**资源使用指标**
| 指标名称 | 告警阈值 | 说明 |
|---------|---------|------|
| CPU使用率 | >80% | 节点CPU使用率 |
| 内存使用率 | >85% | 节点内存使用率 |
| 磁盘使用率 | >80% | 节点磁盘使用率 |
| GPU使用率 | >90% | GPU计算使用率 |

**业务指标**
| 指标名称 | 告警阈值 | 说明 |
|---------|---------|------|
| QPS | <100 | 请求吞吐量异常 |
| 选品成功率 | <80% | AI选品成功率 |
| Agent响应时间 | >5s | Agent处理时间 |

### 4.3 告警级别

| 级别 | 响应时间 | 通知方式 | 处理时限 |
|------|---------|---------|---------|
| P0-紧急 | 5分钟 | 电话+短信+钉钉 | 30分钟 |
| P1-高 | 15分钟 | 短信+钉钉 | 2小时 |
| P2-中 | 30分钟 | 钉钉 | 24小时 |
| P3-低 | 60分钟 | 邮件 | 72小时 |

### 4.4 告警处理流程

```
告警触发 → 确认接收 → 初步判断 → 处理问题 → 验证恢复 → 关闭告警
    │           │           │           │           │
    ▼           ▼           ▼           ▼           ▼
 自动通知    5min内响应   定位原因    解决问题    确认正常
```

---

## 5. 日志管理

### 5.1 日志收集架构

```
应用Pod → Fluent Bit → Kafka → Logstash → Elasticsearch → Kibana
                                    │
                                    ▼
                              冷存储(S3)
```

### 5.2 日志类型

| 日志类型 | 保留周期 | 存储位置 | 说明 |
|---------|---------|---------|------|
| 访问日志 | 30天 | ES热数据 | HTTP请求日志 |
| 应用日志 | 30天 | ES热数据 | 应用运行日志 |
| 审计日志 | 365天 | ES冷数据+S3 | 操作审计日志 |
| 安全日志 | 365天 | ES冷数据+S3 | 安全事件日志 |
| 错误日志 | 90天 | ES热数据 | 错误堆栈日志 |

### 5.3 日志查询

**Kibana查询示例**
```
# 查询API网关错误日志
app: "api-gateway" AND level: "ERROR"

# 查询特定请求ID的日志
request_id: "abc123"

# 查询最近1小时的慢请求
app: "api-gateway" AND duration: >1000 AND @timestamp: [now-1h TO now]
```

**命令行查询**
```bash
# 查看Pod日志
kubectl logs -f deployment/api-gateway -n fms

# 查看最近100行日志
kubectl logs --tail=100 deployment/api-gateway -n fms

# 查看特定时间段的日志
kubectl logs --since=1h deployment/api-gateway -n fms
```

---

## 6. 备份恢复

### 6.1 备份策略

| 备份对象 | 备份方式 | 备份频率 | 保留周期 | 存储位置 |
|---------|---------|---------|---------|---------|
| PostgreSQL | pg_dump + WAL归档 | 每日全量+实时归档 | 30天 | S3 |
| Redis | RDB快照 | 每小时 | 7天 | 本地+S3 |
| Qdrant | 快照 | 每日 | 14天 | S3 |
| Kafka | 日志保留 | 实时 | 7天 | 本地 |
| 配置文件 | Git | 每次变更 | 永久 | Git仓库 |

### 6.2 备份操作

**PostgreSQL备份**
```bash
# 全量备份
pg_dump -h localhost -U postgres -d fms -F c -f /backup/fms_$(date +%Y%m%d).dump

# WAL归档配置（postgresql.conf）
archive_mode = on
archive_command = 'aws s3 cp %p s3://fms-backup/wal/%f'
```

**Redis备份**
```bash
# 手动触发RDB快照
redis-cli BGSAVE

# 复制RDB文件到备份位置
cp /var/lib/redis/dump.rdb /backup/redis_$(date +%Y%m%d).rdb
```

**Qdrant备份**
```bash
# 创建快照
curl -X POST 'http://localhost:6333/collections/fms/snapshots'

# 下载快照
curl 'http://localhost:6333/collections/fms/snapshots/{snapshot_name}' -o snapshot.tar
```

### 6.3 恢复操作

**PostgreSQL恢复**
```bash
# 恢复全量备份
pg_restore -h localhost -U postgres -d fms_restore /backup/fms_20260406.dump

# 时间点恢复（PITR）
# 1. 恢复基础备份
# 2. 应用WAL日志到指定时间点
recovery_target_time = '2026-04-06 12:00:00'
```

**Redis恢复**
```bash
# 停止Redis服务
systemctl stop redis

# 恢复RDB文件
cp /backup/redis_20260406.rdb /var/lib/redis/dump.rdb

# 启动Redis服务
systemctl start redis
```

**Qdrant恢复**
```bash
# 上传快照
curl -X PUT 'http://localhost:6333/collections/fms/snapshots/upload' \
  -H 'Content-Type: multipart/form-data' \
  -F 'snapshot=@snapshot.tar'

# 从快照恢复
curl -X PUT 'http://localhost:6333/collections/fms/snapshots/recover' \
  -H 'Content-Type: application/json' \
  -d '{"location": "snapshot_name"}'
```

---

## 7. 故障处理

### 7.1 常见故障及处理

#### 7.1.1 服务不可用

**现象**: 服务健康检查失败，Pod状态异常

**排查步骤**:
```bash
# 1. 检查Pod状态
kubectl get pods -n fms

# 2. 查看Pod详情
kubectl describe pod <pod-name> -n fms

# 3. 查看Pod日志
kubectl logs <pod-name> -n fms

# 4. 检查事件
kubectl get events -n fms --sort-by='.lastTimestamp'
```

**处理方案**:
- 重启Pod: `kubectl delete pod <pod-name> -n fms`
- 检查资源限制: `kubectl describe resourcequota -n fms`
- 检查配置: `kubectl get configmap -n fms`

#### 7.1.2 数据库连接失败

**现象**: 应用报数据库连接错误

**排查步骤**:
```bash
# 1. 检查数据库状态
kubectl get pods -n fms -l app=postgresql

# 2. 检查连接数
psql -h localhost -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# 3. 检查连接池状态
# PgBouncer管理界面
```

**处理方案**:
- 重启数据库连接池
- 增加连接数限制
- 检查网络连通性

#### 7.1.3 Redis连接超时

**现象**: 缓存服务响应慢或超时

**排查步骤**:
```bash
# 1. 检查Redis状态
redis-cli -c cluster info

# 2. 检查内存使用
redis-cli info memory

# 3. 检查慢查询
redis-cli slowlog get 10
```

**处理方案**:
- 清理大Key
- 扩容Redis集群
- 优化查询命令

#### 7.1.4 GPU推理服务异常

**现象**: LLM推理服务响应慢或失败

**排查步骤**:
```bash
# 1. 检查GPU状态
nvidia-smi

# 2. 检查vLLM服务日志
kubectl logs -f deployment/llm-service -n fms

# 3. 检查GPU内存使用
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

**处理方案**:
- 重启vLLM服务
- 调整批处理大小
- 扩容GPU节点

### 7.2 故障升级流程

```
P3问题 → 值班人员处理 → 24小时内解决
    │
    ▼ 未解决
P2问题 → 技术负责人介入 → 4小时内解决
    │
    ▼ 未解决
P1问题 → 架构师介入 → 2小时内解决
    │
    ▼ 未解决
P0问题 → 全团队响应 → 30分钟内解决
```

### 7.3 应急预案

**系统级故障**
1. 立即通知相关干系人
2. 启动灾备环境
3. 切换流量到灾备
4. 排查主环境问题
5. 恢复主环境
6. 回切流量

**数据丢失**
1. 立即停止写入操作
2. 评估数据丢失范围
3. 从备份恢复数据
4. 验证数据完整性
5. 恢复服务

---

## 8. 日常运维

### 8.1 日常巡检清单

| 检查项 | 检查频率 | 检查内容 | 责任人 |
|--------|---------|---------|--------|
| 服务健康 | 每日 | 所有服务运行状态 | 值班人员 |
| 资源使用 | 每日 | CPU/内存/磁盘使用率 | 值班人员 |
| 日志检查 | 每日 | 错误日志、异常日志 | 值班人员 |
| 备份验证 | 每周 | 备份完整性检查 | DBA |
| 安全扫描 | 每月 | 漏洞扫描、安全审计 | 安全负责人 |
| 容量评估 | 每月 | 资源容量评估 | 架构师 |

### 8.2 运维脚本

**健康检查脚本**
```bash
#!/bin/bash
# health_check.sh

echo "=== 服务健康检查 ==="
kubectl get pods -n fms | grep -v Running

echo "=== 资源使用检查 ==="
kubectl top nodes
kubectl top pods -n fms

echo "=== 告警检查 ==="
curl -s http://alertmanager:9093/api/v2/alerts | jq '.[] | select(.status.state=="active")'

echo "=== 数据库连接检查 ==="
psql -h localhost -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

echo "=== Redis检查 ==="
redis-cli ping
```

**日志清理脚本**
```bash
#!/bin/bash
# log_cleanup.sh

# 清理7天前的日志
find /var/log/fms -name "*.log" -mtime +7 -delete

# 清理ES旧索引
curl -X DELETE "http://elasticsearch:9200/fms-logs-$(date -d '30 days ago' +%Y.%m.%d)"
```

### 8.3 变更管理

**变更流程**
```
变更申请 → 影响评估 → 审批 → 实施 → 验证 → 记录
```

**变更记录模板**
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-20260406-001 |
| 变更类型 | 配置变更/代码变更/基础设施变更 |
| 变更描述 | 更新API网关配置 |
| 影响范围 | API服务 |
| 实施时间 | 2026-04-06 14:00 |
| 实施人员 | 张三 |
| 验证结果 | 通过 |

---

## 附录

### A. 常用命令速查

```bash
# Kubernetes
kubectl get pods -n fms                    # 查看Pod
kubectl logs -f <pod> -n fms               # 查看日志
kubectl exec -it <pod> -n fms -- /bin/sh   # 进入容器
kubectl describe pod <pod> -n fms          # Pod详情

# PostgreSQL
psql -h localhost -U postgres -d fms       # 连接数据库
\dt                                         # 列出表
\l                                          # 列出数据库

# Redis
redis-cli -c                               # 连接集群
cluster info                               # 集群信息
info memory                                # 内存信息

# Qdrant
curl http://localhost:6333/collections     # 列出集合
curl http://localhost:6333/metrics         # 指标信息
```

### B. 应急联系方式

| 场景 | 联系人 | 电话 | 备用联系人 |
|------|------|------|----------|
| 服务故障 | 技术负责人 | ________ | ________ |
| 数据库故障 | DBA | ________ | ________ |
| 网络故障 | 网络工程师 | ________ | ________ |
| 安全事件 | 安全负责人 | ________ | ________ |

---

**文档状态**: ✅ 已完成
