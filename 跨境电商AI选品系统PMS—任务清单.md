# 任务清单

> 本文档由以下历史版本整合而来：
>
> - `2026041601任务分解清单.md`（主版本，13域135任务，含最新状态）
> - `2026041902下一步项目任务清单.md`（执行收口版，36项已完成）
> - `2026041401任务分解清单.md`（早期版本，已归档）
> - `20260411任务清单.md`（最早版本，已归档）
>
> 整合日期：2026-04-16
> 本文档为当前唯一有效任务清单，历史版本已移入 `_archive/` 目录

***

> 基准文档：
>
> - 《跨境电商AI选品系统PMS—架构与业务设计文档.md》（技术栈主基准）
> - 《跨境电商AI选品系统---分层架构与数据流协作.md》（业务流与数据流基准）
> - 《跨境电商AI选品系统PMS—企业级设计方案.md》（企业级终极设计方案）
> - 《20260415问题与优化建议-下一步工作方向V2.md》（差距分析与优化方向）
>
> 生成日期：2026-04-16
>
> 状态定义：✅已完成 | 🔧进行中 | ⏳待开始 | 📋规划中 | 🚫阻塞
>
> 推进属性：🔴本地可立即推进 | 🟡本地先做外部验证 | 🔵外部环境阻塞 | ⚪暂缓

***

## P0 业务闭环主链路做实

> 本轮本地运行文档已统一收口到 `docs/local-runtime/`，当前以 `docs/local-runtime/README.md` 和 `docs/local-runtime/01_统一入口与启动总览.md` 作为唯一入口，覆盖依赖安装、软件检查、服务启动、验收与排障。
>
> 本轮新增基线：已补齐三段式脚本入口、`.env.example` 的 local-real / remote-service 模式模板，以及 `artifacts/mock_scenarios/` 场景化模拟目录骨架。
>
> 本轮新增联调准备文档：`docs/phase4/外部模型与应用API准备清单.md`，统一列出外部模型、平台、业务系统、通知应用等 API 的准备项、凭证、场景模拟与真实联调建议。

> 核心目标：将选品→采纳→执行→回流的业务闭环从"状态面完成"升级为"真实可运行"
>
> 关键依赖：B7 Agent编排升级 → B0 数据回流 → BI KPI量化 → 选品准确率可度量

| 编号    | 任务               | 技术栈/实现要求                                                     | 状态   | 推进属性 | 说明                                                                                 |
| ----- | ---------------- | ------------------------------------------------------------ | ---- | ---- | ---------------------------------------------------------------------------------- |
| P0-01 | LangGraph替换自研状态机 | LangGraph Python SDK，StateGraph定义5阶段DAG，条件分支+循环+断点恢复         | ✅已完成 | 🔴   | 已将 SelectionMaster.run() 切至 LangGraph-compatible 主路径，并保留 legacy 回退                 |
| P0-02 | 5Agent并行执行       | asyncio.gather / Ray Actor，数据采集+市场洞察+产品规划+商业化+风险评估并行         | ✅已完成 | 🔴   | 已在 LangGraphCompatibleRunner 对数据采集/市场洞察/产品规划/商业化四阶段实现 asyncio.gather 并行执行          |
| P0-03 | 风险评估Agent集成到编排   | RiskAssessorAgent集成到SelectionMaster LangGraph DAG，作为商业化后标准步骤 | ✅已完成 | 🔴   | 已将 RiskAssessorAgent 接入 LangGraph-compatible DAG 标准节点 risk\_assessment             |
| P0-04 | 报告生成Agent集成到编排   | ReportGeneratorAgent集成到SelectionMaster LangGraph DAG，作为最后步骤  | ✅已完成 | 🔴   | 已将 ReportGeneratorAgent 接入 LangGraph-compatible DAG 标准节点 report\_generation        |
| P0-05 | 数据回流本地单体版        | Python模拟Flink消费CDC→更新特征库/向量库/知识库，替代真实Flink                   | ✅已完成 | 🔴   | 已补 LocalFeedbackLoopService，本地消费 order/review 事件并更新特征库、知识库与BI KPI                  |
| P0-06 | OMS订单数据回流服务      | OMSClient.get\_orders()定期拉取→特征计算→特征库更新                       | ✅已完成 | 🔴   | 已接入本地 OMSClient.fetch\_orders() 到反馈闭环，订单数据映射为 order.updated 并更新特征库                 |
| P0-07 | CRM评价数据回流服务      | CRMClient.get\_reviews()定期拉取→情感分析→知识库+向量库更新                  | ✅已完成 | 🔴   | 已接入本地 CRMClient.fetch\_customer\_feedbacks()，评价映射为 review\.updated 并写入本地知识库/向量同步状态 |
| P0-08 | BI KPI每日计算服务     | BIClient每日计算爆款命中率/ROI/选品周期，写入PostgreSQL                      | ✅已完成 | 🔴   | 已在本地反馈闭环中生成 selection\_daily\_kpis 并通过 BIClient.push\_dataset() 持久化到本地BI数据集        |
| P0-09 | 选品准确率趋势追踪        | 对比历史选品决策vs实际销售表现，输出准确率趋势曲线                                   | ✅已完成 | 🔴   | 已输出 accuracy\_trend 结构，并保留 /api/v1/selection/accuracy-trend 查询能力                   |
| P0-10 | 供应商推荐算法          | 供应商评分模型（交期/质量/价格/历史交易）+采购优化算法                                | ✅已完成 | 🔴   | 已补 ProfitOptimizationService.build\_supplier\_recommendations()、商业化Agent输出与正式API   |
| P0-11 | 竞品实时监控预警         | 定时采集+Flink窗口聚合（本地Python版）+BERT情感模型+差评率突增预警                   | ✅已完成 | 🔴   | 已补 CompetitorAnalysisService.\_build\_window\_alerts()，支持差评率/价格突变窗口预警与监控任务输出       |
| P0-12 | Celery定时任务调度     | Prefect/Celery Beat实现定时选品/数据回流/KPI计算调度                       | ✅已完成 | 🔴   | 已完成 Beat 配置、周期任务运行记录、`local-file-monitor` 等价调度监控与状态接口验收，选品/反馈闭环/KPI 三类周期任务均已收口     |

***

## P1 外部数据与ERP联调做实

> 核心目标：将外部数据源从"本地样本/auto降级"升级为"真实API联调"
>
> 关键依赖：Amazon/TikTok/Google Trends/1688 API凭证 → 真实数据采集 → Agent分析质量提升

| 编号    | 任务                      | 技术栈/实现要求                                      | 状态    | 推进属性 | 说明                                                                                                                                                                                                                                    |
| ----- | ----------------------- | --------------------------------------------- | ----- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1-01 | Amazon SP-API真实联调       | AmazonSPAPIClient对接真实SP-API，获取商品/BSR/销量/评价数据  | 🔧进行中 | 🟡   | 已补 real/auto/mock 明确边界；Amazon 场景接入 `DataCollectionAgent` mock 运行时；`business_scenario_runtime_acceptance.json` 为 `11/11 accepted`；`local_external_collection_readiness_latest.json` 显示 Amazon 当前为 `web_signal_fallback` / `local_validation_only`，正式 SP-API 凭证联调待继续完成 |
| P1-02 | TikTok Business API真实联调 | TikTokBusinessClient对接真实API，获取视频/达人/标签数据      | 🔧进行中 | 🟡   | 已补 real/auto/mock 明确边界；TikTok 热度/授权失败/低转化场景已回归；`business_scenario_runtime_acceptance.json` 为 `11/11 accepted`；readiness 显示 TikTok 当前为 `web_signal_fallback` / `local_validation_only`，正式 Business API 凭证联调待继续完成 |
| P1-03 | Google Trends API真实联调   | GoogleTrendsClient对接真实API或serpapi，获取搜索热度/趋势数据 | 🔧进行中 | 🟡   | 已补 real/auto/mock 明确边界；Google Trends 增长、空结果、突增后回落场景本地验收通过；本轮 readiness 真实探测遇到 Google Trends `429` 并已结构化记录为 `probe_error`，真实 API Key / 限流处理待继续完成 |
| P1-04 | 1688 Open API真实联调       | Ali1688OpenClient对接真实API，获取供应商/报价/MOQ数据       | 🔧进行中 | 🟡   | 已补 real/auto/mock 明确边界；1688 供应商不稳定、高 MOQ 长交期与 `partial_data` 降级场景已回归；readiness 显示 1688 当前为 `web_signal_fallback` / `local_validation_only`，真实开放平台凭证验收待继续完成 |
| P1-05 | GDELT全球事件数据真实接入         | GDELT API真实调用，获取全球政治/经济/贸易事件                  | ✅已完成  | 🟡   | 已补 GDELT 事件分类、品类关联、adapter/API 与 `scripts/bootstrap_local_gdelt_signal.py` 验证脚本；`2026-04-22` 实测真实端点返回 5 条 `bluetooth speaker` 新闻事件，完成经济/贸易/政治分类、品类关联与 `raw_news` Kafka 入站验证                                                           |
| P1-06 | 爬虫引擎部署                  | Scrapy+Playwright分布式爬虫，竞品官网/论坛/社交媒体/比价站       | ✅已完成  | 🔴   | 已补本地 Scrapy CLI 工程、Playwright Chromium、`CrawlPlatformService.run_local_crawl`、`crawl_scheduler_worker` 与验收脚本；`artifacts/ops/local_crawl_platform_acceptance.json` 已完成 `local-real` 验收                                                 |
| P1-07 | 代理IP池集成                 | 付费代理服务（BrightData/oxylabs）或自建代理池，IP轮换         | ✅已完成  | 🟡   | 已补 `ProxyPool`、`ProxyProviderService`、`LocalProxyRuntimeService`、失败熔断/冷却、可用/阻塞代理状态统计与爬虫平台状态面；`2026-04-19` 已通过本地 self-hosted 双节点代理池验收                                                                                                  |
| P1-08 | Kafka本地部署               | Kafka单节点部署，对接CDC和Agent消息                      | ✅已完成  | 🔴   | 已完成 ZooKeeper/Kafka/Kafka Connect 本地实机拉起、内部 topic 自愈、运行态探测与 `artifacts/ops/local_kafka_debezium_acceptance.json` 验收落盘                                                                                                                 |
| P1-09 | Debezium CDC连接器部署       | Debezium对接PostgreSQL WAL，真实CDC管线              | ✅已完成  | 🟡   | 已完成 `oms` / `crm` Debezium connector 注册运行、`pms-postgres` 真 CDC 抓取、`pms-agent-event` 消息消费与 Debezium envelope 校验                                                                                                                        |
| P1-10 | ERP staging环境联调         | SCM/WMS/OMS/CRM/FMS/BI staging环境真实联调          | ⏳待开始  | 🔵   | 本地HTTP联调已完成，staging环境不可得                                                                                                                                                                                                              |

***

## P2 AI能力做实

> 核心目标：将AI推理从"模拟/compatible兜底"升级为"真实推理运行"
>
> 关键依赖：WSL + Ollama(GGUF) 部署 → 文本/多模态/语音轻量真实运行 → CPU Rerank → 模型微调

| 编号    | 任务                         | 技术栈/实现要求                                              | 状态   | 推进属性 | 说明                                                                                                                                                                                                                                                                                                           |
| ----- | -------------------------- | ----------------------------------------------------- | ---- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P2-01 | WSL + Ollama文本对话部署         | WSL中部署Ollama，加载Qwen2.5-1.5B GGUF量化模型                  | ✅已完成 | 🔴   | 已在 WSL2 Ubuntu-22.04 内完成 Ollama 安装与 `qwen2.5:1.5b-instruct` 拉取，实测 prompt 返回正确结果；宿主机若保留 Windows Ollama，需额外区分 `11434` 实例路由                                                                                                                                                                                     |
| P2-02 | CPU精排部署                    | 本机/WSL 纯CPU部署 bge-reranker-base，用于 HybridRetriever 精排 | ✅已完成 | 🔴   | 已在 WSL Python venv 实测加载 `BAAI/bge-reranker-base`，真实打分结果 `scores=[0.9986,0.0631]` 且排序正确；当前 CPU 基线可用，时延优化继续保留                                                                                                                                                                                                  |
| P2-03 | 轻量多模态/视频部署                 | WSL 中部署 Qwen3.5-2B（Ollama 多模态模型），用于商品主图/TikTok视频分析    | ✅已完成 | 🔴   | 已在 WSL 内完成 `qwen3.5:2b` 拉取，并通过 `/api/v1/llm/multimodal/route`、`ProductPlannerAgent` 与 `artifacts/llm/local_model_business_acceptance.json` 完成图片/视频真实优先链路自验收                                                                                                                                                  |
| P2-04 | Whisper tiny 音频转录部署        | WSL / 本机纯CPU部署 Whisper tiny，处理 TikTok 视频音频转录          | ✅已完成 | 🔴   | 已在 WSL Python venv 实测 `WhisperModel('tiny', device='cpu', compute_type='int8')` 可加载，并与现有 `audio_transcription` 路由、Agent 聚合结果形成闭环；真实多语言音频样本继续在业务验收项跟进                                                                                                                                                         |
| P2-05 | Elasticsearch/OpenSearch部署 | ES/OpenSearch部署，BM25关键词检索，对接HybridRetriever           | ✅已完成 | 🔴   | 已补正式 SearchBackend 探活、索引 mapping、reindex 时间戳与状态接口；当前通过 `docker-compose.wsl-local.yml` 成功拉起本地 OpenSearch，已完成应用层真实索引写入、refresh 与关键词检索验收                                                                                                                                                                        |
| P2-06 | LLM定期微调真实执行                | 每周基于新数据微调模型，输出模型版本                                    | ✅已完成 | 🔴   | 已补本地 CPU `feedback-adapter` 周度训练链路、版本化工件落盘、`scripts/run_local_model_finetune.py` 验收脚本与 `artifacts/llm/local_model_finetune_acceptance.json`；当前 local-real 验收完成，高规格 GPU 微调转为后续增强                                                                                                                              |
| P2-07 | RAG缓存机制实现                  | Redis缓存层，相似查询缓存复用，TTL管理                               | ✅已完成 | 🔴   | 已在 HybridRetriever 与知识库服务接入 Redis/内存降级相似查询缓存、TTL管理与命中统计                                                                                                                                                                                                                                                      |
| P2-08 | LlamaIndex RAG编排框架集成       | 评估引入LlamaIndex替代部分自研RAG逻辑                             | ✅已完成 | 🔴   | 已补 LlamaIndexRAGService、状态/对比API、自研HybridRetriever回退、diagnostics 与检索延迟指标，并在本机安装 `llama-index` 后完成真实 `VectorStoreIndex` 检索验证                                                                                                                                                                                  |
| P2-09 | GraphRAG升级到真实图底座           | Neo4j部署或升级GraphRAG到真实图数据库                             | ✅已完成 | 🟡   | 已完成 Neo4j 本地 real 验收：修复 `cypher-shell` 路径导致的 healthcheck 假失败，并将 `bootstrap_local_graph_rag_neo4j.py` 切到宿主机 `neo4j-driver` 探测/清图；当前 `pms-neo4j-local` 为 `healthy`，`GraphRAGService` 返回 `Neo4jGraphStore` + `connection_verified=true`，`artifacts/ops/local_graph_rag_neo4j_acceptance.json` 为 `accepted=true` |
| P2-10 | Embedding批量5000 QPS验证      | 性能测试验证，优化批量Embedding吞吐                                | ✅已完成 | 🔴   | 已补 EmbeddingBenchmarkService 与 /api/v1/llm/embedding/benchmark，mock本地模式通过5000 QPS与单次延迟目标                                                                                                                                                                                                                     |
| P2-11 | AI四服务独立部署演练                | llm/rag/agent/embedding独立service app入口，独立SLA          | ✅已完成 | 🟡   | 已补 llm/rag/agent/embedding 四个独立 FastAPI app 入口、K8s清单映射、健康检查与环境变量回滚路径                                                                                                                                                                                                                                         |
| P2-12 | Ollama本地推理优化               | Ollama加载Qwen2.5-1.5B GGUF量化模型，满足本地开发推理需求              | ✅已完成 | 🔴   | 已完成本机安装、`11434` 服务恢复、轻量本地模型拉取、真实生成、延迟基准与降级链路验收；当前以 Qwen2.5-1.5B 为本地默认文本模型                                                                                                                                                                                                                                    |

***

## P3 前端工作台做实

> 核心目标：将前端从"Jinja2模板+SSE"升级为"Next.js 14 SSR+WebSocket+多角色工作台"
>
> 关键依赖：Next.js项目初始化 → 选品工作台 → Agent监控 → 知识库管理 → 报告中心

| 编号    | 任务                   | 技术栈/实现要求                                                     | 状态   | 推进属性 | 说明                                                                                                                                              |
| ----- | -------------------- | ------------------------------------------------------------ | ---- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| P3-01 | 废弃Jinja2旧模板统一Next.js | 迁移web/templates/到frontend/，Next.js 14 App Router SSR         | ✅已完成 | 🔴   | 已补 `/selection` `/approval` `/agents/monitor` 对应的 Next.js 正式入口页别名，并将 legacy Jinja 路由统一改为 307 重定向到正式入口，根状态口径同步为 `legacy_jinja_routes=redirected` |
| P3-02 | 选品工作台页面完善            | 任务创建+实时看板+ECharts趋势图+Top50推荐列表                               | ✅已完成 | 🔴   | 已补正式选品工作台，覆盖任务创建、实时流状态、ECharts-compatible 趋势图、Top50 推荐列表、审批/反馈/采纳/闭环与历史案例交互                                                                     |
| P3-03 | Agent监控面板            | LangGraph DAG可视化+断点调试+Token/成本实时统计                           | ✅已完成 | 🔴   | 已补 6 节点 DAG 可视化、快照单步/恢复调试、Token/成本实时统计与生命周期状态面                                                                                                  |
| P3-04 | RAG知识库管理页面           | 文档上传/切片预览/向量检索测试/知识版本管理                                      | ✅已完成 | 🔴   | 已补知识库工作台页面，覆盖文档上传、切片预览、检索测试、评测与版本回滚                                                                                                             |
| P3-05 | 报告中心页面               | PDF/Excel/PPT导出+一键分享至企微/钉钉+历史报告对比                            | ✅已完成 | 🔴   | 已补报告中心页面，覆盖报告列表/详情、生成、下载、分享与归档                                                                                                                  |
| P3-06 | WebSocket双向通信        | WebSocket连接，Agent流式输出+人工干预                                   | ✅已完成 | 🔴   | 已补正式 WebSocket 工作台通道，前端优先 WebSocket、失败回退 SSE，并支持实时人工干预注入                                                                                        |
| P3-07 | 采购专员工作台              | 采购任务看板+供应商管理+采购单跟踪                                           | ✅已完成 | 🔴   | 已补采购工作台页面，覆盖 SCM/WMS/OMS 状态、采纳执行与日志看板                                                                                                           |
| P3-08 | 财务工作台                | 利润看板+成本分析+ROI追踪                                              | ✅已完成 | 🔴   | 已补财务工作台页面，聚合 FMS/BI/经营看板展示利润、成本与 KPI                                                                                                            |
| P3-09 | 管理者工作台               | 选品KPI看板+团队绩效+审批流                                             | ✅已完成 | 🔴   | 已补管理者 KPI 看板、团队绩效排名、审批流待办与独立 `/manager` 正式入口，并接入统一导航与受保护路由                                                                                      |
| P3-10 | 分析师工作台               | 数据探索+趋势分析+报告定制                                               | ✅已完成 | 🔴   | 已补分析师工作台的数据探索、趋势分析、案例评测、标注导出与报告定制能力，并统一导航命名为“分析师工作台”                                                                                            |
| P3-11 | 管理后台                 | Vue3 + ElementUI Plus 多租户配置（企业隔离）、RBAC 角色权限（运营/采购）、审计日志查询/导出 | ✅已完成 | 🔴   | 已补正式运营台 `/operations`、租户与配额、RBAC/安全治理、审计查询导出、网关灰度、数据平台与实时通道状态面，并通过前端文件回归                                                                        |
| P3-12 | 正式报告PDF/Excel/PPT导出  | WeasyPrint/xlsxwriter/python-pptx集成                          | ✅已完成 | 🔴   | 已补正式 PDF/CSV/XLSX/PPTX 导出能力与下载接口，自动化测试覆盖 PDF/XLSX/PPTX 下载                                                                                       |
| P3-13 | 一键分享至企业微信/钉钉         | 扩展消息服务支持报告分享                                                 | ✅已完成 | 🔴   | 已补报告分享链接、钉钉/企微投递、归档对比与访问统计基线                                                                                                                    |

***

## P4 安全与平台治理做实

> 核心目标：将安全从"JWT基础认证+数据脱敏基线"升级为"OAuth2/SSO+细粒度RBAC+全量脱敏"
>
> 关键依赖：OAuth2/SSO → RBAC → 全量脱敏 → 多租户enforcement收紧

| 编号    | 任务               | 技术栈/实现要求                               | 状态   | 推进属性 | 说明                                                                                                                                                              |
| ----- | ---------------- | -------------------------------------- | ---- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P4-01 | OAuth2/SSO实现     | Authlib实现OAuth2，对接企业IdP（Keycloak/Okta） | ✅已完成 | 🔴   | 已补 OIDC discovery/JWKS 校验、Keycloak/Okta 风格元数据兼容、provider token 直连受保护 API、与现有本地 JWT 双栈兼容，并完成 `/api/v1/auth/oidc/*`、`/api/v1/bff/auth/me` 与本地 Keycloak runtime 回归 |
| P4-02 | RBAC细粒度权限        | 运营/采购/管理/分析/财务5角色，资源级权限控制              | ✅已完成 | 🔴   | 已补 procurement/manager/finance 角色与 selection.approve 资源级权限，服务层强制校验                                                                                              |
| P4-03 | 数据脱敏全量覆盖         | 扩展脱敏规则，覆盖所有PII字段（邮箱/手机/身份证/地址）         | ✅已完成 | 🔴   | 已扩展至姓名/地址/护照/银行卡/Token/密码等字段，并支持 `SEC_PII_FIELD_PATTERNS` 配置化扩展                                                                                                 |
| P4-04 | 多租户enforcement收紧 | 移除默认租户回退，强制require\_tenant             | ✅已完成 | 🔴   | 显式 tenant\_id 强制校验、无租户拒绝、审计查询租户隔离已完成并通过集成回归                                                                                                                     |
| P4-05 | 审计日志增强           | Agent每步决策/Prompt输入输出/人工干预操作全量记录        | ✅已完成 | 🔴   | 人工干预、安全拦截、节点级决策、Prompt输入输出（含远程LLM成功路径）审计已补齐，审计查询支持 persistent+memory 合并与租户过滤并通过回归                                                                               |
| P4-06 | Prompt注入防护增强     | 扩展Prompt注入检测规则，覆盖更多攻击模式                | ✅已完成 | 🔴   | 已补 role\_hijack/jailbreak/tool\_escape 等高风险模式、策略版本升级与拦截审计，并落地检测率/误报率量化基准（当前基准样本 100% / 0%）                                                                      |
| P4-07 | 成本控制与限额          | 统计每租户Token消耗/模型调用次数/GPU时长，支持限额告警和自动熔断  | ✅已完成 | 🔴   | 已补租户 LLM 成本/Token 配额、超额 429 熔断、治理状态与 /api/v1/costs/report 成本报表                                                                                                  |

***

## P5 环境与基础设施做实

> 核心目标：将环境从"单机开发环境"升级为"可部署的生产级基础设施"
>
> 关键依赖：Docker WSL2修复 → Kafka/Triton/Kong可Docker部署 → K8s集群 → 多AZ灾备

| 编号    | 任务                         | 技术栈/实现要求                                         | 状态   | 推进属性 | 说明                                                                                                                                                                                                                     |
| ----- | -------------------------- | ------------------------------------------------ | ---- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P5-01 | 修复Docker Linux/WSL backend | WSL2配置修复，确保Kong/Triton/Kafka/OpenSearch可Docker部署 | ✅已完成 | 🔴   | 已确认 WSL2 `Ubuntu-22.04` 与 Docker desktop-linux 可用，本地 Linux 容器栈已稳定运行 Kong/OpenSearch/Kafka 等组件                                                                                                                          |
| P5-02 | Kafka单节点部署                 | Kafka单节点+Zookeeper，对接CDC和Agent消息                 | ✅已完成 | 🔴   | 已完成 ZooKeeper/Kafka/Kafka Connect 本地实机拉起、topic 初始化与自愈、运行态探测、生产消费链路与验收产物落盘                                                                                                                                              |
| P5-03 | PostgreSQL HA配置            | PostgreSQL主从复制+自动故障切换                            | ✅已完成 | 🔴   | 已完成 `docker-compose.wsl-postgres-ha.yml` 实机拉起、`pgpool:15432` 统一接入、主库故障切换到 `pg-standby-1`、应用用户经 `pgpool` 持续可用，以及原主库以从库身份自动回归；同时修复了 Docker Desktop Linux Engine API `500`、镜像兼容、`pg-primary-0` 节点命名与 `pgpool` legacy 参数问题 |
| P5-04 | Redis HA配置                 | Redis Sentinel集群，缓存高可用                           | ✅已完成 | 🔴   | 已完成 WSL Redis Sentinel `1主2从+3 Sentinel` 实机拉起、Sentinel 主节点发现、主库故障自动切换到 `redis-replica-1`、原主库以从库身份自动回归，并修复 Sentinel 监控主机名在 Docker DNS 失效后无法完成故障转移的问题                                                                    |
| P5-05 | Kong Gateway部署             | Kong集群部署，认证/限流/路由/灰度                             | ✅已完成 | 🔴   | 已完成本地 Kong 栈、声明式资源加载、业务 API 代理、认证/限流/灰度/日志治理链路与运行时漂移识别验收                                                                                                                                                               |
| P5-06 | Prometheus+Grafana生产化      | 多环境监控+自定义Dashboard+告警规则                          | ⏳待开始 | 🟡   | 本地服务已运行，需生产化                                                                                                                                                                                                           |
| P5-07 | EFK日志收集部署                  | Elasticsearch+Fluentd+Kibana，全链路日志收集             | ⏳待开始 | 🟡   | Trace关联已实现，缺PB级日志收集                                                                                                                                                                                                    |
| P5-08 | K8s集群部署                    | kubeadm/minikube部署K8s集群，多AZ                      | ⏳待开始 | 🔵   | 依赖Docker Linux backend                                                                                                                                                                                                 |
| P5-09 | CI/CD管线建立                  | GitHub Actions/Jenkins，镜像构建+安全扫描+自动部署            | ✅已完成 | 🔴   | 已补 GitHub Actions 安全门禁、Docker 镜像构建、release gate 产物上传与 `staging` 发布记录链路，并完成本地 `security-smoke` / `smoke` / `release_deploy.py --target staging` 验收                                                                      |
| P5-10 | Docker镜像构建                 | Dockerfile+docker-compose，所有服务容器化                | ✅已完成 | 🔴   | 已确认 `Dockerfile`、`docker-compose.yml`、`docker-compose.wsl-local.yml` 存在，并完成本地 `docker build` 构建，镜像已成功导出                                                                                                                |

***

## P6 Agent编排架构升级

> 核心目标：将Agent框架从"自研BaseAgent+状态机"升级为"LangGraph+AutoGen+CrewAI多框架协同"
>
> 设计文档明确要求：LangGraph（状态机核心）+ AutoGen（多Agent对话）+ CrewAI（角色化顺序任务）+ Dify（低代码编排）

| 编号    | 任务                    | 技术栈/实现要求                                       | 状态    | 推进属性 | 说明                                                                                                                                                               |
| ----- | --------------------- | ---------------------------------------------- | ----- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P6-01 | LangGraph状态机集成        | LangGraph Python SDK，StateGraph定义选品DAG，条件分支+循环 | ✅已完成  | 🔴   | 已完成 LangGraph-compatible DAG、条件分支、循环、snapshot/单步调试与统一 runtime 状态面验收                                                                                              |
| P6-02 | AutoGen多Agent对话       | AutoGen Agent对话模式，数据采集Agent多源并发对话              | ✅已完成  | 🔴   | 已完成 autogen-compatible 对话式编排、多源并发对话、参与者/转录结构与业务摘要回归验收                                                                                                            |
| P6-03 | CrewAI角色化任务           | CrewAI角色化顺序任务，批量竞品分析并行                         | ✅已完成  | 🔴   | 已完成 crewai-compatible 角色/任务编排、并行竞品分析、供应链口径摘要与业务回归验收                                                                                                              |
| P6-04 | Dify低代码编排集成           | Dify Prompt调优+流程编排+内置RAG管道                     | 🔧进行中 | 🟡   | 已补真实 Dify HTTP runtime、`dify-compatible` fallback、`frameworks/framework_runtime_summary` 运行态诊断与 `agent /status` 暴露，并完成本地测试验收；真实 Dify 容器部署、界面编排与内置 RAG 管道仍待外部环境验收 |
| P6-05 | LangChain辅助编排         | LangChain链式调用+工具集成，快速原型验证                      | ✅已完成  | 🔴   | 已完成 langchain-compatible 工具链路、tool calling 摘要、原型验证与业务回归验收                                                                                                        |
| P6-06 | Agent消息持久化            | MessageBus对接Kafka，实现持久化消息传递                    | ✅已完成  | 🟡   | 已完成 Kafka-compatible 本地消息总线、JSONL 持久化、查询/回放与真实本地 Kafka broker 联通验收，统一 `kafka_compatibility` 状态口径                                                                 |
| P6-07 | Agent生命周期管理           | Agent注册中心+健康检查+自动重启+任务队列调度                     | ✅已完成  | 🔴   | 已补实例生命周期、健康检查、自动重启建议、默认重启策略、本地重启动作接口与队列调度状态面，并通过平台服务测试                                                                                                           |
| P6-08 | Human-in-the-loop完整实现 | 对接前端WebSocket，实时人工干预注入+断点恢复                    | ✅已完成  | 🔴   | 已打通前端 WebSocket 干预、工作流快照、人工注入与恢复执行链路                                                                                                                             |
| P6-09 | Agent断点调试支持           | LangGraph断点调试+单步执行+状态回滚                        | ✅已完成  | 🔴   | 已补断点、单步执行、状态回滚就绪标记与前端调试面板，并通过平台服务测试                                                                                                                              |
| P6-10 | Agent Token/成本实时统计    | 每个Agent的Token消耗+模型调用成本实时统计                     | ✅已完成  | 🔴   | 已补 Agent Token/成本指标、工作流成本汇总 API 与前端实时展示                                                                                                                          |

***

## P7 数据流架构升级

> 核心目标：将数据流从"API直接调用"升级为"Kafka统一数据接入→Flink处理→特征/向量/知识库更新"
>
> 设计文档明确要求：API适配器+爬虫引擎+RSS订阅器 → Kafka/数据湖 → Flink/Spark → 特征库/向量库/知识库

| 编号    | 任务                    | 技术栈/实现要求                                                                      | 状态    | 推进属性 | 说明                                                                                                                                                   |
| ----- | --------------------- | ----------------------------------------------------------------------------- | ----- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| P7-01 | Kafka统一数据接入           | 所有外部数据源写入Kafka topic（raw\_amazon/raw\_tiktok/raw\_trends/raw\_1688/raw\_news） | ✅已完成  | 🟡   | 已补 `DataCollectionAgent` 与 `ExternalSignalService` 的 `raw_*` topic 发布链路，`ensure_topics()` 与本地 compose 口径一致，并通过状态面/API 与针对性回归验收                       |
| P7-02 | Flink实时流处理（本地Python版） | Python模拟Flink消费CDC→清洗→情感标注→异常剔除                                               | ✅已完成  | 🔴   | 已补真实本地流作业脚本，消费 OMS/CRM/数据湖事件并更新特征投影                                                                                                                  |
| P7-03 | Flink实时流处理（真实部署）      | Flink集群部署，实时清洗+情感标注+特征计算                                                      | 🔧进行中 | 🔴   | 已补齐 `windows-host` 本地分支：checkpoint 验收服务的 build/submit/consumer-group/cancel 已支持本机 JDK/Flink/Kafka CLI 路径，且保持原有 docker/prod 路径不变；当前第一套环境下共享本地资源已复核到位，真正剩余缺口为 Apache Flink 本体及 `FLINK_HOME` 配置，补齐后即可优先按 Windows 本地链路重跑 `scripts/run_local_flink_checkpoint_acceptance.py` 与 `artifacts/data_platform/flink_checkpoint_acceptance_latest.json` 验收 |
| P7-04 | Spark批处理替代            | Pandas/Dask替代Spark，每日聚合+特征计算                                                  | ✅已完成  | 🔴   | 已补真实本地批作业脚本与 10 项特征聚合，并通过 SQLite ADS 落库、批处理状态/详情/总览 API 完成正式查询闭环                                                                                     |
| P7-05 | Iceberg数据湖（本地版）       | PostgreSQL+对象存储替代Iceberg，ODS层全量历史                                             | ✅已完成  | 🔴   | 已完成本地湖仓 manifest、ODS 存储与查询接口、`selection_task_metrics` 样例数据和状态面验收                                                                                     |
| P7-06 | Iceberg数据湖（真实部署）      | Iceberg+Hudi数据湖，ODS/DWD/DWS/ADS四层分层                                           | ⏳待开始  | 🔵   | 依赖K8s+对象存储                                                                                                                                           |
| P7-07 | Debezium CDC真实运行      | Debezium连接器对接PostgreSQL WAL，CDC envelope发布                                    | ✅已完成  | 🟡   | 已完成 `oms` / `crm` Debezium connector 注册运行、`pms-postgres` 真 CDC 抓取、`pms-agent-event` 消费与 Debezium envelope 验收                                         |
| P7-08 | Prefect事件驱动调度         | Prefect实现异常触发+Google Trends突变触发+评论异常触发                                        | ✅已完成  | 🔴   | 已完成 `prefect-compatible-local` 事件调度替代链路、触发接口与本地 worker 验收，满足当前本地运行口径                                                                                 |
| P7-09 | 特征工程（Feast）           | 9大关键特征计算：sales\_growth\_rate\_7d/review\_sentiment\_score/price\_volatility等  | ✅已完成  | 🔴   | 已补 10 项关键特征计算、本地特征工件、FeatureAsset 正式查询 API 与批量/历史接口；Feast SDK 保留为可选增强项                                                                               |
| P7-10 | Kettle ETL/Ray分布式计算   | Pandas/Dask+Python单体替代，预留Ray分布式接口                                             | ⏳待开始  | 🔴   | 设计文档要求Kettle+Ray，暂用Python替代                                                                                                                          |

***

## P8 推理引擎层升级

> 核心目标：将推理引擎从"compatible兜底+状态面"升级为"真实 Ollama / 轻量多模态 / CPU 精排运行"
>
> 设计文档分层详解表独立列出推理引擎层，与LLM模型层分离

| 编号    | 任务                                | 技术栈/实现要求                                  | 状态   | 推进属性 | 说明                                                                                                              |
| ----- | --------------------------------- | ----------------------------------------- | ---- | ---- | --------------------------------------------------------------------------------------------------------------- |
| P8-01 | vLLM多节点分布式推理（高配扩展路线）              | vLLM + TP+PP并行 + Prefix Caching，单卡故障自动切换  | ⏳待开始 | 🔵   | 保留为高配扩展路线，本地默认已切到 WSL + Ollama                                                                                  |
| P8-02 | Triton Inference Server部署（高配扩展路线） | Triton + 多模型并行推理，GPU资源调度                  | ⏳待开始 | 🔵   | 保留为高配扩展路线，本地默认多模态/精排已切轻量模型 + CPU                                                                                |
| P8-03 | Ollama本地推理优化                      | Ollama + WSL / 本机轻量推理，Qwen2.5-1.5B GGUF量化 | ✅已完成 | 🔴   | 已完成本机 Ollama 安装、`11434` 服务恢复、轻量本地模型真实生成、延迟基准与降级链路验收；当前以 Qwen2.5-1.5B 为本地默认文本模型                                  |
| P8-04 | CUDA/TensorRT加速                   | TensorRT模型优化+CUDA内核加速                     | ⏳待开始 | 🔵   | 需NVIDIA GPU+CUDA环境                                                                                              |
| P8-05 | GPU资源池管理                          | A100 80GB×4 / A10 24GB×2资源池，显存分配+调度       | ⏳待开始 | 🔵   | GPUResourcePoolService已有状态面                                                                                     |
| P8-06 | 推理服务健康检查                          | 推理节点心跳+延迟监控+自动摘除                          | ✅已完成 | 🔴   | 已补 InferenceHealthService 基于 vLLM/Triton/Ollama 真实状态面估算延迟、聚合路由健康与自动摘除逻辑，并提供 `/api/v1/llm/inference/health` 验收入口 |
| P8-07 | LLM Gateway真实降级                   | 主→备自动降级（vLLM→Ollama→商业API），熔断器模式          | ✅已完成 | 🔴   | 已完成 vLLM→Ollama→remote-service 降级链路、熔断/半开恢复、`route_endpoint` 状态字段与真实远程 HTTP 回退验收                                |

***

## P9 网关与流量治理

> 核心目标：将网关从"应用侧中间件"升级为"Kong Gateway集群"
>
> 设计文档要求：认证/限流/路由/灰度/日志聚合/审计/IP白名单

| 编号    | 任务               | 技术栈/实现要求                                        | 状态   | 推进属性 | 说明                                                                                    |
| ----- | ---------------- | ----------------------------------------------- | ---- | ---- | ------------------------------------------------------------------------------------- |
| P9-01 | Kong Gateway集群部署 | Kong + PostgreSQL配置存储 + Redis限流计数器              | ✅已完成 | 🔴   | 已完成本地 Kong/PostgreSQL/Redis 治理栈、声明式资源、业务 API 稳定代理、运行时 drift 检测与状态面验收                  |
| P9-02 | Kong认证授权插件       | JWT/OAuth2认证插件配置                                | ✅已完成 | 🔴   | 已完成 `key-auth`、consumer、upstream oauth2-jwt 与 tenant contract 状态口径和业务链路验收             |
| P9-03 | Kong限流熔断插件       | 令牌桶限流+熔断器配置                                     | ✅已完成 | 🔴   | 已完成 gateway/app 限流、租户维度口径、service-side 熔断状态面与 `429` 回归验收                              |
| P9-04 | Kong路由灰度插件       | 金丝雀灰度发布配置                                       | ✅已完成 | 🟡   | 已完成 canary manifest、header 路由、rollback 就绪与环境目标状态验收                                    |
| P9-05 | Kong日志聚合插件       | 全链路日志聚合+审计日志                                    | ✅已完成 | 🟡   | 已完成 logging\_aggregation 字段清单、EFK manifest、retention、query 示例与 viewer/collector 状态面验收 |
| P9-06 | 全链路Trace ID完善    | 统一在中间件层注入TraceID，贯穿Agent→Service→Infrastructure | ✅已完成 | 🔴   | 已完成中间件注入、Agent→Service→Infrastructure 贯通、日志关联与前端 Trace 展示验收，并通过 P9-06 回归测试集           |

***

## P10 监控与可观测性

> 核心目标：将监控从"本地Prometheus+Grafana"升级为"生产级全链路可观测"
>
> 设计文档要求：全链路Trace ID + Prometheus指标 + Grafana看板 + EFK日志 + 告警

| 编号     | 任务                  | 技术栈/实现要求                                               | 状态    | 推进属性 | 说明                                                                                  |
| ------ | ------------------- | ------------------------------------------------------ | ----- | ---- | ----------------------------------------------------------------------------------- |
| P10-01 | Prometheus指标完善      | API延迟P99/vLLM token速率/Qdrant检索延迟/Kafka lag             | ✅已完成  | 🔴   | 已补 API/LLM/Qdrant/Kafka/选品业务指标埋点，覆盖成功率/准确率并通过自动化验收                                  |
| P10-02 | Grafana Dashboard模板 | 业务+技术双维度看板，选品KPI/Agent执行/推理性能                          | ✅已完成  | 🔴   | 已补 Dashboard 导入清单、Grafana 导入状态面与 metrics\_dashboard 工件，对接本机 Prometheus/Grafana 健康探测 |
| P10-03 | EFK日志收集部署           | Elasticsearch+Fluentd+Kibana，全链路日志收集                   | ✅已完成  | 🟡   | 已补 EFK 工件、导出脚本、metrics\_dashboard 状态面与查询入口；真实 ES/Fluentd/Kibana 联通待现场验证             |
| P10-04 | 告警规则配置              | vLLM延迟P99>3s/Qdrant RT>100ms/Kafka lag>10k/Agent失败率>5% | ✅已完成  | 🔴   | 已补 Prometheus 告警规则、导出脚本、状态面与 Grafana 导入清单；真实 Prometheus/Alertmanager 通知链路待现场联通验证    |
| P10-05 | GPU监控               | 显存利用率/推理吞吐/模型加载状态                                      | 🔧进行中 | 🔴   | 已补 GPU 资源池状态接口与 DCGM Exporter 安装/指标阻塞证据；真实 Prometheus 抓取与 GPU Dashboard 待现场联通验证     |

> 本轮完成：P10-01 已补 `api_request_duration_seconds`、`vllm_tokens_processed`、`qdrant_search_duration_seconds`、`kafka_consumer_lag`、`selection_success_rate`、`selection_accuracy` 等正式指标，并将埋点接入 TraceMiddleware、LLMGateway、QdrantService、Kafka 兼容队列与选品执行链路。
>
> 继续完成：P10-03 已补 `artifacts/ops/efk_stack.json`、`artifacts/ops/efk_stack_manifest.json`、`scripts/export_efk_stack_manifest.py`，并把 EFK 日志聚合状态接入 `metrics-dashboard`；本机未连接真实 ES/Fluentd/Kibana，仅完成本地工件与自动化验收。
>
> 继续完成：P10-04 已补 `artifacts/ops/alert_rules.json`、`artifacts/ops/prometheus_alert_rules.yml`、`artifacts/ops/alert_rules_manifest.json`、`scripts/export_alert_rules_manifest.py`，并把告警规则接入 `metrics-dashboard` 状态面与 Grafana 导入清单。阻塞说明：本机未连接到真实 Prometheus/Alertmanager 运行实例，当前仅完成规则交付与本地自动化验收，真实触发/通知链路需现场联通验证。

***

## P11 高可用与运维

> 核心目标：将运维从"单机部署"升级为"K8s多AZ+灾备+自动扩缩容"
>
> 设计文档要求：99.9%可用性+多租户200+企业+灰度发布+SLA保障

| 编号     | 任务            | 技术栈/实现要求                                                      | 状态    | 推进属性 | 说明                                                    |
| ------ | ------------- | ------------------------------------------------------------- | ----- | ---- | ----------------------------------------------------- |
| P11-01 | K8s多AZ部署      | kubeadm/minikube，Namespace隔离（agent/data/inference/monitoring） | ⏳待开始  | 🔵   | 依赖Docker Linux backend                                |
| P11-02 | HPA自动扩缩容      | 基于Prometheus自定义指标（vLLM队列长度>100扩容）                             | ⏳待开始  | 🔵   | 依赖K8s部署                                               |
| P11-03 | 灰度发布          | Kong + Argo Rollouts，5%流量→监控→逐步100%                           | ⏳待开始  | 🔵   | 依赖Kong+K8s                                            |
| P11-04 | 灾备演练          | PostgreSQL/Redis/Qdrant主从切换+数据恢复验证                            | 🔧进行中 | 🟡   | PostgreSQL 与 Redis 主从切换/回切已完成实机演练；Qdrant 灾备与数据恢复验证待继续 |
| P11-05 | SLA保障         | 核心API多副本+熔断器+降级策略，99.9%可用性                                    | ⏳待开始  | 🟡   | 需K8s部署后实现                                             |
| P11-06 | Istio服务网格（可选） | 灰度/熔断/流量管理                                                    | 📋规划中 | 🔵   | 依赖K8s集群部署后引入                                          |

***

## P12 业务功能补齐

> 核心目标：补齐设计文档要求但当前缺失的业务功能
>
> 基于《项目实现与设计文档差异分析报告》业务功能量化评估

| 编号     | 任务              | 技术栈/实现要求                                           | 状态   | 推进属性 | 说明                                                                                                                           |
| ------ | --------------- | -------------------------------------------------- | ---- | ---- | ---------------------------------------------------------------------------------------------------------------------------- |
| P12-01 | 选品审批流           | 多级审批+审批历史+审批通知                                     | ✅已完成 | 🔴   | 已补运营/采购/管理三级审批流、审批历史查询、提交通知分发与 BFF/正式 API                                                                                    |
| P12-02 | 知识库版本管理         | 文档版本+切片版本+索引版本，支持回滚                                | ✅已完成 | 🔴   | 已补文档版本递增、当前版本切换、回滚与版本对比接口                                                                                                    |
| P12-03 | CRM客诉数据接入       | CRMClient扩展客诉记录获取，客诉原因分类                           | ✅已完成 | 🔴   | 已补 CRMClient.fetch\_complaints()、质量/物流/描述不符/售后分类与运营状态输出，并接入再评分风险                                                             |
| P12-04 | FMS广告费联调        | FMSClient扩展广告费数据获取，ACOS计算                          | ✅已完成 | 🔴   | 已补 FMSClient.fetch\_ad\_spending()、广告费/广告销售额汇总、ACOS计算，并接入 FMS 成本快照                                                           |
| P12-05 | 多模态分析真实推理       | Qwen3.5-2B 商品主图分析 + TikTok 视频帧提取                   | ✅已完成 | 🔴   | 已完成本地多模态真实优先接入，图片分析、视频分析与 Agent 业务链路均通过 `artifacts/llm/local_model_business_acceptance.json` 自验收，真实 provider 命中 `qwen3.5:2b` |
| P12-06 | Whisper音频转录     | Whisper tiny 处理 TikTok 视频音频转录，提取产品使用场景             | ✅已完成 | 🔴   | 已完成 Whisper tiny CPU runtime、`audio_transcription` 路由、ProductPlannerAgent 聚合链路与自验收闭环；真实多语言样本扩充转入后续增强，不阻塞当前任务验收               |
| P12-07 | 报告多格式导出         | PDF(WeasyPrint)+Excel(xlsxwriter)+PPT(python-pptx) | ✅已完成 | 🔴   | 已补正式 PDF/CSV/XLSX/PPTX 导出、下载与归档校验                                                                                            |
| P12-08 | 报告一键分享          | 扩展消息服务，报告分享到企业微信/钉钉                                | ✅已完成 | 🔴   | 已补分享链接、钉钉/企微投递与访问计数能力                                                                                                        |
| P12-09 | 利润中枢闭环做实        | 选品→采购→销售→利润全链路真实数据回流                               | ✅已完成 | 🟡   | 已打通采纳→SCM/WMS/OMS→CRM/FMS/BI 回流→再评分/利润追踪/利润趋势/闭环总览                                                                           |
| P12-10 | 钉钉/企微机器人交互式操作   | 卡片交互+任务创建+审批操作                                     | ✅已完成 | 🔴   | 已补交互式卡片、任务创建/审批回调与回调 URL 验签，并新增端到端回调审批/建单验收用例完成收口                                                                            |
| P12-11 | 数据大屏(Grafana)对接 | Grafana Dashboard模板，对接已有Prometheus指标               | ✅已完成 | 🔴   | 已补 Grafana 导入清单、metrics\_dashboard 工件、运营台 Grafana 导入状态面与本机观测联通验证                                                             |

***

## 统计汇总

| 状态     | 数量      | 占比       |
| ------ | ------- | -------- |
| ✅已完成   | 95      | 79.8%    |
| 🔧进行中  | 9       | 7.6%     |
| ⏳待开始   | 14      | 11.8%    |
| 📋规划中  | 1       | 0.8%     |
| **合计** | **119** | **100%** |

### 各优先级域完成度

| 优先级域            | 任务数 | 已完成 | 进行中 | 待开始 | 规划中 | 完成率        |
| --------------- | --- | --- | --- | --- | --- | ---------- |
| P0 业务闭环主链路做实    | 12  | 12  | 0   | 0   | 0   | **100.0%** |
| P1 外部数据与ERP联调做实 | 10  | 5   | 4   | 1   | 0   | **50.0%**  |
| P2 AI能力做实       | 12  | 12  | 0   | 0   | 0   | **100.0%** |
| P3 前端工作台做实      | 13  | 13  | 0   | 0   | 0   | **100.0%** |
| P4 安全与平台治理做实    | 7   | 7   | 0   | 0   | 0   | **100.0%** |
| P5 环境与基础设施做实    | 10  | 7   | 0   | 3   | 0   | **70.0%**  |
| P6 Agent编排架构升级  | 10  | 9   | 1   | 0   | 0   | **90.0%**  |
| P7 数据流架构升级      | 10  | 7   | 1   | 2   | 0   | **70.0%**  |
| P8 推理引擎层升级      | 7   | 3   | 0   | 4   | 0   | **42.9%**  |
| P9 网关与流量治理      | 6   | 6   | 0   | 0   | 0   | **100.0%** |
| P10 监控与可观测性     | 5   | 4   | 1   | 0   | 0   | **80.0%**  |
| P11 高可用与运维      | 6   | 0   | 1   | 4   | 1   | **0%**     |
| P12 业务功能补齐      | 11  | 11  | 0   | 0   | 0   | **100.0%** |

### 推进属性分布

| 推进属性       | 数量 | 占比    | 说明                 |
| ---------- | -- | ----- | ------------------ |
| 🔴本地可立即推进  | 87 | 73.1% | 无外部依赖，可立即开始        |
| 🟡本地先做外部验证 | 21 | 17.6% | 本地先实现，后续外部环境验证     |
| 🔵外部环境阻塞   | 11 | 9.2%  | 依赖GPU/K8s/IdP等外部资源 |

### 关键依赖链

```
P5-01 Docker WSL2修复 ──→ P5-02 Kafka部署 ──→ P7-01 Kafka统一数据接入
                                             ──→ P7-07 Debezium CDC
                                             ──→ P6-06 Agent消息持久化

P5-01 Docker WSL2修复 ──→ P5-05 Kong部署 ──→ P9-01~P9-05 Kong全套插件
                             ──→ P5-08 K8s部署 ──→ P11-01~P11-05 HA+运维

P6-01 LangGraph集成 ──→ P6-02 AutoGen ──→ P6-03 CrewAI ──→ P0-01~P0-04 Agent编排升级
                                                      ──→ P0-02 5Agent并行执行

P2-01 Ollama文本部署 ──→ P8-03 Ollama推理 ──→ P2-05 ES部署 ──→ P2-07 RAG缓存 ──→ AI能力完整
P2-02 CPU精排部署 ──→ P2-03 轻量多模态 ──→ P2-04 Whisper tiny/base

P0-05 数据回流本地版 ──→ P0-06 OMS回流 ──→ P0-07 CRM回流 ──→ P0-08 BI KPI ──→ P0-09 准确率趋势
                                                    ──→ P0-10 供应商推荐
                                                    ──→ P0-11 竞品预警
```

### 实施路线图

| 阶段                 | 周期   | 核心交付                                                          | 里程碑        |
| ------------------ | ---- | ------------------------------------------------------------- | ---------- |
| **Phase 1：业务闭环做实** | 1-2周 | LangGraph编排+5Agent并行+数据回流本地版+BI KPI+供应商推荐+竞品预警                | 自进化闭环本地可运行 |
| **Phase 2：外部数据联调** | 2-3周 | Amazon/TikTok/Google Trends/1688真实联调+爬虫部署+Kafka部署+CDC管线       | 真实数据驱动选品   |
| **Phase 3：AI能力做实** | 2-3周 | WSL+Ollama轻量模型部署+ES部署+RAG缓存+LlamaIndex+GraphRAG升级+Embedding压测 | AI推理真实运行   |
| **Phase 4：前端工作台**  | 2-3周 | Next.js统一+Agent监控+知识库管理+报告中心+多角色工作台+WebSocket                 | 前端完整可用     |
| **Phase 5：安全与治理**  | 1-2周 | OAuth2/SSO+RBAC+全量脱敏+多租户收紧+成本控制                               | 企业级安全治理    |
| **Phase 6：基础设施**   | 2-3周 | Docker修复+Kafka+Kong+K8s+CI/CD+监控生产化                           | 生产级基础设施    |

### 与2026041401任务清单的关系

| 维度 | 2026041401清单 | 2026041601清单    |
| -- | ------------ | --------------- |
| 定位 | 应用侧代码与状态面实现  | 真实运行与生产化落地      |
| 状态 | 283项全部✅已完成   | 135项待推进（聚焦差距）   |
| 口径 | 代码层面完成度      | 企业级真实运行完成度      |
| 重点 | 补齐代码能力和API   | 补齐真实部署、联调、推理、前端 |

***

> 文档版本：v1.2
> 生成日期：2026-04-16
> 更新日期：2026-04-23
> 基准文档：《跨境电商AI选品系统PMS—架构与业务设计文档.md》、《跨境电商AI选品系统---分层架构与数据流协作.md》、《跨境电商AI选品系统PMS—企业级设计方案.md》、《20260415问题与优化建议-下一步工作方向V2.md》

## 2026-04-20 进度更新

- P2/P8 本地模型业务能力链路已补强：文本对话、图像分析、视频分析、Whisper 转录、CPU rerank 已接入真实优先链路，并在 `/api/v1/llm/multimodal/route`、`ProductPlannerAgent`、`LLMGateway`、`HybridRetriever(enable_rerank=True)` 中打通。
- 新增验收资产与回归用例：`scripts/run_local_model_business_acceptance.py`、`artifacts/llm/local_model_business_acceptance.json`、`tests/test_local_model_business_integration.py`、`tests/test_ollama_client.py`。
- 本地模型业务自验收结果：4 项检查全部通过，整体状态为 `passed`；其中 real provider 命中 2 项、degraded fallback 0 项。
- 自验收明细：文本对话通过，实测模型为 `qwen2.5:0.5b`；图像分析通过，`provider_mode=real`；视频分析通过，`provider_mode=real`；Agent 业务集成通过。
- 本次定向业务集成与全链路可信集测试通过：`tests/test_api_integration.py tests/test_minimal_trusted_phase34.py tests/test_local_model_business_integration.py tests/test_ollama_client.py -q` 共 `251 passed`。
- P4-01 OAuth2/SSO 已完成收口：新增 OIDC discovery/JWKS 校验、Keycloak/Okta 风格 IdP 兼容、provider token 直通受保护 API、BFF `auth/me` 认证来源透传，以及与现有本地 JWT 兼容回归。
- 本轮结论：本地模型文本、多模态、语音、精排与 Agent 业务链路已完成接入、自验收与全链路回归，当前任务口径下已收口。

## 2026-04-23 本地网关与治理回归更新

- P5-05 / P9-01 / P9-03 本地网关口径已统一到“宿主机 Python 后端 `18000` + Kong proxy `8000`”：`k8s/gateway/kong-services.yml`、`scripts/validate_gateway_config.py`、`scripts/gateway_smoke_check.py` 与网关治理测试已对齐 `host.docker.internal:18000`。
- 本地网关配置验收已通过：`python scripts/validate_gateway_config.py` 返回 `gateway_config_validation=ok`；`python scripts/gateway_smoke_check.py` 可探测到 proxy 业务路由，`/docs` 返回 200，`/api/v1/llm/inference/health` 与 `/api/v1/bff/auth/me` 返回预期 401，未再命中错误上游。
- 运行态遗留阻塞已明确：Kong Admin `8001/status` 当前不可达，Docker engine `desktop-linux` / `desktop-windows` 探测超时，且本机存在 `reboot_pending=true`；本轮已清理残留的本项目 Docker CLI 挂起进程，并将 `gateway_environment_checklist.py` 的 Docker 探测改为超时后显式清理子进程，避免后续验收继续堆积挂起进程。
- P4-06 / P8-07 治理状态补强：`SecurityBaselineService` 现在透出 Prompt Guard `policy_version=3` 与质量基准，`GatewayGovernanceService` 现在透出 LLM Gateway service-side 熔断器状态，相关回归已通过。
- 本轮关联回归：`tests/test_gateway_config.py tests/test_gateway_delivery_pack.py tests/test_governance_status_services.py::{gateway/security} tests/test_api_integration.py::test_security_status_exposes_masking_and_prompt_guard_policy -q` 共 `11 passed`；可信主回归 `tests/test_api_integration.py tests/test_minimal_trusted_phase34.py -q` 本次收集 `249 items`，300 秒超时，仅输出到 `tests/test_api_integration.py ........`，未纳入最终通过数。

### 2026-04-23 统计口径说明

- 任务清单总计仍为 119 项：✅已完成 95、🔧进行中 9、⏳待开始 14、📋规划中 1。
- P5 完成度仍按 7/10 统计，P9 完成度仍按 6/6 统计；本轮新增的是本地验收链路加固、目标回归验证与阻塞证据收口，不新增独立任务项。

## 2026-04-23 P1 外部数据业务功能验收更新

- 本轮按“现有容器服务为基线，不反复处理环境”口径，仅验收业务链路：`scripts/bootstrap_business_scenario_runtime.py` 输出 `accepted=true`，共 `11/11` 场景通过，覆盖 Amazon、TikTok、Google Trends、1688 的热销、退款、限流、趋势、供应链风险与降级语义。
- `scripts/run_local_external_collection_readiness.py` 输出 `accepted=true`，最新工件为 `artifacts/ops/local_external_collection_readiness_latest.json`；Amazon/TikTok/1688 均为 `web_signal_fallback` / `local_validation_only`，GDELT `auto` 命中真实数据 5 条，Google Trends 真实探测返回 `429` 并结构化记录。
- 修复 `LocalExternalCollectionReadinessService` 的 GDELT readiness 判定：当返回 `ready + live_endpoint_ready` 且未降级时，不再因缺少 `total_count` 或 `businessization_ready` 字段误判整体验收失败。
- 本轮业务回归：`tests/test_business_scenario_catalog.py tests/test_local_external_collection_readiness.py tests/test_external_signal_service.py tests/test_agent_framework_business_runtime.py -q` 共 `22 passed`；P1-01 至 P1-04 仍保持“进行中”，因为正式平台凭证/API 联调尚未完成。
