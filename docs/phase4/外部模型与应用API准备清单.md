# 外部模型与应用 API 准备清单

> 适用目录：`D:/Project/fms`
>
> 目的：整理当前项目中会调用的外部模型、平台、业务系统与应用 API，说明需要准备什么、如何准备、当前代码如何接入、联调前如何用本地模拟推进、真实联调时如何处理。
>
> 使用原则：
>
> 1. 开发前置阶段优先使用 `mock / local-real(WSL) / remote-service` 三层模式；
> 2. 场景模拟通过 ≠ 真实联调通过；
> 3. 所有真实凭证、密钥、企业 webhook、线上模型地址都必须通过环境变量或安全配置注入，不要写死在代码里。

---

## 1. 分类总览

当前外部依赖可分为 5 类：

1. **本地模型 / 推理服务**
   - vLLM
   - Ollama
   - Triton
2. **在线 LLM / 远程模型服务**
   - OpenAI-compatible 远程 LLM
   - 未来可接入的商业模型代理
3. **外部市场 / 平台数据 API**
   - Amazon SP-API
   - TikTok Business API
   - Google Trends / SerpAPI
   - 1688 Open API
   - GDELT / 新闻类数据源
4. **企业业务系统 API**
   - SCM / WMS / OMS / CRM / FMS / BI / PaaS
5. **企业通知 / 分享 / 应用集成 API**
   - 企业微信
   - 钉钉
   - 邮件 SMTP

---

## 2. 本地模型 / 推理服务

### 2.1 vLLM

**用途**
- 本地主路径 LLM 推理
- 作为 `LLMGateway` 首选推理后端

**代码位置**
- `src/infrastructure/llm_gateway.py`
- `src/services/vllm_status_service.py`
- `src/services/inference_health_service.py`

**需要准备**
- Linux / WSL 可运行环境
- GPU（正式本地大模型时需要）
- vLLM 服务地址

**环境变量**
```env
LLM_VLLM_ENDPOINT=http://localhost:8000/v1
```

**如何准备**
- 推荐在 WSL / Linux 中部署
- 如本机 GPU 不足，可先保留 mock/local-compatible 验证

**前置开发建议**
- 没有真实 vLLM 时，先用本地 mock 或直接用 `LLMGateway` 的 fallback 验证
- 验证重点：超时、降级、熔断、恢复，而不是模型效果本身

**真实联调时要确认**
- `/chat/completions` 是否为 OpenAI-compatible
- 模型名是否可配置
- 超时与重试策略
- Token 统计字段是否可用

---

### 2.2 Ollama

**用途**
- 本地降级路径
- 本地轻量模型开发验证

**代码位置**
- `src/infrastructure/ollama_client.py`
- `src/services/ollama_status_service.py`
- `src/infrastructure/llm_gateway.py`

**需要准备**
- 本机或 WSL 已安装 `ollama`
- 至少一个模型（例如 `qwen2.5:0.5b` / 其他轻量模型）

**环境变量**
```env
LLM_OLLAMA_ENDPOINT=http://localhost:11434
```

**如何准备**
- 安装 Ollama
- 启动 `ollama serve`
- 拉取模型

**当前建议**
- 作为本地降级兜底，优先于在线 LLM
- 不建议把 Ollama 当作企业正式主推理路径

**真实联调时要确认**
- `/api/tags` 可访问
- 模型已实际拉取
- 降级响应时间 < 5s（按当前任务口径）

---

### 2.3 Triton

**用途**
- Rerank / Embedding / 多模态兼容入口

**代码位置**
- `src/services/triton_status_service.py`
- `src/services/rerank.py`
- `scripts/triton_smoke_check.py`

**需要准备**
- Linux / WSL 运行环境
- Triton 可访问地址

**环境变量**
```env
LLM_TRITON_ENDPOINT=http://localhost:8000
LLM_TRITON_ENABLED=false
```

**前置开发建议**
- 没有真实 Triton 时先使用 `scripts/mock_services.py --triton`

---

## 3. 在线 LLM / 远程模型服务

### 3.1 OpenAI-compatible 远程 LLM

**用途**
- 预留在线模型能力
- 在 `remote-service` 模式下作为可选远程能力

**代码位置**
- `src/services/service_gateway.py`
- `src/infrastructure/remote_llm_client.py`
- `src/api/v1/endpoints/llm.py`

**需要准备**
- 远程服务地址
- API Key / Header / Scheme
- 模型名称

**环境变量**
```env
SERVICE_MODE_LLM_MODE=remote-service
SERVICE_MODE_LLM_BASE_URL=http://localhost:8000/api/v1
SERVICE_MODE_ENABLE_FALLBACK=true
LLM_API_KEY=
LLM_API_AUTH_HEADER=Authorization
LLM_API_AUTH_SCHEME=Bearer
LLM_API_MODEL_NAME=
```

**如何准备**
- 优先接入 OpenAI-compatible 网关或公司统一模型代理
- 保留本地 fallback

**处理建议**
- 远程在线模型不是当前默认依赖
- 必须允许失败后自动回退本地路径
- 成本、审计、限额必须一起考虑

---

## 4. 外部市场 / 平台数据 API

### 4.1 Amazon SP-API

**代码位置**
- `src/infrastructure/amazon_sp_api_client.py`
- `src/agents/data_collection.py`

**需要准备**
- Amazon 开发者账号
- SP-API 凭证
- Marketplace / Region 参数

**前置开发建议**
- 优先使用场景模拟：`artifacts/mock_scenarios/external_api/`
- 可通过 `scripts/mock_services.py --external-api` 验证调用链

**真实联调要确认**
- 凭证是否有效
- 限流策略
- 商品、销量、BSR、评价字段是否齐全
- 失败时是否结构化返回错误

---

### 4.2 TikTok Business API

**代码位置**
- `src/infrastructure/tiktok_business_client.py`
- `src/agents/data_collection.py`

**需要准备**
- TikTok Business Access Token
- 业务账号权限

**前置开发建议**
- 先用 mock 场景验证热视频、达人、标签热度路径

**真实联调要确认**
- 区域参数
- 返回字段稳定性
- 分页与限流

---

### 4.3 Google Trends / SerpAPI

**代码位置**
- `src/infrastructure/google_trends_client.py`
- `src/agents/data_collection.py`

**需要准备**
- Google Trends 可用接入方式
- 或 SerpAPI Key

**前置开发建议**
- 用场景模拟“热度暴涨 / 热度回落 / 空结果”

**真实联调要确认**
- 地域参数
- 时间窗口
- 增长率计算输入是否稳定

---

### 4.4 1688 Open API

**代码位置**
- `src/infrastructure/ali1688_open_client.py`
- `src/agents/data_collection.py`

**需要准备**
- AppKey / AppSecret
- 开放平台权限

**前置开发建议**
- 先模拟供应商报价、MOQ、交期波动场景

**真实联调要确认**
- 供应商报价字段
- MOQ
- 阶梯价格
- 交期

---

### 4.5 GDELT / 新闻 / 外部信号源

**代码位置**
- 相关 external signal / data collection 代码路径

**需要准备**
- 端点地址
- 查询参数
- 频率限制认知

**前置开发建议**
- 模拟政治/贸易/物流事件冲击场景

---

## 5. 企业业务系统 API

### 5.1 SCM / WMS / OMS / CRM / FMS / BI / PaaS

**代码位置**
- `src/infrastructure/scm_client.py`
- `src/infrastructure/wms_client.py`
- `src/infrastructure/oms_client.py`
- `src/infrastructure/crm_client.py`
- `src/infrastructure/fms_client.py`
- `src/infrastructure/bi_client.py`
- `src/infrastructure/paas_client.py`
- `src/api/v1/endpoints/integration.py`

**需要准备**
- endpoint
- API key / secret
- path 约定
- 健康检查地址
- 回调 token（如果有）

**前置开发建议**
- 优先 `file://` + `artifacts/erp_local/*`
- 再切 HTTP mock
- 最后切真实 staging / 生产类环境

**如何准备**
- 明确每个系统：
  - 地址
  - 鉴权方式
  - 健康检查路径
  - 数据模型
  - 回调模型

**处理建议**
- 先跑通合同/字段/状态
- 再跑闭环：采纳 -> 下单 -> 库存预留 -> 上架 -> 反馈回流

---

## 6. 企业通知 / 分享 / 应用集成 API

### 6.1 企业微信 / 钉钉

**用途**
- 报告分享
- 预警通知
- 审批消息

**需要准备**
- webhook URL
- 安全策略
- 签名/secret（如启用）

**环境变量（示意）**
```env
WECHAT_WEBHOOK_URL=
DINGTALK_WEBHOOK_URL=
```

**前置开发建议**
- 本地只验证 payload 构造与发送抽象
- 真实 webhook 由企业侧提供后再联通

---

### 6.2 邮件 SMTP

**需要准备**
- SMTP server
- 用户名/密码
- 发件人/收件人

**环境变量**
```env
EMAIL_SMTP_SERVER=
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_TO=
```

---

## 7. 推荐联调顺序

建议顺序：

1. **场景模拟通过**
   - `scripts/mock_services.py`
   - `artifacts/mock_scenarios/`
2. **本地 Linux / WSL 环境通过**
   - Kong / OpenSearch / Ollama / 本地模型
3. **真实 staging / sandbox 联调**
4. **真实生产类环境联调**

---

## 8. 准备清单模板（每个外部 API 都建议补齐）

建议每个外部 API 在接入前，都整理以下 8 项：

1. 系统名称
2. 用途
3. endpoint/base url
4. 鉴权方式
5. 需要的凭证
6. 限流/超时/重试要求
7. 场景模拟文件是否已补
8. 真实联调负责人/环境状态

---

## 9. 当前最需要优先准备的依赖

按当前项目推进优先级，建议优先准备：

1. Ollama 本机安装与模型拉取
2. OpenSearch / Elasticsearch 的稳定本地运行
3. Kong 在 WSL/Linux 中的本地运行
4. Amazon / TikTok / Google Trends / 1688 的场景模拟数据
5. 企业侧 webhook / staging 资料（后续联调时再补）

---

## 10. 当前建议配套文档一起看

- `docs/local-runtime/README.md`
- `docs/local-runtime/01_统一入口与启动总览.md`
- `artifacts/mock_scenarios/README.md`
- `2026041601任务分解清单.md`
- `2026041601任务分解清单-验收标准.md`

这些文档组合起来，足够支撑后续持续推进本地可落地开发与真实联调准备。
