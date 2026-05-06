# MVP Scope

## MVP Goal

把“跨境电商 AI 选品”从单点算法展示变成可讲清楚的业务闭环：发现机会、生成推荐、人工审批、采购执行、销售/利润反馈、再评分、报告沉淀。

This is enough for a GitHub portfolio MVP because it demonstrates both business design and implementation depth. It should not be described as a production-ready commercial deployment until external marketplace credentials and staging ERP systems are fully connected.

## Included In The MVP

- 统一前端入口：Next.js App Shell，覆盖选品、利润中枢、管理者、分析师、采购、财务、Agent、知识库、报告中心、运营台。
- 选品主流程：任务创建、趋势/风险/利润信号聚合、GO / NO-GO 决策、推荐商品和 Top 列表。
- 审批流程：运营初审、采购复审、管理终审，带审计日志和角色边界。
- 采纳执行：本地 SCM / WMS / OMS adapter 输出采购单、仓库预留和 listing 草稿。
- 反馈闭环：OMS / CRM / FMS / WMS / BI 回流后执行再评分、利润追踪和特征资产生成。
- 公开信号：GDELT 公共新闻事件真实端点，用于全球政治、经济、贸易事件信号验证。
- 验收证据：主链路、闭环、多角色工作台、GDELT、外部采集 readiness 均有本地验收工件。

## Not Included In Public MVP

- 不承诺公开仓库直接连通 Amazon SP-API、TikTok Business API、1688 Open API，因为这些需要真实商户凭证。
- 不暴露任何真实客户、供应商、销售订单、利润明细或企业内部密钥。
- 不把监控、K8s、灾备、SLA 作为 GitHub 展示主线；这些可以作为工程扩展，不作为业务 MVP 核心卖点。
- 不把 Google Trends 429 场景包装成已稳定可用能力，应标注为受限公共源。

## Business Demo Priority

优先展示顺序：

1. 首页蓝图和多角色入口。
2. 选品工作台创建任务。
3. AI 推荐和 GO / NO-GO 决策。
4. 三段人工审批。
5. 采购采纳和 SCM / WMS / OMS 执行。
6. 财务利润、销售反馈、再评分。
7. 报告中心沉淀结果。
8. GDELT 公共新闻信号作为真实外部事件来源。

## Frontend Theme And Color Demo

多配色演示不会阻塞业务 MVP，但不应该放在验收主链路上。

- 推荐做法：先固定一个成熟主题，把截图和演示路径跑通。
- 可选增强：用 CSS variables 增加 2-3 套主题 token，只作为展示能力，不影响接口、审批和闭环数据。
- 不建议：为了多配色重构页面结构，或者让配色切换成为业务验收前置条件。

## MVP Delivery Conclusion

可以交付一个 GitHub 展示版 MVP。最佳表述是：

`本项目已完成本地业务闭环 MVP，可公开展示架构、前端工作台、验收工件和演示脚本；真实商业平台 API 接入属于凭证型增强，不阻塞个人能力展示。`
