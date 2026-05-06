# 跨境电商 AI 选品系统 (PMS)

> **定位**：面向跨境电商场景的 AI 选品决策与执行中枢，覆盖从数据采集、市场洞察、产品规划、商业化评估到报告交付的全链路智能选品流程。
>
> **设计基准**：[跨境电商AI选品系统PMS—架构与业务设计文档.md](跨境电商AI选品系统PMS—%20架构与业务设计文档.md) · [跨境电商AI选品系统---分层架构与数据流协作.md](跨境电商AI选品系统---分层架构与数据流协作.md)

***

## 1. 系统概述

本系统是一个企业级跨境电商 AI 选品平台，核心能力包括：

- **Multi-Agent 智能编排**：5 大专业 Agent（数据采集 → 市场洞察 → 产品规划 → 商业化评估 → 报告生成）协同工作，模拟专家团队完成选品全流程
- **多源数据融合**：Amazon / TikTok / Google Trends / 1688 / 媒体资讯 / 爬虫采集，结合内部 ERP（OMS / WMS / SCM / CRM / FMS / BI）数据形成闭环
- **AI 中台服务化**：LLM 智能路由、RAG 混合检索、GraphRAG 知识图谱、Embedding 向量化，统一能力层供上层 Agent 调用
- **企业级平台治理**：多租户隔离、RBAC 权限、审计日志、数据脱敏、IP 白名单、Prompt 注入防护
- **多端交付**：Next.js 工作台、钉钉/企业微信/邮件通知、报告导出

***

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户接入层                                │
│   Web浏览器(Next.js 14) │ 移动端APP │ 企微/钉钉机器人 │ 数据大屏 │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                    网关层 (Kong Gateway)                         │
│   认证授权(JWT/OAuth2) │ 限流熔断 │ 路由灰度 │ 审计 │ IP白名单  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│              UI层 (Next.js 14 + Vue3 + ElementUI Plus)          │
│  选品工作台 │ Agent监控面板 │ RAG知识库管理 │ 报告中心 │ 系统管理  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│           API层 (FastAPI 异步RESTful + WebSocket)                │
│  /selection │ /agents │ /knowledge │ /reports │ /integration    │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│        AI Agent 编排层 (LangGraph + AutoGen + CrewAI + Dify)    │
│  SelectionMaster(总控) → 数据采集 → 市场洞察 → 产品规划 → 商业化 │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                   AI 中台 (统一能力层)                            │
│  llm-service │ rag-service │ agent-service │ embedding-service  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│              LLM 模型层 (轻量本地 + 商业，场景匹配)               │
│ Qwen2.5-1.5B(Ollama)  │ Qwen3.5-2B │ CPU本地模型 │ 商业API      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                    数据层                                        │
│  PostgreSQL │ Redis │ Qdrant │ OpenSearch │ Kafka │ 数据湖       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 业务闭环

```
外部数据源(Amazon/TikTok/1688/Google Trends/爬虫/RSS)
        │
        ▼
  数据采集与接入层 (API适配器 + 爬虫引擎 + RSS订阅器)
        │
        ├── 实时/批量 ──► Kafka / 数据湖
        │
内部ERP(CDC/API) ──► Kafka / 数据湖
  OMS │ WMS │ SCM │ CRM │ FMS │ BI
        │
        ▼
  数据处理层 (Flink/Spark)
        │
        ▼
  特征库 / 向量库 / 知识库
        │
        ▼
  Agent编排层 (数据采集→市场洞察→产品规划→商业化→报告)
        │
        ▼
  选品建议 / 风险结论 / 利润测算 / 报告
        │
        ▼
  运营采纳 → SCM创建采购单 / WMS预留库容 / OMS创建Listing
        │
        ▼
  执行结果回流 → 自进化闭环
```

***

## 3. 核心模块

### 3.1 AI Agent 编排层

| Agent               | 职责                      | 数据来源                                | 关键输出                       |
| ------------------- | ----------------------- | ----------------------------------- | -------------------------- |
| **SelectionMaster** | 总控协调，4阶段状态机编排           | 下游Agent结果                           | 决策输出（Go/No-Go/Conditional） |
| **数据采集Agent**       | 多源数据采集与质量检查             | Amazon/TikTok/1688/Google Trends/爬虫 | 标准化数据集 + 质量报告              |
| **市场洞察Agent**       | TAM/SAM/SOM估算、竞品格局、趋势识别 | 数据湖/特征库/OMS历史销量                     | 机会评分 + 趋势信号                |
| **产品规划Agent**       | 多模态分析、评论聚类、差异化定位        | Amazon评论/TikTok视频/CRM评价/RAG         | 产品规格 + 差异化评分               |
| **商业化Agent**        | 利润测算、动态定价、Go/No-Go决策    | 1688报价/FMS成本/SCM供应商/OMS价格弹性         | 利润测算 + 定价策略                |
| **风险评估Agent**       | 专利检索、媒体情感、合规检查          | GraphRAG/CRM/专利库                    | 风险清单 + 合规结论                |

### 3.2 AI 中台

| 服务                    | 职责                       | 技术实现                                    |
| --------------------- | ------------------------ | --------------------------------------- |
| **llm-service**       | 多模型路由、负载均衡、成本优化、降级策略     | LLM Gateway + Ollama + 熔断器              |
| **rag-service**       | 混合检索（向量+关键词）、Rerank精排、缓存 | Qdrant + OpenSearch + bge-reranker-base |
| **agent-service**     | Agent生命周期管理、任务调度、人工干预    | 异步任务队列 + 断点调试                           |
| **embedding-service** | BGE向量化、批量处理、增量更新         | Qdrant + 批量5000 QPS                     |

### 3.3 ERP 集成

| 系统      | 核心数据               | 交互方式        |
| ------- | ------------------ | ----------- |
| **OMS** | 订单明细、销量、退款记录、促销活动  | API + CDC推送 |
| **WMS** | 实时库存、库龄、周转率、库容利用率  | API         |
| **SCM** | 供应商信息、采购订单、物流跟踪    | API         |
| **CRM** | 客户评价、客诉记录、客户画像     | API + CDC推送 |
| **FMS** | 头程运费、关税、FBA费用、毛利率  | API         |
| **BI**  | 历史KPI、广告转化率、销售趋势报表 | API         |

***

## 4. 技术栈

### 4.1 后端

| 领域        | 技术                                              |
| --------- | ----------------------------------------------- |
| **Web框架** | FastAPI (Uvicorn) + WebSocket                   |
| **AI框架**  | LangGraph + AutoGen + CrewAI + Dify + LangChain |
| **异步任务**  | Celery + Ray Actor                              |
| **ORM**   | SQLAlchemy 2.0 (async) + Alembic                |
| **数据校验**  | Pydantic v2                                     |
| **消息队列**  | Kafka (aiokafka)                                |
| **流处理**   | Flink / Spark                                   |

### 4.2 数据存储

| 存储                 | 用途               |
| ------------------ | ---------------- |
| **PostgreSQL 14+** | 业务数据、用户、租户、审计日志  |
| **Redis 7.0+**     | 缓存、限流计数器、会话      |
| **Qdrant**         | 向量检索、Embedding存储 |
| **OpenSearch**     | 全文检索、日志聚合        |
| **Kafka**          | 事件流、CDC数据管道      |
| **MinIO**          | 对象存储、文件上传        |

### 4.3 AI / 模型

| 模型                    | 用途                                    |
| --------------------- | ------------------------------------- |
| **Qwen2.5-1.5B**      | 文本对话（Ollama GGUF量化）                   |
| **Qwen2.5-7B**        | 轻量查询                                  |
| **Phi-3-mini**        | 敏感词过滤 / 降级                            |
| **BGE-large**         | 文本向量化                                 |
| **bge-reranker-base** | 检索精排（纯CPU）                            |
| **Qwen3.5-2B**        | 多模态分析（商品主图 / 视频帧，Ollama `qwen3.5:2b`） |
| **Whisper tiny**      | 音频转录（纯CPU）                            |

### 4.4 前端

| 技术                        | 用途              |
| ------------------------- | --------------- |
| **Next.js 14**            | App Router, SSR |
| **Vue3 + ElementUI Plus** | 管理界面            |
| **ECharts**               | 数据可视化           |
| **TailwindCSS**           | 样式              |
| **WebSocket / SSE**       | 实时推送            |

### 4.5 基础设施

| 组件                       | 用途             |
| ------------------------ | -------------- |
| **Kong Gateway**         | API网关、认证、限流、灰度 |
| **Docker / K8s**         | 容器化部署          |
| **Prometheus + Grafana** | 监控告警           |
| **Alertmanager**         | 告警通知           |
| **Istio**                | 服务网格（生产环境）     |

***

## 5. 目录结构

```
pms/
├── src/                          # 后端源码
│   ├── agents/                   # AI Agent 模块
│   │   ├── selection_master.py   #   总控协调Agent（状态机）
│   │   ├── data_collection.py    #   数据采集Agent
│   │   ├── market_insight.py     #   市场洞察Agent
│   │   ├── product_planner.py    #   产品规划Agent
│   │   ├── commercial.py         #   商业化Agent
│   │   ├── human_in_loop.py      #   人工干预接口
│   │   └── framework_adapter.py  #   多框架适配层
│   ├── api/v1/endpoints/         # API 路由
│   │   ├── selection.py          #   选品任务接口
│   │   ├── agents.py             #   Agent管理接口
│   │   ├── knowledge.py          #   知识库接口
│   │   ├── reports.py            #   报告接口
│   │   ├── integration.py        #   ERP集成接口
│   │   ├── auth.py               #   认证接口
│   │   └── ...                   #   其他端点
│   ├── apps/                     # AI 中台独立服务
│   │   ├── llm_service.py        #   LLM路由服务
│   │   ├── rag_service.py        #   RAG检索服务
│   │   ├── agent_service.py      #   Agent管理服务
│   │   └── embedding_service.py  #   向量化服务
│   ├── config/                   # 配置管理
│   ├── core/                     # 核心基础能力
│   │   ├── auth.py               #   认证
│   │   ├── rbac.py               #   RBAC权限
│   │   ├── tenant.py             #   多租户
│   │   ├── data_masking.py       #   数据脱敏
│   │   ├── waf.py                #   IP白名单
│   │   ├── rate_limit.py         #   限流
│   │   └── tracing.py            #   链路追踪
│   ├── crawlers/                 # 爬虫模块
│   │   └── amazon.py             #   Amazon数据爬虫
│   ├── infrastructure/           # 基础设施接入
│   │   ├── database.py           #   PostgreSQL
│   │   ├── redis.py              #   Redis
│   │   ├── qdrant.py             #   Qdrant向量库
│   │   ├── kafka.py              #   Kafka消息队列
│   │   ├── llm_gateway.py        #   LLM智能路由
│   │   ├── hybrid_retrieval.py   #   混合检索
│   │   ├── graph_rag.py          #   GraphRAG
│   │   ├── oms_client.py         #   OMS客户端
│   │   ├── wms_client.py         #   WMS客户端
│   │   ├── scm_client.py         #   SCM客户端
│   │   ├── crm_client.py         #   CRM客户端
│   │   ├── fms_client.py         #   FMS客户端
│   │   ├── bi_client.py          #   BI客户端
│   │   ├── dingtalk_client.py    #   钉钉通知
│   │   ├── wechat_client.py      #   企业微信通知
│   │   ├── email_client.py       #   邮件通知
│   │   └── ...                   #   其他基础设施
│   ├── models/                   # ORM / Schema
│   ├── services/                 # 业务服务层
│   │   ├── selection_service.py  #   选品任务服务
│   │   ├── erp_integration_service.py  # ERP集成服务
│   │   ├── external_signal_service.py  # 外部信号服务
│   │   ├── channel_delivery_service.py # 多通道交付服务
│   │   ├── graph_rag_service.py  #   GraphRAG服务
│   │   └── ...                   #   其他服务
│   └── main.py                   # 应用入口
├── frontend/                     # 前端源码
│   ├── app/                      # Next.js App Router
│   │   ├── page.tsx              #   首页/选品工作台
│   │   ├── agents/page.tsx       #   Agent监控面板
│   │   ├── knowledge/page.tsx    #   RAG知识库管理
│   │   ├── reports/page.tsx      #   报告中心
│   │   ├── dashboard/page.tsx    #   数据大屏
│   │   └── operations/page.tsx   #   运维管理
│   ├── components/               # 公共组件
│   └── lib/                      # 工具库
├── tests/                        # 测试
├── k8s/                          # Kubernetes 部署清单
│   ├── gateway/                  #   Kong网关配置
│   └── overlays/                 #   多环境Overlay
├── scripts/                      # 运维脚本
├── docs/                         # 文档
├── artifacts/                    # 构建产物
│   └── erp_local/                #   ERP本地真实样本
├── docker-compose.yml            # Docker编排
├── Dockerfile                    # 容器镜像
├── pyproject.toml                # 依赖管理
└── .env.example                  # 环境变量模板
```

## 6. 环境入口

- 本地开发 / 本地验收：`D:/Project/fms/docs/local-runtime/README.md`
- 多环境规划（`local` / `dev` / `prod`）：`D:/Project/fms/docs/environments/README.md`

***

## 6. 运行要求

### 6.1 必需

| 依赖         | 版本    | 用途       |
| ---------- | ----- | -------- |
| Python     | 3.11+ | 后端运行时    |
| PostgreSQL | 14+   | 业务数据存储   |
| Redis      | 7.0+  | 缓存/限流/会话 |

### 6.2 推荐

| 依赖             | 版本    | 用途         |
| -------------- | ----- | ---------- |
| Qdrant         | 1.7+  | 向量检索       |
| Kafka          | 3.6+  | 消息队列 / CDC |
| OpenSearch     | 2.11+ | 全文检索       |
| Docker Desktop | 最新    | 容器化运行      |
| WSL2           | 最新    | Linux容器支持  |
| Node.js        | 18+   | 前端构建       |

### 6.3 可选（生产环境）

| 依赖                   | 用途    |
| -------------------- | ----- |
| Kong Gateway         | API网关 |
| Prometheus + Grafana | 监控告警  |
| vLLM / Triton        | 模型推理  |
| MinIO                | 对象存储  |

***

## 7. 快速开始

### 7.1 本地开发

```bash
# 1. 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # Linux/Mac

# 2. 安装依赖
pip install .

# 3. 配置环境变量
copy .env.example .env
# 编辑 .env 文件，填入数据库连接等配置

# 4. 查看本地运行摘要与配置校验
python scripts/local_runtime_manager.py summary
python scripts/local_runtime_manager.py check --probes
python scripts/run_local_pilot_acceptance.py

# 5. 安装或刷新 Python 依赖
python scripts/install_python_deps.py --run-check

# 6. 检查宿主机软件（Docker / WSL；按需附带 Node / Ollama）
python scripts/install_local_software.py
# python scripts/install_local_software.py --include-node

# 7. 启动本地依赖服务
python scripts/start_local_services.py
# python scripts/start_local_services.py --with-ollama
# python scripts/start_local_services.py --with-platform

# 8. 启动后端（依赖服务启动后）
scripts\start_local.ps1           # Windows PowerShell
# ./scripts/start_local.sh        # Linux / WSL

# 等价的 Compose 口径
# docker compose -f docker-compose.yml up -d --build --no-deps app

# 9. 启动前端（另一个终端）
cd frontend
npm install
npm run dev
```

### 7.2 Docker Compose

```bash
# 手工方式：启动基础设施
# 推荐优先使用 python scripts/start_local_services.py
docker compose up -d

# 手工方式：只重建并启动后端容器
docker compose up -d --build --no-deps app

# 查看服务状态
docker compose ps

# 停止基础设施
docker compose down
```

### 7.3 访问地址

> 本地 `local-real` 场景下，如果启用了 `docker-compose.wsl-local.yml` 的 Kong：
>
> - 代理入口仍是 `http://localhost:8000`
> - FastAPI 直连入口是 `http://localhost:18000`
>
> 详细说明见 `docs/local-runtime/`

| 服务               | 地址                              |
| ---------------- | ------------------------------- |
| 前端工作台            | <http://localhost:3000>         |
| API 文档 (Swagger) | <http://localhost:18000/docs>   |
| API 文档 (ReDoc)   | <http://localhost:18000/redoc>  |
| 健康检查             | <http://localhost:18000/health> |
| 就绪检查             | <http://localhost:18000/ready>  |
| 存活检查             | <http://localhost:18000/live>   |

***

## 8. 配置说明

### 8.1 环境变量

项目通过 `.env` 文件管理环境变量，主要前缀：

| 前缀               | 用途         | 示例                                                     |
| ---------------- | ---------- | ------------------------------------------------------ |
| `APP_`           | 应用配置       | `APP_NAME`, `APP_ENVIRONMENT`                          |
| `DB_`            | PostgreSQL | `DB_URL`, `DB_POOL_SIZE`                               |
| `REDIS_`         | Redis      | `REDIS_URL`                                            |
| `QDRANT_`        | Qdrant     | `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_URL`             |
| `KAFKA_`         | Kafka      | `KAFKA_BOOTSTRAP_SERVERS`                              |
| `SEC_`           | 安全         | `SEC_SECRET_KEY`                                       |
| `LLM_`           | LLM        | `LLM_PRIMARY_MODEL`, `LLM_OLLAMA_ENDPOINT`             |
| `LOCAL_RUNTIME_` | 本地运行模式     | `LOCAL_RUNTIME_PROFILE`, `LOCAL_RUNTIME_SCENARIO_MODE` |
| `SERVICE_MODE_`  | 服务化模式      | `SERVICE_MODE_LLM_MODE`, `SERVICE_MODE_LLM_BASE_URL`   |
| `DINGTALK_`      | 钉钉         | `DINGTALK_WEBHOOK_URL`                                 |
| `WECHAT_`        | 企业微信       | `WECHAT_WEBHOOK_URL`                                   |
| `SMTP_`          | 邮件         | `SMTP_SERVER`, `SMTP_PORT`                             |

### 8.2 依赖管理

统一以 `pyproject.toml` 为单一依赖源，不再使用 `requirements.txt`。

***

## 9. 测试

```bash
# 运行核心回归测试
python -m pytest tests/test_api_integration.py tests/test_minimal_trusted_phase34.py -q

# 运行全部测试
python -m pytest -q

# 语法检查
python -m py_compile src/main.py

# 代码规范检查
ruff check src tests

# 类型检查
mypy src
```

***

## 10. 当前实现状态

> 详细差距分析见 [20260414差异分析报告.md](20260414差异分析报告.md)

### 10.1 已实现

| 能力                                        | 状态    |
| ----------------------------------------- | ----- |
| FastAPI 应用入口 + 生命周期管理                     | ✅ 已实现 |
| 选品任务 API + SelectionMaster 状态机编排          | ✅ 已实现 |
| 5 大 Agent 核心逻辑（数据采集/市场洞察/产品规划/商业化/报告）     | ✅ 已实现 |
| LLM Gateway 智能路由（多模型/熔断器/降级）              | ✅ 已实现 |
| RAG 混合检索 + GraphRAG 知识图谱                  | ✅ 已实现 |
| 多租户隔离 + RBAC + 审计日志                       | ✅ 已实现 |
| 数据脱敏 + IP 白名单 + Prompt 注入防护               | ✅ 已实现 |
| 多通道消息交付（钉钉/企业微信/邮件）                       | ✅ 已实现 |
| ERP 客户端（OMS/WMS/SCM/CRM/FMS/BI）           | ✅ 已实现 |
| Amazon 爬虫框架 + 反爬策略                        | ✅ 已实现 |
| 外部信号服务（Wikipedia/GitHub/HackerNews 真实API） | ✅ 已实现 |
| Next.js 前端工作台（多页面）                        | ✅ 已实现 |
| PostgreSQL / Redis / Qdrant / Kafka 客户端   | ✅ 已实现 |
| Docker Compose 编排                         | ✅ 已实现 |
| Kong 网关配置 + K8s 部署清单                      | ✅ 已实现 |

### 10.2 待完善（目标态）

| 能力             | 当前状态        | 目标                                                 |
| -------------- | ----------- | -------------------------------------------------- |
| 真实外部 API 集成    | 模拟数据为主      | Amazon SP-API / TikTok / 1688 / Google Trends 真实调用 |
| 爬虫系统           | Amazon 单一爬虫 | Scrapy/Playwright 完整爬虫平台 + 代理IP池                   |
| LangGraph 框架集成 | 自研状态机       | 迁移到 LangGraph + AutoGen/CrewAI 多框架协作               |
| 流处理管道          | 未实现         | Flink/Spark 特征工程 + 实时处理                            |
| ERP 真实对接       | 本地样本联调      | staging HTTP 真实系统联调                                |
| 前端完整工作台        | 基础页面        | Agent 监控面板 + RAG 知识库管理 + 完整报告中心                    |
| vLLM 集群        | 模拟模式        | 真实推理集群部署                                           |
| 监控仪表板          | 配置文件        | Grafana 仪表板 + 告警规则                                 |

***

## 11. 相关文档

### 设计文档

| 文档                                                          | 说明        |
| ----------------------------------------------------------- | --------- |
| [跨境电商AI选品系统PMS—架构与业务设计文档.md](跨境电商AI选品系统PMS—%20架构与业务设计文档.md) | 技术栈与架构基准  |
| [跨境电商AI选品系统---分层架构与数据流协作.md](跨境电商AI选品系统---分层架构与数据流协作.md)    | 业务流与数据流基准 |
| [选品系统设计方案.md](选品系统设计方案.md)                                  | 原始设计方案    |

### 分析报告

| 文档                                       | 说明     |
| ---------------------------------------- | ------ |
| [20260414差异分析报告.md](20260414差异分析报告.md)   | 最新差距分析 |
| [本地环境准备-详解安装部署使用.md](本地环境准备-详解安装部署使用.md) | 环境搭建指南 |

### 运维文档

| 文档                                       | 说明      |
| ---------------------------------------- | ------- |
| [docs/architecture/](docs/architecture/) | 架构设计文档集 |
| [docs/deliverables/](docs/deliverables/) | 交付物文档集  |
| [docs/phase4/](docs/phase4/)             | 上线阶段文档集 |

***

## 12. License

Private — Internal Use Only
