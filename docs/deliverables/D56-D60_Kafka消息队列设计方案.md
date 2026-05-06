# Kafka消息队列设计方案

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 技术设计文档
> **子任务**: D56-D60 Kafka消息队列与事件驱动架构
> **文档版本**: v1.0

---

## 目录

- [1. 概述](#1-概述)
- [2. 架构设计](#2-架构设计)
- [3. Topic设计](#3-topic设计)
- [4. 生产者设计](#4-生产者设计)
- [5. 消费者设计](#5-消费者设计)
- [6. 事件驱动架构](#6-事件驱动架构)
- [7. 监控与运维](#7-监控与运维)

---

## 1. 概述

### 1.1 设计目标

构建基于Kafka的事件驱动架构，实现系统间解耦、异步处理和实时数据流。

### 1.2 核心能力

| 能力 | 说明 | 目标指标 |
|------|------|---------|
| 消息吞吐 | 高吞吐消息处理 | ≥100K msg/s |
| 消息可靠性 | 消息不丢失 | 99.99% |
| 低延迟 | 消息处理延迟 | <100ms |
| 高可用 | 集群可用性 | 99.9% |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kafka Cluster (3 Brokers)                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Topics                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ data-    │ │ agent-   │ │ erp-     │ │ system-  │   │   │
│  │  │ events   │ │ events   │ │ events   │ │ events   │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Consumer Groups                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ data-    │ │ agent-   │ │ erp-     │ │ monitor- │   │   │
│  │  │ processor│ │ worker   │ │ sync     │ │ ing      │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
    │Producer │          │Producer │          │Producer │
    │(Data)   │          │(Agent)  │          │(ERP)    │
    └─────────┘          └─────────┘          └─────────┘
```

### 2.2 集群配置

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: fms-kafka
spec:
  kafka:
    version: 3.5.1
    replicas: 3
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
      - name: tls
        port: 9093
        type: internal
        tls: true
    config:
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      default.replication.factor: 3
      min.insync.replicas: 2
      log.retention.hours: 168
      log.segment.bytes: 1073741824
    storage:
      type: jbod
      volumes:
        - id: 0
          type: persistent-claim
          size: 500Gi
          class: ssd-storage
  zookeeper:
    replicas: 3
    storage:
      type: persistent-claim
      size: 100Gi
```

---

## 3. Topic设计

### 3.1 Topic清单

| Topic名称 | 分区数 | 副本数 | 保留时间 | 说明 |
|----------|--------|--------|---------|------|
| data-collection-events | 12 | 3 | 7天 | 数据采集事件 |
| data-quality-events | 6 | 3 | 7天 | 数据质量事件 |
| agent-task-events | 12 | 3 | 7天 | Agent任务事件 |
| agent-result-events | 12 | 3 | 7天 | Agent结果事件 |
| erp-sync-events | 6 | 3 | 7天 | ERP同步事件 |
| system-alert-events | 3 | 3 | 30天 | 系统告警事件 |
| audit-log-events | 6 | 3 | 365天 | 审计日志事件 |

### 3.2 Topic创建

```python
from kafka.admin import KafkaAdminClient, NewTopic
from kafka import KafkaProducer, KafkaConsumer

class TopicManager:
    def __init__(self, bootstrap_servers: str):
        self.admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers
        )
    
    def create_topic(
        self,
        topic_name: str,
        num_partitions: int = 6,
        replication_factor: int = 3
    ):
        topic = NewTopic(
            name=topic_name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            topic_configs={
                "retention.ms": "604800000",
                "segment.bytes": "1073741824",
                "cleanup.policy": "delete"
            }
        )
        
        self.admin_client.create_topics([topic])
    
    def list_topics(self) -> list[str]:
        return self.admin_client.list_topics()
```

### 3.3 消息格式

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Any, Optional
import uuid

class EventMessage(BaseModel):
    event_id: str = str(uuid.uuid4())
    event_type: str
    source: str
    timestamp: str = datetime.now().isoformat()
    payload: dict[str, Any]
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None

class DataCollectionEvent(EventMessage):
    event_type: str = "data_collected"
    source: str = "data-collection-agent"
    payload: dict[str, Any]

class AgentTaskEvent(EventMessage):
    event_type: str = "agent_task_created"
    source: str = "selection-master"
    payload: dict[str, Any]

class ERPSyncEvent(EventMessage):
    event_type: str = "erp_sync_requested"
    source: str = "erp-gateway"
    payload: dict[str, Any]
```

---

## 4. 生产者设计

### 4.1 生产者配置

```python
from kafka import KafkaProducer
import json

class EventProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3,
            max_in_flight_requests_per_connection=1,
            enable_idempotence=True,
            compression_type='lz4',
            linger_ms=10,
            batch_size=16384
        )
    
    async def send(
        self,
        topic: str,
        message: EventMessage,
        key: str = None
    ) -> bool:
        try:
            future = self.producer.send(
                topic,
                key=key or message.event_id,
                value=message.dict()
            )
            result = future.get(timeout=10)
            return True
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False
    
    async def send_batch(
        self,
        topic: str,
        messages: list[EventMessage]
    ) -> int:
        success_count = 0
        for message in messages:
            if await self.send(topic, message):
                success_count += 1
        return success_count
    
    def close(self):
        self.producer.flush()
        self.producer.close()
```

### 4.2 事件发布器

```python
class EventPublisher:
    def __init__(self, producer: EventProducer):
        self.producer = producer
    
    async def publish_data_collected(
        self,
        source: str,
        data: dict,
        correlation_id: str = None
    ):
        event = DataCollectionEvent(
            payload={
                "source": source,
                "data": data,
                "record_count": len(data) if isinstance(data, list) else 1
            },
            correlation_id=correlation_id
        )
        await self.producer.send("data-collection-events", event)
    
    async def publish_agent_task(
        self,
        task_id: str,
        agent_type: str,
        task_data: dict,
        correlation_id: str = None
    ):
        event = AgentTaskEvent(
            payload={
                "task_id": task_id,
                "agent_type": agent_type,
                "task_data": task_data
            },
            correlation_id=correlation_id
        )
        await self.producer.send("agent-task-events", event)
    
    async def publish_erp_sync(
        self,
        system: str,
        entity: str,
        action: str,
        data: dict,
        correlation_id: str = None
    ):
        event = ERPSyncEvent(
            payload={
                "system": system,
                "entity": entity,
                "action": action,
                "data": data
            },
            correlation_id=correlation_id
        )
        await self.producer.send("erp-sync-events", event)
```

---

## 5. 消费者设计

### 5.1 消费者配置

```python
from kafka import KafkaConsumer
import json

class EventConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str]
    ):
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            max_poll_records=100,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000
        )
    
    async def consume(self, handler: callable):
        for message in self.consumer:
            try:
                event = EventMessage(**message.value)
                await handler(event)
                self.consumer.commit()
            except Exception as e:
                print(f"Error processing message: {e}")
    
    def close(self):
        self.consumer.close()
```

### 5.2 消费者组设计

```python
class DataProcessorConsumer:
    def __init__(self, bootstrap_servers: str):
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="data-processor-group",
            topics=["data-collection-events"]
        )
        self.data_service = DataService()
    
    async def start(self):
        await self.consumer.consume(self._handle_event)
    
    async def _handle_event(self, event: EventMessage):
        if event.event_type == "data_collected":
            await self._process_collected_data(event.payload)
    
    async def _process_collected_data(self, payload: dict):
        data = payload.get("data")
        source = payload.get("source")
        
        processed_data = await self.data_service.process(data, source)
        
        await self.data_service.save(processed_data)

class AgentWorkerConsumer:
    def __init__(self, bootstrap_servers: str, agent_type: str):
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=f"agent-worker-{agent_type}",
            topics=["agent-task-events"]
        )
        self.agent_type = agent_type
        self.agent = get_agent(agent_type)
    
    async def start(self):
        await self.consumer.consume(self._handle_event)
    
    async def _handle_event(self, event: EventMessage):
        if event.event_type == "agent_task_created":
            task_data = event.payload.get("task_data")
            result = await self.agent.execute(task_data)
            
            await self._publish_result(event.event_id, result)
    
    async def _publish_result(self, task_id: str, result: dict):
        publisher = get_event_publisher()
        await publisher.publish_agent_result(task_id, result)
```

---

## 6. 事件驱动架构

### 6.1 事件总线

```python
class EventBus:
    def __init__(self, producer: EventProducer):
        self.producer = producer
        self.handlers: dict[str, list[callable]] = {}
    
    def subscribe(self, event_type: str, handler: callable):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    async def publish(self, topic: str, event: EventMessage):
        await self.producer.send(topic, event)
    
    async def handle(self, event: EventMessage):
        handlers = self.handlers.get(event.event_type, [])
        for handler in handlers:
            await handler(event)

class EventSourcing:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.event_store = EventStore()
    
    async def append(self, aggregate_id: str, event: EventMessage):
        await self.event_store.append(aggregate_id, event)
        await self.event_bus.publish("event-store", event)
    
    async def get_events(self, aggregate_id: str) -> list[EventMessage]:
        return await self.event_store.get_events(aggregate_id)
```

### 6.2 Saga编排

```python
class SagaStep(BaseModel):
    step_id: str
    action: str
    compensate_action: str
    status: str = "pending"

class SagaOrchestrator:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.sagas: dict[str, list[SagaStep]] = {}
    
    async def start_saga(self, saga_id: str, steps: list[SagaStep]):
        self.sagas[saga_id] = steps
        await self._execute_step(saga_id, 0)
    
    async def _execute_step(self, saga_id: str, step_index: int):
        steps = self.sagas.get(saga_id)
        if not steps or step_index >= len(steps):
            return
        
        step = steps[step_index]
        
        try:
            await self.event_bus.publish("saga-events", EventMessage(
                event_type="saga_step_started",
                payload={"saga_id": saga_id, "step": step.dict()}
            ))
            
            step.status = "completed"
            await self._execute_step(saga_id, step_index + 1)
            
        except Exception as e:
            step.status = "failed"
            await self._compensate(saga_id, step_index - 1)
    
    async def _compensate(self, saga_id: str, step_index: int):
        steps = self.sagas.get(saga_id)
        
        for i in range(step_index, -1, -1):
            step = steps[i]
            if step.status == "completed":
                await self.event_bus.publish("saga-events", EventMessage(
                    event_type="saga_compensate",
                    payload={
                        "saga_id": saga_id,
                        "step_id": step.step_id,
                        "action": step.compensate_action
                    }
                ))
                step.status = "compensated"
```

---

## 7. 监控与运维

### 7.1 消费延迟监控

```python
class LagMonitor:
    def __init__(self, bootstrap_servers: str):
        self.admin_client = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
    
    def get_consumer_lag(self, group_id: str) -> dict:
        consumer_groups = self.admin_client.list_consumer_groups()
        
        if group_id not in [g[0] for g in consumer_groups]:
            return {}
        
        offsets = self.admin_client.list_consumer_group_offsets(group_id)
        
        lag_info = {}
        for topic_partition, offset_metadata in offsets.items():
            topic = topic_partition.topic
            partition = topic_partition.partition
            
            end_offsets = self.admin_client.describe_topics([topic])
            
            lag_info[f"{topic}:{partition}"] = {
                "current_offset": offset_metadata.offset,
                "lag": 0
            }
        
        return lag_info
```

### 7.2 健康检查

```python
class KafkaHealthCheck:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
    
    async def check_brokers(self) -> dict:
        try:
            admin = KafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
            cluster_metadata = admin.describe_cluster()
            
            return {
                "status": "healthy",
                "brokers": len(cluster_metadata.brokers),
                "controller_id": cluster_metadata.controller_id
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def check_topics(self) -> dict:
        try:
            admin = KafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
            topics = admin.list_topics()
            
            return {
                "status": "healthy",
                "topic_count": len(topics)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
```

---

## 附录

### A. 配置示例

```yaml
kafka:
  bootstrap_servers: "kafka-1:9092,kafka-2:9092,kafka-3:9092"
  
  producer:
    acks: "all"
    retries: 3
    batch_size: 16384
    linger_ms: 10
    compression_type: "lz4"
  
  consumer:
    group_id: "fms-consumer"
    auto_offset_reset: "earliest"
    enable_auto_commit: false
    max_poll_records: 100
  
  topics:
    data_events: "data-collection-events"
    agent_events: "agent-task-events"
    erp_events: "erp-sync-events"
```

### B. 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-06 | AI助手 | 初始版本 |

---

**文档状态**: ✅ 已完成
