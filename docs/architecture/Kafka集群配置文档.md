# Kafka集群配置文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 基础设施部署文档
> **子任务**: D7 - Kafka消息队列部署
> **文档版本**: v1.0

---

## 1. 概述

Kafka是系统的核心消息队列，承载数据采集事件流、Agent间通信事件和系统日志等，为实时数据处理提供可靠的消息传递能力。

| 项目 | 规格 |
|------|------|
| 集群模式 | 3 Broker集群 |
| 单节点规格 | 4核8G |
| 数据保留 | 7天 (168小时) |
| 副本因子 | 3 |
| 核心Topic数 | 3 (amazon-data / tiktok-data / agent-events) |

---

## 2. 集群架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kafka集群架构                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Producer层                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ 数据采集  │ │ Agent事件 │ │ 系统日志  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Broker集群                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ Broker-1 │ │ Broker-2 │ │ Broker-3 │               │   │
│  │  │ Leader   │ │ Follower │ │ Follower │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Consumer层                            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │   │
│  │  │ ETL处理  │ │ 实时分析  │ │ 数据存储  │               │   │
│  │  └──────────┘ └──────────┘ └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**消息流说明**:
- **Producer层**: 数据采集爬虫(amazon-data/tiktok-data)、Agent事件(agent-events)、系统日志
- **Broker集群**: 3节点高可用，所有Topic副本因子=3，ISR最小值=2
- **Consumer层**: Flink ETL处理、实时分析引擎、PostgreSQL/Qdrant数据入库

---

## 3. K8s StatefulSet部署配置

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka
  namespace: pms-data
spec:
  serviceName: kafka-headless
  replicas: 3
  selector:
    matchLabels:
      app: kafka
  template:
    metadata:
      labels:
        app: kafka
    spec:
      containers:
        - name: kafka
          image: confluentinc/cp-kafka:7.5.0
          ports:
            - containerPort: 9092
              name: kafka
            - containerPort: 9093
              name: kafka-internal
          env:
            - name: KAFKA_BROKER_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: KAFKA_ZOOKEEPER_CONNECT
              value: "zookeeper:2181"
            - name: KAFKA_LISTENER_SECURITY_PROTOCOL_MAP
              value: "PLAINTEXT:PLAINTEXT,INTERNAL:PLAINTEXT"
            - name: KAFKA_ADVERTISED_LISTENERS
              value: "PLAINTEXT://$(POD_NAME).kafka-headless:9092,INTERNAL://$(POD_IP):9093"
            - name: KAFKA_INTER_BROKER_LISTENER_NAME
              value: "INTERNAL"
            - name: KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR
              value: "3"
            - name: KAFKA_TRANSACTION_STATE_LOG_MIN_ISR
              value: "2"
            - name: KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR
              value: "3"
            - name: KAFKA_LOG_RETENTION_HOURS
              value: "168"
            - name: KAFKA_LOG_SEGMENT_BYTES
              value: "1073741824"
          volumeMounts:
            - name: kafka-data
              mountPath: /var/lib/kafka/data
      volumes:
        - name: kafka-data
          persistentVolumeClaim:
            claimName: kafka-pvc
```

---

## 4. Topic配置

### 4.1 核心Topic创建

```bash
# amazon-data: Amazon BSR/评论数据，12分区高吞吐
kafka-topics --create \
  --bootstrap-server kafka-0.kafka-headless:9092 \
  --topic amazon-data \
  --partitions 12 \
  --replication-factor 3 \
  --config retention.ms=604800000

# tiktok-data: TikTok商品数据，6分区
kafka-topics --create \
  --bootstrap-server kafka-0.kafka-headless:9092 \
  --topic tiktok-data \
  --partitions 6 \
  --replication-factor 3

# agent-events: Agent间通信事件，12分区
kafka-topics --create \
  --bootstrap-server kafka-0.kafka-headless:9092 \
  --topic agent-events \
  --partitions 12 \
  --replication-factor 3

# 验证Topic列表
kafka-topics --list --bootstrap-server kafka-0.kafka-headless:9092
```

### 4.2 Topic规划表

| Topic | 分区数 | 副本因子 | 保留时间 | 用途 |
|-------|--------|---------|---------|------|
| amazon-data | 12 | 3 | 7天 | Amazon BSR排名、商品详情、评论数据 |
| tiktok-data | 6 | 3 | 7天 | TikTok商品数据、趋势数据 |
| agent-events | 12 | 3 | 7天 | Agent间通信、任务调度事件 |

---

## 5. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| 3 Broker集群运行 | kafka-0/1/2 全部Running | ☐ |
| ZooKeeper连接正常 | Broker注册成功 | ☐ |
| amazon-data Topic | 12分区, rf=3 | ☐ |
| tiktok-data Topic | 6分区, rf=3 | ☐ |
| agent-events Topic | 12分区, rf=3 | ☐ |
| 消息收发正常 | Producer发送→Consumer接收成功 | ☐ |
| 日志保留配置生效 | retention.ms=604800000 (7天) | ☐ |

---

**文档状态**: ✅ 已完成
