# 跨境电商AI选品系统PMS—详细设计说明书

> **版本**：V11.0
> **创建日期**：2026-04-26
> **项目代号**：Project Aegis
> **文档状态**：正式版（V9+V10合并版）
> **基于版本**：V9.0 + V10.0
> **参考文档**：
> - 跨境电商AI选品系统PMS—详细设计说明书V3~V10
> - 跨境电商AI选品系统PMS—企业级设计方案
> - 跨境电商AI选品系统PMS—架构与业务设计文档
> - 跨境电商AI选品系统PMS—分层架构与数据流协作
> - 跨境电商ERP系统——详细设计说明书V7/V8
> - 跨境电商ERP-需求规格说明书V3
> - 交叉验证ERP与PMS详细设计交互问题和优化建议

------

## 目录

### 第一卷：系统概述

1. **引言**
   - 1.1 文档目的
   - 1.2 文档范围
   - 1.3 术语定义
   - 1.4 V9版本变更说明 ★[基于交叉验证优化]
   - 1.5 V10版本交叉验证优化说明 ★[V10新增]
   - 1.6 当前实现态、近期实现态与目标态说明 ★[V10新增]
2. **系统概述**
   - 2.1 系统定位
   - 2.2 系统边界 ★[V9强化：PMS不写ERP终态]
   - 2.3 核心功能
   - 2.4 非功能需求
3. **架构分阶段策略 ★[V9新增]**
   - 3.1 分阶段架构口径
   - 3.2 能力实现状态标注规范
   - 3.3 版本适用说明

### 第二卷：架构与微服务详细设计

4. **系统架构详细设计**
   - 4.1 部署架构
   - 4.2 微服务划分总览
   - 4.3 服务通信设计
   - 4.4 ERP 14域集成架构
5. **数据架构详细设计**
   - 5.1 数据模型设计
   - 5.2 数据库设计
   - 5.3 数据流设计
   - 5.4 数据主权与主数据边界 ★[V9新增]
   - 5.5 数据可信等级 ★[V9新增]
6. **AI架构详细设计**
   - 6.1 Agent编排设计
   - 6.2 RAG知识库设计
   - 6.3 LLM服务设计
   - 6.4 多模态服务设计

### 第三卷：ERP 14域详细设计

7. **工作台域 (DASHBOARD) ★[AI看板]**
8. **组织权限域 (IAM) ★[V9强化：数据权限维度]**
9. **产品开发域 (PDM) ★[AI选品] ★[V9强化：PMS-PDM边界]**
10. **销售运营域 (SOM) ★[V9强化：Listing归属确认]**
11. **广告管理域 (ADS) ★[AI优化]**
12. **订单域 (OMS) ★[AI风控] ★[V9强化：订单链路完整化]**
13. **供应链域 (SCM) ★[AI补货]**
14. **仓储域 (WMS) ★[AI预测]**
15. **FBA/海外仓域 (FBA)**
16. **物流域 (TMS)**
17. **客服售后域 (CRM) ★[AI情感]**
18. **财务域 (FMS)**
19. **商业智能域 (BI) ★[KPI]**
20. **系统设置域 (SYS)**

### 第四卷：PMS模块实现详细设计

21. **选品服务详细设计**
22. **Agent服务详细设计**
23. **知识域服务详细设计**
24. **AI域服务详细设计**
25. **数据域服务详细设计**
26. **集成域服务详细设计 ★[V9强化：建议池+草稿模式]**
27. **报告域服务详细设计**
28. **WebSocket接口详细设计**

### 第五卷：PMS与ERP 14域交互设计

29. **PMS-ERP集成架构 ★[V9强化：建议/草稿/审批模式]**
30. **PMS数据输入设计（AI感知）**
31. **PMS数据输出设计（AI驱动） ★[V9强化：不写终态]**
32. **建议执行状态机 ★[V9新增]**
33. **闭环反馈设计**
34. **ERP 14域集成客户端详细设计**
35. **集成事件与异步通信**
36. **集成异常处理与容错**
37. **API路径规范 ★[V9新增]**
38. **数据权限与审计上下文 ★[V9新增]**

### 第六卷：前端与运维

39. **前端架构设计**
40. **部署架构设计**
41. **监控与运维设计**
42. **安全与权限设计 ★[V9强化：双主体模型]**

### 附录

- 附录A：V8→V9→V11变更记录
- 附录B：术语表
- 附录C：ERP 14域接口对照表
- 附录D：PMS-ERP 14域交互矩阵
- 附录E：数据主权与主数据边界说明
- 附录F：数据可信等级定义
- 附录G：V10交叉验证优化补充设计 ★[V10新增]
- 附录H：PMS-ERP权限、接口、事件、数据主权矩阵 ★[V10新增]

------

# 第一卷：系统概述

## 1. 引言

### 1.1 文档目的

本文档旨在详细描述跨境电商AI选品系统PMS的架构与模块实现设计。V9版本基于V8，重点解决交叉验证中发现的ERP与PMS交互问题，核心优化包括：

1. **PMS不写ERP终态**：PMS只写入建议池/草稿/待审批动作，ERP审批后执行
2. **API路径规范化**：统一ERP接口路径为`/api/internal/v1/`，PMS专用
3. **数据权限维度补全**：IAM支持10个权限维度，PMS调用必须携带完整审计上下文
4. **数据主权明确**：明确每类数据的主系统归属
5. **数据可信等级**：为每类数据源定义可信等级
6. **建议执行状态机**：建立完整的建议生命周期状态机
7. **订单链路完整化**：OMS订单模型扩展为完整链路
8. **PDM-PMS边界冻结**：PMS=决策建议，PDM=产品开发承接
9. **Listing归属确认**：Listing归SOM，OMS不创建Listing
10. **分阶段架构策略**：区分当前实现态、近期演进态和目标规划态

### 1.2 文档范围

本文档涵盖系统的全部功能模块，包括：选品服务、Agent编排服务、知识库服务、数据中台服务、集成服务、前端工作台，以及ERP 14域详细设计和PMS-ERP交互规范。

### 1.3 术语定义

| 术语 | 英文 | 说明 |
| :--- | :--- | :--- |
| **PMS** | Product Management System | 产品管理系统（AI选品系统） |
| **Agent** | AI Agent | AI智能体 |
| **RAG** | Retrieval-Augmented Generation | 检索增强生成 |
| **LLM** | Large Language Model | 大语言模型 |
| **ERP** | Enterprise Resource Planning | 企业资源计划系统 |
| **CDC** | Change Data Capture | 变更数据捕获 |
| **TAM** | Total Addressable Market | 总可寻址市场 |
| **ROI** | Return on Investment | 投资回报率 |
| **BSR** | Best Sellers Rank | 畅销榜排名 |
| **ACOS** | Advertising Cost of Sales | 广告成本销售比 |
| **ROAS** | Return on Ad Spend | 广告支出回报率 |
| **CTR** | Click-Through Rate | 点击率 |
| **DASHBOARD** | Dashboard Domain | 工作台域 |
| **IAM** | Identity & Access Management | 组织权限域 |
| **PDM** | Product Development Management | 产品开发域 |
| **SOM** | Sales Operation Management | 销售运营域 |
| **ADS** | Advertising Management | 广告管理域 |
| **OMS** | Order Management System | 订单域 |
| **SCM** | Supply Chain Management | 供应链域 |
| **WMS** | Warehouse Management System | 仓储域 |
| **FBA** | Fulfillment by Amazon | FBA/海外仓域 |
| **TMS** | Transportation Management System | 物流域 |
| **CRM** | Customer Relationship Management | 客服售后域 |
| **FMS** | Financial Management System | 财务域 |
| **BI** | Business Intelligence | 商业智能域 |
| **SYS** | System Settings | 系统设置域 |

### 1.4 V9版本变更说明

| 变更项 | V8 | V9 | 优化来源 |
| :--- | :--- | :--- | :--- |
| **PMS写入模式** | 直接创建ERP业务单据 | 只写建议池/草稿/待审批动作 | 交叉验证4.2 |
| **API路径** | `/api/v1/...` 混用 | 统一`/api/internal/v1/...` | 交叉验证3.5 |
| **数据权限维度** | 租户+组织+店铺 | 10维(tenant/org/dept/store/marketplace/channel/warehouse/supplier/category/data_level) | 交叉验证3.4 |
| **审计上下文** | 仅tenant_id+user_id | tenant_id+actor_id+actor_type+scope+purpose+trace_id | 交叉验证3.4 |
| **数据主权** | 未明确 | 每类数据明确主系统归属 | 交叉验证5.4 |
| **数据可信等级** | 无 | A/B/C/D四级 | 交叉验证4.3 |
| **建议状态机** | 简单pending/completed | 10态完整状态机 | 交叉验证7.3 |
| **订单链路** | 简化销售订单 | 平台订单→ERP订单→履约单→包裹→运单→售后 | 交叉验证3.6 |
| **PDM-PDM边界** | 职责重叠 | PMS=决策建议，PDM=产品开发承接 | 交叉验证5.2 |
| **Listing归属** | OMS有创建Listing接口 | Listing归SOM，OMS不创建Listing | 交叉验证5.1 |
| **AI能力分布** | ERP各域与PMS重复 | PMS=跨域AI决策中心，ERP=领域规则+执行 | 交叉验证5.3 |
| **权限模型** | 单一用户主体 | 双主体模型(用户主体+服务主体) | 交叉验证4.5 |
| **分阶段架构** | 目标态混用 | 四阶段架构口径+能力状态标注 | 交叉验证3.2/4.1 |
| **推荐输出** | score+建议 | score+evidence+data_sources+confidence+risk_flags+explainability | 交叉验证4.3 |
| **接入方式** | 混用API/CDC/BI | 按数据类型明确接入方式 | 交叉验证4.4 |

### 1.5 V10版本交叉验证优化说明 ★[V10新增]

V10版本以V8完整设计为基础，结合《交叉验证ERP与PMS详细设计交互问题和优化建议》进行收敛和增强。V10不推翻V8的业务模块、服务拆分、数据库设计和ERP 14域覆盖范围，而是在系统边界、权限模型、接口规范、数据主权、建议执行闭环、实现阶段口径等方面进行统一。

#### 1.5.1 V10核心修订原则

| 原则 | V10统一口径 |
|---|---|
| ERP主权原则 | ERP是经营数据真相源、审批层、执行层和审计主控 |
| PMS定位原则 | PMS是外部数据采集、AI分析、选品推荐和跨域经营建议系统 |
| 非侵入原则 | PMS不得绕过ERP审批流直接写入正式业务终态数据 |
| 建议先行原则 | PMS输出进入ERP建议池、草稿单据或待审批动作 |
| 权限继承原则 | PMS读取ERP数据必须继承用户/服务主体的数据权限范围 |
| 可解释原则 | PMS所有AI建议必须包含证据链、数据源、置信度和风险标识 |
| 闭环反馈原则 | ERP执行结果、拒绝原因、业务效果必须回流PMS用于模型优化 |
| 阶段收敛原则 | 当前实现态、近期实现态、目标态和外部依赖必须分开标注 |

#### 1.5.2 V10重点优化项

1. 明确ERP V8/V10为ERP侧主设计口径，PMS V10为PMS侧主设计口径。
2. 明确PMS与ERP的系统边界：PMS生成建议，ERP完成审批和执行。
3. 统一ERP 14域交互边界，特别是PDM、SOM、ADS、OMS、SCM、WMS、FMS、BI职责。
4. 修正Listing草稿归属：Listing草稿归SOM，不归OMS。
5. 修正广告优化建议入口：PMS广告建议进入ADS，不直接进入SOM。
6. 补充IAM数据权限维度：tenant、org、department、store、marketplace、channel、warehouse、supplier、category、data_level。
7. 补充PMS双主体权限模型：用户主体与服务主体。
8. 补充ERP/PMS统一API路径、鉴权、幂等、审计、trace规范。
9. 补充PMS数据源可信等级、AI建议输出标准和建议执行状态机。
10. 补充API、CDC、事件、BI/数仓四类集成方式的适用边界。

### 1.6 当前实现态、近期实现态与目标态说明 ★[V10新增]

V10要求所有能力按以下状态标注，避免将目标态误判为当前交付范围。

| 状态 | 含义 | 约束 |
|---|---|---|
| 当前实现态 | 当前版本必须设计和实现的能力 | 纳入开发、测试、验收 |
| 近期实现态 | 下一阶段或近期迭代计划能力 | 完成接口预留和数据模型兼容 |
| 目标态 | 中长期架构规划能力 | 不作为当前交付阻塞项 |
| 外部依赖 | 依赖ERP、平台API、三方数据或模型能力 | 必须标注依赖方、降级策略和验收条件 |

#### 1.6.1 PMS能力状态基线

| 能力 | V11状态 | 说明 |
|---|---|---|
| 选品任务、选品评分、推荐报告 | 当前实现态 | PMS核心能力 |
| ERP经营数据读取 | 当前实现态 | 通过ERP授权API或同步数据读取 |
| 建议池/草稿动作输出 | 当前实现态 | 不直接写正式终态单据 |
| 采纳、拒绝、执行反馈闭环 | 当前实现态 | ERP反馈执行状态和业务效果 |
| ADS广告优化闭环 | 近期实现态 | 依赖ERP ADS域接口和广告平台数据 |
| FBA库存与库容预测 | 近期实现态 | 依赖ERP FBA/WMS库存数据 |
| Multi-Agent自动编排 | 近期实现态 | 必须受权限、审批和开关约束 |
| CDC + Kafka + Flink全量实时链路 | 目标态 | 按域逐步开启，不要求一次性完成 |
| 自动创建采购单/Listing正式单据 | 不允许直接执行 | 只能生成草稿、建议或待审批动作 |

------

## 2. 系统概述

### 2.1 系统定位

本系统是跨境电商企业的**AI决策辅助系统**，通过AI技术实现智能选品决策、市场趋势预测、竞品分析和供应链优化。系统与ERP 14个业务域深度集成，形成"AI建议→ERP审批→ERP执行→效果反馈→模型优化"的闭环。

**核心原则 ★[V9强化]**：

| 原则 | 说明 |
| :--- | :--- |
| **ERP是经营数据真相源** | 所有业务主数据、正式单据、审批流均在ERP |
| **PMS是AI决策辅助系统** | PMS生成建议、草稿、预警，不直接创建ERP正式业务单据 |
| **PMS不绕过ERP审批流** | PMS的建议必须经ERP权限校验和审批后才能执行 |
| **PMS=跨域AI决策中心** | 跨域智能推荐由PMS统一编排，ERP域内保留轻量规则 |
| **数据主权清晰** | 每类数据有明确的主系统归属 |

**系统双重角色**：

| 角色 | 说明 |
| :--- | :--- |
| **AI决策层** | 基于多源数据生成选品建议、定价策略、补货建议、广告优化、风险预警等智能决策 |
| **AI建议层 ★[V9修正]** | 通过标准化接口将智能决策下发ERP建议池/草稿，经ERP审批后执行 |

### 2.2 系统边界 ★[V9强化]

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     AI选品系统 (PMS)                                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  选品服务    │  │  Agent服务  │  │ 知识库服务  │  │  报告服务   │  │  数据中台   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                              │
│  │  集成服务    │  │  AI中台     │  │  建议管理   │  │  广告优化   │                              │
│  └──────┬──────┘  └─────────────┘  └──────┬──────┘  └─────────────┘                              │
│         │                                  │                                                        │
│    ┌────┴──────────────────────────────────┴──────────────────────────────────────────────────┐   │
│    │                    Integration Service (14域客户端 + 建议池接口) ★[V9]                       │   │
│    └────┬──────────────────────────────────────────────────────────────────────────────────────┘   │
├─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│         │ /api/internal/v1/... (PMS专用) ★[V9]                                                     │
│         │ Kafka CDC / WebSocket                                                                   │
│         ▼                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              ERP系统 (14个业务域) — 经营数据真相源 ★[V9]                        │   │
│  │                                                                                              │   │
│  │  ┌──────────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                              │   │
│  │  │DASHBOARD │ │ IAM │ │ PDM │ │ SOM │ │ ADS │ │ OMS │ │ SCM │                              │   │
│  │  │ AI看板   │ │权限 │ │AI选品│ │销售 │ │AI优化│ │AI风控│ │AI补货│                              │   │
│  │  └──────────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                              │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                                  │   │
│  │  │ WMS │ │ FBA │ │ TMS │ │ CRM │ │ FMS │ │ BI  │ │ SYS │                                  │   │
│  │  │AI预测│ │海外仓│ │物流 │ │AI情感│ │财务 │ │ KPI │ │设置 │                                  │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                                  │   │
│  │                                                                                              │   │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────────┐│   │
│  │  │  建议接收层 ★[V9新增]                                                                      ││   │
│  │  │  Recommendation / Draft / PendingAction / RiskAlert / InsightCard                         ││   │
│  │  │  → 权限校验 → 审批流 → 执行 → 反馈                                                         ││   │
│  │  └──────────────────────────────────────────────────────────────────────────────────────────┘│   │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                     外部系统                                                        │
│  Amazon API │ TikTok API │ 1688 API │ Google Trends │ Google Ads API │ 爬虫平台                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**PMS写入边界 ★[V9关键修正]**：

| PMS可写入ERP的类型 | 说明 | 是否需审批 |
| :--- | :--- | :--- |
| **Recommendation** | AI建议（选品/补货/定价/广告/风险） | 是 |
| **Draft** | 草稿单据（Listing草稿/采购草稿） | 是 |
| **PendingAction** | 待审批动作 | 是 |
| **RiskAlert** | 风险预警 | 否（仅通知） |
| **InsightCard** | AI洞察卡片 | 否（仅展示） |

| PMS不可写入ERP的类型 ★[V9禁止] | 说明 |
| :--- | :--- |
| 正式采购订单 | 必须经ERP SCM审批后创建 |
| 正式Listing上架 | 必须经ERP SOM审批后上架 |
| 正式广告活动 | 必须经ERP ADS审批后创建 |
| 正式入库货件 | 必须经ERP FBA审批后创建 |
| 库存调拨 | 必须经ERP WMS审批后执行 |

### 2.3 核心功能

| 功能模块 | 子功能 | 说明 | ERP交互域 | 实现状态 ★[V9] |
| :--- | :--- | :--- | :--- | :--- |
| **选品决策** | 任务创建、智能分析、推荐列表、采纳提交 | 核心选品流程 | PDM/SCM/WMS/SOM | 近期实现 |
| **市场洞察** | 市场规模、趋势分析、竞品格局、机会评分 | 市场分析能力 | OMS/BI/SOM | 近期实现 |
| **产品规划** | 评论分析、痛点挖掘、规格推荐、差异化定位 | 产品定义能力 | CRM/PDM | 近期实现 |
| **商业化分析** | 成本测算、利润分析、定价策略、ROI预测 | 商业化决策 | FMS/SCM/TMS/FBA | 近期实现 |
| **广告优化** | 广告策略建议、关键词优化、ACOS优化 | 广告智能 | ADS/SOM | 目标态 |
| **风险评估** | 专利风险、舆情风险、供应链风险、合规风险 | 风险识别 | SCM/WMS/TMS/CRM | 近期实现 |
| **知识库** | 文档管理、混合检索、知识图谱、多模态知识 | 企业记忆 | - | 近期实现 |
| **报告生成** | PDF/Excel/PPT生成、图表渲染、一键分享 | 报告输出 | DASHBOARD | 近期实现 |
| **数据采集** | API采集、爬虫采集、CDC采集 | 数据获取 | 全域CDC | 近期实现 |
| **智能建议** | 选品/补货/定价/广告/风险建议 | AI驱动执行 | 全域 | 目标态 |
| **闭环反馈** | 执行反馈、效果追踪、模型优化 | 持续改进 | BI/DASHBOARD | 目标态 |
| **看板展示** | AI看板、KPI仪表盘、实时监控 | 决策可视化 | DASHBOARD/BI | 近期实现 |

### 2.4 非功能需求

| 类别 | 需求 | 指标 |
| :--- | :--- | :--- |
| **性能** | API响应时间 | P95 < 200ms |
| **性能** | 选品任务耗时 | < 4小时 |
| **性能** | LLM推理延迟 | < 3s |
| **性能** | ERP集成调用延迟 | P95 < 500ms |
| **可用性** | 系统可用性 | ≥ 99.9% |
| **可扩展性** | 并发用户数 | ≥ 1000 |
| **安全性** | 数据加密 | TLS 1.3 + AES-256 |
| **安全性** | 认证方式 | JWT + OAuth2 |
| **安全性** | ERP接口认证 | API Key + HMAC签名 |
| **安全性** | 审计追踪 ★[V9] | 所有ERP调用记录完整审计日志 |
| **可观测性** | 监控覆盖 | 100%核心服务 |
| **可靠性** | ERP集成重试 | 3次指数退避 |
| **一致性** | 采纳执行一致性 | 最终一致性（秒级） |

------

## 3. 架构分阶段策略 ★[V9新增]

### 3.1 分阶段架构口径

| 阶段 | 架构形态 | PMS能力范围 | ERP集成范围 |
| :--- | :--- | :--- | :--- |
| **一期** | 模块化单体 + 逻辑领域分层 | 选品决策+市场洞察+知识库+报告 | PDM/SOM/OMS/BI (API查询) |
| **二期** | 关键域服务化 | +商业化分析+风险评估+闭环反馈 | +SCM/WMS/FMS (API+CDC) |
| **三期** | 事件驱动 + AI服务化 | +广告优化+智能建议+Agent编排 | +ADS/FBA/CRM/TMS (API+CDC+事件) |
| **四期** | 完整微服务 / 插件平台 | +多租户+灰度+自动化执行 | +DASHBOARD/IAM/SYS (全量集成) |

### 3.2 能力实现状态标注规范

本文档中每个能力、接口、表、Agent、数据源均标注实现状态：

| 状态标签 | 含义 | 图标 |
| :--- | :--- | :--- |
| **已实现** | 当前代码已完成 | ✅ |
| **近期实现** | 当前版本计划（一期/二期） | 🔵 |
| **目标态** | 架构规划（三期/四期） | 🟡 |
| **外部依赖** | 依赖ERP或第三方系统能力 | 🔴 |

### 3.3 版本适用说明

| 文档 | 角色 | 说明 |
| :--- | :--- | :--- |
| **PMS V9（本文档）** | 当前详细设计主口径 | 所有PMS开发以此为准 |
| **ERP V8** | ERP详细设计主口径 | PMS-ERP交互以ERP V8接口定义为准 |
| **ERP需求规格说明书V3** | 业务需求基线 | 功能范围以需求规格为准 |
| **PMS V3~V8** | 历史演进参考 | 不作为当前实现依据 |

------

# 第二卷：架构与微服务详细设计

## 4. 系统架构详细设计

### 4.1 部署架构

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          生产环境部署架构                                             │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                    ┌─────────────────────────┐                                      │
│                                    │      CDN (CloudFront)    │                                      │
│                                    └───────────┬─────────────┘                                      │
│                                                │                                                    │
│                                    ┌───────────▼─────────────┐                                      │
│                                    │   Load Balancer (ALB)    │                                      │
│                                    └───────────┬─────────────┘                                      │
│                                                │                                                    │
│  ┌─────────────────────────────────────────────┼─────────────────────────────────────────────┐    │
│  │                              Kubernetes集群 (多AZ)                                          │    │
│  │  ┌──────────────────────────────────────────┼──────────────────────────────────────────┐  │    │
│  │  │                           Namespace: gateway                                        │  │    │
│  │  │                    ┌──────────────────────┴──────────────────────┐                  │  │    │
│  │  │                    │           Kong Gateway (3 Pods)              │                  │  │    │
│  │  │                    └──────────────────────┬──────────────────────┘                  │  │    │
│  │  └──────────────────────────────────────────┼──────────────────────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────┼──────────────────────────────────────────┐  │    │
│  │  │                           Namespace: app                                            │  │    │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │  │    │
│  │  │  │ selection   │  │   agent     │  │ knowledge   │  │   report    │                 │  │    │
│  │  │  │  service    │  │  service    │  │  service    │  │  service    │                 │  │    │
│  │  │  │ replicas:4  │  │ replicas:4  │  │ replicas:3  │  │ replicas:2  │                 │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                 │  │    │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │  │    │
│  │  │  │    llm      │  │    rag      │  │ embedding   │  │  frontend   │                 │  │    │
│  │  │  │  service    │  │  service    │  │  service    │  │  (Next.js)  │                 │  │    │
│  │  │  │ replicas:3  │  │ replicas:3  │  │ replicas:2  │  │ replicas:2  │                 │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                 │  │    │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │  │    │
│  │  │  │ integration │  │   erp-      │  │   ads       │  │suggestion   │                 │  │    │
│  │  │  │  service    │  │  sync       │  │  service    │  │  service    │                 │  │    │
│  │  │  │ replicas:3  │  │ replicas:2  │  │ replicas:2  │  │ replicas:2  │                 │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                 │  │    │
│  │  └──────────────────────────────────────────────────────────────────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────┐  │    │
│  │  │                           Namespace: data                                             │  │    │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │  │    │
│  │  │  │ PostgreSQL  │  │   Qdrant    │  │   Redis     │  │   Kafka     │                  │  │    │
│  │  │  │ Patroni(3)  │  │ Cluster(3)  │  │ Sentinel(6) │  │ Cluster(3)  │                  │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                  │  │    │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                                   │  │    │
│  │  │  │Elasticsearch│  │   Neo4j     │  │   MinIO     │                                   │  │    │
│  │  │  │ Cluster(3)  │  │ Cluster(3)  │  │  Cluster(4) │                                   │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘                                   │  │    │
│  │  └──────────────────────────────────────────────────────────────────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────┐  │    │
│  │  │                           Namespace: ai                                               │  │    │
│  │  │  ┌─────────────────────────────┐  ┌─────────────────────────────┐                    │  │    │
│  │  │  │      vLLM 节点池            │  │      Triton 节点池           │                    │  │    │
│  │  │  │  Qwen2.5-72B (4×A100)      │  │  LLaVA-13B (2×A10)          │                    │  │    │
│  │  │  │  DeepSeek-V3 (2×A100)      │  │  BGE/CLIP (2×A10)           │                    │  │    │
│  │  │  └─────────────────────────────┘  └─────────────────────────────┘                    │  │    │
│  │  └──────────────────────────────────────────────────────────────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 微服务划分总览

| 服务 | 职责 | 技术栈 | 端口 | 实现状态 |
| :--- | :--- | :--- | :--- | :--- |
| **selection-service** | 选品任务管理、推荐生成 | FastAPI + SQLAlchemy | 8001 | 🔵 |
| **agent-service** | Agent编排、LangGraph工作流 | FastAPI + LangGraph | 8002 | 🔵 |
| **knowledge-service** | 知识库管理、RAG检索 | FastAPI + LlamaIndex | 8003 | 🔵 |
| **report-service** | 报告生成、PDF/Excel/PPT导出 | FastAPI + Jinja2 | 8004 | 🔵 |
| **data-service** | 数据采集、特征平台 | FastAPI + Airflow | 8005 | 🔵 |
| **integration-service** | ERP 14域集成、CDC消费 | FastAPI + Kafka | 8006 | 🔵 |
| **llm-service** | LLM网关、模型路由 | FastAPI + vLLM | 8007 | 🔵 |
| **rag-service** | 混合检索、Rerank | FastAPI + Qdrant | 8008 | 🔵 |
| **ads-service** | 广告优化、ACOS分析 | FastAPI | 8009 | 🟡 |
| **feature-service** | 特征存储、特征计算 | FastAPI + Feast | 8010 | 🟡 |
| **suggestion-service** | 建议管理、状态机 ★[V9] | FastAPI | 8011 | 🔵 |
| **frontend** | Web前端 | Next.js 14 | 3000 | 🔵 |
| **gateway** | API网关 | Kong | 8000 | 🔵 |

### 4.3 服务通信设计

| 通信方式 | 场景 | 技术 |
| :--- | :--- | :--- |
| **同步REST** | 服务间查询、前端API调用 | HTTP/REST + OpenAPI |
| **异步事件** | ERP数据同步、建议状态变更 | Kafka |
| **WebSocket** | Agent进度推送、实时看板 | Socket.IO |
| **gRPC** | LLM推理调用、特征服务调用 | gRPC + Protobuf |

### 4.4 ERP 14域集成架构

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PMS Integration Service — 14域集成架构 (V9)                                 │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  PMS Services Layer                                                                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │
│  │  │Selection │ │  Agent   │ │Knowledge │ │  Report  │ │   Ads    │ │Suggestion│              │  │
│  │  │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │              │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘              │  │
│  └───────┼─────────────┼────────────┼────────────┼────────────┼────────────┼───────────────────┘  │
│          │             │            │            │            │            │                         │
│  ┌───────▼─────────────▼────────────▼────────────▼────────────▼────────────▼───────────────────┐  │
│  │  ERPIntegrationService (统一集成门面)                                                          │  │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────┐    │  │
│  │  │  BaseERPClient (限流/重试/熔断/缓存/签名/审计上下文 ★[V9])                               │  │  │
│  │  └──────────────────────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                                              │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │  │
│  │  │Dashboard  │ │   IAM     │ │   PDM     │ │   SOM     │ │   ADS     │ │   OMS     │       │  │
│  │  │ Client    │ │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │       │  │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘       │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │  │
│  │  │   SCM     │ │   WMS     │ │   FBA     │ │   TMS     │ │   CRM     │ │   FMS     │       │  │
│  │  │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │       │  │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘       │  │
│  │  ┌───────────┐ ┌───────────┐                                                                  │  │
│  │  │    BI     │ │   SYS     │                                                                  │  │
│  │  │  Client   │ │  Client   │                                                                  │  │
│  │  └───────────┘ └───────────┘                                                                  │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│            │                              │                              │                           │
│     ┌──────▼──────┐              ┌───────▼──────┐              ┌───────▼──────┐                    │
│     │  REST API   │              │    Kafka     │              │  WebSocket   │                    │
│     │/api/internal│              │  CDC/事件    │              │  实时推送     │                    │
│     │  /v1/ ★[V9]│              │              │              │              │                    │
│     └─────────────┘              └──────────────┘              └──────────────┘                    │
│            │                              │                              │                           │
│  ┌─────────▼──────────────────────────────▼──────────────────────────────▼──────────────────────┐  │
│  │  ERP System (14 Domains) — 经营数据真相源 ★[V9]                                               │  │
│  │                                                                                              │  │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────────┐│  │
│  │  │  建议接收层 ★[V9新增]                                                                      ││  │
│  │  │  Recommendation / Draft / PendingAction / RiskAlert / InsightCard                         ││  │
│  │  │  → 权限校验(IAM) → 审批流 → 执行 → 结果反馈(PMS)                                            ││  │
│  │  └──────────────────────────────────────────────────────────────────────────────────────────┘│  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

------

## 5. 数据架构详细设计

### 5.1 数据模型设计

核心数据模型保持V8设计，V9新增以下模型：

**建议数据模型 ★[V9新增]**：

```python
class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(UUID, primary_key=True, default=uuid4)
    tenant_id = Column(String(36), nullable=False)
    suggestion_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    target_domain = Column(String(20), nullable=False)
    target_action = Column(String(100), nullable=False)
    suggestion_data = Column(JSONB, nullable=False)
    score = Column(Float)
    confidence = Column(Float)
    evidence = Column(JSONB)
    data_sources = Column(JSONB)
    risk_flags = Column(JSONB)
    explainability = Column(Text)
    status = Column(String(20), default="created")
    actor_id = Column(String(36), nullable=False)
    actor_type = Column(String(20), nullable=False)
    scope = Column(JSONB)
    idempotency_key = Column(String(64), unique=True)
    trace_id = Column(String(64))
    source_system = Column(String(20), default="pms")
    recommendation_id = Column(UUID)
    audit_context = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

### 5.2 数据库设计

V8所有数据库表保持不变，V9新增以下表：

```sql
CREATE TABLE suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    suggestion_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    target_domain VARCHAR(20) NOT NULL,
    target_action VARCHAR(100) NOT NULL,
    suggestion_data JSONB NOT NULL,
    score FLOAT,
    confidence FLOAT,
    evidence JSONB,
    data_sources JSONB,
    risk_flags JSONB,
    explainability TEXT,
    status VARCHAR(20) DEFAULT 'created',
    actor_id VARCHAR(36) NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    scope JSONB,
    idempotency_key VARCHAR(64) UNIQUE,
    trace_id VARCHAR(64),
    source_system VARCHAR(20) DEFAULT 'pms',
    recommendation_id UUID,
    audit_context JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_suggestions_tenant_status ON suggestions(tenant_id, status);
CREATE INDEX idx_suggestions_domain ON suggestions(target_domain);
CREATE INDEX idx_suggestions_trace ON suggestions(trace_id);

CREATE TABLE suggestion_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suggestion_id UUID NOT NULL REFERENCES suggestions(id),
    tenant_id VARCHAR(36) NOT NULL,
    execution_status VARCHAR(20),
    approved_by VARCHAR(36),
    approved_at TIMESTAMP,
    rejected_reason TEXT,
    actual_roi FLOAT,
    actual_sales FLOAT,
    actual_acos FLOAT,
    predicted_roi FLOAT,
    predicted_sales FLOAT,
    predicted_acos FLOAT,
    deviation FLOAT,
    feedback_source VARCHAR(20),
    feedback_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_channel_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    platform_order_id VARCHAR(100) NOT NULL,
    platform VARCHAR(30) NOT NULL,
    marketplace VARCHAR(20) NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'USD',
    order_date TIMESTAMP NOT NULL,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_fulfillment_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    sales_order_id UUID NOT NULL REFERENCES oms_orders(id),
    fulfillment_status VARCHAR(30) NOT NULL,
    warehouse_id VARCHAR(50),
    assigned_at TIMESTAMP,
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    fulfillment_order_id UUID NOT NULL REFERENCES oms_fulfillment_orders(id),
    tracking_number VARCHAR(100),
    carrier VARCHAR(50),
    shipment_status VARCHAR(30) NOT NULL,
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    order_id UUID NOT NULL REFERENCES oms_orders(id),
    refund_type VARCHAR(30) NOT NULL,
    refund_reason TEXT,
    refund_amount DECIMAL(12,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE iam_data_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id VARCHAR(36) NOT NULL,
    permission_dimension VARCHAR(30) NOT NULL,
    allowed_values JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 5.3 数据流设计

数据流全景保持V8设计，V9关键修正：

| 修正项 | V8 | V9 | 原因 |
| :--- | :--- | :--- | :--- |
| PMS→PDM写入 | create_selection_proposal(直接创建) | submit_selection_recommendation(建议池) | PMS不写ERP终态 |
| PMS→SCM写入 | create_purchase_order(直接创建) | submit_purchase_recommendation(建议池) | PMS不写ERP终态 |
| PMS→SOM写入 | create_listing_draft(草稿) | submit_listing_draft(草稿需审批) | 草稿需经审批 |
| PMS→ADS写入 | adjust_ad_strategy(直接调整) | submit_ads_suggestion(建议池) | PMS不写ERP终态 |
| PMS→FBA写入 | create_inbound_shipment(直接创建) | submit_replenishment_suggestion(建议池) | PMS不写ERP终态 |
| PMS→OMS写入 | create_listing_draft(OMS) | 已移除 ★[V9] | Listing归SOM |

### 5.4 数据主权与主数据边界 ★[V9新增]

| 数据 | 主系统 | PMS角色 | 说明 |
| :--- | :--- | :--- | :--- |
| 商品主数据 | ERP PDM | 只读 | PMS不修改商品主数据 |
| SKU / SPU | ERP PDM | 只读 | PMS不创建SKU/SPU |
| Listing | ERP SOM | 只读+建议 | PMS可提交Listing草稿建议 |
| 订单 | ERP OMS | 只读 | PMS通过CDC/API读取 |
| 库存 | ERP WMS/FBA | 只读+建议 | PMS可提交补货建议 |
| 采购 | ERP SCM | 只读+建议 | PMS可提交采购建议 |
| 成本利润 | ERP FMS | 只读 | PMS通过API读取 |
| KPI结果 | ERP BI | 只读+推送 | PMS可推送AI洞察卡片 |
| 广告活动 | ERP ADS | 只读+建议 | PMS可提交广告优化建议 |
| 选品任务 | PMS | 读写 | PMS自有数据 |
| AI推荐 | PMS | 读写 | PMS自有数据 |
| AI评分 | PMS | 读写 | PMS自有数据 |
| AI证据链 | PMS | 读写 | PMS自有数据 |
| 建议执行状态 | ERP + PMS | 双向同步 | ERP执行后反馈PMS |

### 5.5 数据可信等级 ★[V9新增]

| 可信等级 | 数据源 | 说明 | 对AI推荐的影响 |
| :--- | :--- | :--- | :--- |
| **A级** | ERP订单/库存/财务 | 内部真实数据 | 直接作为特征输入 |
| **A级** | Amazon官方API | 官方平台数据 | 直接作为特征输入 |
| **B级** | 第三方数据服务(Keepa/JungleScout) | 专业数据服务 | 需交叉验证后使用 |
| **C级** | 爬虫数据 | 非官方采集 | 需清洗+验证后使用 |
| **C级** | 社媒趋势(Reddit/Instagram) | 非结构化趋势 | 仅作辅助参考 |
| **D级** | LLM推断 | AI生成内容 | 必须标注来源，需人工校验 |

PMS推荐结果必须输出：

```python
class RecommendationOutput:
    score: float
    evidence: List[Dict]
    data_sources: List[Dict]
    confidence: float
    risk_flags: List[str]
    explainability: str
    data_trust_level: str
```

------

## 6. AI架构详细设计

### 6.1 Agent编排设计

Agent列表保持V8设计，V9新增信任等级标注：

| Agent | 职责 | LLM模型 | 输出可信等级 | 实现状态 |
| :--- | :--- | :--- | :--- | :--- |
| **DataCollectionAgent** | 数据采集与清洗 | Phi-3-mini | A-C(取决于数据源) | 🔵 |
| **MarketInsightAgent** | 市场洞察分析 | Qwen2.5-72B | D | 🔵 |
| **ProductPlanningAgent** | 产品规划建议 | Qwen2.5-72B | D | 🔵 |
| **CommercialAnalysisAgent** | 商业化分析 | Qwen2.5-72B | D | 🔵 |
| **AdsStrategyAgent** | 广告策略建议 | Qwen2.5-72B | D | 🟡 |
| **RiskAssessmentAgent** | 风险评估 | DeepSeek-V3 | D | 🔵 |
| **ReviewAnalysisAgent** | 评论情感分析 | Qwen2.5-72B | C-D | 🔵 |
| **ReplenishmentAgent** | 补货建议 | Qwen2.5-72B | D | 🟡 |
| **PriceOptimizationAgent** | 定价优化 | Qwen2.5-72B | D | 🟡 |

**AI能力分布原则 ★[V9]**：

```
PMS = 跨域AI决策中心（跨域推荐、综合分析、策略编排）
ERP各域 = 领域规则 + 执行 + 审批 + 反馈 + 轻量域内助手
```

ERP域内可保留轻量规则引擎或域内助手，但跨域智能推荐由PMS统一编排，避免AI能力重复建设和推荐建议冲突。

### 6.2 RAG知识库设计

保持V8设计，V9新增租户隔离要求：

- 向量库(Qdrant)按tenant_id过滤
- Elasticsearch索引按tenant_id分片
- 知识图谱(Neo4j)按tenant_id子图隔离
- 特征库(Feast)按tenant_id+scope过滤

### 6.3 LLM服务设计

保持V8设计不变。

### 6.4 多模态服务设计

保持V8设计不变。

------

# 第三卷：ERP 14域详细设计

## 7. 工作台域 (DASHBOARD) ★[AI看板]

### 7.1 领域概述

工作台域管理用户看板布局、AI洞察卡片和KPI仪表盘。PMS将AI洞察推送到DASHBOARD展示。

### 7.2 领域模型

保持V8设计：DashboardLayout → Widget → AIInsightCard。

### 7.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | 实现状态 |
| :--- | :--- | :--- | :--- |
| GET | `/api/internal/v1/dashboard/layouts` | 获取用户看板布局 | 🔵 |
| PUT | `/api/internal/v1/dashboard/layouts` | 更新看板布局 | 🔵 |
| GET | `/api/internal/v1/dashboard/widgets/{type}/data` | 获取组件数据 | 🔵 |
| GET | `/api/internal/v1/dashboard/kpi` | 获取KPI指标 | 🔵 |
| GET | `/api/internal/v1/dashboard/ai-insights` | 获取AI洞察摘要 | 🔵 |
| POST | `/api/internal/v1/dashboard/insight-cards` | 接收AI洞察卡片 ★[V9] | 🔵 |
| GET | `/api/internal/v1/dashboard/todos` | 获取待办事项 | 🔵 |
| GET | `/api/internal/v1/dashboard/alerts` | 获取告警通知 | 🔵 |

### 7.4 数据库设计

保持V8设计（dashboard_layouts, dashboard_widgets, ai_insight_cards）。

### 7.5 PMS交互设计 ★[V9修正]

| 交互方向 | 接口 | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| **PMS→DASHBOARD** | `push_ai_insight` | 推送AI洞察卡片 | InsightCard（无需审批） |
| **PMS→DASHBOARD** | `update_kpi_widget` | 更新KPI指标 | InsightCard（无需审批） |
| **DASHBOARD→PMS** | `query_selection_summary` | 查询选品汇总 | 只读 |
| **DASHBOARD→PMS** | `query_suggestion_stats` | 查询建议统计 | 只读 |

```python
class DashboardClient(BaseERPClient):

    async def push_ai_insight(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/dashboard/insight-cards", data={
            "insight_type": data["insight_type"],
            "title": data["title"],
            "summary": data["summary"],
            "detail": data.get("detail", {}),
            "priority": data.get("priority", "medium"),
            "source_domain": "pms",
            "valid_from": datetime.utcnow().isoformat(),
            "audit_context": audit.to_dict()
        })

    async def update_kpi_widget(self, kpi_data: Dict, audit: AuditContext) -> Dict:
        return await self._request("PUT", "/api/internal/v1/dashboard/kpi", data={
            **kpi_data, "audit_context": audit.to_dict()
        })
```

------

## 8. 组织权限域 (IAM) ★[V9强化：数据权限维度]

### 8.1 领域概述

组织权限域负责用户认证、角色管理、权限控制和租户隔离。V9强化了数据权限维度，从3维扩展到10维。

### 8.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     Tenant       │────▶│      User        │────▶│      Role        │
│     租户          │ 1:N │     用户          │ N:M │     角色          │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │  DataPermission  │
                                              │  数据权限(10维)   │ ★[V9]
                                              └─────────────────┘
```

### 8.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 |
| :--- | :--- | :--- |
| POST | `/api/internal/v1/iam/auth/verify` | 验证Token |
| GET | `/api/internal/v1/iam/users/{id}/permissions` | 获取用户权限(含数据权限维度) ★[V9] |
| GET | `/api/internal/v1/iam/tenants/{id}/config` | 获取租户配置 |
| POST | `/api/internal/v1/iam/service-accounts/verify` | 服务间认证验证 |
| GET | `/api/internal/v1/iam/data-permissions/{role_id}` | 获取角色数据权限 ★[V9新增] |

### 8.4 数据库设计

保持V8设计，V9新增：

```sql
CREATE TABLE iam_data_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id VARCHAR(36) NOT NULL,
    permission_dimension VARCHAR(30) NOT NULL,
    allowed_values JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(role_id, permission_dimension)
);
```

**10维数据权限 ★[V9]**：

| 权限维度 | 示例 | 说明 |
| :--- | :--- | :--- |
| tenant | tenant-001 | 租户隔离 |
| org | 公司A | 公司/组织 |
| department | 选品部 | 部门 |
| store | US-Store-01 | 店铺 |
| marketplace | amazon_us, amazon_jp | 市场 |
| channel | amazon, tiktok, walmart | 渠道 |
| warehouse | WH-CN-01, FBA-US-01 | 仓库 |
| supplier | SUP-001 | 供应商 |
| category | Electronics, Home | 类目 |
| data_level | detail, summary, masked | 数据级别 |

### 8.5 PMS交互设计 ★[V9修正]

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **IAM→PMS** | `verify_token` | PMS验证用户Token |
| **IAM→PMS** | `get_user_permissions` | PMS获取用户权限(含10维数据权限) ★[V9] |
| **IAM→PMS** | `get_tenant_config` | PMS获取租户配置 |
| **IAM→PMS** | `get_data_permissions` | PMS获取角色数据权限 ★[V9] |
| **PMS→IAM** | `register_service_account` | PMS注册服务间调用账号 |

```python
class IAMClient(BaseERPClient):

    async def verify_token(self, token: str) -> Dict:
        return await self._request("POST", "/api/internal/v1/iam/auth/verify", data={"token": token})

    async def get_user_permissions(self, user_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/iam/users/{user_id}/permissions")

    async def get_data_permissions(self, role_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/iam/data-permissions/{role_id}")

    async def get_tenant_config(self, tenant_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/iam/tenants/{tenant_id}/config")

    async def register_service_account(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/internal/v1/iam/service-accounts", data=data)
```

------

## 9. 产品开发域 (PDM) ★[AI选品] ★[V9强化：PMS-PDM边界]

### 9.1 领域概述

产品开发域管理产品全生命周期。V9明确PMS与PDM的职责边界：**PMS负责决策建议，PDM负责产品开发承接**。

### 9.2 职责边界 ★[V9冻结]

| 能力 | 归属 | 说明 |
| :--- | :--- | :--- |
| 市场采集 | PMS | 外部数据采集与分析 |
| AI选品评分 | PMS | AI评分与推荐 |
| 选品建议 | PMS | AI生成的选品建议 |
| 产品立项 | ERP PDM | 正式产品立项审批 |
| 产品资料主数据 | ERP PDM | SPU/SKU主数据管理 |
| 开发流程 | ERP PDM | 产品开发流程管理 |
| 质检标准 | ERP PDM | 质检与合规 |
| IP/合规记录 | ERP PDM | 知识产权与合规 |

### 9.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/pdm/recommendations` | 接收选品建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/pdm/products` | 获取产品列表 | 只读 |
| GET | `/api/internal/v1/pdm/products/{id}/specs` | 获取产品规格 | 只读 |
| GET | `/api/internal/v1/pdm/competitor-analysis` | 获取竞品分析 | 只读 |
| GET | `/api/internal/v1/pdm/product-lifecycle` | 获取产品生命周期 | 只读 |
| GET | `/api/internal/v1/pdm/recommendations/{id}/status` | 查询建议审批状态 ★[V9新增] | 只读 |

### 9.4 数据库设计

保持V8设计（pdm_selection_proposals, pdm_products, pdm_competitor_analysis）。

### 9.5 PMS交互设计 ★[V9关键修正]

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→PDM** | `submit_selection_recommendation` | 提交选品建议到建议池 | V8: create_selection_proposal(直接创建) |
| **PDM→PMS** | `query_product_specs` | 查询产品规格 | 不变 |
| **PDM→PMS** | `query_competitor_analysis` | 查询竞品分析 | 不变 |
| **PDM→PMS** | `query_product_lifecycle` | 查询产品生命周期 | 不变 |
| **PDM→PMS** | `query_recommendation_status` | 查询建议审批状态 ★[V9] | 新增 |

```python
class PDMClient(BaseERPClient):

    async def submit_selection_recommendation(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/pdm/recommendations", data={
            "type": "selection_recommendation",
            "source": "ai_pms",
            "ai_suggested": True,
            "product_name": data["product_title"],
            "category": data["category"],
            "target_market": data.get("target_market", "US"),
            "estimated_cost": data.get("estimated_cost"),
            "market_analysis": data.get("market_analysis"),
            "risk_assessment": data.get("risk_assessment"),
            "score": data.get("score"),
            "confidence": data.get("confidence"),
            "evidence": data.get("evidence", []),
            "data_sources": data.get("data_sources", []),
            "risk_flags": data.get("risk_flags", []),
            "explainability": data.get("explainability", ""),
            "audit_context": audit.to_dict()
        })

    async def query_recommendation_status(self, recommendation_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/pdm/recommendations/{recommendation_id}/status")

    async def query_product_specs(self, category: str) -> List[Dict]:
        return await self._request("GET", "/api/internal/v1/pdm/products", params={"category": category, "status": "active"})

    async def query_competitor_analysis(self, product_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/pdm/products/{product_id}/competitor-analysis")

    async def query_product_lifecycle(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/pdm/product-lifecycle", params={"category": category})
```

------

## 10. 销售运营域 (SOM) ★[V9强化：Listing归属确认]

### 10.1 领域概述

销售运营域管理Listing创建、价格调整和销售策略执行。V9确认**Listing归SOM，OMS不创建Listing**。

### 10.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/som/listing-drafts` | 创建Listing草稿 ★[V9修正] | Draft |
| PUT | `/api/internal/v1/som/listings/{id}/price-suggestions` | 提交定价建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/som/listings` | 获取Listing列表 | 只读 |
| GET | `/api/internal/v1/som/listings/{id}/performance` | 获取Listing表现 | 只读 |
| GET | `/api/internal/v1/som/category-bsr` | 获取类目BSR | 只读 |
| GET | `/api/internal/v1/som/pricing-benchmark` | 获取定价基准 | 只读 |
| GET | `/api/internal/v1/som/listing-drafts/{id}/status` | 查询草稿审批状态 ★[V9新增] | 只读 |

### 10.3 数据库设计

保持V8设计（som_listings, som_pricing_history）。

### 10.4 PMS交互设计 ★[V9关键修正]

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→SOM** | `submit_listing_draft` | 提交Listing草稿(需审批) | V8: create_listing_draft |
| **PMS→SOM** | `submit_pricing_suggestion` | 提交定价建议 | V8: adjust_listing_price(直接调整) |
| **SOM→PMS** | `query_listing_performance` | 查询Listing表现 | 不变 |
| **SOM→PMS** | `query_category_bsr` | 查询类目BSR | 不变 |
| **SOM→PMS** | `query_pricing_benchmark` | 查询定价基准 | 不变 |
| **SOM→PMS** | `query_draft_status` | 查询草稿审批状态 ★[V9] | 新增 |

```python
class SOMClient(BaseERPClient):

    async def submit_listing_draft(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/som/listing-drafts", data={
            **data, "source": "ai_pms", "audit_context": audit.to_dict()
        })

    async def submit_pricing_suggestion(self, listing_id: str, price_data: Dict, audit: AuditContext) -> Dict:
        return await self._request("PUT", f"/api/internal/v1/som/listings/{listing_id}/price-suggestions", data={
            **price_data, "source": "ai_pms", "audit_context": audit.to_dict()
        })

    async def query_draft_status(self, draft_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/som/listing-drafts/{draft_id}/status")

    async def query_listing_performance(self, asin: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/som/listings", params={"asin": asin})

    async def query_category_bsr(self, category: str, marketplace: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/som/category-bsr", params={"category": category, "marketplace": marketplace})

    async def query_pricing_benchmark(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/som/pricing-benchmark", params={"category": category})
```

------

## 11. 广告管理域 (ADS) ★[AI优化]

### 11.1 领域概述

广告管理域管理亚马逊广告活动。V9确认**ADS独立于SOM**，PMS广告建议进入ADS而非SOM。

### 11.2 职责边界 ★[V9冻结]

| 域 | 职责 |
| :--- | :--- |
| ADS | 广告策略、预算、关键词、投放、ACOS、ROI、广告活动 |
| SOM | Listing、渠道SKU、价格、销售运营 |
| FMS | 广告成本归集、利润核算 |
| BI | 广告指标分析、KPI评估 |
| PMS | 广告优化建议生成方 |

### 11.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| GET | `/api/internal/v1/ads/campaigns` | 获取广告活动列表 | 只读 |
| GET | `/api/internal/v1/ads/campaigns/{id}/performance` | 获取活动表现 | 只读 |
| POST | `/api/internal/v1/ads/suggestions` | 接收广告优化建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/ads/suggestions/{id}/status` | 查询建议审批状态 ★[V9新增] | 只读 |
| GET | `/api/internal/v1/ads/acos-analysis` | 获取ACOS分析 | 只读 |
| GET | `/api/internal/v1/ads/campaigns/{id}/keywords` | 获取关键词列表 | 只读 |

### 11.4 数据库设计

保持V8设计（ads_campaigns, ads_keywords, ads_daily_performance, ads_optimization_log）。

### 11.5 PMS交互设计 ★[V9关键修正]

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→ADS** | `submit_ads_suggestion` | 提交广告优化建议 | V8: adjust_ad_strategy(直接调整) |
| **PMS→ADS** | `submit_keyword_bid_suggestion` | 提交关键词竞价建议 | V8: adjust_keyword_bid(直接调整) |
| **PMS→ADS** | `submit_budget_suggestion` | 提交预算调整建议 | V8: adjust_campaign_budget(直接调整) |
| **ADS→PMS** | `query_campaign_performance` | 查询广告表现 | 不变 |
| **ADS→PMS** | `query_acos_analysis` | 查询ACOS分析 | 不变 |
| **ADS→PMS** | `query_keyword_performance` | 查询关键词表现 | 不变 |
| **ADS→PMS** | `query_suggestion_status` | 查询建议审批状态 ★[V9] | 新增 |
| **ADS→PMS** | CDC: `cdc.ads.campaigns` | CDC推送广告变更 | 不变 |

```python
class ADSClient(BaseERPClient):

    async def submit_ads_suggestion(self, campaign_id: str, strategy: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/ads/suggestions", data={
            "campaign_id": campaign_id,
            "suggestion_type": strategy["type"],
            "suggestion_data": strategy["data"],
            "source": "ai_pms",
            "confidence": strategy.get("confidence", 0.8),
            "evidence": strategy.get("evidence", []),
            "risk_flags": strategy.get("risk_flags", []),
            "audit_context": audit.to_dict()
        })

    async def submit_keyword_bid_suggestion(self, keyword_id: str, bid_data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/ads/suggestions", data={
            "keyword_id": keyword_id,
            "suggestion_type": "keyword_bid_adjustment",
            "suggestion_data": bid_data,
            "source": "ai_pms",
            "audit_context": audit.to_dict()
        })

    async def submit_budget_suggestion(self, campaign_id: str, budget_data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/ads/suggestions", data={
            "campaign_id": campaign_id,
            "suggestion_type": "budget_adjustment",
            "suggestion_data": budget_data,
            "source": "ai_pms",
            "audit_context": audit.to_dict()
        })

    async def query_suggestion_status(self, suggestion_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/ads/suggestions/{suggestion_id}/status")

    async def query_campaign_performance(self, campaign_id: str, days: int = 30) -> Dict:
        return await self._request("GET", f"/api/internal/v1/ads/campaigns/{campaign_id}/performance", params={"days": days})

    async def query_acos_analysis(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/ads/acos-analysis", params={"category": category})

    async def query_keyword_performance(self, campaign_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/ads/campaigns/{campaign_id}/keywords")
```

------

## 12. 订单域 (OMS) ★[AI风控] ★[V9强化：订单链路完整化]

### 12.1 领域概述

订单域管理订单全生命周期。V9将订单模型从简化销售订单扩展为完整链路，并**移除OMS创建Listing的接口**。

### 12.2 完整订单链路 ★[V9新增]

```
平台订单 ChannelOrder
        ↓
ERP销售订单 SalesOrder
        ↓
履约单 FulfillmentOrder
        ↓
包裹 Package
        ↓
物流运单 Shipment
        ↓
售后 / 退款 / 重发
```

### 12.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| GET | `/api/internal/v1/oms/orders` | 获取订单列表 | 只读 |
| GET | `/api/internal/v1/oms/orders/{id}` | 获取订单详情 | 只读 |
| GET | `/api/internal/v1/oms/sales-trend` | 获取销售趋势 | 只读 |
| GET | `/api/internal/v1/oms/order-statistics` | 获取订单统计 | 只读 |
| POST | `/api/internal/v1/oms/risk-alerts` | 提交风险预警 ★[V9修正] | RiskAlert |
| GET | `/api/internal/v1/oms/compliance-risks` | 获取合规风险 | 只读 |
| GET | `/api/internal/v1/oms/refunds` | 获取退款列表 ★[V9新增] | 只读 |
| GET | `/api/internal/v1/oms/fulfillment/{order_id}` | 获取履约信息 ★[V9新增] | 只读 |

**V9移除接口 ★[V9]**：

| 移除接口 | 原因 |
| :--- | :--- |
| `POST /api/v1/oms/listing-drafts` | Listing归SOM，OMS不创建Listing |
| `PUT /api/v1/oms/listing-drafts/{id}/price` | Listing归SOM，OMS不调整Listing价格 |

### 12.4 数据库设计

保持V8设计，V9新增完整订单链路表：

```sql
CREATE TABLE oms_channel_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    platform_order_id VARCHAR(100) NOT NULL,
    platform VARCHAR(30) NOT NULL,
    marketplace VARCHAR(20) NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'USD',
    order_date TIMESTAMP NOT NULL,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_fulfillment_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    sales_order_id UUID NOT NULL REFERENCES oms_orders(id),
    fulfillment_status VARCHAR(30) NOT NULL,
    warehouse_id VARCHAR(50),
    assigned_at TIMESTAMP,
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    fulfillment_order_id UUID NOT NULL REFERENCES oms_fulfillment_orders(id),
    tracking_number VARCHAR(100),
    carrier VARCHAR(50),
    shipment_status VARCHAR(30) NOT NULL,
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    order_id UUID NOT NULL REFERENCES oms_orders(id),
    refund_type VARCHAR(30) NOT NULL,
    refund_reason TEXT,
    refund_amount DECIMAL(12,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 12.5 PMS交互设计 ★[V9关键修正]

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→OMS** | `submit_risk_alert` | 提交风险预警 | V8: mark_risk_order |
| **OMS→PMS** | `query_sales_trend` | 查询销售趋势 | 不变 |
| **OMS→PMS** | `query_order_statistics` | 查询订单统计 | 不变 |
| **OMS→PMS** | `query_compliance_risks` | 查询合规风险 | 不变 |
| **OMS→PMS** | `query_refund_data` | 查询退款数据 ★[V9] | 新增 |
| **OMS→PMS** | `query_fulfillment_info` | 查询履约信息 ★[V9] | 新增 |
| **OMS→PMS** | CDC: `cdc.oms.orders` | CDC推送订单变更 | 不变 |

```python
class OMSClient(BaseERPClient):

    async def submit_risk_alert(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/oms/risk-alerts", data={
            **data, "source": "ai_pms", "audit_context": audit.to_dict()
        })

    async def query_sales_trend(self, category: str, market: str, days: int = 90) -> Dict:
        return await self._request("GET", "/api/internal/v1/oms/sales-trend", params={"category": category, "market": market, "days": days})

    async def query_order_statistics(self, params: Dict) -> Dict:
        return await self._request("GET", "/api/internal/v1/oms/order-statistics", params=params)

    async def query_compliance_risks(self, asin: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/oms/compliance-risks", params={"asin": asin})

    async def query_refund_data(self, asin: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/oms/refunds", params={"asin": asin})

    async def query_fulfillment_info(self, order_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/oms/fulfillment/{order_id}")
```

------

## 13. 供应链域 (SCM) ★[AI补货]

### 13.1 领域概述

供应链域管理供应商、采购订单和补货计划。V9修正PMS写入方式为建议池模式。

### 13.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/scm/recommendations` | 接收采购/补货建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/scm/suppliers` | 获取供应商列表 | 只读 |
| GET | `/api/internal/v1/scm/suppliers/{id}/performance` | 获取供应商表现 | 只读 |
| GET | `/api/internal/v1/scm/supplier-risk` | 获取供应商风险 | 只读 |
| GET | `/api/internal/v1/scm/purchase-cost` | 获取采购成本 | 只读 |
| GET | `/api/internal/v1/scm/recommendations/{id}/status` | 查询建议审批状态 ★[V9新增] | 只读 |

### 13.3 数据库设计

保持V8设计（scm_suppliers, scm_purchase_orders）。

### 13.4 PMS交互设计 ★[V9关键修正]

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→SCM** | `submit_purchase_recommendation` | 提交采购建议 | V8: create_purchase_order(直接创建) |
| **PMS→SCM** | `submit_replenishment_recommendation` | 提交补货建议 | V8: create_replenishment_plan(直接创建) |
| **SCM→PMS** | `query_supplier_performance` | 查询供应商表现 | 不变 |
| **SCM→PMS** | `query_supplier_risk` | 查询供应商风险 | 不变 |
| **SCM→PMS** | `query_purchase_cost` | 查询采购成本 | 不变 |
| **SCM→PMS** | `query_recommendation_status` | 查询建议审批状态 ★[V9] | 新增 |
| **SCM→PMS** | CDC: `cdc.scm.purchase_orders` | CDC推送采购变更 | 不变 |

```python
class SCMClient(BaseERPClient):

    async def submit_purchase_recommendation(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/scm/recommendations", data={
            "type": "purchase_recommendation",
            "source": "ai_pms",
            "product_specs": data.get("product_specs", {}),
            "quantity": data.get("quantity"),
            "suggested_supplier": data.get("supplier_id"),
            "audit_context": audit.to_dict()
        })

    async def submit_replenishment_recommendation(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/scm/recommendations", data={
            "type": "replenishment_recommendation",
            "source": "ai_pms",
            "sku": data.get("sku"),
            "quantity": data.get("quantity"),
            "urgency": data.get("urgency", "normal"),
            "audit_context": audit.to_dict()
        })

    async def query_recommendation_status(self, recommendation_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/scm/recommendations/{recommendation_id}/status")

    async def query_supplier_performance(self, supplier_id: str) -> Dict:
        return await self._request("GET", f"/api/internal/v1/scm/suppliers/{supplier_id}/performance")

    async def query_supplier_risk(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/scm/supplier-risk", params={"category": category})

    async def query_purchase_cost(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/scm/purchase-cost", params={"category": category})
```

------

## 14. 仓储域 (WMS) ★[AI预测]

### 14.1 领域概述

仓储域管理仓库库存、库龄和库容。V9修正PMS写入方式，并明确数据接入方式。

### 14.2 数据接入方式 ★[V9明确]

| 数据 | 接入方式 | 说明 |
| :--- | :--- | :--- |
| 库存变动 | CDC / 领域事件 | 实时同步 |
| 库存快照 | API / 定时同步 | 按需查询 |
| 库龄/周转率 | BI / 数据仓库 | 汇总分析 |
| 实时可售库存 | ERP API | 实时查询 |

### 14.3 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/wms/capacity-suggestions` | 提交库容建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/wms/inventory` | 获取库存状态 | 只读 |
| GET | `/api/internal/v1/wms/inventory-risk` | 获取库存风险 | 只读 |
| GET | `/api/internal/v1/wms/warehouse-capacity` | 获取仓库容量 | 只读 |
| GET | `/api/internal/v1/wms/suggestions/{id}/status` | 查询建议状态 ★[V9新增] | 只读 |

### 14.4 数据库设计

保持V8设计（wms_inventory）。

### 14.5 PMS交互设计

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→WMS** | `submit_capacity_suggestion` | 提交库容建议 | V8: reserve_capacity(直接预留) |
| **WMS→PMS** | `query_inventory_status` | 查询库存状态 | 不变 |
| **WMS→PMS** | `query_inventory_risk` | 查询库存风险 | 不变 |
| **WMS→PMS** | `query_warehouse_capacity` | 查询仓库容量 | 不变 |
| **WMS→PMS** | CDC: `cdc.wms.inventory` | CDC推送库存变更 | 不变 |

```python
class WMSClient(BaseERPClient):

    async def submit_capacity_suggestion(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/wms/capacity-suggestions", data={
            **data, "source": "ai_pms", "audit_context": audit.to_dict()
        })

    async def query_inventory_status(self, asin: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/wms/inventory", params={"asin": asin})

    async def query_inventory_risk(self, category: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/wms/inventory-risk", params={"category": category})

    async def query_warehouse_capacity(self, warehouse_id: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/wms/warehouse-capacity", params={"warehouse_id": warehouse_id})
```

------

## 15. FBA/海外仓域 (FBA)

### 15.1 领域概述

FBA/海外仓域管理亚马逊FBA库存和入库计划。V9修正PMS写入方式为建议池模式。

### 15.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/fba/replenishment-suggestions` | 提交FBA补货建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/fba/inventory` | 获取FBA库存 | 只读 |
| GET | `/api/internal/v1/fba/fee-estimate` | 获取FBA费用估算 | 只读 |
| GET | `/api/internal/v1/fba/restock-recommendations` | 获取补货建议 | 只读 |
| GET | `/api/internal/v1/fba/suggestions/{id}/status` | 查询建议状态 ★[V9新增] | 只读 |

### 15.3 数据库设计

保持V8设计（fba_inventory, fba_inbound_shipments, fba_fee_estimates, fba_inventory_sync）。

### 15.4 PMS交互设计

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **PMS→FBA** | `submit_replenishment_suggestion` | 提交FBA补货建议 | V8: create_inbound_shipment(直接创建) |
| **FBA→PMS** | `query_fba_inventory` | 查询FBA库存 | 不变 |
| **FBA→PMS** | `query_fee_estimate` | 查询FBA费用 | 不变 |
| **FBA→PMS** | `query_restock_recommendations` | 查询补货建议 | 不变 |

```python
class FBAClient(BaseERPClient):

    async def submit_replenishment_suggestion(self, data: Dict, audit: AuditContext) -> Dict:
        return await self._request("POST", "/api/internal/v1/fba/replenishment-suggestions", data={
            **data, "source": "ai_pms", "audit_context": audit.to_dict()
        })

    async def query_fba_inventory(self, sku: str = None) -> Dict:
        params = {"sku": sku} if sku else {}
        return await self._request("GET", "/api/internal/v1/fba/inventory", params=params)

    async def query_fee_estimate(self, asin: str) -> Dict:
        return await self._request("GET", "/api/internal/v1/fba/fee-estimate", params={"asin": asin})

    async def query_restock_recommendations(self, category: str = None) -> Dict:
        params = {"category": category} if category else {}
        return await self._request("GET", "/api/internal/v1/fba/restock-recommendations", params=params)
```

------

## 16. 物流域 (TMS)

### 16.1 领域概述

物流域管理头程物流、尾程配送和运费计算。

### 16.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 | PMS写入类型 |
| :--- | :--- | :--- | :--- |
| POST | `/api/internal/v1/tms/shipment-suggestions` | 提交物流建议 ★[V9修正] | Recommendation |
| GET | `/api/internal/v1/tms/shipping-cost` | 获取运费 | 只读 |
| GET | `/api/internal/v1/tms/logistics-risk` | 获取物流风险 | 只读 |
| GET | `/api/internal/v1/tms/delivery-performance` | 获取配送表现 | 只读 |

### 16.3 数据库设计

保持V8设计（tms_shipping_rates）。

### 16.4 PMS交互设计

保持V8设计，API路径修正为`/api/internal/v1/`。

------

## 17. 客服售后域 (CRM) ★[AI情感]

### 17.1 领域概述

客服售后域管理客户评价、投诉和售后服务。PMS仅读取CRM数据，不写入。

### 17.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 |
| :--- | :--- | :--- |
| GET | `/api/internal/v1/crm/review-analysis` | 获取评价分析 |
| GET | `/api/internal/v1/crm/complaint-analysis` | 获取投诉分析 |
| GET | `/api/internal/v1/crm/customer-insights` | 获取客户洞察 |

### 17.3 数据库设计

保持V8设计（crm_reviews, crm_complaints）。

### 17.4 PMS交互设计

保持V8设计，PMS仅读取CRM数据，通过CDC接收评价变更。

------

## 18. 财务域 (FMS)

### 18.1 领域概述

财务域管理成本核算、利润分析和资金管理。PMS仅读取FMS数据。

### 18.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 |
| :--- | :--- | :--- |
| GET | `/api/internal/v1/fms/cost-breakdown` | 获取成本分解 |
| GET | `/api/internal/v1/fms/profit-analysis` | 获取利润分析 |
| GET | `/api/internal/v1/fms/budget-status` | 获取预算状态 |

### 18.3 数据库设计

保持V8设计（fms_cost_breakdown）。

### 18.4 PMS交互设计

保持V8设计，PMS仅读取FMS数据。

------

## 19. 商业智能域 (BI) ★[KPI]

### 19.1 领域概述

商业智能域管理KPI指标、报表分析和趋势预测。BI负责评估PMS建议效果。

### 19.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 |
| :--- | :--- | :--- |
| GET | `/api/internal/v1/bi/kpi-dashboard` | 获取KPI仪表盘 |
| GET | `/api/internal/v1/bi/market-trend` | 获取市场趋势 |
| GET | `/api/internal/v1/bi/category-bsr` | 获取类目BSR |
| GET | `/api/internal/v1/bi/product-performance` | 获取产品表现 |
| GET | `/api/internal/v1/bi/suggestion-effectiveness` | 查询建议效果评估 ★[V9新增] |

### 19.3 数据库设计

保持V8设计（bi_kpi_metrics）。

### 19.4 PMS交互设计

| 交互方向 | 接口 | 说明 | V8→V9变更 |
| :--- | :--- | :--- | :--- |
| **BI→PMS** | `query_market_trend` | 查询市场趋势 | 不变 |
| **BI→PMS** | `query_category_bsr` | 查询类目BSR | 不变 |
| **BI→PMS** | `query_product_performance` | 查询产品表现 | 不变 |
| **BI→PMS** | `query_kpi_dashboard` | 查询KPI仪表盘 | 不变 |
| **BI→PMS** | `query_suggestion_effectiveness` | 查询建议效果评估 ★[V9] | 新增 |

------

## 20. 系统设置域 (SYS)

### 20.1 领域概述

系统设置域管理ERP系统的全局配置和集成参数。

### 20.2 核心接口

| 方法 | 路径 ★[V9修正] | 说明 |
| :--- | :--- | :--- |
| GET | `/api/internal/v1/sys/configs` | 获取系统配置列表 |
| GET | `/api/internal/v1/sys/configs/{key}` | 获取配置项 |
| GET | `/api/internal/v1/sys/integration-params/{domain}` | 获取域集成参数 |
| GET | `/api/internal/v1/sys/health` | 系统健康检查 |

### 20.3 数据库设计

保持V8设计（sys_configs, sys_integration_params）。

### 20.4 PMS交互设计

保持V8设计，API路径修正为`/api/internal/v1/`。

------

# 第四卷：PMS模块实现详细设计

## 21. 选品服务详细设计

### 21.1 服务概述

选品服务是PMS的核心业务服务，负责选品任务的全生命周期管理。V9关键修正：采纳执行不再直接创建ERP业务单据，而是提交建议到ERP建议池。

### 21.2 核心接口

保持V8设计不变。

### 21.3 核心代码 ★[V9关键修正]

```python
class AuditContext:
    def __init__(self, tenant_id: str, actor_id: str, actor_type: str,
                 scope: Dict, purpose: str, trace_id: str):
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.scope = scope
        self.purpose = purpose
        self.trace_id = trace_id

    def to_dict(self) -> Dict:
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "scope": self.scope,
            "purpose": self.purpose,
            "trace_id": self.trace_id,
            "source_system": "pms"
        }


class SelectionService:
    def __init__(self, db: AsyncSession, agent_service: AgentService,
                 integration_service: ERPIntegrationService,
                 suggestion_service: SuggestionService):
        self.db = db
        self.agent_service = agent_service
        self.integration = integration_service
        self.suggestion_service = suggestion_service

    async def create_task(self, user_id: str, tenant_id: str,
                          params: SelectionParams) -> SelectionTask:
        task = SelectionTask(
            id=uuid4(), tenant_id=tenant_id, user_id=user_id,
            category=params.category, target_market=params.target_market,
            budget_range=params.budget_range, target_roi=params.target_roi,
            status="pending", progress=0, created_at=datetime.utcnow()
        )
        self.db.add(task)
        await self.db.commit()
        await self.agent_service.start_selection_workflow(task.id, {
            "category": params.category, "target_market": params.target_market,
            "budget_range": params.budget_range, "target_roi": params.target_roi,
            "tenant_id": tenant_id, "user_id": user_id
        })
        return task

    async def adopt_recommendation(self, recommendation_id: UUID,
                                    user_id: str, tenant_id: str) -> Suggestion:
        recommendation = await self._get_recommendation(recommendation_id)
        if recommendation.status != "approved":
            raise ValueError("Recommendation must be approved before adoption")

        audit = AuditContext(
            tenant_id=tenant_id, actor_id=user_id, actor_type="user",
            scope={"category": recommendation.category,
                   "marketplace": recommendation.target_market},
            purpose="selection_adoption",
            trace_id=str(uuid4())
        )

        suggestion = await self.suggestion_service.create_suggestion(
            suggestion_type="selection_adoption",
            title=f"选品采纳: {recommendation.product_title}",
            target_domain="PDM",
            target_action="create_selection_proposal",
            suggestion_data={
                "product_title": recommendation.product_title,
                "category": recommendation.category,
                "target_market": recommendation.target_market,
                "estimated_cost": recommendation.commercial_analysis.get("costs", {}).get("total", 0),
                "market_analysis": recommendation.market_analysis,
                "risk_assessment": recommendation.risk_assessment,
                "score": recommendation.score,
                "confidence": recommendation.confidence,
                "evidence": recommendation.evidence,
                "data_sources": recommendation.data_sources,
                "risk_flags": recommendation.risk_flags,
                "explainability": recommendation.explainability
            },
            audit=audit
        )

        recommendation.status = "adopted"
        recommendation.suggestion_id = suggestion.id
        await self.db.commit()

        return suggestion

    def _build_erp_suggestions(self, recommendation: Recommendation) -> List[Dict]:
        suggestions = [
            {"domain": "PDM", "action": "submit_selection_recommendation",
             "data": {"product_title": recommendation.product_title,
                      "category": recommendation.category}},
            {"domain": "SCM", "action": "submit_purchase_recommendation",
             "data": {"product_specs": recommendation.product_plan.get("specs", {})}},
            {"domain": "WMS", "action": "submit_capacity_suggestion",
             "data": {"warehouse_id": "default",
                      "quantity": recommendation.commercial_analysis.get("initial_order_qty", 100)}},
            {"domain": "SOM", "action": "submit_listing_draft",
             "data": {"title": recommendation.product_title,
                      "price": recommendation.commercial_analysis.get("suggested_price")}},
        ]
        if recommendation.ads_strategy:
            suggestions.append({"domain": "ADS", "action": "submit_ads_suggestion",
                                "data": recommendation.ads_strategy})
        if recommendation.risk_assessment.get("fba_recommended"):
            suggestions.append({"domain": "FBA", "action": "submit_replenishment_suggestion",
                                "data": {"sku": recommendation.sku}})
        return suggestions
```

------

## 22. Agent服务详细设计

### 22.1 服务概述

Agent服务负责AI Agent的编排与执行。V9新增Agent输出可信等级标注和证据链要求。

### 22.2 Agent列表

保持V8设计，所有Agent输出必须包含可信等级和证据链。

### 22.3 Agent编排工作流

保持V8设计，V9修正：Agent输出必须包含完整证据链。

```python
class AgentOutput:
    result: Dict
    score: float
    confidence: float
    evidence: List[Dict]
    data_sources: List[Dict]
    risk_flags: List[str]
    explainability: str
    data_trust_level: str
```

------

## 23. 知识域服务详细设计

保持V8设计，V9新增租户隔离过滤。

------

## 24. AI域服务详细设计

保持V8设计不变。

------

## 25. 数据域服务详细设计

保持V8设计，V9新增数据可信等级标注。

------

## 26. 集成域服务详细设计 ★[V9强化：建议池+草稿模式]

### 26.1 服务概述

集成域服务负责PMS与ERP 14域的集成。V9核心修正：所有写入ERP的操作改为提交建议/草稿/待审批动作，不再直接创建ERP正式业务单据。

### 26.2 ERPIntegrationService ★[V9关键修正]

```python
class ERPIntegrationService:

    async def submit_suggestion(self, domain: str, action: str,
                                 data: Dict, audit: AuditContext) -> Dict:
        client = self._get_client(domain)
        method_name = action
        method = getattr(client, method_name)
        result = await method(data, audit)
        await self._log_suggestion(domain, action, data, audit, result)
        return result

    async def execute_adoption(self, execution_id: UUID) -> Dict:
        execution = await self._get_execution(execution_id)
        recommendation = await self._get_recommendation(execution.recommendation_id)

        audit = AuditContext(
            tenant_id=execution.tenant_id,
            actor_id=execution.user_id,
            actor_type="user",
            scope={"category": recommendation.category},
            purpose="selection_adoption",
            trace_id=str(uuid4())
        )

        execution.status = "submitting"
        execution.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            step1_result = await self._execute_step(execution, 0,
                lambda: self.pdm.submit_selection_recommendation({
                    "product_title": recommendation.product_title,
                    "category": recommendation.category,
                    "estimated_cost": recommendation.commercial_analysis.get("costs", {}).get("total", 0),
                    "market_analysis": recommendation.market_analysis,
                    "risk_assessment": recommendation.risk_assessment,
                    "score": recommendation.score,
                    "confidence": recommendation.confidence,
                    "evidence": recommendation.evidence,
                    "data_sources": recommendation.data_sources,
                    "risk_flags": recommendation.risk_flags,
                    "explainability": recommendation.explainability
                }, audit))
            execution.pdm_recommendation_id = step1_result.get("id")

            step2_result = await self._execute_step(execution, 1,
                lambda: self.scm.submit_purchase_recommendation({
                    "product_specs": recommendation.product_plan.get("specs", {}),
                    "quantity": recommendation.commercial_analysis.get("initial_order_qty", 100)
                }, audit))
            execution.scm_recommendation_id = step2_result.get("id")

            step3_result = await self._execute_step(execution, 2,
                lambda: self.wms.submit_capacity_suggestion({
                    "warehouse_id": "default",
                    "quantity": recommendation.commercial_analysis.get("initial_order_qty", 100)
                }, audit))
            execution.wms_suggestion_id = step3_result.get("id")

            step4_result = await self._execute_step(execution, 3,
                lambda: self.som.submit_listing_draft({
                    "title": recommendation.product_title,
                    "price": recommendation.commercial_analysis.get("suggested_price"),
                    "category": recommendation.category
                }, audit))
            execution.som_draft_id = step4_result.get("id")

            if recommendation.ads_strategy:
                step5_result = await self._execute_step(execution, 4,
                    lambda: self.ads.submit_ads_suggestion(
                        recommendation.ads_strategy.get("campaign_id", ""),
                        recommendation.ads_strategy, audit))
                execution.ads_suggestion_id = step5_result.get("id")

            if recommendation.risk_assessment.get("fba_recommended"):
                step6_result = await self._execute_step(execution, 5,
                    lambda: self.fba.submit_replenishment_suggestion({
                        "sku": recommendation.sku
                    }, audit))
                execution.fba_suggestion_id = step6_result.get("id")

            execution.status = "submitted"
            execution.submitted_at = datetime.utcnow()
            await self.db.commit()

            await self.dashboard.push_ai_insight({
                "insight_type": "adoption_submitted",
                "title": f"选品采纳已提交: {recommendation.product_title}",
                "summary": f"已向PDM/SCM/WMS/SOM提交建议，等待ERP审批",
                "priority": "high"
            }, audit)

            return {
                "pdm_recommendation_id": execution.pdm_recommendation_id,
                "scm_recommendation_id": execution.scm_recommendation_id,
                "wms_suggestion_id": execution.wms_suggestion_id,
                "som_draft_id": execution.som_draft_id,
                "ads_suggestion_id": execution.ads_suggestion_id,
                "fba_suggestion_id": execution.fba_suggestion_id,
                "status": "submitted_awaiting_approval"
            }
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            await self.db.commit()
            raise
```

------

## 27. 报告域服务详细设计

保持V8设计不变。

------

## 28. WebSocket接口详细设计

保持V8设计不变。

------

# 第五卷：PMS与ERP 14域交互设计

## 29. PMS-ERP集成架构 ★[V9强化：建议/草稿/审批模式]

### 29.1 集成总体架构

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PMS-ERP 集成架构 (V9)                                                       │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  PMS (AI决策辅助系统)                                                                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                                                      │  │
│  │  │ AI分析   │ │ 建议生成  │ │ 证据链   │                                                      │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘                                                      │  │
│  └───────┼─────────────┼────────────┼───────────────────────────────────────────────────────────┘  │
│          │             │            │                                                               │
│  ┌───────▼─────────────▼────────────▼───────────────────────────────────────────────────────────┐  │
│  │  PMS写入层 ★[V9关键]                                                                          │  │
│  │                                                                                              │  │
│  │  可写入类型:                                                                                   │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐                  │  │
│  │  │Recommendation  │ │    Draft       │ │ PendingAction  │ │  RiskAlert     │                  │  │
│  │  │ 建议(需审批)    │ │ 草稿(需审批)   │ │ 待审批动作      │ │ 风险预警(通知) │                  │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘ └────────────────┘                  │  │
│  │  ┌────────────────┐                                                                           │  │
│  │  │ InsightCard    │                                                                           │  │
│  │  │ 洞察卡片(展示) │                                                                           │  │
│  │  └────────────────┘                                                                           │  │
│  │                                                                                              │  │
│  │  禁止写入: 正式采购订单 / 正式Listing / 正式广告活动 / 正式入库货件 / 库存调拨                      │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│          │                                                                                         │
│  ┌───────▼──────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  ERP 建议接收层 ★[V9新增]                                                                      │  │
│  │                                                                                              │  │
│  │  Recommendation/Draft/PendingAction/RiskAlert/InsightCard                                     │  │
│  │          ↓                                                                                    │  │
│  │  权限校验(IAM: 10维数据权限)                                                                    │  │
│  │          ↓                                                                                    │  │
│  │  审批流(人工审批 / 规则自动审批)                                                                 │  │
│  │          ↓                                                                                    │  │
│  │  执行(ERP各域正式业务动作)                                                                      │  │
│  │          ↓                                                                                    │  │
│  │  反馈(执行结果 → PMS)                                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│          │                                                                                         │
│  ┌───────▼──────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  ERP (经营数据真相源)                                                                           │  │
│  │  PDM / SOM / ADS / OMS / SCM / WMS / FBA / TMS / CRM / FMS / BI / DASHBOARD / IAM / SYS      │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 29.2 PMS写入类型定义 ★[V9]

| 写入类型 | 说明 | 是否需审批 | 目标域 |
| :--- | :--- | :--- | :--- |
| **Recommendation** | AI建议（选品/补货/定价/广告/采购） | 是 | PDM/SCM/ADS/WMS/FBA/TMS |
| **Draft** | 草稿单据（Listing草稿） | 是 | SOM |
| **PendingAction** | 待审批动作 | 是 | 通用 |
| **RiskAlert** | 风险预警 | 否（仅通知） | OMS/SCM |
| **InsightCard** | AI洞察卡片 | 否（仅展示） | DASHBOARD/BI |

### 29.3 写入接口必须字段 ★[V9]

所有PMS写入ERP的接口必须包含：

```json
{
    "tenant_id": "tenant-001",
    "actor_id": "user-123",
    "actor_type": "user",
    "scope": {
        "marketplace": "amazon_us",
        "category": "Electronics"
    },
    "purpose": "selection_adoption",
    "idempotency_key": "adopt-rec-456-v1",
    "trace_id": "trace-789",
    "source_system": "pms",
    "recommendation_id": "rec-456",
    "audit_context": {
        "tenant_id": "tenant-001",
        "actor_id": "user-123",
        "actor_type": "user",
        "scope": {},
        "purpose": "selection_adoption",
        "trace_id": "trace-789",
        "source_system": "pms"
    }
}
```

------

## 30. PMS数据输入设计（AI感知）

### 30.1 数据输入分类 ★[V9明确]

| 数据类型 | 接入方式 | 可信等级 | 示例 |
| :--- | :--- | :--- | :--- |
| ERP经营数据 | Internal API | A | 订单、库存、财务 |
| ERP变更事件 | CDC / 领域事件 | A | 订单变更、库存变动 |
| 官方平台API | API采集 | A-B | Amazon SP-API |
| 第三方数据服务 | API采集 | B | Keepa, JungleScout |
| 爬虫数据 | 爬虫采集 | C | 竞品页面 |
| 社媒趋势 | API/爬虫 | C | Reddit, Instagram |
| LLM推断 | 内部推理 | D | AI分析结果 |

### 30.2 数据接入方式矩阵 ★[V9明确]

| ERP域 | 实时查询(API) | 变更同步(CDC/事件) | 汇总分析(BI/数仓) |
| :--- | :--- | :--- | :--- |
| PDM | 产品规格、竞品分析 | - | - |
| SOM | Listing表现、BSR | - | 销售汇总 |
| ADS | 广告表现、ACOS | 广告活动变更 | 广告ROI汇总 |
| OMS | 订单统计 | 订单变更 ★ | 销量趋势 |
| SCM | 供应商表现 | 采购单变更 | 采购汇总 |
| WMS | 实时库存 | 库存变更 ★ | 库龄/周转率 |
| FBA | FBA库存 | FBA库存变更 | FBA费用汇总 |
| TMS | 运费查询 | - | 物流成本汇总 |
| CRM | 评价分析 | 评价变更 | 客诉趋势 |
| FMS | 成本分解 | - | 利润分析 |
| BI | KPI指标 | - | 趋势报告 |

------

## 31. PMS数据输出设计（AI驱动） ★[V9强化：不写终态]

### 31.1 输出类型与目标域

| 输出类型 | 目标域 | 接口 | 说明 |
| :--- | :--- | :--- | :--- |
| 选品建议 | PDM | submit_selection_recommendation | Recommendation |
| 采购建议 | SCM | submit_purchase_recommendation | Recommendation |
| 补货建议 | SCM | submit_replenishment_recommendation | Recommendation |
| 库容建议 | WMS | submit_capacity_suggestion | Recommendation |
| Listing草稿 | SOM | submit_listing_draft | Draft |
| 定价建议 | SOM | submit_pricing_suggestion | Recommendation |
| 广告优化建议 | ADS | submit_ads_suggestion | Recommendation |
| 关键词竞价建议 | ADS | submit_keyword_bid_suggestion | Recommendation |
| 预算调整建议 | ADS | submit_budget_suggestion | Recommendation |
| FBA补货建议 | FBA | submit_replenishment_suggestion | Recommendation |
| 物流建议 | TMS | submit_shipment_suggestion | Recommendation |
| 风险预警 | OMS | submit_risk_alert | RiskAlert |
| AI洞察卡片 | DASHBOARD | push_ai_insight | InsightCard |
| KPI更新 | DASHBOARD | update_kpi_widget | InsightCard |

### 31.2 推荐输出规范 ★[V9]

PMS所有推荐结果必须输出：

```python
class RecommendationOutput:
    score: float
    evidence: List[Dict]
    data_sources: List[Dict]
    confidence: float
    risk_flags: List[str]
    explainability: str
    data_trust_level: str
```

------

## 32. 建议执行状态机 ★[V9新增]

### 32.1 状态定义

```
created ──→ scored ──→ submitted ──→ approved ──→ executing ──→ executed ──→ measured
                │           │            │            │            │
                │           │            │            │            └──→ partially_executed
                │           │            │            └──→ failed ──→ rolled_back
                │           │            └──→ rejected
                │           └──→ expired
                └──→ discarded
```

| 状态 | 说明 |
| :--- | :--- |
| **created** | 建议已创建 |
| **scored** | 建议已评分 |
| **submitted** | 建议已提交到ERP |
| **approved** | ERP审批通过 |
| **rejected** | ERP审批拒绝 |
| **executing** | ERP执行中 |
| **partially_executed** | 部分执行 |
| **executed** | 执行完成 |
| **failed** | 执行失败 |
| **rolled_back** | 已回滚 |
| **measured** | 效果已评估 |
| **expired** | 建议已过期 |
| **discarded** | 建议已丢弃 |

### 32.2 状态转换规则

```python
SUGGESTION_TRANSITIONS = {
    "created": ["scored", "discarded"],
    "scored": ["submitted", "discarded"],
    "submitted": ["approved", "rejected", "expired"],
    "approved": ["executing"],
    "rejected": [],
    "executing": ["executed", "partially_executed", "failed"],
    "partially_executed": ["executed", "failed"],
    "executed": ["measured"],
    "failed": ["rolled_back"],
    "rolled_back": [],
    "measured": [],
    "expired": [],
    "discarded": []
}
```

### 32.3 ERP反馈事件 ★[V9]

ERP应向PMS回流以下事件：

| 事件 | 说明 | 触发时机 |
| :--- | :--- | :--- |
| `suggestion.approved` | 建议审批通过 | ERP审批通过 |
| `suggestion.rejected` | 建议审批拒绝 | ERP审批拒绝 |
| `suggestion.executing` | 建议开始执行 | ERP开始执行 |
| `suggestion.executed` | 建议执行完成 | ERP执行完成 |
| `suggestion.failed` | 建议执行失败 | ERP执行失败 |
| `suggestion.measured` | 建议效果已评估 | BI评估完成 |

------

## 33. 闭环反馈设计

### 33.1 反馈数据流

```
PMS建议提交 → ERP审批 → ERP执行 → 执行结果 → BI评估 → PMS模型优化
```

### 33.2 反馈数据类型 ★[V9]

| 反馈类型 | 来源 | 说明 |
| :--- | :--- | :--- |
| 审批反馈 | ERP各域 | 采纳/拒绝/原因/审批人 |
| 执行反馈 | ERP各域 | 执行动作/执行结果/执行时间 |
| 销售表现 | ERP OMS/BI | 销量/销售额/退货率 |
| 库存表现 | ERP WMS/FBA | 库存变化/库龄/周转率 |
| 广告表现 | ERP ADS/BI | ACOS/CPC/CTR/ROAS |
| 利润表现 | ERP FMS/BI | 实际利润/利润偏差 |
| KPI变化 | ERP BI | KPI指标变化 |

### 33.3 反馈评估 ★[V9]

```python
class FeedbackEvaluator:

    async def evaluate_suggestion(self, suggestion_id: UUID) -> Dict:
        suggestion = await self._get_suggestion(suggestion_id)
        predicted = suggestion.suggestion_data.get("predictions", {})
        actual = await self._collect_actual_metrics(suggestion)

        evaluation = {
            "suggestion_id": str(suggestion_id),
            "predicted_roi": predicted.get("roi"),
            "actual_roi": actual.get("roi"),
            "roi_deviation": self._calc_deviation(predicted.get("roi"), actual.get("roi")),
            "predicted_sales": predicted.get("sales"),
            "actual_sales": actual.get("sales"),
            "sales_deviation": self._calc_deviation(predicted.get("sales"), actual.get("sales")),
            "predicted_acos": predicted.get("acos"),
            "actual_acos": actual.get("acos"),
            "acos_deviation": self._calc_deviation(predicted.get("acos"), actual.get("acos")),
            "overall_score": self._calc_overall_score(predicted, actual)
        }

        await self._save_evaluation(suggestion_id, evaluation)
        return evaluation
```

------

## 34. ERP 14域集成客户端详细设计

### 34.1 BaseERPClient ★[V9强化]

```python
class BaseERPClient:

    def __init__(self, base_url: str, api_key: str, secret_key: str,
                 iam_client: IAMClient = None):
        self.base_url = base_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.iam_client = iam_client
        self.retry_config = {"max_retries": 3, "backoff_ms": 1000}
        self.circuit_breaker = {"failure_threshold": 5, "recovery_timeout_ms": 30000}

    async def _request(self, method: str, path: str,
                        data: Dict = None, params: Dict = None) -> Dict:
        url = f"{self.base_url}{path}"
        timestamp = str(int(time.time()))
        signature = self._sign(method, path, timestamp, data)

        headers = {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json",
            "X-Source-System": "pms"
        }

        if self.iam_client and data and "audit_context" in data:
            audit = data["audit_context"]
            headers["X-Tenant-Id"] = audit.get("tenant_id", "")
            headers["X-Actor-Id"] = audit.get("actor_id", "")
            headers["X-Actor-Type"] = audit.get("actor_type", "")
            headers["X-Trace-Id"] = audit.get("trace_id", "")

        async with aiohttp.ClientSession() as session:
            for attempt in range(self.retry_config["max_retries"]):
                try:
                    async with session.request(method, url, json=data,
                                               params=params, headers=headers,
                                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 409:
                            return {"status": "duplicate", "message": "Idempotency conflict"}
                        elif resp.status >= 500:
                            raise ExternalServiceError(f"ERP returned {resp.status}")
                        else:
                            raise ValidationError(f"Request failed: {resp.status}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt == self.retry_config["max_retries"] - 1:
                        raise
                    await asyncio.sleep(self.retry_config["backoff_ms"] * (2 ** attempt) / 1000)

    def _sign(self, method: str, path: str, timestamp: str, body: Dict) -> str:
        message = f"{method.upper()}{path}{timestamp}"
        if body:
            message += json.dumps(body, sort_keys=True)
        return hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
```

### 34.2 客户端工厂

```python
class ERPClientFactory:

    def __init__(self, config: Dict, iam_client: IAMClient):
        self.config = config
        self.iam_client = iam_client
        self._clients = {}

    def get_client(self, domain: str) -> BaseERPClient:
        if domain not in self._clients:
            domain_config = self.config.get(domain, {})
            client_class = self._get_client_class(domain)
            self._clients[domain] = client_class(
                base_url=domain_config.get("base_url", ""),
                api_key=domain_config.get("api_key", ""),
                secret_key=domain_config.get("secret_key", ""),
                iam_client=self.iam_client
            )
        return self._clients[domain]

    def _get_client_class(self, domain: str) -> type:
        mapping = {
            "DASHBOARD": DashboardClient, "IAM": IAMClient, "PDM": PDMClient,
            "SOM": SOMClient, "ADS": ADSClient, "OMS": OMSClient,
            "SCM": SCMClient, "WMS": WMSClient, "FBA": FBAClient,
            "TMS": TMSClient, "CRM": CRMClient, "FMS": FMSClient,
            "BI": BIClient, "SYS": SYSClient
        }
        return mapping.get(domain, BaseERPClient)
```

------

## 35. 集成事件与异步通信

### 35.1 Kafka事件主题

| 主题 | 方向 | 说明 |
| :--- | :--- | :--- |
| `cdc.oms.orders` | ERP→PMS | 订单变更 |
| `cdc.wms.inventory` | ERP→PMS | 库存变更 |
| `cdc.scm.purchase_orders` | ERP→PMS | 采购变更 |
| `cdc.ads.campaigns` | ERP→PMS | 广告变更 |
| `cdc.crm.reviews` | ERP→PMS | 评价变更 |
| `pms.suggestions.created` | PMS→ERP | 建议创建 |
| `pms.suggestions.status_changed` | PMS→ERP | 建议状态变更 |
| `erp.suggestions.approved` | ERP→PMS | 建议审批通过 ★[V9] |
| `erp.suggestions.rejected` | ERP→PMS | 建议审批拒绝 ★[V9] |
| `erp.suggestions.executed` | ERP→PMS | 建议执行完成 ★[V9] |
| `erp.suggestions.measured` | ERP→PMS | 建议效果评估 ★[V9] |

### 35.2 事件格式 ★[V9]

```json
{
    "event_id": "evt-123",
    "event_type": "erp.suggestions.approved",
    "timestamp": "2026-04-26T10:00:00Z",
    "source": "erp",
    "domain": "PDM",
    "data": {
        "suggestion_id": "sug-456",
        "recommendation_id": "rec-789",
        "approved_by": "user-001",
        "approved_at": "2026-04-26T10:00:00Z",
        "execution_id": "exec-101"
    },
    "audit_context": {
        "tenant_id": "tenant-001",
        "actor_id": "user-001",
        "actor_type": "user",
        "trace_id": "trace-789"
    }
}
```

------

## 36. 集成异常处理与容错

保持V8设计，V9新增建议提交失败处理：

| 异常场景 | 处理策略 |
| :--- | :--- |
| 建议提交失败 | 重试3次，记录失败日志，通知用户 |
| 建议审批超时 | 标记为expired，通知用户 |
| 建议执行失败 | 标记为failed，触发回滚 |
| ERP服务不可用 | 熔断，缓存建议待恢复后重试 |

------

## 37. API路径规范 ★[V9新增]

### 37.1 ERP API路径规范

| 路径前缀 | 用途 | 说明 |
| :--- | :--- | :--- |
| `/api/admin/v1/` | 管理后台 | ERP管理界面调用 |
| `/api/open/v1/` | 外部开放接口 | 第三方系统调用 |
| `/api/internal/v1/` | 内部服务接口 | PMS专用集成接口 ★[V9] |
| `/api/pms/v1/` | PMS专用接口（可选） | 可选的PMS专用路径 |

### 37.2 PMS调用规范

- PMS调用ERP统一走 `/api/internal/v1/` 路径
- 不混用前端API（`/api/admin/v1/`）
- 所有请求必须携带审计上下文Header

------

## 38. 数据权限与审计上下文 ★[V9新增]

### 38.1 双主体权限模型

```text
用户主体：user_id + roles + scopes + data_permissions(10维)
服务主体：service_account_id + allowed_domains + allowed_actions
```

### 38.2 Agent执行权限

Agent执行时必须具备：

```json
{
    "actor_type": "agent",
    "actor_id": "agent-market-insight-001",
    "tenant_id": "tenant-001",
    "scope": {
        "marketplace": "amazon_us",
        "category": "Electronics"
    },
    "data_purpose": "market_analysis",
    "trace_id": "trace-789"
}
```

### 38.3 审计日志

所有PMS→ERP调用记录完整审计日志：

| 字段 | 说明 |
| :--- | :--- |
| timestamp | 调用时间 |
| tenant_id | 租户ID |
| actor_id | 操作者ID |
| actor_type | 操作者类型(user/service_account/agent) |
| domain | ERP域 |
| action | 操作 |
| trace_id | 链路追踪ID |
| request_data | 请求数据(脱敏) |
| response_status | 响应状态 |
| duration_ms | 耗时 |

------

# 第六卷：前端、部署、运维与安全

## 39. 前端架构设计

### 39.1 技术栈

| 技术 | 版本 | 用途 |
| :--- | :--- | :--- |
| Next.js | 14 | 前端框架 |
| React | 18 | UI库 |
| TypeScript | 5 | 类型安全 |
| Tailwind CSS | 3 | 样式框架 |
| Ant Design | 5 | UI组件库 |
| ECharts | 5 | 图表库 |
| Socket.IO | 4 | WebSocket客户端 |

### 39.2 页面列表 ★[V9更新]

| 页面 | 路由 | 说明 | 对应ERP域 |
| :--- | :--- | :--- | :--- |
| AI看板 | `/dashboard` | AI洞察+KPI+待办 | DASHBOARD |
| 选品任务 | `/selection/tasks` | 任务列表+创建 | PDM |
| 选品详情 | `/selection/tasks/[id]` | 任务进度+推荐 | PDM |
| 市场洞察 | `/market-insight` | 市场分析 | BI |
| 产品规划 | `/product-planning` | 产品规格 | PDM |
| 商业化分析 | `/commercial-analysis` | 成本利润 | FMS |
| 广告优化 | `/ads-optimization` | 广告策略 | ADS |
| 风险评估 | `/risk-assessment` | 风险预警 | OMS/SCM |
| 智能建议 | `/suggestions` | 建议列表+审批状态 ★[V9] | 全域 |
| 建议详情 | `/suggestions/[id]` | 建议详情+证据链 ★[V9] | 全域 |
| 知识库 | `/knowledge` | 文档管理 | - |
| FBA库存 | `/fba-inventory` | FBA库存面板 | FBA |
| 系统设置 | `/settings` | 集成配置 | SYS |

### 39.3 建议审批页面 ★[V9新增]

```typescript
interface SuggestionCardProps {
    suggestion: {
        id: string;
        suggestion_type: string;
        title: string;
        target_domain: string;
        target_action: string;
        score: number;
        confidence: number;
        evidence: Array<{source: string; content: string; trust_level: string}>;
        risk_flags: string[];
        explainability: string;
        status: string;
        created_at: string;
    };
    onApprove: (id: string) => void;
    onReject: (id: string, reason: string) => void;
}

const SuggestionCard: React.FC<SuggestionCardProps> = ({suggestion, onApprove, onReject}) => {
    const statusColor = {
        created: "blue", scored: "cyan", submitted: "orange",
        approved: "green", rejected: "red", executing: "purple",
        executed: "green", failed: "red", measured: "gold"
    }[suggestion.status] || "default";

    return (
        <Card title={suggestion.title} extra={<Tag color={statusColor}>{suggestion.status}</Tag>}>
            <Descriptions column={2}>
                <Descriptions.Item label="目标域">{suggestion.target_domain}</Descriptions.Item>
                <Descriptions.Item label="目标动作">{suggestion.target_action}</Descriptions.Item>
                <Descriptions.Item label="评分">{suggestion.score?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="置信度">{(suggestion.confidence * 100).toFixed(1)}%</Descriptions.Item>
            </Descriptions>
            <Collapse ghost>
                <Panel header="证据链" key="evidence">
                    {suggestion.evidence?.map((e, i) => (
                        <div key={i} style={{marginBottom: 8}}>
                            <Tag color={e.trust_level === "A" ? "green" : e.trust_level === "B" ? "blue" : "orange"}>
                                可信度{e.trust_level}
                            </Tag>
                            <Text type="secondary">{e.source}:</Text> {e.content}
                        </div>
                    ))}
                </Panel>
                <Panel header="风险标记" key="risks">
                    {suggestion.risk_flags?.map((r, i) => (
                        <Tag key={i} color="warning">{r}</Tag>
                    ))}
                </Panel>
                <Panel header="可解释性" key="explain">
                    <Paragraph>{suggestion.explainability}</Paragraph>
                </Panel>
            </Collapse>
            {suggestion.status === "submitted" && (
                <Space style={{marginTop: 16}}>
                    <Button type="primary" onClick={() => onApprove(suggestion.id)}>审批通过</Button>
                    <Button danger onClick={() => {
                        const reason = prompt("拒绝原因:");
                        if (reason) onReject(suggestion.id, reason);
                    }}>审批拒绝</Button>
                </Space>
            )}
        </Card>
    );
};
```

------

## 40. 部署架构设计

### 40.1 环境规划

| 环境 | 用途 | 规模 |
| :--- | :--- | :--- |
| DEV | 开发测试 | 1节点K8s |
| STAGING | 预发布验证 | 3节点K8s |
| PROD | 生产环境 | 多AZ K8s集群 |

### 40.2 资源规划

| 服务 | CPU | 内存 | GPU | 副本数 |
| :--- | :--- | :--- | :--- | :--- |
| selection-service | 2核 | 4GB | - | 4 |
| agent-service | 4核 | 8GB | - | 4 |
| integration-service | 2核 | 4GB | - | 3 |
| suggestion-service | 2核 | 4GB | - | 2 |
| ads-service | 2核 | 4GB | - | 2 |
| llm-service | 4核 | 16GB | 4×A100 | 1 |
| PostgreSQL | 4核 | 16GB | - | 3(Patroni) |
| Qdrant | 4核 | 16GB | - | 3 |
| Kafka | 4核 | 8GB | - | 3 |

### 40.3 Kubernetes部署清单 ★[V9]

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
    name: suggestion-service
    namespace: pms
spec:
    replicas: 2
    selector:
        matchLabels:
            app: suggestion-service
    template:
        metadata:
            labels:
                app: suggestion-service
        spec:
            containers:
                - name: suggestion-service
                  image: pms/suggestion-service:v9.0
                  ports:
                    - containerPort: 8000
                  env:
                    - name: DATABASE_URL
                      valueFrom:
                        secretKeyRef:
                            name: pms-secrets
                            key: database-url
                    - name: KAFKA_BROKERS
                      valueFrom:
                        configMapKeyRef:
                            name: pms-config
                            key: kafka-brokers
                  resources:
                    requests:
                        cpu: "1"
                        memory: "2Gi"
                    limits:
                        cpu: "2"
                        memory: "4Gi"
                  livenessProbe:
                    httpGet:
                        path: /health
                        port: 8000
                    initialDelaySeconds: 30
                    periodSeconds: 10
                  readinessProbe:
                    httpGet:
                        path: /ready
                        port: 8000
                    initialDelaySeconds: 10
                    periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
    name: suggestion-service
    namespace: pms
spec:
    selector:
        app: suggestion-service
    ports:
        - port: 8000
          targetPort: 8000
    type: ClusterIP
```

------

## 41. 监控与运维设计

### 41.1 监控体系

| 层级 | 工具 | 监控内容 |
| :--- | :--- | :--- |
| 基础设施 | Prometheus + Grafana | CPU/内存/磁盘/网络 |
| 应用 | OpenTelemetry + Jaeger | 请求延迟/错误率/吞吐量 |
| AI模型 | MLflow | 模型精度/推理延迟/Token消耗 |
| ERP集成 | 自定义Dashboard | 各域调用延迟/成功率/熔断状态 |
| 建议 ★[V9] | 自定义Dashboard | 建议提交数/审批率/执行率/准确率 |
| 业务 | Grafana | 选品任务数/采纳率/建议准确率 |

### 41.2 告警规则 ★[V9更新]

| 告警 | 条件 | 级别 | 通知方式 |
| :--- | :--- | :--- | :--- |
| ERP调用超时 | P99 > 5s 持续5分钟 | WARNING | 飞书/邮件 |
| ERP调用失败率 | > 10% 持续3分钟 | CRITICAL | 飞书/电话 |
| 熔断触发 | 任意域熔断 | CRITICAL | 飞书/电话 |
| LLM推理超时 | P99 > 10s 持续5分钟 | WARNING | 飞书 |
| 选品任务积压 | 待处理 > 50 | WARNING | 飞书 |
| 磁盘使用率 | > 85% | WARNING | 飞书/邮件 |
| 建议审批超时 ★[V9] | submitted超过24h未审批 | WARNING | 飞书 |
| 建议执行失败 ★[V9] | failed状态持续10分钟 | CRITICAL | 飞书/电话 |
| 建议准确率下降 ★[V9] | measured准确率 < 60% | WARNING | 飞书 |

### 41.3 建议监控Dashboard ★[V9新增]

```json
{
    "dashboard": "PMS建议监控",
    "panels": [
        {"title": "建议提交数(24h)", "type": "stat", "query": "sum(pms_suggestions_created_total[24h])"},
        {"title": "审批通过率", "type": "gauge", "query": "sum(pms_suggestions_approved_total) / sum(pms_suggestions_submitted_total)"},
        {"title": "执行成功率", "type": "gauge", "query": "sum(pms_suggestions_executed_total) / sum(pms_suggestions_approved_total)"},
        {"title": "建议准确率(ROI偏差<20%)", "type": "gauge", "query": "sum(pms_suggestions_measured_accurate_total) / sum(pms_suggestions_measured_total)"},
        {"title": "各域建议分布", "type": "pie", "query": "sum by (target_domain)(pms_suggestions_created_total)"},
        {"title": "建议状态分布", "type": "bar", "query": "sum by (status)(pms_suggestions_created_total)"}
    ]
}
```

------

## 42. 安全与权限设计

### 42.1 认证与授权

| 层级 | 机制 | 说明 |
| :--- | :--- | :--- |
| 用户认证 | JWT + OAuth2 | 通过IAM域统一认证 |
| 服务间认证 | API Key + HMAC签名 | PMS与ERP服务间调用 |
| 数据隔离 | 租户ID字段隔离 | 所有表含tenant_id |
| 接口权限 | RBAC + 10维数据权限 ★[V9] | 基于角色+数据维度的访问控制 |

### 42.2 数据安全

| 措施 | 说明 |
| :--- | :--- |
| 传输加密 | TLS 1.3 |
| 存储加密 | AES-256 (敏感字段) |
| API Key加密 | AES-256-GCM (SYS域存储) |
| 日志脱敏 | 敏感字段自动掩码 |
| 审计日志 | 所有ERP调用记录审计日志 |
| 幂等键 ★[V9] | 所有建议提交携带idempotency_key防重复 |

### 42.3 ERP集成安全

```python
class SecurityMiddleware:

    def sign_request(self, api_key: str, method: str, path: str, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = str(uuid4())
        message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}"
        signature = hmac.new(api_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {
            "X-API-Key": api_key[:8] + "****",
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
            "X-Source-System": "pms"
        }

    def verify_request(self, headers: Dict, method: str, path: str, body: str = "") -> bool:
        api_key = self._get_full_api_key(headers["X-API-Key"])
        expected = self.sign_request(api_key, method, path, body)
        return hmac.compare_digest(headers.get("X-Signature"), expected["X-Signature"])

    def validate_audit_context(self, headers: Dict) -> bool:
        required = ["X-Tenant-Id", "X-Actor-Id", "X-Actor-Type", "X-Trace-Id"]
        return all(headers.get(h) for h in required)
```

### 42.4 建议安全控制 ★[V9新增]

| 控制项 | 说明 |
| :--- | :--- |
| 建议提交鉴权 | 验证actor_id是否有对应域的提交权限 |
| 建议审批鉴权 | 验证approver_id是否有对应域的审批权限 |
| 建议查看鉴权 | 验证viewer_id是否有对应域+scope的查看权限 |
| 建议撤销 | 仅创建者或管理员可撤销 |
| 建议超时 | submitted超过24h自动标记expired |
| 建议限流 | 每个租户每小时最多提交100条建议 |

------

# 附录

## 附录A：V8→V9→V11变更记录

### A.1 V8→V9变更

| 章节 | 变更类型 | 变更内容 |
| :--- | :--- | :--- |
| 1.4 | 新增 | V9版本变更说明表 |
| 2.3 | 修改 | 核心原则增加"不写ERP终态数据""数据可信等级" |
| 3.4 | 修改 | ERP集成架构增加建议/草稿/审批模式 |
| 4.2 | 新增 | suggestions, suggestion_feedback, oms_channel_orders等表 |
| 4.3 | 修改 | 数据流全景增加建议状态机流转 |
| 6-19 | 修改 | 14域ERP设计修正交互模式(PMS→建议/草稿, 不写终态) |
| 21 | 修改 | 选品服务采纳改为提交建议而非直接创建ERP单据 |
| 26 | 修改 | 集成服务增加建议管理与状态机执行 |
| 29 | 新增 | PMS-ERP集成架构(建议/草稿/审批模式) |
| 30 | 新增 | PMS数据输入设计(数据可信等级) |
| 31 | 新增 | PMS数据输出设计(不写终态) |
| 32 | 新增 | 建议执行状态机(13状态) |
| 33 | 新增 | 闭环反馈设计(反馈评估) |
| 34 | 修改 | ERP客户端增加审计上下文、幂等键、API路径修正 |
| 35 | 修改 | Kafka事件增加建议审批/执行/评估反馈事件 |
| 37 | 新增 | API路径规范(/api/internal/v1/) |
| 38 | 新增 | 数据权限与审计上下文(10维数据权限、双主体权限模型) |
| 39 | 修改 | 前端增加建议审批页面 |
| 41 | 修改 | 监控增加建议监控Dashboard |
| 42 | 修改 | 安全增加建议安全控制、幂等键 |

### A.2 V9+V10→V11合并变更 ★[V11新增]

| 章节 | 变更类型 | 变更内容 | 来源 |
| :--- | :--- | :--- | :--- |
| 1.5 | 新增 | V10版本交叉验证优化说明(8条核心原则+10项优化) | V10 |
| 1.6 | 新增 | 当前实现态、近期实现态与目标态说明(能力状态基线) | V10 |
| 附录G | 新增 | V10交叉验证优化补充设计(D.1-D.9) | V10 |
| 附录H | 新增 | PMS-ERP权限、接口、事件、数据主权矩阵 | V10 |

## 附录B：术语表

| 术语 | 说明 |
| :--- | :--- |
| PMS | 产品管理系统（AI选品系统） |
| Agent | AI智能体 |
| RAG | 检索增强生成 |
| LLM | 大语言模型 |
| ERP | 企业资源计划系统 |
| CDC | 变更数据捕获 |
| Saga | 长事务编排模式 |
| ACOS | 广告成本销售比 |
| BSR | 畅销榜排名 |
| TAM | 总可寻址市场 |
| ROI | 投资回报率 |
| ROAS | 广告支出回报率 |
| CTR | 点击率 |
| RBAC | 基于角色的访问控制 |
| HMAC | 基于哈希的消息认证码 |
| Recommendation ★[V9] | AI建议（需ERP审批） |
| Draft ★[V9] | 草稿单据（需ERP审批） |
| RiskAlert ★[V9] | 风险预警（仅通知） |
| InsightCard ★[V9] | AI洞察卡片（仅展示） |
| Idempotency Key ★[V9] | 幂等键（防重复提交） |
| Audit Context ★[V9] | 审计上下文（操作追溯） |
| Data Trust Level ★[V9] | 数据可信等级(A/B/C/D) |

## 附录C：ERP 14域接口对照表 ★[V9修正]

| 域 | PMS→ERP接口(V9) | ERP→PMS接口 | CDC Topic |
| :--- | :--- | :--- | :--- |
| DASHBOARD | push_ai_insight, update_kpi_widget | query_selection_summary, query_suggestion_stats | - |
| IAM | register_service_account | verify_token, get_user_permissions, get_tenant_config | - |
| PDM | submit_selection_recommendation ★ | query_product_specs, query_competitor_analysis, query_product_lifecycle | - |
| SOM | submit_listing_draft ★, submit_pricing_suggestion ★ | query_listing_performance, query_category_bsr, query_pricing_benchmark | - |
| ADS | submit_ads_suggestion ★, submit_keyword_bid_suggestion ★, submit_budget_suggestion ★ | query_campaign_performance, query_acos_analysis, query_keyword_performance | cdc.ads.campaigns |
| OMS | submit_risk_alert ★ | query_sales_trend, query_order_statistics, query_compliance_risks | cdc.oms.orders |
| SCM | submit_purchase_recommendation ★, submit_replenishment_recommendation ★ | query_supplier_performance, query_supplier_risk, query_purchase_cost | cdc.scm.purchase_orders |
| WMS | submit_capacity_suggestion ★ | query_inventory_status, query_inventory_risk, query_warehouse_capacity | cdc.wms.inventory |
| FBA | submit_replenishment_suggestion ★ | query_fba_inventory, query_fee_estimate, query_restock_recommendations | - |
| TMS | submit_shipment_suggestion ★ | query_shipping_cost, query_logistics_risk, query_delivery_performance | - |
| CRM | - | query_review_analysis, query_complaint_analysis, query_customer_insights | cdc.crm.reviews |
| FMS | - | query_cost_breakdown, query_profit_analysis, query_budget_status | - |
| BI | - | query_market_trend, query_category_bsr, query_product_performance, query_kpi_dashboard | - |
| SYS | update_integration_params | get_integration_params, get_system_config, health_check | - |

> ★ 标记表示V9修正：从直接创建ERP业务单据改为提交建议/草稿/预警

## 附录D：建议状态机完整转换表 ★[V9新增]

| 当前状态 | 可转换状态 | 触发条件 | 执行者 |
| :--- | :--- | :--- | :--- |
| created | scored | AI评分完成 | PMS Agent |
| created | discarded | 用户丢弃 | 用户 |
| scored | submitted | 用户采纳提交 | 用户 |
| scored | discarded | 用户丢弃 | 用户 |
| submitted | approved | ERP审批通过 | ERP审批人 |
| submitted | rejected | ERP审批拒绝 | ERP审批人 |
| submitted | expired | 超时未审批(24h) | 系统 |
| approved | executing | ERP开始执行 | ERP系统 |
| executing | executed | ERP执行完成 | ERP系统 |
| executing | partially_executed | 部分执行完成 | ERP系统 |
| executing | failed | 执行失败 | ERP系统 |
| partially_executed | executed | 剩余部分执行完成 | ERP系统 |
| partially_executed | failed | 剩余部分执行失败 | ERP系统 |
| executed | measured | BI评估完成 | BI系统 |
| failed | rolled_back | 回滚完成 | ERP系统 |

## 附录E：数据可信等级定义 ★[V9新增]

| 等级 | 说明 | 数据来源 | 使用场景 |
| :--- | :--- | :--- | :--- |
| **A** | 高可信 | ERP经营数据、官方平台API | 核心决策依据 |
| **B** | 较可信 | 第三方数据服务(Keepa等) | 辅助决策参考 |
| **C** | 一般可信 | 爬虫数据、社媒趋势 | 趋势参考，需交叉验证 |
| **D** | 低可信 | LLM推断、AI分析结果 | 探索性参考，需人工确认 |

## 附录F：10维数据权限模型 ★[V9新增]

| 维度 | 说明 | 示例 |
| :--- | :--- | :--- |
| tenant | 租户隔离 | tenant-001 |
| org | 组织 | 华南事业部 |
| department | 部门 | 选品部 |
| store | 店铺 | US-Store-01 |
| marketplace | 市场 | amazon_us |
| channel | 渠道 | FBA/FBM |
| warehouse | 仓库 | US-WH-01 |
| supplier | 供应商 | supplier-A |
| category | 品类 | Electronics |
| data_level | 数据密级 | public/internal/confidential |

------

## 附录G：V10交叉验证优化补充设计 ★[V10新增]

### G.1 PMS与ERP系统边界

PMS作为AI决策辅助系统，负责外部市场数据采集、ERP经营数据融合、选品机会识别、AI评分、建议生成、风险识别、证据链组织和报告输出。ERP作为业务主系统，负责组织权限、主数据、审批流、正式单据、库存、订单、采购、财务、广告投放、履约和审计。

```text
外部市场数据 + ERP经营数据
        ↓
PMS采集 / 特征加工 / AI分析 / 建议生成
        ↓
ERP建议池 / 草稿单据 / 待审批动作
        ↓
ERP权限校验 / 规则校验 / 审批流
        ↓
ERP正式执行业务动作
        ↓
执行状态 / 销售效果 / 库存变化 / 利润结果 / KPI反馈
        ↓
PMS模型评估与策略优化
```

### G.2 PMS不得直接写入ERP正式终态数据

PMS允许写入ERP的数据类型限定如下：

| 写入类型 | 是否允许 | 示例 | ERP承接域 |
|---|---|---|---|
| AI建议 | 允许 | 选品建议、广告优化建议、补货建议 | PDM/ADS/SCM/WMS/BI |
| 草稿单据 | 允许 | Listing草稿、采购计划草稿、补货计划草稿 | SOM/SCM/WMS/FBA |
| 待审批动作 | 允许 | 建议采纳申请、自动执行申请 | PDM/SOM/ADS/SCM |
| 正式业务单据 | 禁止直接写入 | 正式采购单、正式Listing、正式广告活动 | 由ERP审批后生成 |
| 财务终态数据 | 禁止写入 | 成本凭证、利润结果、付款状态 | FMS主控 |
| 库存终态数据 | 禁止写入 | 实际库存、出入库结果 | WMS/FBA主控 |

### G.3 PMS-ERP 14域交互矩阵

| ERP域 | ERP职责 | PMS读取 | PMS写入/建议 | ERP反馈 |
|---|---|---|---|---|
| DASHBOARD | 工作台、待办、预警、洞察入口 | 看板指标、待办状态 | AI洞察卡片、建议提醒 | 用户点击、处理结果 |
| IAM | 租户、用户、角色、权限、审计 | 权限、scope、数据范围 | 无；仅授权申请 | 授权结果、审计记录 |
| PDM | 产品开发、SPU/SKU、质检、IP合规 | 产品资料、类目、开发状态 | 选品建议、产品优化建议 | 立项、驳回、开发进度 |
| SOM | Listing、渠道SKU、价格、销售运营 | Listing表现、价格、销售状态 | Listing草稿、定价建议 | 上架结果、销售表现 |
| ADS | 广告活动、关键词、预算、ACOS、ROI | 广告数据、关键词表现、预算消耗 | 广告优化建议 | 投放结果、ACOS/ROI变化 |
| OMS | 订单、履约、退款、异常、风控 | 销量、退货、履约异常 | 风险预警 | 订单状态、退货率、异常处理 |
| SCM | 供应商、采购、报价、交期 | 供应商、报价、MOQ、交期 | 采购建议、供应风险 | 采购结果、交付表现 |
| WMS | 库存、库龄、出入库、库容 | 库存、周转、库龄 | 库存预测、库容建议 | 库存变化、缺货/滞销结果 |
| FBA | FBA库存、货件、海外仓 | FBA库存、货件状态 | FBA补货建议 | FBA销售、库容、补货结果 |
| TMS | 物流商、运费、轨迹、时效 | 运费、时效、异常率 | 物流风险建议 | 物流履约结果 |
| CRM | 评论、客诉、售后、情绪 | 评论、客诉、退换货原因 | 产品痛点建议 | 客诉改善、售后结果 |
| FMS | 成本、利润、对账、费用 | 成本、利润、广告费、物流费 | 利润风险提示 | 实际利润、费用归集结果 |
| BI | KPI、报表、经营分析 | 汇总指标、KPI结果 | AI洞察、指标解释 | 指标变化、建议效果评估 |
| SYS | 参数、集成配置、开关 | 配置、开关、字典 | 配置变更申请 | 配置审计、开关状态 |

### G.4 PMS数据源可信等级

| 数据源 | 可信等级 | 使用规则 |
|---|---|---|
| ERP订单、库存、财务、采购、广告真实数据 | A | 作为经营判断主依据 |
| 官方平台API数据 | A/B | 需记录采集时间和平台限制 |
| 第三方数据服务 | B | 需记录供应商、更新时间和覆盖范围 |
| 爬虫数据 | C | 需去重、校验、限频、标注来源 |
| 社媒趋势数据 | C | 仅作为趋势信号，不单独作为执行依据 |
| LLM推断结果 | D | 必须附解释、证据和人工复核要求 |

### G.5 PMS AI建议标准输出结构

```json
{
  "recommendation_id": "rec_xxx",
  "tenant_id": "tenant_xxx",
  "domain": "PDM|SOM|ADS|SCM|WMS|FBA|BI",
  "recommendation_type": "selection|listing|pricing|ads|replenishment|risk|insight",
  "target_refs": [{"type": "sku|asin|listing|supplier|campaign", "id": "..."}],
  "score": 0.0,
  "confidence": 0.0,
  "evidence": [],
  "data_sources": [],
  "risk_flags": [],
  "explainability": "human readable reason",
  "expected_impact": {
    "sales": null,
    "profit": null,
    "inventory_turnover": null,
    "acos": null
  },
  "required_approval": true,
  "idempotency_key": "idem_xxx",
  "trace_id": "trace_xxx"
}
```

### G.6 建议执行状态机

```text
created
  ↓
scored
  ↓
submitted
  ↓
approved / rejected
  ↓
executing
  ↓
partially_executed / executed / failed / rolled_back
  ↓
measured
```

| 状态 | 含义 | 责任系统 |
|---|---|---|
| created | PMS生成建议 | PMS |
| scored | PMS完成评分和证据链 | PMS |
| submitted | 建议提交ERP | PMS/ERP |
| approved | ERP审批通过 | ERP |
| rejected | ERP审批拒绝 | ERP |
| executing | ERP开始执行 | ERP |
| partially_executed | 部分执行成功 | ERP |
| executed | 执行完成 | ERP |
| failed | 执行失败 | ERP |
| rolled_back | 执行回滚 | ERP |
| measured | BI/PMS完成效果评估 | ERP BI/PMS |

### G.7 PMS权限与审计上下文

PMS调用ERP必须携带：

```text
tenant_id
actor_type = user / service_account / agent
actor_id
user_id，可为空，仅服务任务时为空
service_account_id，可为空，仅用户交互时为空
scope
data_purpose
marketplace
channel
store_id
warehouse_id
trace_id
idempotency_key
```

Agent不得拥有无限权限。Agent执行权限必须来自用户授权、服务账号授权或系统任务授权，并在审计日志中保留完整链路。

### G.8 PMS集成方式选择规则

| 数据类型 | 推荐方式 | 示例 |
|---|---|---|
| 实时查询 | ERP API | 可售库存、当前价格、当前广告预算 |
| 高频变化 | CDC/领域事件 | 库存变动、订单状态、广告消耗 |
| 汇总分析 | BI/数仓 | KPI、利润趋势、周转率、类目表现 |
| 外部趋势 | PMS采集任务 | Google Trends、社媒、竞品爬虫 |
| 模型特征 | 特征库 | 销售预测特征、补货特征、广告特征 |

### G.9 关键领域边界修正

1. PDM承接产品立项和产品开发；PMS负责选品机会识别和AI评分。
2. SOM负责Listing、渠道SKU和价格；PMS只能生成Listing草稿或优化建议。
3. ADS负责广告活动、关键词、预算和效果；PMS广告优化建议必须进入ADS。
4. OMS负责订单、履约、退款和风控结果；PMS不负责创建Listing。
5. SCM负责供应商、采购、报价和交期；PMS生成采购建议，不生成正式采购单。
6. WMS/FBA负责库存真实状态；PMS生成预测和补货建议，不修改实际库存。
7. FMS负责成本、费用、利润和对账真实结果；PMS只读取或生成风险提示。
8. BI负责经营指标和建议效果评估；PMS读取BI指标用于模型优化。

------

## 附录H：PMS-ERP权限、接口、事件、数据主权矩阵 ★[V10新增]

### H.1 权限矩阵

| ERP域 | PMS用户主体权限 | PMS服务主体权限 | Agent权限 |
|---|---|---|---|
| DASHBOARD | 读取+推送洞察 | 推送洞察 | 仅推送洞察 |
| IAM | 读取权限配置 | 验证Token | 验证Token |
| PDM | 读取+提交建议 | 提交建议 | 仅提交建议 |
| SOM | 读取+提交草稿 | 提交草稿 | 仅提交草稿 |
| ADS | 读取+提交建议 | 提交建议 | 仅提交建议 |
| OMS | 读取+提交预警 | 提交预警 | 仅提交预警 |
| SCM | 读取+提交建议 | 提交建议 | 仅提交建议 |
| WMS | 读取+提交建议 | 提交建议 | 仅提交建议 |
| FBA | 读取+提交建议 | 提交建议 | 仅提交建议 |
| TMS | 读取+提交建议 | 提交建议 | 仅提交建议 |
| CRM | 读取 | 读取 | 读取 |
| FMS | 读取 | 读取 | 读取 |
| BI | 读取+推送洞察 | 读取+推送 | 读取 |
| SYS | 读取+配置变更 | 读取 | 读取 |

### H.2 接口矩阵

| ERP域 | PMS→ERP写入接口 | ERP→PMS读取接口 | CDC Topic |
|---|---|---|---|
| DASHBOARD | push_ai_insight, update_kpi_widget | query_selection_summary, query_suggestion_stats | - |
| IAM | register_service_account | verify_token, get_user_permissions, get_tenant_config | - |
| PDM | submit_selection_recommendation | query_product_specs, query_competitor_analysis, query_product_lifecycle | - |
| SOM | submit_listing_draft, submit_pricing_suggestion | query_listing_performance, query_category_bsr, query_pricing_benchmark | - |
| ADS | submit_ads_suggestion, submit_keyword_bid_suggestion, submit_budget_suggestion | query_campaign_performance, query_acos_analysis, query_keyword_performance | cdc.ads.campaigns |
| OMS | submit_risk_alert | query_sales_trend, query_order_statistics, query_compliance_risks | cdc.oms.orders |
| SCM | submit_purchase_recommendation, submit_replenishment_recommendation | query_supplier_performance, query_supplier_risk, query_purchase_cost | cdc.scm.purchase_orders |
| WMS | submit_capacity_suggestion | query_inventory_status, query_inventory_risk, query_warehouse_capacity | cdc.wms.inventory |
| FBA | submit_replenishment_suggestion | query_fba_inventory, query_fee_estimate, query_restock_recommendations | - |
| TMS | submit_shipment_suggestion | query_shipping_cost, query_logistics_risk, query_delivery_performance | - |
| CRM | - | query_review_analysis, query_complaint_analysis, query_customer_insights | cdc.crm.reviews |
| FMS | - | query_cost_breakdown, query_profit_analysis, query_budget_status | - |
| BI | - | query_market_trend, query_category_bsr, query_product_performance, query_kpi_dashboard | - |
| SYS | update_integration_params | get_integration_params, get_system_config, health_check | - |

### H.3 事件矩阵

| 事件 | 生产者 | 消费者 | 触发场景 |
|---|---|---|---|
| cdc.oms.orders | ERP OMS | PMS erp-sync | 订单变更 |
| cdc.scm.purchase_orders | ERP SCM | PMS erp-sync | 采购订单变更 |
| cdc.wms.inventory | ERP WMS | PMS erp-sync | 库存变更 |
| cdc.crm.reviews | ERP CRM | PMS erp-sync | 评价变更 |
| cdc.ads.campaigns | ERP ADS | PMS erp-sync | 广告活动变更 |
| pms.suggestions.submitted | PMS suggestion | ERP各域 | 建议提交 |
| pms.suggestions.approved | ERP各域 | PMS suggestion | 建议审批通过 |
| pms.suggestions.rejected | ERP各域 | PMS suggestion | 建议审批拒绝 |
| pms.suggestions.executed | ERP各域 | PMS suggestion | 建议执行完成 |
| pms.suggestions.failed | ERP各域 | PMS suggestion | 建议执行失败 |
| pms.suggestions.measured | ERP BI / PMS | PMS agent | 建议效果评估完成 |
| pms.feedback.collected | PMS integration | PMS agent | 反馈收集事件 |
| pms.insights.pushed | PMS integration | ERP DASHBOARD | AI洞察推送 |

### H.4 数据主权矩阵

| 数据 | 主系统 | PMS角色 | 写入类型 | 审批要求 |
|---|---|---|---|---|
| 商品主数据 | ERP PDM | 只读 | - | - |
| SKU/SPU | ERP PDM | 只读 | - | - |
| Listing | ERP SOM | 只读+建议 | Draft | 需审批 |
| 订单 | ERP OMS | 只读 | - | - |
| 库存 | ERP WMS/FBA | 只读+建议 | Recommendation | 需审批 |
| 采购 | ERP SCM | 只读+建议 | Recommendation | 需审批 |
| 成本利润 | ERP FMS | 只读 | - | - |
| KPI结果 | ERP BI | 只读+推送 | InsightCard | 无需审批 |
| 广告活动 | ERP ADS | 只读+建议 | Recommendation | 需审批 |
| 选品任务 | PMS | 读写 | - | - |
| AI推荐 | PMS | 读写 | - | - |
| AI评分 | PMS | 读写 | - | - |
| AI证据链 | PMS | 读写 | - | - |
| 建议执行状态 | ERP + PMS | 双向同步 | - | - |

------

> **文档结束** — 跨境电商AI选品系统PMS详细设计说明书 V11.0
>
> 本文档为V9.0与V10.0合并版，基于V8.0版本，根据《交叉验证ERP与PMS详细设计交互问题和优化建议》文档，核心修正：
> 1. **PMS不写ERP终态数据**：所有写入改为提交建议/草稿/待审批动作，ERP审批后执行
> 2. **API路径标准化**：统一为 `/api/internal/v1/`，不混用前端API
> 3. **数据所有权明确**：ERP为经营数据真相源，PMS为AI决策辅助系统
> 4. **10维数据权限**：租户/组织/部门/店铺/市场/渠道/仓库/供应商/品类/密级
> 5. **数据可信等级**：A/B/C/D四级，所有AI输出标注可信等级
> 6. **建议执行状态机**：13状态完整生命周期管理
> 7. **闭环反馈**：审批反馈→执行反馈→效果评估→模型优化
> 8. **审计上下文**：所有PMS→ERP调用携带完整审计上下文
> 9. **幂等控制**：建议提交携带idempotency_key防重复
> 10. **边界修正**：Listing归属SOM，PMS不创建Listing；PDM-PMS职责分离
> 11. **V10核心修订原则**：ERP主权/非侵入/建议先行/权限继承/可解释/闭环反馈/阶段收敛 ★[V10]
> 12. **能力状态基线**：当前实现态/近期实现态/目标态/外部依赖四阶段标注 ★[V10]
> 13. **集成方式选择规则**：API/CDC/事件/BI四类集成方式适用边界 ★[V10]
> 14. **权限接口事件数据主权矩阵**：14域完整权限/接口/事件/数据主权矩阵 ★[V10]
