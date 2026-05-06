# 多环境配置规划

本目录定义当前仓库推荐保留的三套环境口径：

1. `local`：开发者本机验收环境
2. `dev`：单机 ECS + Ubuntu 22.04 + Docker Compose 测试环境
3. `prod`：生产最小可接受 MVP 环境

## 1. 环境矩阵

| 环境 | app 部署方式 | 中间件部署方式 | AI 策略 | 主要目标 |
| --- | --- | --- | --- | --- |
| `local` | 宿主机 Python 进程 | Docker Compose | 可选本地 Ollama | 开发、调试、本地验收 |
| `dev` | Docker Compose | Docker Compose | 默认外部/兼容 LLM，可选 GPU 本地 Ollama | 最经济的 Linux 真实联调环境 |
| `prod` | Docker Compose | 应用层 Compose，状态层优先外部托管 | 默认外部 LLM，私有化时单独 GPU 节点 | 生产 MVP，上线最小闭环 |

## 2. 当前单一事实来源

### `local`

- 环境变量模板：`D:/Project/fms/.env.example`
- 基础中间件：`D:/Project/fms/docker-compose.yml`
- WSL 扩展依赖：`D:/Project/fms/docker-compose.wsl-local.yml`
- 可选 Kafka：`D:/Project/fms/docker-compose.local-kafka.yml`
- 可选本地 LLM：`D:/Project/fms/docker-compose.local-llm.yml`
- 文档入口：`D:/Project/fms/docs/local-runtime/README.md`

### `dev`

- 环境变量模板：`D:/Project/fms/.env.dev.example`
- Compose 文件：`D:/Project/fms/docker-compose.dev.yml`
- Kong 配置：`D:/Project/fms/docker/kong/kong.compose-app.yml`

### `prod`

- 环境变量模板：`D:/Project/fms/.env.prod.example`
- Compose 文件：`D:/Project/fms/docker-compose.prod.yml`
- Kong 配置：`D:/Project/fms/docker/kong/kong.compose-app.yml`

## 3. 关键设计决策

### 3.1 local 继续保持 host-run app

这是当前最合适的开发路径，因为：

- 改 Python 代码后反馈最快，不需要反复构建镜像。
- 本地 Windows + WSL + Docker Desktop 组合下，问题定位更直接。
- 现在本地基线已经围绕这个口径完成验收，不能为了统一形式反向破坏开发效率。

### 3.2 dev 改为 app 进 Compose

`dev` 不是开发机，而是最经济的 Linux 真实联调环境，所以要把 `app` 纳入 Compose：

- 更接近真实交付形态。
- Kong upstream 走容器内 `app:8000`，不依赖宿主机端口映射技巧。
- 更适合做镜像、环境变量、启动顺序、健康检查、部署回放。

### 3.3 prod 采用“应用层 Compose + 状态层优先托管”的 MVP

生产最低可接受方案不建议把 PostgreSQL / Redis 继续和应用完全绑在同一台主机上：

- 数据安全和备份要求高于本地/测试。
- 云托管数据库和缓存比自管高可用集群更省运维成本。
- 对当前项目最经济的生产 MVP，是把复杂度优先放在业务交付，而不是自建全套 HA。

因此当前推荐：

- `app` / `kong` / 可选 `worker`：Compose 部署
- PostgreSQL：云 RDS
- Redis：云 Tair / Redis
- Qdrant / OpenSearch / Neo4j：视成本与查询规模决定先自管还是外置
- 本地私有化 LLM：只有在明确要求时才单独加 GPU 节点

## 4. 资源与成本基线

### `local`

- 继续按现有本地基线执行。
- Windows 重资源目录统一放在 `D:\aitools`。

### `dev`

推荐两档：

1. CPU 档
   - `8 vCPU / 16 GB RAM`
   - 系统盘尽量小，额外挂载 `200 GB` 数据盘
   - 适合联调 API、搜索、向量、图谱、网关，不强制本地 LLM
2. GPU 档
   - `8-16 vCPU / 32 GB RAM`
   - `1 x 16-24 GB VRAM` GPU
   - 只在要验证私有化 Ollama / 多模态链路时启用 `gpu-llm` profile

### `prod`

生产 MVP 推荐：

1. 默认方案
   - `1 x 8 vCPU / 16 GB RAM ECS`：`kong + app + worker`
   - 云托管 `RDS PostgreSQL + Redis`
   - 数据盘 `300 GB+`
   - 不启用本地 GPU LLM，优先走外部模型或独立 AI 节点
2. 私有化模型方案
   - 在默认方案基础上，额外增加 `1 x GPU ECS`
   - 只承载 `ollama` 或后续独立 AI 推理服务
   - 不建议把 GPU 负载和主业务 API 混跑

### 阿里云资源清单（`dev/prod`）

仅针对云上环境补充资源清单；`local` 继续沿用本机 + Docker Compose 口径。当前默认边界仍然是“应用层 Compose + 状态层优先托管”，所以 ACK / K8s 不作为当前 MVP 必选项。

| 类别 | 当前组件 / 用途 | 阿里云资源建议 | 适用环境 | 备注 |
| --- | --- | --- | --- | --- |
| 网络基础 | 云上私网隔离、子网划分、安全访问 | VPC + vSwitch + Security Group | `dev` / `prod` | 建议按环境拆分网段，应用、数据库、缓存尽量留在同一 VPC |
| 公网出口 | 拉镜像、访问外部 LLM / 第三方 API | NAT Gateway + EIP | `dev` / `prod` | 减少应用节点直接暴露公网，统一控制出站访问 |
| 应用计算 | `kong`、`app`、`app-worker` | ECS | `dev` / `prod` | 当前 README 默认仍以单机 ECS + Docker Compose 为主 |
| 容器镜像 | `PMS_APP_IMAGE`、版本分发 | ACR 容器镜像服务 | `dev` / `prod` | 用于存放后端应用镜像与后续环境发布版本 |
| 关系型数据库 | PostgreSQL | RDS PostgreSQL | `prod` 必选，`dev` 可选 | 与 `.env.prod.example` 中 `DB_URL` 口径一致 |
| 缓存 | Redis | Tair / 云数据库 Redis 版 | `prod` 必选，`dev` 可选 | 与 `.env.prod.example` 中 `REDIS_URL` 口径一致 |
| 对象存储 | `artifacts`、导出文件、备份归档 | OSS | `prod` | 可承接 `/data/pms/artifacts` 中需要长期保存或共享的文件 |
| 日志与审计 | 应用日志、Kong 日志、运维留痕 | SLS 日志服务 | `prod` | 建议集中检索并设置保留周期 |
| 监控与告警 | 指标、链路、健康检查、告警 | ARMS + Prometheus / Grafana 服务 | `prod` | 用于替代单机自建监控的长期运维成本 |
| 搜索服务 | OpenSearch 检索 | 阿里云 Elasticsearch/OpenSearch 服务，或 ECS 自管 OpenSearch | `dev` / `prod` | README 当前口径允许按成本与规模决定自管还是外置 |
| 向量检索 | Qdrant | ECS 自管 Qdrant | `dev` / `prod` | 当前仓库以 Qdrant 为主，云上优先保持兼容口径 |
| 图数据库 | Neo4j 图谱能力 | ECS 自管 Neo4j，或图数据库 GDB（需额外适配） | `dev` / `prod` | 现有代码直连 Neo4j 协议，切换托管图数据库前要先验证兼容性 |
| 消息队列 | Kafka（按需启用） | 消息队列 Kafka 版 | `dev` / `prod` 按需 | 仅在 `dev/prod` 明确引入 Kafka 时申请 |
| 实时计算 | Flink 流式任务（按需启用） | 实时计算 Flink 版 | `prod` 按需 | 对应后续数据平台或实时链路扩展 |
| AI 推理 | 私有化 Ollama / 独立推理节点 | GPU ECS，或 PAI / 百炼 | `dev` / `prod` 按需 | 默认优先外部 LLM；只有私有化要求明确时再增加 GPU 资源 |
| 公网入口与安全 | 域名解析、流量接入、基础防护 | SLB / ALB + WAF + 云解析 DNS | `prod` | Kong 继续作为应用层网关，云上补齐公网接入与防护层 |
| 容器编排（后续） | 多副本、滚动升级、弹性伸缩 | ACK | `prod` 后续阶段 | 当前 MVP 不直接引入，只有在单机 Compose 不再满足时再升级 |

## 5. 数据落盘规则

- Windows 本地：`D:\aitools\fms\...`
- Linux `dev/prod`：`/data/pms/...`

建议至少拆出：

- `/data/pms/postgres`
- `/data/pms/redis`
- `/data/pms/qdrant`
- `/data/pms/opensearch`
- `/data/pms/neo4j`
- `/data/pms/cache`
- `/data/pms/artifacts`
- `/data/pms/ollama`

## 6. 启动口径

### `local`

```powershell
python D:/Project/fms/scripts/install_python_deps.py --run-check
python D:/Project/fms/scripts/install_local_software.py
python D:/Project/fms/scripts/start_local_services.py
powershell -NoProfile -File D:/Project/fms/scripts/start_local.ps1
```

### `dev`

```bash
cp .env.dev.example .env.dev
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --build
```

需要本地 GPU LLM 时：

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml --profile gpu-llm up -d --build
```

### `prod`

```bash
cp .env.prod.example .env.prod
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

如需私有化 Ollama：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml --profile gpu-private-llm up -d
```

## 7. 当前边界

- `local` 继续保留宿主机 app 启动，不和 `dev/prod` 强行统一。
- `dev` 才是“全 Compose、单机 Linux 真实环境”。
- `prod` 当前先做 MVP，不直接引入 K8s、全自建 HA、全量 GPU 化。
- Kafka 仍只保留 `D:/Project/fms/docker-compose.local-kafka.yml` 一套标准文件；如 `dev/prod` 需要 Kafka，继续复用它的服务语义与别名约定。
