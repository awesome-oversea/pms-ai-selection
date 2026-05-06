# 跨境电商AI选品系统 PMS — 阿里云资源清单

> 基于《本地环境安装部署指南》及全部 docker-compose 配置映射生成
> 生成日期：2026-04-20

---

## 一、资源总览

| 层级 | 本地组件 | 阿里云产品 | 规格/版本 | 实例数 | 备注 |
|------|----------|-----------|-----------|--------|------|
| **计算-应用** | FastAPI App (pms-app) | ECS / ACK Pod | 2C4G+ | 2+ | 主应用，含 Celery Worker |
| **计算-爬虫** | Crawler Worker | ECS / ACK Pod | 2C4G | 1-3 | Scrapy/Playwright 爬虫 |
| **计算-Flink** | Flink JobManager + TaskManager | 实时计算 Flink 版 | 2 CU 起 | 1 | 流式特征计算 |
| **数据库-主库** | PostgreSQL 16 (pms-postgres) | RDS PostgreSQL | 高可用版 4C8G | 1 主 + 1 备 | wal_level=logical, max_wal_senders=10 |
| **数据库-HA** | PgPool + 3节点 repmgr | RDS PostgreSQL 自带 HA | — | — | 云上无需自建 PgPool |
| **数据库-Keycloak** | PostgreSQL 16 (keycloak-db) | RDS PostgreSQL | 基础版 1C2G | 1 | 或与主库共用实例 |
| **缓存** | Redis 7 单节点 | Tair (Redis 企业版) | 4G 标准版 | 1 | 本地单节点场景 |
| **缓存-HA** | Redis 1主2从 + 3 Sentinel | Tair (Redis 企业版) 集群 | 4G 集群版 | 3 节点 | 云上 Sentinel 由 Tair 内置 |
| **向量库** | Qdrant v1.9.5 / v1.15.3 集群 | ECS 自建 / 百炼向量检索 | 4C8G | 1 或 3 | 阿里云无原生 Qdrant，需 ECS 自建或用百炼 |
| **搜索引擎** | OpenSearch 2.11 | Elasticsearch (阿里云) | 7.10 / 8.x | 3 节点 | 兼容 OpenSearch API |
| **图数据库** | Neo4j 5.26 Community | ECS 自建 / 图数据库 GDB | 4C16G | 1 | GDB 兼容 Gremlin，Neo4j 需自建 |
| **消息队列** | Kafka 7.6.1 (单 Broker) | 消息队列 Kafka 版 | 标准版 2C4G | 3 Broker | 云上建议 3 Broker 高可用 |
| **消息队列-ZK** | ZooKeeper 7.6.1 | 消息队列 Kafka 版内置 | — | — | 云上无需自建 ZK |
| **CDC** | Debezium Connect 2.7.3 | DTS 数据传输 | — | 1 | 或继续用 Debezium on ECS |
| **API 网关** | Kong 3.8 (DB-less) | API 网关 / MSE 云原生网关 | — | 1 | 云上推荐 MSE Ingress |
| **认证** | Keycloak (latest) | IDaaS / ECS 自建 Keycloak | 2C4G | 1 | 或用阿里云 IDaaS EIAM |
| **对象存储** | 本地 Volume | OSS | 标准存储 | 1 | 模型文件/爬虫数据/备份 |
| **容器镜像** | Docker Hub | 容器镜像服务 ACR | 标准版 | 1 | 私有镜像仓库 |
| **LLM 推理** | Ollama (qwen2.5:1.5b / qwen3.5:2b) | 百炼 / PAI-EAS | — | 1 | 云上推荐百炼 API 或 PAI-EAS |
| **LLM 精排** | bge-reranker-base (CPU) | 百炼 Embedding | — | 1 | 或 PAI-EAS 自部署 |
| **LLM 语音** | Whisper tiny/base (CPU) | 百炼 Paraformer / ECS 自建 | 2C4G | 1 | 或用百炼语音识别 API |
| **LLM 微调** | CPU Feedback Adapter | PAI-DSW / PAI-DLC | GPU A10/V100 | 1 | 按需使用 |
| **DNS/CDN** | localhost | 云解析 DNS + CDN | — | 1 | 前端静态资源加速 |
| **监控** | Docker logs | ARMS + SLS | — | 1 | 应用监控 + 日志采集 |
| **安全** | SEC_SECRET_KEY | WAF + 安全中心 | — | 1 | Web 应用防火墙 |

---

## 二、分栈资源明细

### 2.1 基础数据栈（对应 docker-compose.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| postgres | postgres:16-alpine | RDS PostgreSQL 高可用版 | 4C8G, 100G SSD | 5432 | pg_data: 业务数据 + CDC slot |
| redis | redis:7-alpine | Tair Redis 标准版 | 4G 内存 | 6379 | redis_data: AOF 持久化 |
| qdrant | qdrant/qdrant:v1.9.5 | ECS 自建 Qdrant | 4C8G, 200G SSD | 6333/6334 | qdrant_data: 向量索引 |
| zookeeper | cp-zookeeper:7.6.1 | Kafka 版内置 | — | 2181 | — |
| kafka | cp-kafka:7.6.1 | 消息队列 Kafka 版 标准版 | 3×2C4G, 500G SSD | 9092 | Topic: 9 业务 + 3 Connect 内部 |
| kafka-init | cp-kafka:7.6.1 | Kafka 版自动创建 | — | — | — |
| kafka-connect | debezium/connect:2.7.3 | DTS / ECS 自建 | 2C4G | 8083 | — |
| debezium-init | curlimages/curl:8.8.0 | DTS 自动配置 | — | — | — |
| crawler-worker | 自建 Dockerfile | ECS / ACK Job | 2C4G | — | 临时 |
| app | 自建 Dockerfile | ECS / ACK Deployment | 2C4G+ | 8000 | — |

### 2.2 WSL 本地搜索/网关/图谱栈（对应 docker-compose.wsl-local.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| kong-database | postgres:16-alpine | RDS PostgreSQL (共用) | — | 15433 | kong_db_data |
| kong-migrations | kong:3.8 | MSE 云原生网关免迁移 | — | — | — |
| kong-gateway | kong:3.8 (DB-less) | MSE 云原生网关 / API 网关 | — | 8000/8001 | kong.yml 声明式配置 |
| opensearch | opensearch:2.11.0 | Elasticsearch 8.x | 3×4C16G, 500G SSD | 9200 | opensearch_data: 索引数据 |
| neo4j | neo4j:5.26-community | ECS 自建 Neo4j | 4C16G, 200G SSD | 7474/7687 | neo4j_data: 图数据 |

### 2.3 WSL 平台栈（对应 docker-compose.wsl-platform.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| redis-master | redis:7.4-alpine | Tair Redis 集群版 | 3×4G | 16379 | redis_master_data |
| redis-replica-1 | redis:7.4-alpine | Tair Redis 集群版内置 | — | 16380 | redis_replica_1_data |
| redis-replica-2 | redis:7.4-alpine | Tair Redis 集群版内置 | — | 16381 | redis_replica_2_data |
| redis-sentinel-1/2/3 | redis:7.4-alpine | Tair Redis 集群版内置 | — | 26379/26380/26381 | — |
| keycloak-db | postgres:16-alpine | RDS PostgreSQL (共用) | — | 15434 | keycloak_db_data |
| keycloak | keycloak:latest | IDaaS EIAM / ECS 自建 | 2C4G | 18082/19000 | Realm 配置 |
| flink-jobmanager | flink:2.2.0-scala_2.12 | 实时计算 Flink 版 | 2 CU | 18081 | Checkpoint: OSS |
| flink-taskmanager | flink:2.2.0-scala_2.12 | 实时计算 Flink 版内置 | 2 CU | — | — |

### 2.4 PostgreSQL HA 栈（对应 docker-compose.wsl-postgres-ha.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| pg-primary | bitnamilegacy/postgresql-repmgr:17.6.0 | RDS PostgreSQL 主实例 | 4C8G, 100G SSD | 15435 | pg_primary_data |
| pg-standby-1 | bitnamilegacy/postgresql-repmgr:17.6.0 | RDS PostgreSQL 只读实例 | 4C8G, 100G SSD | 15436 | pg_standby_1_data |
| pg-standby-2 | bitnamilegacy/postgresql-repmgr:17.6.0 | RDS PostgreSQL 只读实例 | 4C8G, 100G SSD | 15437 | pg_standby_2_data |
| pgpool | bitnamilegacy/pgpool:4.6.3 | RDS 代理 (内置读写分离) | — | 15432 | — |

> **说明**：云上使用 RDS PostgreSQL 高可用版时，主备切换、读写分离、连接池均由 RDS 内置能力提供，无需自建 PgPool 和 repmgr 集群。

### 2.5 Qdrant 集群栈（对应 docker-compose.wsl-qdrant-cluster.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| qdrant-node-1 | qdrant/qdrant:v1.15.3 | ECS 自建 Qdrant 集群 | 4C8G, 200G SSD | 16333/16334/16335 | qdrant_node_1_data |
| qdrant-node-2 | qdrant/qdrant:v1.15.3 | ECS 自建 Qdrant 集群 | 4C8G, 200G SSD | 16433/16434/16435 | qdrant_node_2_data |
| qdrant-node-3 | qdrant/qdrant:v1.15.3 | ECS 自建 Qdrant 集群 | 4C8G, 200G SSD | 16533/16534/16535 | qdrant_node_3_data |

> **说明**：阿里云无原生 Qdrant 托管服务。可选方案：(1) 3 台 ECS 自建 Qdrant 集群；(2) 使用百炼向量检索服务（API 模式，需改代码适配）；(3) 单 ECS 部署 Qdrant 单节点（开发/预发环境）。

### 2.6 Kafka/CDC 栈（对应 docker-compose.local-kafka.yml）

| 本地服务 | 镜像/版本 | 阿里云替代 | 推荐规格 | 端口映射 | 存储需求 |
|----------|-----------|-----------|----------|----------|----------|
| zookeeper | cp-zookeeper:7.6.1 | Kafka 版内置 | — | 12181 | — |
| kafka | cp-kafka:7.6.1 | 消息队列 Kafka 版 | 3×2C4G, 500G SSD | 9092 | 9 业务 Topic + 3 Connect Topic |
| kafka-init | cp-kafka:7.6.1 | Kafka 版自动创建 | — | — | — |
| kafka-connect | debezium/connect:2.7.3 | DTS 数据同步 / ECS 自建 | 2C4G | 8083 | Connector: oms + crm |

---

## 三、AI/LLM 资源清单

| 本地组件 | 模型/版本 | 阿里云替代 | 推荐规格 | 用途 |
|----------|-----------|-----------|----------|------|
| Ollama 文本模型 | qwen2.5:1.5b-instruct (GGUF) | 百炼 qwen2.5 系列 API | 按量计费 | 文本对话/选品分析 |
| Ollama 多模态 | qwen3.5:2b (Ollama 多模态) | 百炼 qwen-vl 系列 API | 按量计费 | 图像/视频分析 |
| CPU 精排 | bge-reranker-base | 百炼 Embedding API | 按量计费 | 搜索结果重排 |
| Whisper 语音 | whisper-base (CPU) | 百炼 Paraformer 语音识别 | 按量计费 | 音频转录 |
| 模型微调 | CPU Feedback Adapter | PAI-DSW + PAI-DLC | GPU A10 (24G) | 定期微调 |
| Dify 编排 | Dify 容器 | 百炼 Agent Builder / ECS 自建 | 2C4G | 低代码工作流 |

---

## 四、网络与安全资源

| 资源 | 阿里云产品 | 规格 | 用途 |
|------|-----------|------|------|
| VPC | 专有网络 VPC | /16 网段 | 全部资源隔离 |
| 交换机 | vSwitch | /20 网段 × 2 可用区 | 多可用区部署 |
| 安全组 | 安全组 | — | 入站/出站规则控制 |
| 负载均衡 | SLB / ALB | — | 应用层流量分发 |
| NAT 网关 | NAT Gateway | — | ECS 出公网（拉镜像/调 API） |
| 弹性公网 IP | EIP | — | 对外暴露服务 |
| Web 应用防火墙 | WAF 3.0 | — | API 防护 |
| SSL 证书 | SSL 证书服务 | — | HTTPS |
| DNS | 云解析 DNS | — | 域名解析 |
| CDN | CDN | — | 前端静态资源加速 |

---

## 五、存储资源汇总

| 数据类型 | 阿里云产品 | 预估容量 | 说明 |
|----------|-----------|----------|------|
| PostgreSQL 业务数据 | RDS SSD | 100 GB | 订单/评价/产品/用户 |
| Redis 缓存 | Tair 内存 | 4 GB | 会话/特征/限流 |
| Qdrant 向量索引 | ECS SSD | 200 GB | 选品向量/知识分块 |
| OpenSearch 索引 | Elasticsearch SSD | 500 GB | 产品/评论/趋势全文索引 |
| Neo4j 图数据 | ECS SSD | 200 GB | 竞品/品牌/供应商关系图 |
| Kafka 消息 | Kafka SSD | 500 GB (3×) | CDC + 业务事件 |
| Flink Checkpoint | OSS | 50 GB | 流计算状态快照 |
| 模型文件 | OSS | 50 GB | GGUF/PyTorch 模型包 |
| 爬虫数据 | OSS | 100 GB | 原始 HTML/JSON |
| 应用日志 | SLS | 30 GB/月 | 结构化日志 + 告警 |
| 容器镜像 | ACR | 20 GB | 私有镜像存储 |
| 备份 | OSS + HBR | 200 GB | 数据库/配置定期备份 |

---

## 六、费用估算（月度，华东1-杭州）

### 6.1 托管服务

| 产品 | 规格 | 月费（估算） |
|------|------|-------------|
| RDS PostgreSQL 高可用版 | 4C8G + 100G SSD | ¥1,200 |
| RDS PostgreSQL 只读实例 ×2 | 4C8G + 100G SSD ×2 | ¥2,400 |
| Tair Redis 集群版 | 3×4G | ¥1,800 |
| 消息队列 Kafka 版 | 3×2C4G + 500G | ¥2,400 |
| 实时计算 Flink 版 | 2 CU | ¥600 |
| Elasticsearch | 3×4C16G + 500G | ¥4,500 |
| DTS 数据传输 | 小规格 | ¥300 |
| OSS 标准存储 | 500 GB | ¥100 |
| SLS 日志服务 | 30 GB/月 | ¥50 |
| ACR 容器镜像 | 标准版 | ¥100 |
| 云解析 DNS | 企业版 | ¥50 |
| **小计** | | **¥13,500** |

### 6.2 自建服务（ECS）

| 产品 | 规格 | 月费（估算） |
|------|------|-------------|
| ECS 应用服务器 ×2 | ecs.c7.2xlarge (8C16G) | ¥2,400 |
| ECS Qdrant 集群 ×3 | ecs.g7.xlarge (4C16G) | ¥2,100 |
| ECS Neo4j | ecs.g7.xlarge (4C16G) | ¥700 |
| ECS Keycloak | ecs.c7.large (2C4G) | ¥350 |
| ECS Debezium Connect | ecs.c7.large (2C4G) | ¥350 |
| SLB 负载均衡 | 标准版 | ¥200 |
| NAT 网关 + EIP | — | ¥200 |
| **小计** | | **¥6,300** |

### 6.3 AI/LLM 服务

| 产品 | 规格 | 月费（估算） |
|------|------|-------------|
| 百炼 API (qwen2.5) | 按量计费 | ¥500-2,000 |
| 百炼 Embedding | 按量计费 | ¥100-500 |
| 百炼语音识别 | 按量计费 | ¥50-200 |
| PAI-DSW (微调) | GPU A10 按量 | ¥200-800 |
| **小计** | | **¥850-3,500** |

### 6.4 总计

| 类别 | 月费范围 |
|------|----------|
| 托管服务 | ¥13,500 |
| 自建 ECS | ¥6,300 |
| AI/LLM | ¥850-3,500 |
| **合计** | **¥20,650-23,300/月** |

> **说明**：以上为生产环境估算。开发/预发环境可适当降配（如 Kafka 单 Broker、Elasticsearch 单节点、Redis 标准版），月费可压缩至 ¥8,000-12,000。

---

## 七、架构映射说明

### 7.1 云上无需自建的组件

| 本地组件 | 原因 | 云上替代 |
|----------|------|----------|
| PgPool | RDS 内置读写分离和连接池 | RDS 代理 |
| repmgr (3 节点) | RDS 内置主备切换 | RDS 高可用版 |
| Redis Sentinel (3 节点) | Tair 内置哨兵和故障切换 | Tair 集群版 |
| ZooKeeper | Kafka 版内置协调服务 | 消息队列 Kafka 版 |
| Kong Database | MSE 云原生网关 DB-less 模式 | MSE Ingress |
| Kong Migrations | MSE 无需数据库迁移 | — |

### 7.2 需要代码适配的组件

| 本地组件 | 云上替代 | 适配工作 |
|----------|----------|----------|
| Qdrant (HTTP API) | 百炼向量检索 | 需封装百炼 SDK 适配层 |
| Ollama (OpenAI 兼容) | 百炼 API | 修改 LLM_OLLAMA_ENDPOINT → 百炼 endpoint |
| Debezium CDC | DTS 数据同步 | 修改 CDC 消费格式适配 |
| Keycloak OIDC | IDaaS EIAM | 修改 SEC_OIDC_* 配置 |
| OpenSearch | Elasticsearch | API 基本兼容，少量插件差异 |
| Flink SQL | 实时计算 Flink 版 | Checkpoint 路径改 OSS |
| Whisper 本地 | 百炼 Paraformer | 修改音频转录接口调用 |

### 7.3 端口映射对照

| 本地端口 | 服务 | 云上暴露方式 |
|----------|------|-------------|
| 5432 | PostgreSQL | RDS 内网端点 |
| 6379 | Redis | Tair 内网端点 |
| 6333 | Qdrant | SLB/ECS 内网 |
| 8000 | FastAPI App | ALB/SLB → ECS |
| 8001 | Kong Admin | 不暴露公网 |
| 8080 | Shop Admin | 不暴露公网 |
| 8083 | Kafka Connect | 不暴露公网 |
| 9092 | Kafka | Kafka 内网端点 |
| 15432 | PgPool | RDS 代理端点 |
| 16333-16533 | Qdrant Cluster | SLB 内网 |
| 17474 | Neo4j Browser | 不暴露公网 |
| 17687 | Neo4j Bolt | SLB 内网 |
| 18081 | Flink UI | 不暴露公网 |
| 18082 | Keycloak | SLB 内网 |
| 19200 | OpenSearch | SLB 内网 |

---

## 八、部署建议

### 8.1 推荐部署架构

```
┌─────────────────────────────────────────────────────────────────┐
│  阿里云 VPC (10.0.0.0/16)                                       │
│                                                                  │
│  ┌─── 可用区 A ──────────────┐  ┌─── 可用区 B ──────────────┐   │
│  │                            │  │                            │   │
│  │  ALB (公网入口)            │  │  ALB 备                    │   │
│  │    ↓                       │  │                            │   │
│  │  ECS 应用 ×1               │  │  ECS 应用 ×1               │   │
│  │  ECS Qdrant ×1             │  │  ECS Qdrant ×1             │   │
│  │  ECS Neo4j                 │  │  ECS Qdrant ×1             │   │
│  │  ECS Keycloak              │  │                            │   │
│  │  ECS Debezium              │  │                            │   │
│  │                            │  │                            │   │
│  └────────────────────────────┘  └────────────────────────────┘   │
│                                                                  │
│  ┌─── 托管服务 ───────────────────────────────────────────────┐   │
│  │  RDS PostgreSQL HA (主:AZ-A, 备:AZ-B) + 2 只读             │   │
│  │  Tair Redis 集群版 (3 节点跨 AZ)                           │   │
│  │  Kafka 版 (3 Broker 跨 AZ)                                 │   │
│  │  Elasticsearch (3 节点跨 AZ)                               │   │
│  │  Flink 实时计算版                                          │   │
│  │  DTS (CDC → Kafka)                                        │   │
│  │  OSS / SLS / ACR                                          │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── AI 服务 ────────────────────────────────────────────────┐   │
│  │  百炼 API (qwen2.5 / qwen-vl / Embedding / Paraformer)    │   │
│  │  PAI-DSW / PAI-DLC (按需微调)                              │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 部署优先级

| 优先级 | 资源 | 原因 |
|--------|------|------|
| P0 | VPC + 交换机 + 安全组 | 网络基座 |
| P0 | RDS PostgreSQL + Tair Redis | 数据层核心 |
| P0 | OSS + ACR | 存储和镜像 |
| P1 | Kafka 版 + DTS | 消息和 CDC |
| P1 | ECS 应用集群 | 业务计算 |
| P1 | ALB + EIP | 流量入口 |
| P2 | Elasticsearch | 搜索能力 |
| P2 | ECS Qdrant 集群 | 向量检索 |
| P2 | Flink 实时计算版 | 流式计算 |
| P3 | 百炼 API | AI 能力 |
| P3 | ECS Neo4j | 图谱能力 |
| P3 | WAF + SLS | 安全和监控 |
