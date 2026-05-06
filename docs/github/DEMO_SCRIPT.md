# Demo Script

## Demo Positioning

演示目标：用 8-12 分钟证明这个系统不是“AI 页面拼装”，而是围绕跨境电商选品真实业务角色设计的闭环产品。

推荐开场：

`这是一个跨境电商 AI 选品 PMS。它从趋势和事件信号开始，输出选品决策，经过运营、采购、管理层审批，再进入本地 ERP 执行，最后把销售、评价、利润和库存反馈回选品模型，形成可复盘的利润闭环。`

## 0. Preparation

- 启动后端、本地依赖和前端。
- 准备浏览器访问 `http://localhost:3000`。
- 准备截图目录：`docs/github/screenshots`。
- 准备一个演示关键词：`蓝牙耳机` 或 `bluetooth headset`。
- 准备目标市场：`US`。
- 准备预算：`50000`。

## 1. Homepage And Role Matrix

页面：`/`

讲法：

- 这是统一工作台入口，不是单页面 demo。
- 首页展示选品、利润、管理者、分析师、采购、财务、报告和运营治理入口。
- 未登录时也能作为蓝图预览，方便 GitHub 截图展示。

截图建议：`01-home-blueprint.png`

## 2. Selection Workbench

页面：`/workbench/selection`

操作：

- 创建选品任务，输入关键词、品类、目标市场和预算。
- 展示任务总数、待审批、高风险任务、平均 ROI、GO 决策数。
- 展示实时流状态、关键趋势/决策、Agent 步骤和准确率趋势。

讲法：

- 运营角色不需要看底层模型日志，重点看“推荐什么、为什么、风险在哪、下一步谁审批”。
- WebSocket 优先、SSE 回退属于体验保障，不作为业务演示主线。

截图建议：`02-selection-workbench.png`

## 3. AI Decision Output

页面：`/workbench/selection` 或任务详情区

讲法：

- 系统输出 GO / NO-GO、推荐商品、信心分、利润测算、风险提示和趋势方向。
- 当前验收样例中，蓝牙耳机美国站任务最终形成 `GO` 决策。
- 业务结果不是只停留在推荐，而是继续进入审批和执行。

截图建议：`03-ai-decision.png`

## 4. Approval Chain

页面：`/approval`、`/manager` 或工作台审批区

操作：

- 展示运营初审、采购复审、管理终审。
- 展示审批历史和审计记录。

讲法：

- AI 不直接替代业务决策，关键节点保留 human-in-the-loop。
- 审批链路支持运营判断趋势、采购判断供应商和 MOQ、管理者判断预算与风险。

截图建议：`04-approval-chain.png`

## 5. Procurement Execution

页面：`/procurement`

讲法：

- 采纳后进入本地 SCM / WMS / OMS adapter。
- 系统生成采购单、仓库预留和 listing draft。
- 演示重点是“从推荐进入执行”，不是停留在报告。

验收样例可讲数字：

- 数量：`240`。
- 推荐价：`39.99`。
- 执行链：`SCM pending_review`、`WMS reserved`、`OMS draft_created`。

截图建议：`05-procurement-execution.png`

## 6. Finance And Profit Feedback

页面：`/finance`、`/dashboard`

讲法：

- 执行后系统拉取销售、评价、利润、库存和投诉信号。
- 本地闭环样例完成再评分：`85.8`，结果仍为 `GO`。
- 财务视角重点看毛利、毛利率、库存风险、ROI 和每日 KPI。

验收样例可讲数字：

- 7 日销量：`12`。
- 评价分：`4.6`。
- 评价数：`13`。
- 毛利：`139.0`。
- 毛利率：`28.5%`。
- 可用库存：`18`。

截图建议：`06-profit-feedback.png`

## 7. Report Center

页面：`/reports`

讲法：

- 报告中心用于把选品过程沉淀成可分享、可归档、可复盘的正式输出。
- 这里适合展示个人产品能力：不只是做表单，而是让业务结论能被管理层消费。

截图建议：`07-report-center.png`

## 8. Public Event Signal

页面：`/trends` 或验收证据页

讲法：

- GDELT 是真实公共新闻事件端点，已在本地验收中返回 5 条新闻事件。
- 该能力用于补充全球政治、经济、贸易事件对品类机会和风险的影响。
- Amazon、TikTok、1688 属于凭证型平台源，公开 MVP 中按本地 adapter contract 演示，不伪装成已持有真实商户权限。

截图建议：`08-public-signal-gdelt.png`

## 9. Close With Acceptance Evidence

页面：`docs/github/ACCEPTANCE_EVIDENCE.md`

讲法：

- MVP 不是只凭口头说明，已保留主链路、闭环、多角色工作台、GDELT 和 readiness 验收工件。
- GitHub 展示时建议只放摘要，不上传大体积 runtime DB、日志或密钥。

截图建议：`09-acceptance-evidence.png`

## 10. Suggested Closing Statement

`这个 MVP 展示的是我把 AI 能力落到业务系统里的方法：先定义角色和决策链路，再做 AI 推荐和审批闭环，最后用执行反馈和利润指标验证推荐是否真的有业务价值。`
