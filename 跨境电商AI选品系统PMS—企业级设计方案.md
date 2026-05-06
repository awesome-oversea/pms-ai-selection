## 跨境电商AI选品系统PMS——企业级终极设计方案

> 文档口径说明：本文件用于描述**目标态 / 规划态企业级蓝图**，默认不代表当前仓库源码已全部落地。
> 当前实现边界请以 `docs/当前系统能力边界.md` 为准；当前阶段验收请以 `tasks/验收标准/阶段验收清单.md` 为准。
>
> 本方案深度融合您现有的 **OMS / WMS / SCM / CRM / FMS / BI / PaaS**、**AutoGen4j / LangGraph4j / LlamaIndex** 以及 **API集成平台（200+企业）**，将AI选品从“工具”升级为驱动全链路的**利润中枢系统**。方案已整合 **Amazon / TikTok / Google Trends / 1688 / 媒体资讯** 等多源外部数据，并在Agent层全面集成 **LangChain**（快速原型与辅助编排），形成真正的企业级决策闭环。

***

## 附：完整技术栈清单（已包含 AutoGen + LangGraph + LangChain）

| 层级           | 技术组件                                 | 说明                             |
| :----------- | :----------------------------------- | :----------------------------- |
| **前端/UI**    | Next.js 14 (App Router)              | 主框架，SSR优化首屏                    |
| <br />       | Vue3 + ElementUI Plus                | 后台管理组件库                        |
| <br />       | React (部分)                           | 复杂交互组件                         |
| <br />       | WebSocket / SSE                      | 实时推送（Agent流式输出、看板刷新）           |
| <br />       | ECharts                              | 数据可视化（趋势图、榜单）                  |
| **网关**       | Kong Gateway                         | API网关，认证/限流/路由/灰度              |
| **后端/API**   | FastAPI                              | 异步RESTful API服务                |
| <br />       | Flask（辅助）                            | 轻量内部服务                         |
| <br />       | WebSocket                            | 双向通信                           |
| **Agent框架**  | **LangChain**                        | 快速原型、链式调用、工具集成（Python）         |
| <br />       | **AutoGen**                          | 多Agent对话、代码生成（Python版）           |
| <br />       | **LangGraph**                        | 有状态工作流、条件分支、循环（Python版，状态机核心）    |
| <br />       | Dify                                 | 低代码Agent编排、Prompt调优            |
| <br />       | CrewAI                               | 角色化顺序任务（批量竞品分析）                |
| **AI应用平台**   | Dify                                 | 流程编排 + 内置RAG管道                 |
| <br />       | Langflow（可选）                         | 可视化RAG流水线                      |
| **推理引擎**     | vLLM                                 | 多节点分布式推理（主模型）                  |
| <br />       | Triton Inference Server              | 高性能推理（Rerank、多模态）              |
| <br />       | Ollama                               | 轻量模型边缘部署                       |
| <br />       | TGI（备用）                              | Hugging Face TGI               |
| **模型**       | Qwen2.5-72B / DeepSeek-V3            | 主LLM（Agent推理、报告生成）             |
| <br />       | BGE-large-zh                         | Embedding模型（文本向量化）             |
| <br />       | bge-reranker-v2                      | Rerank模型（检索精排）                 |
| <br />       | LLaVA-13B                            | 多模态（商品主图/TikTok视频分析）           |
| <br />       | Whisper                              | 音频转录（TikTok视频音频）               |
| <br />       | Phi-3-mini                           | 轻量模型（敏感词过滤、简单分类）               |
| **向量数据库**    | Qdrant                               | 主库，实时检索，HNSW/IVF\_FLAT         |
| <br />       | Milvus                               | 辅助库，十亿级离线批量                    |
| <br />       | Chroma（可选）                           | 原型测试                           |
| **RAG编排**    | **LlamaIndex**                     | RAG流水线编排（Python版）                |
| <br />       | LangChain（辅助）                        | 原型验证、快速RAG搭建                   |
| **缓存/消息**    | Redis                                | 热向量缓存、会话状态、限流计数器               |
| <br />       | Kafka                                | 消息队列（统一数据接入）                   |
| **数据处理**     | Flink                                | 实时流处理（清洗、情感标注）                 |
| <br />       | Spark                                | 批处理（每日聚合、特征计算）                 |
| <br />       | Pandas / Dask                        | 辅助数据分析                         |
| **数据湖/存储**   | Iceberg + Hudi                       | 数据湖（ODS层，全量历史）                 |
| <br />       | PostgreSQL                           | 关系数据库（业务数据、配置、审计）              |
| <br />       | Elasticsearch                        | 关键词索引（BM25检索）                  |
| **ETL/调度**   | Kettle                               | ETL工具（抽取供应商/财务数据）              |
| <br />       | Ray                                  | 分布式计算、vLLM Actor管理、并行Embedding |
| <br />       | Airflow                              | 工作流编排（定时任务）                    |
| <br />       | Prefect                              | 事件驱动（异常触发）                     |
| **基础设施**     | Kubernetes                           | 容器编排（多AZ部署）                    |
| <br />       | Docker                               | 容器化                            |
| <br />       | Prometheus + Grafana                 | 监控与可视化                         |
| <br />       | EFK (Elasticsearch+Fluentd+Kibana)   | 日志收集与全链路追踪                     |
| <br />       | Istio（可选）                            | 服务网格（灰度、熔断）                    |
| **ERP/内部系统** | OMS                                  | 订单管理系统（销量、转化）                  |
| <br />       | WMS                                  | 仓储管理系统（库存、库龄）                  |
| <br />       | SCM                                  | 供应链管理系统（成本、供应商）                |
| <br />       | CRM                                  | 客户关系管理（评价、客诉）                  |
| <br />       | FMS                                  | 财务管理系统（利润、广告）                  |
| <br />       | BI                                   | 商业智能（报表、趋势）                    |
| <br />       | PMS                                  | 产品管理系统（产品定义）                   |
| <br />       | CMS                                  | 内容管理系统（Listing）                |
| **集成平台**     | API集成平台（200+企业）                      | 统一对接内外部API                     |
| **外部数据源**    | Amazon SP-API                        | 商品BSR、价格、评论、销量                 |
| <br />       | TikTok Shop API                      | 商品热度、视频互动、标签                   |
| <br />       | Google Trends API                    | 搜索热度、地域分布                      |
| <br />       | 1688 Open API                        | 商品价格、MOQ、供应商评分                 |
| <br />       | 媒体资讯RSS/API                          | 行业新闻、政策法规                      |
| **开发工具**     | Jupyter / VSCode / Cursor / Continue | 开发、调试、AI辅助编程                   |
| **UI原型**     | Gradio / Streamlit                   | 快速原型验证                         |

***

## 一、系统定位与核心价值

### 1.1 定位升级

| 传统 PMS | AI选品系统（本方案）    |
| :----- | :------------- |
| 记录商品   | **决定做什么商品**    |
| 被动响应   | **主动决策**       |
| 孤岛系统   | **嵌入ERP操作系统**  |
| 经验驱动   | **数据 + AI 驱动** |

### 1.2 在企业架构中的位置

text

```
                    ┌─────────────────────────────────┐
                    │       AI选品中枢                  │
                    │    (Selection Hub)               │  ← 利润入口
                    └───────────────┬─────────────────┘
                                    │ 驱动
        ┌───────────────┬───────────┼───────────┬───────────────┐
        ▼               ▼           ▼           ▼               ▼
   ┌────────┐      ┌────────┐  ┌────────┐  ┌────────┐      ┌────────┐
   │  PMS   │ ──→  │  SCM   │─→│  WMS   │─→│  OMS   │ ──→  │  CRM   │
   └────────┘      └────────┘  └────────┘  └────────┘      └────────┘
        │               │           │           │               │
        └───────────────┴───────────┴───────────┴───────────────┘
                                    │
                                    ▼
                              ┌──────────┐
                              │   FMS   │ → BI
                              └──────────┘
```

**闭环链路**：选品决策 → 产品定义 → 采购备货 → 仓储物流 → 销售履约 → 客户反馈 → 利润核算 → 反哺AI → 形成自进化飞轮。

### 1.3 核心价值指标

| 指标    | 传统方式    | AI选品系统 | 提升幅度      |
| :---- | :------ | :----- | :-------- |
| 选品效率  | 2\~4周/款 | 4小时/款  | **↑ 90%** |
| 爆款命中率 | \~60%   | ≥85%   | **↑ 35%** |
| 决策周期  | 周级      | 分钟级    | **↓ 95%** |
| 人工成本  | 3\~5人   | 0.5人   | **↓ 60%** |
| 系统可用性 | —       | 99.9%  | —         |

***

## 二、总体架构（全栈融合版）

### 2.1 七层架构图（最终版）

text

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 用户接入层：浏览器（Web） │ 移动App │ 企业微信机器人 │ 钉钉 │ Slack                               │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 网关层：Kong Gateway（集群）—— 认证 │ 限流 │ 路由 │ 日志聚合 │ 灰度发布                           │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ UI层：Next.js（SSR） + Vue3 + ElementUI Plus + WebSocket/SSE                                    │
│   ├── 选品工作台（任务创建、实时看板、ECharts趋势图）                                            │
│   ├── Agent监控（LangGraph4j可视化，断点调试，Human-in-the-loop）                                │
│   ├── RAG知识库管理（内外部文档上传、切片预览、向量检索测试）                                    │
│   └── 报告中心（PDF/Excel/PPT 导出，一键分享至企业微信/钉钉）                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Agent层：LangChain + AutoGen4j + LangGraph4j + Dify + CrewAI                                    │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐ │
│   │                         Selection Master Agent（总控）                                    │ │
│   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                    │ │
│   │  │ 数据采集Agent │→│ 市场洞察Agent │→│ 产品规划Agent │→│ 商业化Agent   │                    │ │
│   │  │ (爬虫/API/    │ │ (Jaxx模式)    │ │ (Jobs模式)    │ │ (Pony模式)    │                    │ │
│   │  │  Kafka/Flink) │ │ Google Trends│ │ LLaVA/评论聚类│ │ 利润测算/定价 │                    │ │
│   │  │  Amazon/TikTok│ │ 供需比/生命周期│ │ 竞品分析/痛点 │ │ ROI/备货计划  │                    │ │
│   │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘                    │ │
│   │          ↑                 ↑                 ↑                 ↑                        │ │
│   │      (并行执行)   Ray Actor / CompletableFuture  (工具调用：1688/SCM/FMS/专利库)        │ │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘ │
│   辅助能力：LangChain（快速原型、链式调用）、AutoGen（A/B测试代码生成）、CrewAI（批量竞品分析子任务）│
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ API层：FastAPI（异步RESTful）+ WebSocket                                                        │
│   ├── /api/v1/selection    （选品任务创建/状态查询）                                            │
│   ├── /api/v1/agents       （Agent触发/停止/人工干预）                                          │
│   ├── /api/v1/knowledge    （RAG混合检索/知识入库）                                             │
│   ├── /api/v1/reports      （报告生成/下载/分享）                                               │
│   └── /api/v1/integration  （对接SCM/OMS/CRM/FMS及外部数据源网关）                              │
│   OpenAPI文档自动生成，集成Kong限流鉴权，全链路Trace ID注入                                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AI中台：统一能力层                                                                              │
│   ├── llm-service      （多模型路由：vLLM/Triton/Ollama，按任务复杂度降本30%+）                 │
│   ├── rag-service      （混合检索 + GraphRAG）                                                  │
│   ├── agent-service    （Agent生命周期管理）                                                    │
│   └── embedding-service（BGE向量化，5000 QPS）                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 推理层：vLLM（多节点分布式，TP+PP并行，Prefix Caching）+ Triton + Ollama + TGI                   │
│   ├── 主模型：Qwen2.5-72B / DeepSeek-V3（Agent推理、报告生成）                                  │
│   ├── Embedding：BGE-large-zh（实时向量化）                                                     │
│   ├── Rerank：bge-reranker-v2（精排延迟<20ms）                                                  │
│   └── 多模态：LLaVA-13B（商品主图/TikTok视频分析）+ Whisper（音频转录）                          │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ RAG层：Qdrant（主库，实时检索）+ Milvus（辅助，十亿级离线）+ Elasticsearch + LlamaIndex        │
│   ├── 混合检索：语义向量（Qdrant）+ 关键词BM25（ES）→ RRF融合 → BGE-reranker → LLM              │
│   ├── GraphRAG：供应商关系图谱、品类关联、新闻事件传播、专利侵权路径                             │
│   └── Redis缓存：热向量、Agent会话状态、限流计数器                                               │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 数据中台：Kafka + Flink + Spark + Iceberg + PostgreSQL + Feast                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ 外部数据源                         内部ERP系统                                           │   │
│   │ ├── Amazon API (BSR/价格/评论)     ├── SCM (成本/供应商)                                 │   │
│   │ ├── TikTok Shop API (热度/视频)    ├── OMS (销量/转化)                                   │   │
│   │ ├── Google Trends (搜索热度)       ├── WMS (库存)                                        │   │
│   │ ├── 1688 API (成本/MOQ)            ├── CRM (评价/客诉)                                   │   │
│   │ └── 媒体资讯RSS (新闻/政策)        ├── FMS (利润/广告)                                   │   │
│   │                                    └── BI (报表/趋势)                                    │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────┘   │
│   实时管道：采集 → Kafka (多topic) → Flink（清洗、去重、情感标注）→ Iceberg（ODS）                │
│            ↓ 同时触发                                                                           │
│         Qdrant（向量化同步）←→ Spark（每日聚合：BSR变化率、价格波动、评论趋势）                  │
│            ↓                                                                                    │
│         PostgreSQL（ADS层）+ Elasticsearch（关键词索引）                                        │
│   特征存储：Feast（销量增长率、评论情绪、Google热度、竞争强度、供应稳定性、新闻情感等）           │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 调度层：Ray（实时分布式计算 / vLLM Actor管理 / 并行Embedding）                                  │
│        + Airflow（定时工作流：每日数据同步ETL、周度选品报告、模型微调）                          │
│        + Prefect（事件驱动：Kafka堆积扩容、新品爆增自动分析、Google Trends突变触发、评论/新闻异常预警）│
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 基础设施层：Kubernetes（多AZ部署，GPU调度：NVIDIA Device Plugin + MIG）                         │
│            Docker + Prometheus（指标采集）+ Grafana（业务+技术看板）                             │
│            EFK（全链路Trace ID日志）+ Istio（可选，灰度/熔断）                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心升级点

| 能力    | 传统方案  | 本方案                                                                                  |
| :---- | :---- | :----------------------------------------------------------------------------------- |
| Agent | 流程编排  | **多框架融合：LangChain（原型/链式）+ AutoGen4j（对话）+ LangGraph4j（状态机）+ Dify（低代码）+ CrewAI（任务分解）** |
| RAG   | 简单检索  | **企业知识中枢 + GraphRAG**                                                                |
| 数据    | ETL管道 | **数据中台 + 特征存储**                                                                      |
| AI    | 单一模型  | **多模型路由 + 成本优化**                                                                     |
| 系统    | 孤立工具  | **嵌入ERP操作系统**                                                                        |

***

## 三、核心模块设计（微服务 + ERP深度融合 + 外部数据）

### 3.1 AI选品中枢微服务（Selection Hub）

| 服务名                       | 职责                     | 依赖数据源                               |
| :------------------------ | :--------------------- | :---------------------------------- |
| `selection-service`       | 选品任务创建、状态管理、流程编排       | LangGraph4j                         |
| `product-insight-service` | 市场洞察、趋势分析、供需比计算        | Amazon, TikTok, Google Trends, 内部BI |
| `competitor-service`      | 竞品监控、价格/评论变化跟踪         | Amazon, TikTok API                  |
| `profit-service`          | 利润测算、定价优化、ROI预测        | 1688 API（成本）, FMS                   |
| `supply-service`          | 供应链能力评估、交期/成本分析        | 1688 API, SCM                       |
| `risk-service`            | 合规检查、IP侵权预警、差评风险       | 媒体资讯, 外部专利库, RAG                    |
| `strategy-service`        | 产品定义、差异化建议、组合创新        | 所有外部数据 + CMS                        |
| `report-service`          | 多格式报告生成（PDF/Excel/PPT） | 所有上游                                |

### 3.2 与现有ERP及外部系统的数据集成矩阵

| 系统/数据源            | 输入数据（AI读取）     | 输出动作（AI触发）    |
| :---------------- | :------------- | :------------ |
| **Amazon API**    | BSR排名、价格、评论、销量 | 竞品定价策略、选品机会评分 |
| **TikTok API**    | 视频互动、标签热度、达人数据 | 社交趋势权重、爆款标签推荐 |
| **Google Trends** | 搜索热度、地域趋势      | 需求预测、季节性调整    |
| **1688 API**      | 产品价格、MOQ、供应商评分 | 成本测算、采购建议     |
| **媒体资讯**          | 行业新闻、政策法规      | 风险预警、知识库更新    |
| **SCM**           | 产品成本、供应商交期     | 自动询价、生成采购单    |
| **WMS**           | 库存周转率、仓储容量     | 选品时校验库存能力     |
| **OMS**           | 历史销量、转化率       | 销量预测、特征提取     |
| **CRM**           | 用户评价、客诉        | 痛点挖掘、情感分析     |
| **FMS**           | 利润结构、广告ROI     | 利润测算、定价推荐     |
| **BI**            | 品类趋势、市场份额      | 选品效果归因        |

**集成方式**：通过已有 **API集成平台（200+企业）** 统一接入，Kong网关统一鉴权和限流。

***

## 四、Multi-Agent 系统（决策引擎）

### 4.1 技术组合选型

| 框架            | 角色                  | 理由                       |
| :------------ | :------------------ | :----------------------- |
| **LangChain** | 快速原型、链式调用、工具集成      | Python生态丰富，适合快速验证和轻量级任务链 |
| **AutoGen**   | 多Agent对话、代码生成       | Python原生，与现有系统无缝集成         |
| **LangGraph** | 有状态工作流、条件分支、循环      | 状态机天然适配选品四阶段             |
| **Dify**      | 低代码Agent编排、Prompt调优 | 业务人员可快速调整                |
| **CrewAI**    | 角色化顺序任务             | 批量竞品分析、子任务分解             |

### 4.2 Agent分层体系（最终版）

text

```
                        Selection Master Agent（总控）
                                   │
        ┌──────────────┬───────────┼───────────┬──────────────┐
        ▼              ▼           ▼           ▼              ▼
   ┌─────────┐   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ Data    │   │ Market  │  │Competitor│ │ Profit  │  │ Supply  │
   │ Agent   │   │ Agent   │  │ Agent    │  │ Agent   │  │ Agent   │
   │(所有源) │   │(Google  │  │(Amazon/  │  │(1688/   │  │(SCM/    │
   │         │   │ Trends) │  │ TikTok)  │  │ FMS)    │  │1688)    │
   └─────────┘   └─────────┘  └─────────┘  └─────────┘  └─────────┘
        │              │            │           │            │
        └──────────────┴────────────┼───────────┴────────────┘
                                    ▼
                           ┌─────────────────┐
                           │ Product Agent    │ （产品定义）
                           └────────┬────────┘
                                    ▼
                           ┌─────────────────┐
                           │ Risk Agent       │ （媒体资讯/专利）
                           └────────┬────────┘
                                    ▼
                           ┌─────────────────┐
                           │ Commercial Agent │ （商业化决策）
                           └────────┬────────┘
                                    ▼
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Listing  │   │ Report   │   │ Test     │
              │ Agent    │   │ Agent    │   │ Agent    │
              └──────────┘   └──────────┘   └──────────┘
```

### 4.3 LangGraph4j 状态机实现（核心代码）

java

```
StateGraph<SelectionState> graph = new StateGraph<>();

graph.addNode("data_collection", new DataAgent());
graph.addNode("market_analysis", new MarketAgent());
graph.addNode("parallel_analysis", new ParallelAnalysisNode()); // 内部并行
graph.addNode("product_definition", new ProductAgent());
graph.addNode("risk_assessment", new RiskAgent());
graph.addNode("commercial_decision", new CommercialAgent());
graph.addNode("report_generation", new ReportAgent());

graph.setEntryPoint("data_collection");
graph.addEdge("data_collection", "market_analysis");
graph.addConditionalEdge("market_analysis", state -> 
    state.hasOpportunity() ? "parallel_analysis" : END);
graph.addEdge("parallel_analysis", "product_definition");
graph.addEdge("product_definition", "risk_assessment");
graph.addEdge("risk_assessment", "commercial_decision");
graph.addEdge("commercial_decision", "report_generation");

// 并行执行内部实现（Ray Actor + CompletableFuture）
CompletableFuture.allOf(
    marketFuture, competitorFuture, profitFuture, supplyFuture
).join();
```

**状态持久化**：使用 Redis 存储 checkpoint，支持断点续跑和人工干预。

### 4.4 Tool调用体系（连接现实世界）

| Agent            | 调用的工具/API                                              |
| :--------------- | :----------------------------------------------------- |
| Market Agent     | Amazon Product API, TikTok Trends, Google Trends, 内部BI |
| Competitor Agent | Keepa API, 爬虫引擎, 价格追踪服务                                |
| Profit Agent     | `finance-service`（FMS）, 广告成本API                        |
| Supply Agent     | `supplier-service`（SCM）, 1688 API                      |
| Risk Agent       | 专利检索API, 合规数据库, 媒体资讯RSS                                |

### 4.5 Human-in-the-loop

- **关键决策点**：当 ROI 预测低于阈值（如 <15%），或风险评分过高时，暂停流程，推送至前端等待人工审批。
- **人工干预能力**：支持修改产品定义、调整利润权重、驳回选品建议。
- **审计日志**：所有人工操作与 Agent 决策一并记录，存储至 Iceberg 审计表，保留180天。

***

## 五、RAG 知识系统（企业记忆与壁垒）

### 5.1 知识来源（内外部统一）

| 来源                | 内容类型            | 用途        |
| :---------------- | :-------------- | :-------- |
| **OMS**           | 历史爆款SKU、销量序列    | 爆款模式挖掘    |
| **CRM**           | 用户评论、客诉、评分      | 痛点聚类、情感分析 |
| **SCM**           | 供应商档案、质量评分      | 供应链风险评估   |
| **FMS**           | 产品利润表、广告ROI     | 利润测算基准    |
| **BI**            | 品类趋势、市场份额       | 宏观洞察      |
| **Amazon/TikTok** | 竞品榜单、评论、视频      | 市场热度、竞品分析 |
| **Google Trends** | 关键词搜索趋势         | 需求预测、蓝海发现 |
| **1688**          | 商品价格、供应商数据      | 成本结构、货源评估 |
| **媒体资讯**          | 行业新闻、政策法规、KOL评测 | 风险预警、趋势捕捉 |

### 5.2 混合检索架构（LlamaIndex + LangChain + Qdrant + ES）

text

```
用户Query: "适合欧洲站夏季的户外储能电源，要求轻便、高转化"
        │
        ├── 语义检索 (Qdrant, BGE向量) → Top100
        └── 关键词检索 (ES, BM25) → Top100
                │
                └── RRF融合 → Top50
                        │
                        └── BGE-reranker-v2 → Top10
                                │
                                └── 注入LLM上下文 → 生成回答（附来源）
```

**LangChain 辅助**：在原型阶段使用 LangChain 的 `RetrievalQA` 链快速验证检索效果，生产环境迁移至 LlamaIndex。

### 5.3 向量数据库设计

| Collection         | 向量维度 | 索引类型      | 用途                       | 分区策略   |
| :----------------- | :--- | :-------- | :----------------------- | :----- |
| `product_vectors`  | 1024 | HNSW      | 商品语义检索（含Amazon/TikTok商品） | 按平台分区  |
| `review_vectors`   | 768  | IVF\_FLAT | 评论情感/痛点                  | 按月分区   |
| `trend_vectors`    | 512  | HNSW      | Google Trends时序特征        | 按关键词分区 |
| `supplier_vectors` | 768  | IVF\_FLAT | 1688供应商能力匹配              | 按品类分区  |
| `news_vectors`     | 1024 | HNSW      | 媒体资讯、行业报告                | 按时间分区  |
| `knowledge_base`   | 1024 | HNSW      | 专利、合规文档、内部手册             | 按租户分区  |

### 5.4 GraphRAG（进阶能力）

利用知识图谱整合内外部数据：

- **节点类型**：品类、商品、供应商、竞品、专利、新闻事件、趋势词
- **边类型**：竞争、供应、侵权、提及、关联
- **典型查询**：

  cypher
  ```
  MATCH (t:TrendWord)-[:MENTIONED_IN]->(n:News)
  WHERE t.name = '储能电源' AND n.published > date('2025-01-01')
  RETURN n.title, n.sentiment
  ```
- **应用场景**：新闻情绪对品类的影响分析、专利侵权路径发现、趋势词扩散追踪。

***

## 六、推理层（高并发 & 成本优化）

### 6.1 多模型架构

| 模型类型      | 模型实例                      | 部署引擎              | 实例数       | 用途              |
| :-------- | :------------------------ | :---------------- | :-------- | :-------------- |
| 主LLM      | Qwen2.5-72B / DeepSeek-V3 | vLLM (TP=4, PP=2) | 4节点×8 GPU | Agent推理、报告生成    |
| Embedding | BGE-large-zh              | vLLM              | 2节点       | 实时向量化（5000 QPS） |
| Rerank    | bge-reranker-v2           | Triton            | 1节点       | 检索精排（<20ms）     |
| 多模态       | LLaVA-13B                 | Triton            | 2节点       | 商品主图、TikTok视频分析 |
| 轻量        | Phi-3-mini                | Ollama            | 边缘节点      | 敏感词过滤、简单分类      |

### 6.2 vLLM 多节点优化策略

- **并行策略**：张量并行（TP=4） + 流水线并行（PP=2）支持超大模型
- **显存优化**：启用 `--enable-prefix-caching` 复用重复 Prompt 的 KV Cache
- **动态 batching**：提升吞吐量 30%+
- **多模型路由**：LLM Gateway 根据任务复杂度自动选择模型（如简单分类走 Ollama，复杂推理走 vLLM），**整体成本降低 30%+**

### 6.3 配置示例（vLLM）

bash

```
python -m vllm.entrypoints.openai.api_server \
  --model qwen/Qwen2.5-72B-Instruct \
  --tensor-parallel-size 4 \
  --pipeline-parallel-size 2 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.9
```

***

## 七、数据中台（护城河核心）

### 7.1 数据整合架构

text

```
外部数据源                        内部ERP系统
├── Amazon API                    ├── SCM (成本/供应商)
├── TikTok Shop API               ├── OMS (销量/转化)
├── Google Trends                 ├── WMS (库存)
├── 1688 API                      ├── CRM (评价/客诉)
├── 媒体资讯RSS                   ├── FMS (利润/广告)
└── 社交媒体监听                  └── BI (报表/指标)
                │
                └── 统一数据管道（Kafka + Flink + Iceberg）
```

### 7.2 实时数据流

text

```
爬虫/API 推送
       ↓
 Kafka (topic: raw_amazon, raw_tiktok, raw_trends, raw_1688, raw_news, raw_orders)
       ↓
 Flink (实时清洗：去重、格式归一化、情感标注、异常剔除)
       ↓
 Iceberg (ODS层，全量存储) ←→ Qdrant (向量化同步，实时检索)
       ↓
 Spark (每日/每小时聚合：计算BSR变化率、价格波动、评论趋势、Google热度)
       ↓
 PostgreSQL (ADS层，供API查询) + Elasticsearch (关键词索引)
```

### 7.3 特征工程（Feast）

关键特征列表（用于爆款预测模型）：

| 特征名                      | 计算方式                 | 数据来源                   | 更新频率 |
| :----------------------- | :------------------- | :--------------------- | :--- |
| `sales_growth_rate_7d`   | (本周销量 - 上周销量) / 上周销量 | OMS                    | 每日   |
| `review_sentiment_score` | 平均情感得分（-1到1）         | CRM                    | 实时   |
| `price_volatility`       | 过去7天价格标准差/均价         | Amazon API             | 每日   |
| `competition_intensity`  | 同类目在售商品数 / 搜索量       | Amazon + Google Trends | 每周   |
| `supply_stability`       | 供应商历史交期准时率           | SCM / 1688             | 每月   |
| `profit_margin`          | (售价 - 总成本) / 售价      | FMS + 1688             | 实时   |
| `google_trends_7d`       | 过去7天搜索热度均值           | Google Trends          | 每日   |
| `tiktok_viral_score`     | 视频互动率 + 标签热度         | TikTok API             | 每小时  |
| `news_sentiment`         | 相关新闻情感得分（-1\~1）      | 媒体资讯                   | 实时   |

***

## 八、调度系统（双引擎 + 事件驱动）

| 调度类型     | 工具      | 典型任务                                                     | 频率    |
| :------- | :------ | :------------------------------------------------------- | :---- |
| **实时计算** | Ray     | vLLM推理Actor管理、并行Embedding、在线特征计算                         | 毫秒级   |
| **定时调度** | Airflow | 每日全量数据同步、每周选品周报生成、每月模型微调                                 | 日/周/月 |
| **事件驱动** | Prefect | Kafka消息堆积触发扩容、新品爆增自动启动分析、Google Trends突变触发、评论/新闻异常触发竞品预警 | 秒级    |

**新增事件触发场景**：

- **Google Trends突变**：当某个关键词搜索热度24小时内上升>200%，触发Market Agent重新分析该品类。
- **TikTok爆款视频出现**：当视频互动量超过阈值，自动抓取商品信息并进入选品候选池。
- **负面新闻爆发**：媒体资讯情感得分低于-0.7，触发Risk Agent评估相关品类风险。

***

## 九、企业级能力（生产必备）

| 能力维度      | 实现方案                                                                                             |
| :-------- | :----------------------------------------------------------------------------------------------- |
| **多租户**   | 通过 `tenant_id` 隔离：Qdrant分区、PostgreSQL schema、Iceberg分区；支持200+企业独立数据与模型实例                         |
| **权限控制**  | RBAC（角色：运营/采购/管理员/审计），Kong + Spring Security，最小权限原则                                              |
| **审计日志**  | 记录Agent每一步决策、Prompt输入输出、人工干预操作，存储至Iceberg审计表，保留180天                                              |
| **成本控制**  | 统计每个租户的Token消耗、模型调用次数、GPU时长；支持限额告警和自动熔断                                                          |
| **SLA保障** | 主模型超时（30s）自动降级到备用模型（vLLM→Ollama），核心API多副本+熔断器                                                    |
| **灰度发布**  | Kong + Argo Rollouts：新版本部署5%流量，监控错误率/延迟，逐步提升至100%                                                |
| **可观测性**  | 全链路Trace ID（从UI到推理层），Prometheus采集指标（API延迟P99、vLLM token速率、Qdrant检索延迟、Kafka lag），Grafana看板（业务+技术） |

***

## 十、核心业务流程（闭环示例）

### 10.1 智能选品完整流程

text

```
1. 运营人员在选品工作台输入需求：
   - 类目：户外储能电源
   - 目标市场：欧洲站（德国/法国）
   - ROI阈值：≥20%
   - 价格区间：€150-€300

2. Selection Master Agent 分解任务，并行触发：
   - Market Agent：调用Google Trends、Amazon API，分析供需比、生命周期
   - Competitor Agent：抓取Top20竞品的价格、评论、排名趋势
   - Profit Agent：对接FMS和1688 API，计算FBA/头程/佣金/广告成本
   - Supply Agent：对接SCM，评估现有供应商能力

3. 结果汇总后，Product Agent生成产品定义：
   - 建议容量：300Wh-500Wh（蓝海区间）
   - 差异化卖点：太阳能充电+Type-C快充+IP67防水
   - 痛点解决：针对竞品差评“太重”“充电慢”改进

4. Risk Agent检查：
   - 专利检索无侵权（通过GraphRAG）
   - 媒体资讯无负面新闻
   - 欧盟CE认证需要补充

5. Commercial Agent输出商业化报告：
   - 建议售价€249
   - 预估毛利率32%
   - 首单备货量500台
   - ROI预测：8个月回本

6. Report Agent生成PDF报告，推送到前端。

7. 运营人员一键“采纳” → 自动在PMS创建产品草稿 → 触发SCM询价 → 生成采购单 → WMS预留库容 → OMS创建Listing草稿。

8. 销售后数据（OMS销量、CRM评论）定期回流到特征库（Feast）和RAG知识库，完成闭环学习。
```

### 10.2 实时竞品监控预警

text每30分钟，Spark Streaming读取Kafka新评论        ↓ Flink窗口聚合（滑动窗口10分钟），调用BERT情感模型        ↓ 若某ASIN差评率突增>20%，Prefect触发事件        ↓ 自动调用Competitor Agent重新评估该商品        ↓ 生成预警报告（含原因分析、建议动作）        ↓ 通过企业微信/钉钉机器人通知对应运营

***

## 十一、部署架构（生产级）

### 11.1 Kubernetes 集群拓扑

text

```
                          CDN (CloudFront)
                               │
                        Kong Gateway (3 Pods, HPA)
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   Next.js Pods           FastAPI Pods           Dify Pods
   (2 replicas)           (4 replicas)           (2 replicas)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                        Ray Cluster
                   (Head + 8 Worker Pods)
                               │
        ┌──────────────────────┼──────────────────────┬──────────────┐
        │                      │                      │              │
   vLLM Pods              Qdrant Pods            Milvus Pods     Kafka Cluster
   (4 GPU, TP/PP)         (3 SSDs, Raft)         (5 SSDs)        (3 Brokers)
        │                      │                      │
   Triton Pods            Redis Sentinel         ES Cluster
   (2 GPU)                (3 Pods)               (3 Pods)
```

### 11.2 K8s 资源配置要点

- **Namespace 隔离**：`agent`、`data`、`inference`、`monitoring`
- **GPU 调度**：NVIDIA Device Plugin + MIG（多实例GPU），每个 vLLM Pod 申请 4 个 GPU
- **HPA**：基于 Prometheus 自定义指标（vLLM 队列长度 > 100 扩容）
- **存储**：Qdrant/Milvus 使用本地 SSD（NVMe），Iceberg 数据湖挂载 S3

### 11.3 监控与告警

| 监控对象   | 关键指标    | 告警阈值   | 动作        |
| :----- | :------ | :----- | :-------- |
| vLLM   | 推理延迟P99 | >3s    | 扩容/降级     |
| Qdrant | 检索RT    | >100ms | 增加副本      |
| Kafka  | 消费者lag  | >10k   | 触发Flink扩容 |
| Agent  | 任务失败率   | >5%    | 通知开发      |
| GPU    | 显存利用率   | >95%   | 迁移负载      |

***

## 十二、实施路线图（0→1→10）

| 阶段                        | 周期  | 核心交付                                                                                             | 里程碑          |
| :------------------------ | :-- | :----------------------------------------------------------------------------------------------- | :----------- |
| **Phase 1：基础搭建**          | 1个月 | K8s基础环境、vLLM单节点、Qdrant、基础爬虫（亚马逊BSR）、简单RAG问答                                                      | 可演示“商品趋势问答”  |
| **Phase 2：Multi-Agent集成** | 2个月 | LangChain原型验证 + LangGraph + AutoGen框架、Dify低代码编排、多节点vLLM、接入TikTok/Google Trends/1688 API、前端选品看板V1 | 完成四Agent协同流程 |
| **Phase 3：ERP闭环 + RAG增强** | 2个月 | 混合检索（Qdrant+ES）、Rerank、Flink实时管道、对接SCM/OMS/FMS、媒体资讯接入、GraphRAG、自动报告生成                            | 打通从选品到采购的闭环  |
| **Phase 4：生产就绪**          | 1个月 | 灰度发布、全链路监控、多租户支持（200+企业）、用户培训、SLA保障                                                              | 正式上线，替代人工选品  |

***

## 十三、最终业务价值总结

| 维度       | 价值                                   |
| :------- | :----------------------------------- |
| **效率**   | 选品周期从2周→4小时，人效提升5倍                   |
| **准确性**  | 爆款命中率从60%→85%，年利润预计增加30%             |
| **成本**   | 替代80%重复性分析工作，人力成本降低60%               |
| **可扩展**  | 支持亿级商品、千亿级模型、200+租户                  |
| **竞争壁垒** | 数据湖+RAG+GraphRAG+多源外部数据形成企业独有的选品知识资产 |
| **风险控制** | 通过媒体资讯和专利库，提前7\~30天发现潜在政策或侵权风险       |

***

## 十四、架构本质一句话

> **AI选品系统 = （数据中台 + RAG知识系统） × Multi-Agent决策引擎 ÷ ERP闭环执行**

- **Agent** = 替代人脑决策（LangChain + AutoGen4j + LangGraph4j + Dify + CrewAI）
- **RAG** = 沉淀企业经验，越用越强（LlamaIndex + LangChain + GraphRAG）
- **数据中台** = 核心竞争力，竞品无法复制
- **ERP融合** = 真正商业价值，形成自进化飞轮
- **外部数据** = 拓宽视野，发现蓝海

***

## 附录：下一步深度设计（按需输出）

如您需要进一步落地，我可以提供：

1. **数据库详细设计**（50+核心表：产品表、任务表、Agent日志表、向量元数据表、特征表、外部数据源配置表等）
2. **Agent Prompt工程模板**（生产级：市场洞察、利润测算、风险预警、报告生成等）
3. **爆款预测模型**（XGBoost + LLM融合的特征工程与训练代码）
4. **架构图PPT版**（可直接用于汇报的[Draw.io/PPT](https://draw.io/PPT)文件）
5. **面试/汇报话术**（针对CTO、产品总监、投资人的不同侧重点）

**请回复您需要的部分，例如：“我要数据库设计”或“Agent Prompt模板”。**
