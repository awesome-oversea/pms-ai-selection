# Flink集群部署文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 实时计算引擎部署文档
> **子任务**: D12 - Flink集群部署
> **文档版本**: v1.0

---

## 1. 概述

Flink是系统的实时数据处理引擎，负责消费Kafka中的原始采集数据，执行ETL清洗/转换/加载作业，输出结构化数据到PostgreSQL和Qdrant。

| 项目 | 规格 |
|------|------|
| 集群模式 | Standalone on K8s |
| JobManager | 1实例, 2048MB内存 |
| TaskManager | 3实例, 4096MB内存, 4 Slot/TM |
| 总计算Slot | 12 |
| 版本 | Flink 1.17.1 |
| State Backend | Kafka Checkpoint, 间隔30s |

---

## 2. K8s部署配置

### 2.1 JobManager Deployment

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
```

### 2.2 TaskManager Deployment

```yaml
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

---

## 3. 集群拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│                    Flink集群拓扑                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              JobManager (调度与协调)                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Job调度   │ │Checkpoint│ │ Web UI   │               │   │
│  │  │          │ │ 协调     │ │ :8081    │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              TaskManager × 3 (计算执行)                   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ TM-1     │ │ TM-2     │ │ TM-3     │               │   │
│  │  │ 4 Slots  │ │ 4 Slots  │ │ 4 Slots  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │ Kafka    │ ←→ │ ETL Job  │ →  │ PG/Qdrant│                  │
│  │ Source   │    │          │    │ Sink     │                  │
│  └──────────┘    └──────────┘    └──────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| JobManager Pod Running | Web UI :8081可达 | ☐ |
| TaskManager ≥3个 | Slot总数≥12 | ☐ |
| Checkpoint配置 | 间隔30s, Kafka State Backend | ☐ |
| Job提交正常 | 测试Job可提交并Running | ☐ |
| Web Dashboard | 可查看Job/TM/Slot状态 | ☐ |

---

**文档状态**: ✅ 已完成
