# PostgreSQL集群配置文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 数据库部署配置
> **关联子任务**: D4-D6 Worker节点与数据存储
> **文档版本**: v1.0

---

## 1. 集群架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL 16 集群架构                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    PgBouncer 连接池                       │   │
│  │  读写入口 :5432   │   只读入口 :5433   │  管理入口 :5434  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐            │   │
│  │  │ Primary  │──→│ Replica1 │   │ Replica2 │            │   │
│  │  │ (读写)   │──→│ (只读)   │   │ (只读)   │            │   │
│  │  │ 500G SSD │   │ 500G SSD │   │ 500G SSD │            │   │
│  │  └──────────┘   └──────────┘   └──────────┘            │   │
│  │       流复制(异步) ──────────────────────┘                │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 节点规格

| 节点 | 规格 | 存储 | 可用区 | 角色 |
|------|------|------|--------|------|
| pg-primary-0 | 4C/16G | 500G gp3 SSD | AZ-A | Primary(读写) |
| pg-replica-0 | 4C/16G | 500G gp3 SSD | AZ-B | Replica(只读) |
| pg-replica-1 | 4C/16G | 500G gp3 SSD | AZ-C | Replica(只读) |

## 3. 关键配置参数

```ini
# postgresql.conf - Primary节点
max_connections = 500
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 64MB
maintenance_work_mem = 1GB
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
synchronous_commit = on
checkpoint_completion_target = 0.9
random_page_cost = 1.1
effective_io_concurrency = 200
```

## 4. PgBouncer连接池配置

```ini
[databases]
fms = host=postgres-primary port=5432 dbname=fms
fms_readonly = host=postgres-replica port=5432 dbname=fms

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = md5
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
```

## 5. 备份策略

| 备份类型 | 频率 | 保留期 | 存储位置 |
|---------|------|--------|---------|
| 全量备份 | 每日凌晨2:00 | 30天 | OSS/S3 |
| WAL归档 | 实时 | 7天 | 本地+OSS |
| 逻辑备份(pg_dump) | 每周日 | 90天 | OSS/S3 |

## 6. K8s部署配置

参考: [k8s/postgresql.yml](../../k8s/postgresql.yml)

---

**文档状态**: ✅ 已完成
**关联文档**: [D04-D06_Worker节点与数据存储部署方案](../deliverables/D04-D06_Worker节点与数据存储部署方案.md)
