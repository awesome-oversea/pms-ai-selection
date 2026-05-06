# 跨境电商AI选品系统PMS—详细设计说明书

> **版本**：V10.0
> **创建日期**：2026-04-26
> **项目代号**：Project Aegis
> **文档状态**：正式版（基于ERP/PMS交叉验证优化）
> **基于版本**：V8.0
> **参考文档**：
> - 跨境电商AI选品系统PMS—详细设计说明书V3~V7
> - 跨境电商AI选品系统PMS—企业级设计方案
> - 跨境电商AI选品系统PMS—架构与业务设计文档
> - 跨境电商AI选品系统PMS—分层架构与数据流协作
> - 跨境电商ERP系统——详细设计说明书V7
> - 跨境电商ERP-需求规格说明书V3
> - 跨境电商ERP-技术实现方案V3

------

---

## 1.5 V10版本交叉验证优化说明

V10版本以V8完整设计为基础，结合《交叉验证ERP与PMS详细设计交互问题和优化建议》进行收敛和增强。V10不推翻V8的业务模块、服务拆分、数据库设计和ERP 14域覆盖范围，而是在系统边界、权限模型、接口规范、数据主权、建议执行闭环、实现阶段口径等方面进行统一。

### 1.5.1 V10核心修订原则

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

### 1.5.2 V10重点优化项

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

## 1.6 当前实现态、近期实现态与目标态说明

V10要求所有能力按以下状态标注，避免将目标态误判为当前交付范围。

| 状态 | 含义 | 约束 |
|---|---|---|
| 当前实现态 | 当前版本必须设计和实现的能力 | 纳入开发、测试、验收 |
| 近期实现态 | 下一阶段或近期迭代计划能力 | 完成接口预留和数据模型兼容 |
| 目标态 | 中长期架构规划能力 | 不作为当前交付阻塞项 |
| 外部依赖 | 依赖ERP、平台API、三方数据或模型能力 | 必须标注依赖方、降级策略和验收条件 |

### 1.6.1 PMS能力状态基线

| 能力 | V10状态 | 说明 |
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

## 目录

### 第一卷：系统概述

1. **引言**
   - 1.1 文档目的
   - 1.2 文档范围
   - 1.3 术语定义
   - 1.4 V8版本变更说明
2. **系统概述**
   - 2.1 系统定位
   - 2.2 系统边界
   - 2.3 核心功能
   - 2.4 非功能需求

### 第二卷：架构与微服务详细设计

3. **系统架构详细设计**
   - 3.1 部署架构
   - 3.2 微服务划分总览
   - 3.3 服务通信设计
   - 3.4 ERP 14域集成架构 ★[V8新增]
4. **数据架构详细设计**
   - 4.1 数据模型设计
   - 4.2 数据库设计
   - 4.3 数据流设计
   - 4.4 数据湖设计
5. **AI架构详细设计**
   - 5.1 Agent编排设计
   - 5.2 RAG知识库设计
   - 5.3 LLM服务设计
   - 5.4 多模态服务设计

### 第三卷：ERP 14域详细设计 ★[V8新增卷]

6. **工作台域 (DASHBOARD) ★[AI看板]**
7. **组织权限域 (IAM)**
8. **产品开发域 (PDM) ★[AI选品]**
9. **销售运营域 (SOM)**
10. **广告管理域 (ADS) ★[AI优化]**
11. **订单域 (OMS) ★[AI风控]**
12. **供应链域 (SCM) ★[AI补货]**
13. **仓储域 (WMS) ★[AI预测]**
14. **FBA/海外仓域 (FBA)**
15. **物流域 (TMS)**
16. **客服售后域 (CRM) ★[AI情感]**
17. **财务域 (FMS)**
18. **商业智能域 (BI) ★[KPI]**
19. **系统设置域 (SYS)**

### 第四卷：PMS模块实现详细设计

20. **选品服务详细设计**
21. **Agent服务详细设计**
22. **知识域服务详细设计**
23. **AI域服务详细设计**
24. **数据域服务详细设计**
25. **集成域服务详细设计**
26. **报告域服务详细设计**
27. **WebSocket接口详细设计**

### 第五卷：PMS与ERP 14域交互设计

28. **PMS-ERP集成架构**
29. **PMS数据输入设计（AI感知）**
30. **PMS数据输出设计（AI驱动）**
31. **闭环反馈设计**
32. **ERP 14域集成客户端详细设计**
33. **集成事件与异步通信**
34. **集成异常处理与容错**

### 第六卷：前端与运维

35. **前端架构设计**
36. **部署架构设计**
37. **监控与运维设计**
38. **安全与权限设计**

### 附录

- 附录A：V7→V8变更记录
- 附录B：术语表
- 附录C：ERP 14域接口对照表
- 附录D：V10交叉验证优化补充设计
- 附录E：PMS-ERP权限、接口、事件、数据主权矩阵

------

# 第一卷：系统概述

## 1. 引言

### 1.1 文档目的

本文档旨在详细描述跨境电商AI选品系统PMS的架构与模块实现设计，包括架构设计、模块设计、数据库设计、核心代码实现等内容。V8版本在V7基础上重点强化了ERP 14域的详细设计，将ERP集成从9域扩展到14域（新增DASHBOARD、IAM、ADS、FBA、SYS），并为每个域提供完整的领域模型、接口定义、数据库设计和PMS交互规范。

### 1.2 文档范围

本文档涵盖系统的全部功能模块，包括：选品服务、Agent编排服务、知识库服务、数据中台服务、集成服务、前端工作台，以及**V8新增的ERP 14域详细设计**。

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
| **ACOS** | Advertising Cost of Sales | 广告成本销售比 |

### 1.4 V8版本变更说明
   - 1.5 V10版本交叉验证优化说明
   - 1.6 当前实现态、近期实现态与目标态说明

| 变更项 | V7 | V8 | 说明 |
| :--- | :--- | :--- | :--- |
| **ERP域覆盖** | 9域(PDM/OMS/SCM/WMS/CRM/FMS/BI/SOM/TMS) | 14域(新增DASHBOARD/IAM/ADS/FBA/SYS) | 完整覆盖ERP全部业务域 |
| **域详细设计** | 仅集成客户端设计 | 每域独立章节：领域模型+接口+数据库+PMS交互 | 新增第三卷，14个域完整设计 |
| **AI增强域** | PDM/OMS/SCM/WMS/CRM/BI/SOM | 新增DASHBOARD(AI看板)/ADS(AI优化)/CRM(AI情感) | 明确每个AI增强域的AI能力 |
| **集成客户端** | 9个客户端 | 14个客户端(新增DashboardClient/IAMClient/ADSClient/FBAClient/SYSClient) | 完整14域客户端 |
| **数据流** | 9域数据流 | 14域数据流，含ADS广告数据、FBA库存数据、DASHBOARD看板数据 | 数据流全景升级 |
| **闭环反馈** | 基础闭环 | 增加广告效果反馈、FBA库存反馈、看板指标反馈 | 多维度闭环 |
| **前端页面** | 8个页面 | 增加广告优化面板、FBA库存面板、系统设置页 | 前端对齐14域 |

------

## 2. 系统概述

### 2.1 系统定位

本系统是跨境电商企业的核心决策支持系统，通过AI技术实现智能选品决策、市场趋势预测、竞品分析和供应链优化。系统与ERP 14个业务域深度集成，形成"AI决策→ERP执行→效果反馈→模型优化"的闭环。

**系统双重角色**：

| 角色 | 说明 |
| :--- | :--- |
| **AI决策层** | 基于多源数据生成选品建议、定价策略、补货建议、广告优化、风险预警等智能决策 |
| **AI驱动层** | 通过标准化接口将智能决策下发ERP 14域执行，驱动业务自动化 |

### 2.2 系统边界

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     AI选品系统 (PMS)                                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  选品服务    │  │  Agent服务  │  │ 知识库服务  │  │  报告服务   │  │  数据中台   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                              │
│  │  集成服务    │  │  AI中台     │  │  用户服务   │  │  广告优化   │                              │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────┘                              │
│         │                                                                                          │
│    ┌────┴──────────────────────────────────────────────────────────────────────────────────────┐   │
│    │                          Integration Service (14域客户端)                                  │   │
│    └────┬──────────────────────────────────────────────────────────────────────────────────────┘   │
├─────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
│         │ REST API / Kafka CDC / WebSocket                                                          │
│         ▼                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              ERP系统 (14个业务域)                                              │   │
│  │                                                                                              │   │
│  │  ┌──────────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                              │   │
│  │  │DASHBOARD │ │ IAM │ │ PDM │ │ SOM │ │ ADS │ │ OMS │ │ SCM │                              │   │
│  │  │ AI看板   │ │权限 │ │AI选品│ │销售 │ │AI优化│ │AI风控│ │AI补货│                              │   │
│  │  └──────────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                              │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                                  │   │
│  │  │ WMS │ │ FBA │ │ TMS │ │ CRM │ │ FMS │ │ BI  │ │ SYS │                                  │   │
│  │  │AI预测│ │海外仓│ │物流 │ │AI情感│ │财务 │ │ KPI │ │设置 │                                  │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                                  │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                     外部系统                                                        │
│  Amazon API │ TikTok API │ 1688 API │ Google Trends │ Google Ads API │ 爬虫平台                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 核心功能

| 功能模块 | 子功能 | 说明 | ERP交互域 |
| :--- | :--- | :--- | :--- |
| **选品决策** | 任务创建、智能分析、推荐列表、采纳执行 | 核心选品流程 | PDM/SCM/WMS/SOM |
| **市场洞察** | 市场规模、趋势分析、竞品格局、机会评分 | 市场分析能力 | OMS/BI/SOM |
| **产品规划** | 评论分析、痛点挖掘、规格推荐、差异化定位 | 产品定义能力 | CRM/PDM |
| **商业化分析** | 成本测算、利润分析、定价策略、ROI预测 | 商业化决策 | FMS/SCM/TMS/FBA |
| **广告优化** | 广告策略建议、关键词优化、ACOS优化 | 广告智能 | ADS/SOM |
| **风险评估** | 专利风险、舆情风险、供应链风险、合规风险 | 风险识别 | SCM/WMS/TMS/CRM |
| **知识库** | 文档管理、混合检索、知识图谱、多模态知识 | 企业记忆 | - |
| **报告生成** | PDF/Excel/PPT生成、图表渲染、一键分享 | 报告输出 | DASHBOARD |
| **数据采集** | API采集、爬虫采集、CDC采集 | 数据获取 | 全域CDC |
| **智能建议** | 选品/补货/定价/广告/风险建议 | AI驱动执行 | 全域 |
| **闭环反馈** | 执行反馈、效果追踪、模型优化 | 持续改进 | BI/DASHBOARD |
| **看板展示** | AI看板、KPI仪表盘、实时监控 | 决策可视化 | DASHBOARD/BI |

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
| **可观测性** | 监控覆盖 | 100%核心服务 |
| **可靠性** | ERP集成重试 | 3次指数退避 |
| **一致性** | 采纳执行一致性 | 最终一致性（秒级） |

------

# 第二卷：架构与微服务详细设计

## 3. 系统架构详细设计

### 3.1 部署架构

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
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                                 │  │    │
│  │  │  │ integration │  │   erp-      │  │   ads       │                                 │  │    │
│  │  │  │  service    │  │  sync       │  │  service    │                                 │  │    │
│  │  │  │ replicas:3  │  │ replicas:2  │  │ replicas:2  │                                 │  │    │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘                                 │  │    │
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

### 3.2 微服务划分总览

| 服务 | 职责 | 技术栈 | 端口 |
| :--- | :--- | :--- | :--- |
| **selection-service** | 选品任务管理、推荐生成、采纳执行 | FastAPI + SQLAlchemy | 8001 |
| **agent-service** | Agent编排、LangGraph工作流执行 | FastAPI + LangGraph | 8002 |
| **knowledge-service** | 知识库管理、RAG检索、知识图谱 | FastAPI + LlamaIndex | 8003 |
| **report-service** | 报告生成、PDF/Excel/PPT导出 | FastAPI + Jinja2 | 8004 |
| **data-service** | 数据采集、Flink/Spark作业、特征平台 | FastAPI + Airflow | 8005 |
| **integration-service** | ERP 14域集成、CDC消费、事件发布 | FastAPI + Kafka | 8006 |
| **llm-service** | LLM网关、模型路由、推理服务 | FastAPI + vLLM | 8007 |
| **rag-service** | 混合检索、Rerank、缓存 | FastAPI + Qdrant | 8008 |
| **ads-service** | 广告优化、ACOS分析、关键词建议 | FastAPI | 8009 |
| **feature-service** | 特征存储、特征计算、特征服务 | FastAPI + Feast | 8010 |
| **frontend** | Web前端 | Next.js 14 | 3000 |
| **gateway** | API网关 | Kong | 8000 |

### 3.3 服务通信设计

| 通信方式 | 场景 | 技术 |
| :--- | :--- | :--- |
| **同步REST** | 服务间查询、前端API调用 | HTTP/REST + OpenAPI |
| **异步事件** | ERP数据同步、任务状态变更 | Kafka |
| **WebSocket** | Agent进度推送、实时看板 | Socket.IO |
| **gRPC** | LLM推理调用、特征服务调用 | gRPC + Protobuf |

### 3.4 ERP 14域集成架构 ★[V8新增]

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PMS Integration Service — 14域集成架构                                      │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  PMS Services Layer                                                                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │  │
│  │  │Selection │ │  Agent   │ │Knowledge │ │  Report  │ │   Ads    │ │  Data    │              │  │
│  │  │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │ │ Service  │              │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘              │  │
│  └───────┼─────────────┼────────────┼────────────┼────────────┼────────────┼───────────────────┘  │
│          │             │            │            │            │            │                         │
│  ┌───────▼─────────────▼────────────▼────────────▼────────────▼────────────▼───────────────────┐  │
│  │  ERPIntegrationService (统一集成门面)                                                          │  │
│  │  ┌──────────────────────────────────────────────────────────────────────────────────────┐    │  │
│  │  │  BaseERPClient (限流/重试/熔断/缓存/签名/日志)                                           │    │  │
│  │  └──────────────────────────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                                              │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │  │
│  │  │Dashboard  │ │   IAM     │ │   PDM     │ │   SOM     │ │   ADS     │ │   OMS     │       │  │
│  │  │ Client    │ │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │       │  │
│  │  │★[V8新增]  │ │★[V8新增]  │ │           │ │           │ │★[V8新增]  │ │           │       │  │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘       │  │
│  │  ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐       │  │
│  │  │   SCM     │ │   WMS     │ │   FBA     │ │   TMS     │ │   CRM     │ │   FMS     │       │  │
│  │  │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │ │  Client   │       │  │
│  │  │           │ │           │ │★[V8新增]  │ │           │ │           │ │           │       │  │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘       │  │
│  │        ┌─────┴─────┐ ┌─────┴─────┐                                                        │  │
│  │        │    BI     │ │   SYS     │                                                        │  │
│  │        │  Client   │ │  Client   │                                                        │  │
│  │        │           │ │★[V8新增]  │                                                        │  │
│  │        └───────────┘ └───────────┘                                                        │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│          │             │            │            │            │            │                         │
│  ┌───────▼─────────────▼────────────▼────────────▼────────────▼────────────▼───────────────────┐  │
│  │  ERP System (14 Domains)                                                                      │  │
│  │  DASHBOARD │ IAM │ PDM │ SOM │ ADS │ OMS │ SCM │ WMS │ FBA │ TMS │ CRM │ FMS │ BI │ SYS   │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**14域AI增强标记**：

| 域 | AI增强 | AI能力 |
| :--- | :--- | :--- |
| DASHBOARD | ★AI看板 | 智能看板布局、异常指标自动高亮、AI洞察摘要 |
| IAM | - | 标准RBAC，无AI增强 |
| PDM | ★AI选品 | 选品推荐、产品规格推荐、竞品分析 |
| SOM | - | 标准销售运营 |
| ADS | ★AI优化 | 广告策略优化、关键词推荐、ACOS优化、预算分配 |
| OMS | ★AI风控 | 订单风控、欺诈检测、合规风险预警 |
| SCM | ★AI补货 | 智能补货建议、供应商风险评估、采购计划优化 |
| WMS | ★AI预测 | 库存需求预测、库龄风险预警、库容优化 |
| FBA | - | 标准FBA管理 |
| TMS | - | 标准物流管理 |
| CRM | ★AI情感 | 评价情感分析、客诉智能分类、客户洞察 |
| FMS | - | 标准财务管理 |
| BI | ★KPI | KPI智能分析、趋势预测、异常检测 |
| SYS | - | 标准系统配置 |

------

## 4. 数据架构详细设计

### 4.1 数据模型设计

#### 4.1.1 核心实体关系

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│SelectionTask │────▶│Recommendation│────▶│   Adoption   │     │  Suggestion  │
│  选品任务     │ 1:N │   推荐       │ 1:1 │  Execution   │     │  智能建议     │
└──────────────┘     └──────────────┘     │  采纳执行     │     └──────┬───────┘
                                           └──────────────┘            │
                                                                        │ 1:N
                                                                ┌───────▼───────┐
                                                                │  Suggestion   │
                                                                │  Feedback     │
                                                                │  建议反馈      │
                                                                └───────────────┘
```

### 4.2 数据库设计

#### 4.2.1 核心业务表

| 表名 | 说明 | 核心字段 |
| :--- | :--- | :--- |
| `selection_tasks` | 选品任务 | id, tenant_id, category, target_market, status, progress |
| `recommendations` | 选品推荐 | id, task_id, product_asin, product_title, overall_score, status |
| `adoption_executions` | 采纳执行 | id, recommendation_id, erp_steps, current_step, status |
| `suggestions` | 智能建议 | id, tenant_id, suggestion_type, priority, confidence, status |
| `suggestion_feedback` | 建议反馈 | id, suggestion_id, execution_status, actual_roi, actual_sales |
| `erp_sync_log` | ERP同步日志 | id, domain, action, direction, status, latency_ms |
| `ads_optimization_log` | 广告优化日志 ★[V8新增] | id, campaign_id, suggestion, before_acos, after_acos |
| `fba_inventory_sync` | FBA库存同步 ★[V8新增] | id, sku, fba_qty, inbound_qty, reserve_qty |

#### 4.2.2 新增表SQL (V8)

```sql
CREATE TABLE ads_optimization_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    campaign_id VARCHAR(100) NOT NULL,
    ad_group_id VARCHAR(100),
    keyword_id VARCHAR(100),
    optimization_type VARCHAR(50) NOT NULL,
    suggestion JSONB NOT NULL,
    before_metrics JSONB,
    after_metrics JSONB,
    acos_before DECIMAL(5,4),
    acos_after DECIMAL(5,4),
    status VARCHAR(20) DEFAULT 'pending',
    applied_at TIMESTAMP,
    feedback_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE fba_inventory_sync (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    asin VARCHAR(20),
    fba_fulfillable INT DEFAULT 0,
    fba_inbound INT DEFAULT 0,
    fba_reserved INT DEFAULT 0,
    fba_researching INT DEFAULT 0,
    warehouse_id VARCHAR(50),
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dashboard_widget_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    widget_type VARCHAR(50) NOT NULL,
    widget_config JSONB NOT NULL,
    data_source VARCHAR(50),
    refresh_interval INT DEFAULT 300,
    position JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE iam_role_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(36) NOT NULL,
    role_code VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(36) NOT NULL,
    scope JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sys_integration_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    domain VARCHAR(20) NOT NULL,
    config_key VARCHAR(100) NOT NULL,
    config_value JSONB NOT NULL,
    encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 4.3 数据流设计

#### 4.3.1 PMS-ERP 14域数据流全景

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              PMS-ERP 14域数据流全景                                                   │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              数据输入（ERP → PMS）                                            │  │
│  │                                                                                              │  │
│  │  DASHBOARD(看板指标) ──API──▶ integration-service ──▶ 缓存/特征库                             │  │
│  │  IAM(用户权限) ──API──▶ integration-service ──▶ 权限缓存                                     │  │
│  │  PDM(产品/竞品) ──API──▶ integration-service ──▶ 特征库/缓存                                 │  │
│  │  SOM(Listing/广告) ──API──▶ integration-service ──▶ 特征库/缓存                              │  │
│  │  ADS(广告数据) ──API──▶ integration-service ──▶ 特征库/缓存 ★[V8新增]                        │  │
│  │  OMS(订单/销量) ──CDC──▶ Kafka ──▶ erp-sync-service ──▶ 特征库/缓存                         │  │
│  │  SCM(供应商/采购) ──CDC──▶ Kafka ──▶ erp-sync-service ──▶ 特征库/缓存                        │  │
│  │  WMS(库存/库龄) ──CDC──▶ Kafka ──▶ erp-sync-service ──▶ 特征库/缓存                         │  │
│  │  FBA(FBA库存) ──API──▶ integration-service ──▶ 特征库/缓存 ★[V8新增]                         │  │
│  │  TMS(物流/运费) ──API──▶ integration-service ──▶ 特征库/缓存                                 │  │
│  │  CRM(评价/客诉) ──CDC──▶ Kafka ──▶ erp-sync-service ──▶ 知识库/缓存                         │  │
│  │  FMS(成本/利润) ──API──▶ integration-service ──▶ 特征库/缓存                                 │  │
│  │  BI(KPI/报表) ──API──▶ integration-service ──▶ 特征库/缓存                                   │  │
│  │  SYS(系统配置) ──API──▶ integration-service ──▶ 配置缓存 ★[V8新增]                           │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              数据输出（PMS → ERP）                                            │  │
│  │                                                                                              │  │
│  │  选品采纳 ──▶ integration-service ──▶ PDM(选品提报) + SCM(采购单) + WMS(库容) + SOM(Listing)  │  │
│  │  补货建议 ──▶ integration-service ──▶ SCM(采购计划) + WMS(库容) + FBA(补货计划) ★[V8]        │  │
│  │  定价建议 ──▶ integration-service ──▶ SOM(调整Listing价格)                                    │  │
│  │  广告优化 ──▶ integration-service ──▶ ADS(调整广告策略) ★[V8新增]                             │  │
│  │  风险预警 ──▶ integration-service ──▶ OMS(风控标记) + SCM(供应商风险)                          │  │
│  │  产品优化 ──▶ integration-service ──▶ PDM(更新产品) + SOM(优化Listing)                        │  │
│  │  看板推送 ──▶ integration-service ──▶ DASHBOARD(AI洞察卡片) ★[V8新增]                         │  │
│  │  系统配置 ──▶ integration-service ──▶ SYS(集成配置) ★[V8新增]                                 │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              闭环反馈（ERP → PMS）                                            │  │
│  │                                                                                              │  │
│  │  执行结果 ──▶ integration-service ──▶ suggestion_feedback ──▶ 模型优化                        │  │
│  │  业务指标 ──▶ BI ──▶ integration-service ──▶ 特征库 ──▶ Agent学习                             │  │
│  │  广告效果 ──▶ ADS ──▶ integration-service ──▶ ads_optimization_log ──▶ 广告模型 ★[V8]        │  │
│  │  FBA库存 ──▶ FBA ──▶ integration-service ──▶ fba_inventory_sync ──▶ 补货模型 ★[V8]          │  │
│  │  看板指标 ──▶ DASHBOARD ──▶ integration-service ──▶ 特征库 ──▶ 看板模型 ★[V8]                │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 数据湖设计

| 层级 | 前缀 | 说明 | 存储格式 | 示例表 |
| :--- | :--- | :--- | :--- | :--- |
| ODS | `ods.` | 原始数据层 | Parquet | ods_amazon_product, ods_amazon_review |
| DWD | `dwd.` | 明细数据层 | Parquet | dwd_product_info, dwd_review_sentiment |
| DWS | `dws.` | 汇总数据层 | Parquet | dws_product_daily_stats, dws_category_daily_stats |
| ADS | `ads.` | 应用数据层 | Parquet | ads_selection_features, ads_erp_sync_metrics |
| ERP | `erp.` | ERP同步数据层 | Parquet | erp_oms_orders, erp_wms_inventory, erp_ads_campaigns ★[V8] |

------

## 5. AI架构详细设计

### 5.1 Agent编排设计

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional

class SelectionState(TypedDict):
    task_id: str
    tenant_id: str
    category: str
    target_market: str
    budget_range: Optional[Dict]
    target_roi: float
    current_step: str
    progress: int
    collected_data: Dict[str, Any]
    market_analysis: Dict[str, Any]
    product_plan: Dict[str, Any]
    commercial_analysis: Dict[str, Any]
    ads_strategy: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    errors: List[str]
    erp_queries_log: List[Dict[str, Any]]

def build_selection_workflow() -> StateGraph:
    workflow = StateGraph(SelectionState)
    workflow.add_node("validate_input", validate_input_node)
    workflow.add_node("data_collection", data_collection_node)
    workflow.add_node("market_insight", market_insight_node)
    workflow.add_node("product_planning", product_planning_node)
    workflow.add_node("commercial_analysis", commercial_analysis_node)
    workflow.add_node("ads_strategy", ads_strategy_node)
    workflow.add_node("risk_assessment", risk_assessment_node)
    workflow.add_node("generate_recommendations", generate_recommendations_node)
    workflow.set_entry_point("validate_input")
    workflow.add_edge("validate_input", "data_collection")
    workflow.add_edge("data_collection", "market_insight")
    workflow.add_edge("market_insight", "product_planning")
    workflow.add_edge("product_planning", "commercial_analysis")
    workflow.add_edge("commercial_analysis", "ads_strategy")
    workflow.add_edge("ads_strategy", "risk_assessment")
    workflow.add_edge("risk_assessment", "generate_recommendations")
    workflow.add_edge("generate_recommendations", END)
    return workflow.compile()
```

### 5.2 RAG知识库设计

| 组件 | 技术 | 说明 |
| :--- | :--- | :--- |
| 向量存储 | Qdrant | 主库，HNSW索引，实时检索 |
| 关键词索引 | Elasticsearch | BM25检索，关键词匹配 |
| Rerank模型 | bge-reranker-v2 | 检索精排，提升准确率 |
| Embedding | BGE-large-zh | 文本向量化 |
| 知识图谱 | Neo4j | GraphRAG，实体关系推理 |

### 5.3 LLM服务设计

| 模型 | 用途 | 部署方式 |
| :--- | :--- | :--- |
| Qwen2.5-72B | Agent推理、报告生成 | vLLM (4×A100) |
| DeepSeek-V3 | 复杂推理、备选 | vLLM (2×A100) |
| LLaVA-13B | 多模态分析 | Triton (2×A10) |
| BGE-large-zh | Embedding | Triton (2×A10) |
| Phi-3-mini | 轻量分类、过滤 | Ollama (CPU) |
| Whisper | 语音转录 | Ollama (CPU) |

### 5.4 多模态服务设计

```python
class MultiModalAnalyzer:

    async def analyze_image(self, image_url: str) -> ImageAnalysis:
        image = await self.download_image(image_url)
        inputs = self.clip_processor(images=image, return_tensors="pt")
        image_features = self.clip_model.get_image_features(**inputs)
        description = await self.llava_client.generate(
            prompt="请详细描述这张商品图片的内容，包括产品外观、颜色、材质、设计特点等。",
            image=image
        )
        tags = await self.extract_visual_tags(image)
        return ImageAnalysis(vector=image_features.tolist(), description=description, tags=tags, source_url=image_url)

    async def analyze_video(self, video_url: str) -> VideoAnalysis:
        video_path = await self.download_video(video_url)
        key_frames = await self.extract_key_frames(video_path, interval=5)
        frame_analyses = [await self.analyze_image(frame) for frame in key_frames]
        audio_path = await self.extract_audio(video_path)
        transcript = await self.transcribe_audio(audio_path)
        summary = await self.summarize_video_content(frame_analyses, transcript)
        return VideoAnalysis(key_frames=frame_analyses, transcript=transcript, summary=summary)
```

------

# 第三卷：ERP 14域详细设计 ★[V8新增卷]

> 本卷详细设计ERP 14个业务域，每个域包含：领域模型、核心接口、数据库设计、与PMS的交互规范。

## 6. 工作台域 (DASHBOARD) ★[AI看板]

### 6.1 领域概述

工作台域是ERP系统的统一入口和决策中枢，为不同角色用户提供个性化看板、关键指标监控、任务待办和AI洞察摘要。

### 6.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  DashboardLayout │────▶│  DashboardWidget │────▶│  WidgetDataSource│
│  看板布局         │ 1:N │  看板组件         │ N:1 │  组件数据源       │
└──────────────────┘     └──────────────────┘     └──────────────────┘
┌──────────────────┐     ┌──────────────────┐
│  AIInsightCard   │     │  KPIIndicator    │
│  AI洞察卡片       │     │  KPI指标         │
└──────────────────┘     └──────────────────┘
```

### 6.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/dashboard/layouts` | 获取用户看板布局 |
| PUT | `/api/v1/dashboard/layouts` | 更新看板布局 |
| GET | `/api/v1/dashboard/widgets/{type}/data` | 获取组件数据 |
| GET | `/api/v1/dashboard/kpi` | 获取KPI指标 |
| GET | `/api/v1/dashboard/ai-insights` | 获取AI洞察摘要 |
| GET | `/api/v1/dashboard/todos` | 获取待办事项 |
| GET | `/api/v1/dashboard/alerts` | 获取告警通知 |

### 6.4 数据库设计

```sql
CREATE TABLE dashboard_layouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    layout_name VARCHAR(100) NOT NULL,
    layout_config JSONB NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dashboard_widgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layout_id UUID NOT NULL REFERENCES dashboard_layouts(id),
    widget_type VARCHAR(50) NOT NULL,
    widget_title VARCHAR(200),
    widget_config JSONB NOT NULL,
    data_source VARCHAR(50) NOT NULL,
    refresh_interval INT DEFAULT 300,
    position JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_insight_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    insight_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    detail JSONB,
    priority VARCHAR(20) DEFAULT 'medium',
    source_domain VARCHAR(20),
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    dismissed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→DASHBOARD** | `push_ai_insight` | PMS将选品洞察、风险预警、广告优化建议推送到看板 |
| **PMS→DASHBOARD** | `update_kpi_widget` | PMS更新选品相关KPI指标 |
| **DASHBOARD→PMS** | `query_selection_summary` | 看板查询选品任务汇总数据 |
| **DASHBOARD→PMS** | `query_suggestion_stats` | 看板查询智能建议统计数据 |

```python
class DashboardClient(BaseERPClient):

    async def push_ai_insight(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/dashboard/ai-insights", data={
            "insight_type": data["insight_type"],
            "title": data["title"],
            "summary": data["summary"],
            "detail": data.get("detail", {}),
            "priority": data.get("priority", "medium"),
            "source_domain": "pms",
            "valid_from": datetime.utcnow().isoformat()
        })

    async def update_kpi_widget(self, kpi_data: Dict) -> Dict:
        return await self._request("PUT", "/api/v1/dashboard/kpi", data=kpi_data)

    async def query_selection_summary(self, tenant_id: str) -> Dict:
        return await self._request("GET", "/api/v1/dashboard/widgets/selection_summary/data", params={"tenant_id": tenant_id})

    async def query_suggestion_stats(self, tenant_id: str) -> Dict:
        return await self._request("GET", "/api/v1/dashboard/widgets/suggestion_stats/data", params={"tenant_id": tenant_id})
```

------

## 7. 组织权限域 (IAM)

### 7.1 领域概述

组织权限域负责用户认证、角色管理、权限控制和租户隔离，为PMS与ERP提供统一的身份与访问管理。

### 7.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     Tenant       │────▶│      User        │────▶│      Role        │
│     租户          │ 1:N │     用户          │ N:M │     角色          │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                       │
                                                  ┌────▼────┐
                                                  │Permission│
                                                  │  权限     │
                                                  └─────────┘
```

### 7.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/iam/auth/login` | 用户登录 |
| POST | `/api/v1/iam/auth/refresh` | 刷新Token |
| GET | `/api/v1/iam/users/me` | 获取当前用户信息 |
| GET | `/api/v1/iam/users/me/permissions` | 获取当前用户权限 |
| GET | `/api/v1/iam/tenants/{id}/config` | 获取租户配置 |
| GET | `/api/v1/iam/roles` | 获取角色列表 |
| POST | `/api/v1/iam/service-accounts/verify` | 服务间认证验证 |

### 7.4 数据库设计

```sql
CREATE TABLE iam_tenants (
    id VARCHAR(36) PRIMARY KEY,
    tenant_name VARCHAR(200) NOT NULL,
    plan VARCHAR(50) DEFAULT 'standard',
    config JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE iam_users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES iam_tenants(id),
    username VARCHAR(100) NOT NULL,
    email VARCHAR(200),
    status VARCHAR(20) DEFAULT 'active',
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE iam_roles (
    id VARCHAR(36) PRIMARY KEY,
    role_code VARCHAR(50) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE iam_user_roles (
    user_id VARCHAR(36) NOT NULL REFERENCES iam_users(id),
    role_id VARCHAR(36) NOT NULL REFERENCES iam_roles(id),
    tenant_id VARCHAR(36) NOT NULL,
    scope JSONB,
    PRIMARY KEY (user_id, role_id, tenant_id)
);

CREATE TABLE iam_service_accounts (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    service_name VARCHAR(100) NOT NULL,
    api_key_hash VARCHAR(256) NOT NULL,
    permissions JSONB NOT NULL DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 7.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **IAM→PMS** | `verify_token` | PMS验证用户Token有效性 |
| **IAM→PMS** | `get_user_permissions` | PMS获取用户权限列表 |
| **IAM→PMS** | `get_tenant_config` | PMS获取租户配置 |
| **PMS→IAM** | `register_service_account` | PMS注册服务间调用账号 |

```python
class IAMClient(BaseERPClient):

    async def verify_token(self, token: str) -> Dict:
        return await self._request("POST", "/api/v1/iam/auth/verify", data={"token": token})

    async def get_user_permissions(self, user_id: str) -> Dict:
        return await self._request("GET", f"/api/v1/iam/users/{user_id}/permissions")

    async def get_tenant_config(self, tenant_id: str) -> Dict:
        return await self._request("GET", f"/api/v1/iam/tenants/{tenant_id}/config")

    async def register_service_account(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/iam/service-accounts", data=data)
```

------

## 8. 产品开发域 (PDM) ★[AI选品]

### 8.1 领域概述

产品开发域管理产品全生命周期，从选品提报、产品定义、规格确认到产品上架。PMS的AI选品能力直接驱动PDM的产品创建流程。

### 8.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ SelectionProposal│────▶│   ProductSpec    │────▶│  CompetitorAnalysis│
│  选品提报         │ 1:1 │   产品规格       │ 1:N │   竞品分析        │
└──────────────────┘     └──────────────────┘     └──────────────────┘
┌──────────────────┐     ┌──────────────────┐
│  ProductLifecycle│     │  ProductDocument │
│  产品生命周期     │     │  产品文档         │
└──────────────────┘     └──────────────────┘
```

### 8.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/pdm/selection-proposals` | 创建选品提报 |
| GET | `/api/v1/pdm/selection-proposals` | 获取提报列表 |
| GET | `/api/v1/pdm/selection-proposals/{id}` | 获取提报详情 |
| PUT | `/api/v1/pdm/selection-proposals/{id}/approve` | 审批提报 |
| GET | `/api/v1/pdm/products` | 获取产品列表 |
| GET | `/api/v1/pdm/products/{id}/specs` | 获取产品规格 |
| GET | `/api/v1/pdm/competitor-analysis` | 获取竞品分析 |
| GET | `/api/v1/pdm/product-lifecycle` | 获取产品生命周期 |

### 8.4 数据库设计

```sql
CREATE TABLE pdm_selection_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    source VARCHAR(20) DEFAULT 'manual',
    ai_suggested BOOLEAN DEFAULT FALSE,
    product_name VARCHAR(500) NOT NULL,
    category VARCHAR(200) NOT NULL,
    target_market VARCHAR(50) NOT NULL,
    estimated_cost DECIMAL(12,2),
    market_analysis JSONB,
    risk_assessment JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    approved_by VARCHAR(36),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pdm_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    proposal_id UUID REFERENCES pdm_selection_proposals(id),
    product_name VARCHAR(500) NOT NULL,
    category VARCHAR(200) NOT NULL,
    asin VARCHAR(20),
    specs JSONB NOT NULL DEFAULT '{}',
    lifecycle_stage VARCHAR(30) DEFAULT 'development',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pdm_competitor_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    product_id UUID REFERENCES pdm_products(id),
    competitor_asin VARCHAR(20) NOT NULL,
    competitor_name VARCHAR(500),
    price DECIMAL(10,2),
    rating DECIMAL(3,2),
    review_count INT,
    features JSONB,
    strengths TEXT[],
    weaknesses TEXT[],
    analyzed_at TIMESTAMP DEFAULT NOW()
);
```

### 8.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→PDM** | `create_selection_proposal` | PMS采纳推荐后创建选品提报 |
| **PMS→PDM** | `update_product_data` | PMS更新产品资料 |
| **PDM→PMS** | `query_product_specs` | PMS查询产品规格信息 |
| **PDM→PMS** | `query_competitor_analysis` | PMS查询竞品分析数据 |
| **PDM→PMS** | `query_product_lifecycle` | PMS查询产品生命周期阶段 |

```python
class PDMClient(BaseERPClient):

    async def create_selection_proposal(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/pdm/selection-proposals", data={
            "type": "selection_proposal", "source": "ai_pms", "ai_suggested": True,
            "product_name": data["product_title"], "category": data["category"],
            "target_market": data.get("target_market", "US"),
            "estimated_cost": data.get("estimated_cost"),
            "market_analysis": data.get("market_analysis"),
            "risk_assessment": data.get("risk_assessment"),
            "metadata": data.get("metadata", {})
        })

    async def query_product_specs(self, category: str) -> List[Dict]:
        return await self._request("GET", "/api/v1/pdm/products", params={"category": category, "status": "active", "page_size": 100})

    async def query_competitor_analysis(self, product_id: str) -> Dict:
        return await self._request("GET", f"/api/v1/pdm/products/{product_id}/competitor-analysis")

    async def query_product_lifecycle(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/pdm/product-lifecycle", params={"category": category})
```

------

## 9. 销售运营域 (SOM)

### 9.1 领域概述

销售运营域管理Listing创建、价格调整、库存分配和销售策略执行，是PMS选品采纳后的核心执行域。

### 9.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    Listing       │────▶│  PricingStrategy │     │ SalesPerformance │
│   Listing管理     │ 1:1 │   定价策略        │     │  销售表现         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 9.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/som/listings` | 创建Listing草稿 |
| PUT | `/api/v1/som/listings/{id}/price` | 调整Listing价格 |
| GET | `/api/v1/som/listings` | 获取Listing列表 |
| GET | `/api/v1/som/listings/{id}/performance` | 获取Listing表现 |
| GET | `/api/v1/som/category-bsr` | 获取类目BSR |
| GET | `/api/v1/som/pricing-benchmark` | 获取定价基准 |

### 9.4 数据库设计

```sql
CREATE TABLE som_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    title VARCHAR(500) NOT NULL,
    price DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    quantity INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft',
    marketplace VARCHAR(20) DEFAULT 'amazon',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE som_pricing_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES som_listings(id),
    old_price DECIMAL(10,2),
    new_price DECIMAL(10,2),
    reason VARCHAR(200),
    source VARCHAR(20) DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 9.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→SOM** | `create_listing_draft` | PMS采纳后创建Listing草稿 |
| **PMS→SOM** | `adjust_listing_price` | PMS定价建议调整价格 |
| **SOM→PMS** | `query_listing_performance` | PMS查询Listing表现数据 |
| **SOM→PMS** | `query_category_bsr` | PMS查询类目BSR排名 |
| **SOM→PMS** | `query_pricing_benchmark` | PMS查询定价基准数据 |

```python
class SOMClient(BaseERPClient):

    async def create_listing_draft(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/som/listings", data=data)

    async def adjust_listing_price(self, listing_id: str, price_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/v1/som/listings/{listing_id}/price", data=price_data)

    async def query_listing_performance(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/som/listings", params={"asin": asin})

    async def query_category_bsr(self, category: str, marketplace: str) -> Dict:
        return await self._request("GET", "/api/v1/som/category-bsr", params={"category": category, "marketplace": marketplace})

    async def query_pricing_benchmark(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/som/pricing-benchmark", params={"category": category})
```

------

## 10. 广告管理域 (ADS) ★[AI优化]

### 10.1 领域概述

广告管理域管理亚马逊广告活动的创建、优化和效果追踪。PMS的AI优化能力为ADS提供智能广告策略建议、关键词优化和ACOS优化。

### 10.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Campaign       │────▶│   AdGroup        │────▶│   Keyword        │
│   广告活动        │ 1:N │   广告组          │ 1:N │   关键词          │
└──────────────────┘     └──────────────────┘     └──────────────────┘
┌──────────────────┐     ┌──────────────────┐
│  AdPerformance   │     │  BudgetAllocation│
│  广告表现         │     │  预算分配         │
└──────────────────┘     └──────────────────┘
```

### 10.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/ads/campaigns` | 获取广告活动列表 |
| GET | `/api/v1/ads/campaigns/{id}/performance` | 获取活动表现 |
| GET | `/api/v1/ads/campaigns/{id}/keywords` | 获取关键词列表 |
| PUT | `/api/v1/ads/campaigns/{id}/budget` | 调整活动预算 |
| PUT | `/api/v1/ads/campaigns/{id}/bids` | 调整竞价 |
| PUT | `/api/v1/ads/keywords/{id}/bid` | 调整关键词竞价 |
| POST | `/api/v1/ads/campaigns/{id}/suggestions/apply` | 应用AI建议 |
| GET | `/api/v1/ads/acos-analysis` | 获取ACOS分析 |

### 10.4 数据库设计

```sql
CREATE TABLE ads_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    campaign_id VARCHAR(100) NOT NULL,
    campaign_name VARCHAR(500) NOT NULL,
    campaign_type VARCHAR(30) NOT NULL,
    marketplace VARCHAR(20) DEFAULT 'amazon',
    daily_budget DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'active',
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ads_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES ads_campaigns(id),
    keyword_text VARCHAR(500) NOT NULL,
    match_type VARCHAR(20) NOT NULL,
    bid DECIMAL(10,4),
    impressions INT DEFAULT 0,
    clicks INT DEFAULT 0,
    spend DECIMAL(10,2) DEFAULT 0,
    sales DECIMAL(10,2) DEFAULT 0,
    acos DECIMAL(5,4),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ads_daily_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES ads_campaigns(id),
    date DATE NOT NULL,
    impressions INT DEFAULT 0,
    clicks INT DEFAULT 0,
    ctr DECIMAL(5,4),
    spend DECIMAL(10,2) DEFAULT 0,
    sales DECIMAL(10,2) DEFAULT 0,
    acos DECIMAL(5,4),
    roas DECIMAL(10,2),
    orders INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(campaign_id, date)
);
```

### 10.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→ADS** | `adjust_ad_strategy` | PMS下发广告优化建议 |
| **PMS→ADS** | `adjust_keyword_bid` | PMS建议关键词竞价调整 |
| **PMS→ADS** | `adjust_campaign_budget` | PMS建议预算调整 |
| **ADS→PMS** | `query_campaign_performance` | PMS查询广告活动表现 |
| **ADS→PMS** | `query_acos_analysis` | PMS查询ACOS分析数据 |
| **ADS→PMS** | `query_keyword_performance` | PMS查询关键词表现 |

```python
class ADSClient(BaseERPClient):

    async def adjust_ad_strategy(self, campaign_id: str, strategy: Dict) -> Dict:
        return await self._request("POST", f"/api/v1/ads/campaigns/{campaign_id}/suggestions/apply", data={
            "suggestion_type": strategy["type"],
            "suggestion_data": strategy["data"],
            "source": "ai_pms",
            "confidence": strategy.get("confidence", 0.8)
        })

    async def adjust_keyword_bid(self, keyword_id: str, bid_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/v1/ads/keywords/{keyword_id}/bid", data=bid_data)

    async def adjust_campaign_budget(self, campaign_id: str, budget_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/v1/ads/campaigns/{campaign_id}/budget", data=budget_data)

    async def query_campaign_performance(self, campaign_id: str, days: int = 30) -> Dict:
        return await self._request("GET", f"/api/v1/ads/campaigns/{campaign_id}/performance", params={"days": days})

    async def query_acos_analysis(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/ads/acos-analysis", params={"category": category})

    async def query_keyword_performance(self, campaign_id: str) -> Dict:
        return await self._request("GET", f"/api/v1/ads/campaigns/{campaign_id}/keywords")
```

------

## 11. 订单域 (OMS) ★[AI风控]

### 11.1 领域概述

订单域管理订单全生命周期，包括订单接收、处理、发货和售后。PMS的AI风控能力为OMS提供欺诈检测和合规风险预警。

### 11.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     Order        │────▶│   OrderItem      │────▶│  ComplianceRisk  │
│     订单          │ 1:N │   订单明细        │ 1:N │   合规风险        │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 11.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/oms/orders` | 获取订单列表 |
| GET | `/api/v1/oms/orders/{id}` | 获取订单详情 |
| GET | `/api/v1/oms/sales-trend` | 获取销售趋势 |
| GET | `/api/v1/oms/order-statistics` | 获取订单统计 |
| POST | `/api/v1/oms/listing-drafts` | 创建Listing草稿 |
| PUT | `/api/v1/oms/listing-drafts/{id}/price` | 调整Listing价格 |
| GET | `/api/v1/oms/compliance-risks` | 获取合规风险 |

### 11.4 数据库设计

```sql
CREATE TABLE oms_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    asin VARCHAR(20),
    sku VARCHAR(100),
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    order_status VARCHAR(30) NOT NULL,
    marketplace VARCHAR(20) DEFAULT 'amazon',
    order_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE oms_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES oms_orders(id),
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2),
    item_status VARCHAR(30),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 11.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→OMS** | `create_listing_draft` | PMS采纳后创建Listing草稿 |
| **PMS→OMS** | `adjust_listing_price` | PMS定价建议调整价格 |
| **OMS→PMS** | `query_sales_trend` | PMS查询销售趋势 |
| **OMS→PMS** | `query_order_statistics` | PMS查询订单统计 |
| **OMS→PMS** | `query_compliance_risks` | PMS查询合规风险 |
| **OMS→PMS** | CDC: `cdc.oms.orders` | CDC推送订单变更 |

```python
class OMSClient(BaseERPClient):

    async def create_listing_draft(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/oms/listing-drafts", data=data)

    async def adjust_listing_price(self, listing_id: str, price_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/v1/oms/listing-drafts/{listing_id}/price", data=price_data)

    async def query_sales_trend(self, category: str, market: str, days: int = 90) -> Dict:
        return await self._request("GET", "/api/v1/oms/sales-trend", params={"category": category, "market": market, "days": days})

    async def query_order_statistics(self, params: Dict) -> Dict:
        return await self._request("GET", "/api/v1/oms/order-statistics", params=params)

    async def query_compliance_risks(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/oms/compliance-risks", params={"asin": asin})
```

------

## 12. 供应链域 (SCM) ★[AI补货]

### 12.1 领域概述

供应链域管理供应商、采购订单和补货计划。PMS的AI补货能力为SCM提供智能补货建议、供应商风险评估和采购计划优化。

### 12.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    Supplier      │────▶│  PurchaseOrder   │────▶│ ReplenishmentPlan│
│    供应商         │ 1:N │   采购订单        │ 1:N │   补货计划        │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 12.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/scm/suppliers` | 获取供应商列表 |
| GET | `/api/v1/scm/suppliers/{id}/performance` | 获取供应商表现 |
| GET | `/api/v1/scm/supplier-risk` | 获取供应商风险 |
| GET | `/api/v1/scm/purchase-cost` | 获取采购成本 |
| POST | `/api/v1/scm/purchase-orders` | 创建采购订单 |
| POST | `/api/v1/scm/replenishment-plans` | 创建补货计划 |

### 12.4 数据库设计

```sql
CREATE TABLE scm_suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    supplier_code VARCHAR(50) NOT NULL,
    supplier_name VARCHAR(500) NOT NULL,
    category VARCHAR(200),
    lead_time_days INT,
    quality_score DECIMAL(3,2),
    price_competitiveness DECIMAL(3,2),
    reliability_score DECIMAL(3,2),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE scm_purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    supplier_id UUID REFERENCES scm_suppliers(id),
    po_number VARCHAR(50) NOT NULL,
    product_specs JSONB NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'pending',
    expected_delivery DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 12.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→SCM** | `create_purchase_order` | PMS采纳后创建采购订单 |
| **PMS→SCM** | `create_replenishment_plan` | PMS补货建议创建补货计划 |
| **SCM→PMS** | `query_supplier_performance` | PMS查询供应商表现 |
| **SCM→PMS** | `query_supplier_risk` | PMS查询供应商风险 |
| **SCM→PMS** | `query_purchase_cost` | PMS查询采购成本 |
| **SCM→PMS** | CDC: `cdc.scm.purchase_orders` | CDC推送采购订单变更 |

```python
class SCMClient(BaseERPClient):

    async def create_purchase_order(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/scm/purchase-orders", data=data)

    async def create_replenishment_plan(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/scm/replenishment-plans", data=data)

    async def query_supplier_performance(self, supplier_id: str) -> Dict:
        return await self._request("GET", f"/api/v1/scm/suppliers/{supplier_id}/performance")

    async def query_supplier_risk(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/scm/supplier-risk", params={"category": category})

    async def query_purchase_cost(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/scm/purchase-cost", params={"category": category})
```

------

## 13. 仓储域 (WMS) ★[AI预测]

### 13.1 领域概述

仓储域管理仓库库存、库龄和库容。PMS的AI预测能力为WMS提供库存需求预测、库龄风险预警和库容优化建议。

### 13.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Warehouse      │────▶│   Inventory      │────▶│  InventoryRisk   │
│   仓库            │ 1:N │   库存            │ 1:N │   库存风险        │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 13.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/wms/inventory` | 获取库存状态 |
| GET | `/api/v1/wms/inventory-risk` | 获取库存风险 |
| GET | `/api/v1/wms/warehouse-capacity` | 获取仓库容量 |
| POST | `/api/v1/wms/capacity-reservation` | 预留库容 |

### 13.4 数据库设计

```sql
CREATE TABLE wms_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    asin VARCHAR(20),
    warehouse_id VARCHAR(50) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    reserved INT DEFAULT 0,
    available INT GENERATED ALWAYS AS (quantity - reserved) STORED,
    age_days INT DEFAULT 0,
    last_restock_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 13.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→WMS** | `reserve_capacity` | PMS采纳后预留库容 |
| **WMS→PMS** | `query_inventory_status` | PMS查询库存状态 |
| **WMS→PMS** | `query_inventory_risk` | PMS查询库存风险 |
| **WMS→PMS** | `query_warehouse_capacity` | PMS查询仓库容量 |
| **WMS→PMS** | CDC: `cdc.wms.inventory` | CDC推送库存变更 |

```python
class WMSClient(BaseERPClient):

    async def reserve_capacity(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/wms/capacity-reservation", data=data)

    async def query_inventory_status(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/wms/inventory", params={"asin": asin})

    async def query_inventory_risk(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/wms/inventory-risk", params={"category": category})

    async def query_warehouse_capacity(self, warehouse_id: str) -> Dict:
        return await self._request("GET", "/api/v1/wms/warehouse-capacity", params={"warehouse_id": warehouse_id})
```

------

## 14. FBA/海外仓域 (FBA)

### 14.1 领域概述

FBA/海外仓域管理亚马逊FBA库存、入库计划和海外仓运营。PMS通过FBA域获取FBA库存数据并下发补货计划。

### 14.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  FBAInventory    │────▶│  InboundShipment │────▶│  FBAFeeStructure │
│  FBA库存         │ 1:N │  入库货件         │ 1:1 │  FBA费用结构      │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 14.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/fba/inventory` | 获取FBA库存 |
| GET | `/api/v1/fba/inventory/{sku}` | 获取SKU的FBA库存详情 |
| GET | `/api/v1/fba/inbound-shipments` | 获取入库货件列表 |
| POST | `/api/v1/fba/inbound-shipments` | 创建入库货件计划 |
| GET | `/api/v1/fba/fee-estimate` | 获取FBA费用估算 |
| GET | `/api/v1/fba/restock-recommendations` | 获取补货建议 |

### 14.4 数据库设计

```sql
CREATE TABLE fba_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    asin VARCHAR(20),
    marketplace VARCHAR(20) DEFAULT 'amazon',
    fulfillable_qty INT DEFAULT 0,
    inbound_qty INT DEFAULT 0,
    reserved_qty INT DEFAULT 0,
    researching_qty INT DEFAULT 0,
    unsellable_qty INT DEFAULT 0,
    last_updated TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE fba_inbound_shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    shipment_id VARCHAR(100) NOT NULL,
    shipment_name VARCHAR(500),
    status VARCHAR(30) NOT NULL,
    destination_fulfillment_center VARCHAR(50),
    items JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE fba_fee_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    product_tier VARCHAR(50),
    monthly_storage_fee DECIMAL(10,4),
    fulfillment_fee DECIMAL(10,4),
    referral_fee_percent DECIMAL(5,4),
    total_fba_cost DECIMAL(10,2),
    estimated_at TIMESTAMP DEFAULT NOW()
);
```

### 14.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→FBA** | `create_inbound_shipment` | PMS补货建议创建入库货件 |
| **FBA→PMS** | `query_fba_inventory` | PMS查询FBA库存数据 |
| **FBA→PMS** | `query_fee_estimate` | PMS查询FBA费用估算 |
| **FBA→PMS** | `query_restock_recommendations` | PMS查询补货建议 |

```python
class FBAClient(BaseERPClient):

    async def create_inbound_shipment(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/fba/inbound-shipments", data=data)

    async def query_fba_inventory(self, sku: str = None) -> Dict:
        params = {"sku": sku} if sku else {}
        return await self._request("GET", "/api/v1/fba/inventory", params=params)

    async def query_fee_estimate(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/fba/fee-estimate", params={"asin": asin})

    async def query_restock_recommendations(self, category: str = None) -> Dict:
        params = {"category": category} if category else {}
        return await self._request("GET", "/api/v1/fba/restock-recommendations", params=params)
```

------

## 15. 物流域 (TMS)

### 15.1 领域概述

物流域管理头程物流、尾程配送和运费计算。PMS通过TMS域获取物流成本数据用于商业化分析。

### 15.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Shipment        │────▶│  ShippingRate    │────▶│  LogisticsRisk   │
│  货件            │ 1:N │  运费费率         │ 1:N │  物流风险         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 15.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/tms/shipping-cost` | 获取运费 |
| GET | `/api/v1/tms/logistics-risk` | 获取物流风险 |
| GET | `/api/v1/tms/delivery-performance` | 获取配送表现 |
| POST | `/api/v1/tms/shipment-plans` | 创建货件计划 |

### 15.4 数据库设计

```sql
CREATE TABLE tms_shipping_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    origin_country VARCHAR(3) NOT NULL,
    destination_country VARCHAR(3) NOT NULL,
    shipping_method VARCHAR(50) NOT NULL,
    weight_tier VARCHAR(30),
    rate_per_kg DECIMAL(10,4),
    min_charge DECIMAL(10,2),
    transit_days_min INT,
    transit_days_max INT,
    effective_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 15.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **PMS→TMS** | `create_shipment_plan` | PMS创建货件计划 |
| **TMS→PMS** | `query_shipping_cost` | PMS查询运费数据 |
| **TMS→PMS** | `query_logistics_risk` | PMS查询物流风险 |
| **TMS→PMS** | `query_delivery_performance` | PMS查询配送表现 |

```python
class TMSClient(BaseERPClient):

    async def create_shipment_plan(self, data: Dict) -> Dict:
        return await self._request("POST", "/api/v1/tms/shipment-plans", data=data)

    async def query_shipping_cost(self, origin: str, destination: str, weight_kg: float) -> Dict:
        return await self._request("GET", "/api/v1/tms/shipping-cost", params={"origin": origin, "destination": destination, "weight_kg": weight_kg})

    async def query_logistics_risk(self, route: str) -> Dict:
        return await self._request("GET", "/api/v1/tms/logistics-risk", params={"route": route})

    async def query_delivery_performance(self, carrier: str = None) -> Dict:
        params = {"carrier": carrier} if carrier else {}
        return await self._request("GET", "/api/v1/tms/delivery-performance", params=params)
```

------

## 16. 客服售后域 (CRM) ★[AI情感]

### 16.1 领域概述

客服售后域管理客户评价、投诉和售后服务。PMS的AI情感能力为CRM提供评价情感分析、客诉智能分类和客户洞察。

### 16.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   CustomerReview │────▶│ SentimentAnalysis│     │  Complaint       │
│   客户评价        │ 1:1 │   情感分析        │     │  投诉            │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 16.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/crm/reviews` | 获取评价列表 |
| GET | `/api/v1/crm/review-analysis` | 获取评价分析 |
| GET | `/api/v1/crm/complaints` | 获取投诉列表 |
| GET | `/api/v1/crm/complaint-analysis` | 获取投诉分析 |
| GET | `/api/v1/crm/customer-insights` | 获取客户洞察 |

### 16.4 数据库设计

```sql
CREATE TABLE crm_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    review_id VARCHAR(100),
    rating INT NOT NULL,
    title VARCHAR(500),
    content TEXT,
    sentiment VARCHAR(20),
    sentiment_score DECIMAL(5,4),
    verified_purchase BOOLEAN DEFAULT FALSE,
    review_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE crm_complaints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    order_id VARCHAR(100),
    asin VARCHAR(20),
    complaint_type VARCHAR(50) NOT NULL,
    description TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'open',
    resolution TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);
```

### 16.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **CRM→PMS** | `query_review_analysis` | PMS查询评价分析数据 |
| **CRM→PMS** | `query_complaint_analysis` | PMS查询投诉分析数据 |
| **CRM→PMS** | `query_customer_insights` | PMS查询客户洞察 |
| **CRM→PMS** | CDC: `cdc.crm.reviews` | CDC推送评价变更 |

```python
class CRMClient(BaseERPClient):

    async def query_review_analysis(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/crm/review-analysis", params={"asin": asin})

    async def query_complaint_analysis(self, category: str) -> Dict:
        return await self._request("GET", "/api/v1/crm/complaint-analysis", params={"category": category})

    async def query_customer_insights(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/crm/customer-insights", params={"asin": asin})
```

------

## 17. 财务域 (FMS)

### 17.1 领域概述

财务域管理成本核算、利润分析和资金管理。PMS通过FMS域获取全链路成本数据用于商业化分析。

### 17.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  CostBreakdown   │────▶│  ProfitAnalysis  │────▶│  BudgetStatus    │
│  成本分解         │ 1:1 │  利润分析         │ 1:1 │  预算状态         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 17.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/fms/cost-breakdown` | 获取成本分解 |
| GET | `/api/v1/fms/profit-analysis` | 获取利润分析 |
| GET | `/api/v1/fms/budget-status` | 获取预算状态 |

### 17.4 数据库设计

```sql
CREATE TABLE fms_cost_breakdown (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    bom_cost DECIMAL(10,2),
    shipping_cost DECIMAL(10,2),
    tariff_cost DECIMAL(10,2),
    fba_fee DECIMAL(10,2),
    ad_cost DECIMAL(10,2),
    other_cost DECIMAL(10,2),
    total_cost DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    period DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 17.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **FMS→PMS** | `query_cost_breakdown` | PMS查询成本分解 |
| **FMS→PMS** | `query_profit_analysis` | PMS查询利润分析 |
| **FMS→PMS** | `query_budget_status` | PMS查询预算状态 |

```python
class FMSClient(BaseERPClient):

    async def query_cost_breakdown(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/fms/cost-breakdown", params={"asin": asin})

    async def query_profit_analysis(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/fms/profit-analysis", params={"asin": asin})

    async def query_budget_status(self, tenant_id: str) -> Dict:
        return await self._request("GET", "/api/v1/fms/budget-status", params={"tenant_id": tenant_id})
```

------

## 18. 商业智能域 (BI) ★[KPI]

### 18.1 领域概述

商业智能域管理KPI指标、报表分析和趋势预测。PMS的AI能力为BI提供KPI智能分析、趋势预测和异常检测。

### 18.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  KPIDashboard    │────▶│  TrendReport     │────▶│  AnomalyAlert    │
│  KPI仪表盘       │ 1:N │  趋势报告         │ 1:N │  异常告警         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 18.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/bi/kpi-dashboard` | 获取KPI仪表盘 |
| GET | `/api/v1/bi/market-trend` | 获取市场趋势 |
| GET | `/api/v1/bi/category-bsr` | 获取类目BSR |
| GET | `/api/v1/bi/product-performance` | 获取产品表现 |

### 18.4 数据库设计

```sql
CREATE TABLE bi_kpi_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(15,4),
    target_value DECIMAL(15,4),
    period DATE NOT NULL,
    category VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 18.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **BI→PMS** | `query_market_trend` | PMS查询市场趋势 |
| **BI→PMS** | `query_category_bsr` | PMS查询类目BSR |
| **BI→PMS** | `query_product_performance` | PMS查询产品表现 |
| **BI→PMS** | `query_kpi_dashboard` | PMS查询KPI仪表盘 |

```python
class BIClient(BaseERPClient):

    async def query_market_trend(self, category: str, market: str) -> Dict:
        return await self._request("GET", "/api/v1/bi/market-trend", params={"category": category, "market": market})

    async def query_category_bsr(self, category: str, market: str) -> Dict:
        return await self._request("GET", "/api/v1/bi/category-bsr", params={"category": category, "market": market})

    async def query_product_performance(self, asin: str) -> Dict:
        return await self._request("GET", "/api/v1/bi/product-performance", params={"asin": asin})

    async def query_kpi_dashboard(self, tenant_id: str) -> Dict:
        return await self._request("GET", "/api/v1/bi/kpi-dashboard", params={"tenant_id": tenant_id})
```

------

## 19. 系统设置域 (SYS)

### 19.1 领域概述

系统设置域管理ERP系统的全局配置、集成参数和运行参数。PMS通过SYS域获取和更新集成配置。

### 19.2 领域模型

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  SystemConfig    │────▶│ IntegrationParam │────▶│  RuntimeParam    │
│  系统配置         │ 1:N │  集成参数         │ 1:N │  运行参数         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 19.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/api/v1/sys/configs` | 获取系统配置列表 |
| GET | `/api/v1/sys/configs/{key}` | 获取配置项 |
| PUT | `/api/v1/sys/configs/{key}` | 更新配置项 |
| GET | `/api/v1/sys/integration-params` | 获取集成参数 |
| PUT | `/api/v1/sys/integration-params/{domain}` | 更新域集成参数 |
| GET | `/api/v1/sys/health` | 系统健康检查 |

### 19.4 数据库设计

```sql
CREATE TABLE sys_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    config_key VARCHAR(200) NOT NULL,
    config_value JSONB NOT NULL,
    config_type VARCHAR(30) DEFAULT 'string',
    description TEXT,
    encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, config_key)
);

CREATE TABLE sys_integration_params (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL,
    domain VARCHAR(20) NOT NULL,
    base_url VARCHAR(500),
    api_key_encrypted TEXT,
    timeout_ms INT DEFAULT 30000,
    retry_config JSONB DEFAULT '{"max_retries": 3, "backoff_ms": 1000}',
    rate_limit JSONB DEFAULT '{"requests_per_second": 10}',
    circuit_breaker JSONB DEFAULT '{"failure_threshold": 5, "recovery_timeout_ms": 30000}',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, domain)
);
```

### 19.5 PMS交互设计

| 交互方向 | 接口 | 说明 |
| :--- | :--- | :--- |
| **SYS→PMS** | `get_integration_params` | PMS获取各域集成参数 |
| **PMS→SYS** | `update_integration_params` | PMS更新域集成参数 |
| **SYS→PMS** | `get_system_config` | PMS获取系统配置 |
| **PMS→SYS** | `health_check` | PMS检查ERP系统健康状态 |

```python
class SYSClient(BaseERPClient):

    async def get_integration_params(self, domain: str) -> Dict:
        return await self._request("GET", f"/api/v1/sys/integration-params/{domain}")

    async def update_integration_params(self, domain: str, params: Dict) -> Dict:
        return await self._request("PUT", f"/api/v1/sys/integration-params/{domain}", data=params)

    async def get_system_config(self, key: str) -> Dict:
        return await self._request("GET", f"/api/v1/sys/configs/{key}")

    async def health_check(self) -> Dict:
        return await self._request("GET", "/api/v1/sys/health")
```

------

# 第四卷：PMS模块实现详细设计

## 20. 选品服务详细设计

### 20.1 服务概述

选品服务是PMS的核心业务服务，负责选品任务的全生命周期管理，包括任务创建、数据采集、Agent分析、推荐生成和采纳执行。

### 20.2 模块架构

```
┌──────────────────────────────────────────────────────────────────┐
│                      Selection Service                            │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ TaskManager  │  │ RecEngine    │  │AdoptionEngine│           │
│  │ 任务管理器    │  │ 推荐引擎      │  │ 采纳执行引擎  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ ScoringModel │  │ SuggestionMgr│  │ FeedbackLoop │           │
│  │ 评分模型      │  │ 建议管理器    │  │ 反馈闭环      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### 20.3 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/selection/tasks` | 创建选品任务 |
| GET | `/api/v1/selection/tasks` | 获取任务列表 |
| GET | `/api/v1/selection/tasks/{id}` | 获取任务详情 |
| POST | `/api/v1/selection/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/v1/selection/tasks/{id}/recommendations` | 获取推荐列表 |
| POST | `/api/v1/selection/recommendations/{id}/adopt` | 采纳推荐 |
| GET | `/api/v1/selection/suggestions` | 获取智能建议 |
| POST | `/api/v1/selection/suggestions/{id}/feedback` | 提交建议反馈 |

### 20.4 核心代码

```python
class SelectionService:
    def __init__(self, db: AsyncSession, agent_service: AgentService, integration_service: ERPIntegrationService):
        self.db = db
        self.agent_service = agent_service
        self.integration = integration_service

    async def create_task(self, user_id: str, tenant_id: str, params: SelectionParams) -> SelectionTask:
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
            "budget_range": params.budget_range, "target_roi": params.target_roi
        })
        return task

    async def adopt_recommendation(self, recommendation_id: UUID, user_id: str) -> AdoptionExecution:
        recommendation = await self._get_recommendation(recommendation_id)
        if recommendation.status != "approved":
            raise ValueError("Recommendation must be approved before adoption")
        execution = AdoptionExecution(
            id=uuid4(), recommendation_id=recommendation_id, user_id=user_id,
            status="pending", erp_steps=self._build_erp_steps(recommendation),
            current_step=0, created_at=datetime.utcnow()
        )
        self.db.add(execution)
        recommendation.status = "adopted"
        await self.db.commit()
        await self.integration.execute_adoption(execution.id)
        return execution

    def _build_erp_steps(self, recommendation: Recommendation) -> List[Dict]:
        steps = [
            {"domain": "PDM", "action": "create_selection_proposal", "data": {"product_title": recommendation.product_title, "category": recommendation.category}},
            {"domain": "SCM", "action": "create_purchase_order", "data": {"product_specs": recommendation.product_plan.get("specs", {})}},
            {"domain": "WMS", "action": "reserve_capacity", "data": {"warehouse_id": "default", "quantity": recommendation.commercial_analysis.get("initial_order_qty", 100)}},
            {"domain": "SOM", "action": "create_listing_draft", "data": {"title": recommendation.product_title, "price": recommendation.commercial_analysis.get("suggested_price")}},
        ]
        if recommendation.ads_strategy:
            steps.append({"domain": "ADS", "action": "adjust_ad_strategy", "data": recommendation.ads_strategy})
        if recommendation.risk_assessment.get("fba_recommended"):
            steps.append({"domain": "FBA", "action": "create_inbound_shipment", "data": {"sku": recommendation.sku}})
        return steps
```

------

## 21. Agent服务详细设计

### 21.1 服务概述

Agent服务负责AI Agent的编排与执行，基于LangGraph实现状态机工作流，协调多个专业Agent完成选品分析任务。

### 21.2 Agent列表

| Agent | 职责 | LLM模型 | 输入 | 输出 |
| :--- | :--- | :--- | :--- | :--- |
| **DataCollectionAgent** | 数据采集与清洗 | Phi-3-mini | 类目/市场 | 原始数据集 |
| **MarketInsightAgent** | 市场洞察分析 | Qwen2.5-72B | 原始数据 | 市场分析报告 |
| **ProductPlanningAgent** | 产品规划建议 | Qwen2.5-72B | 市场分析+评论 | 产品规格方案 |
| **CommercialAnalysisAgent** | 商业化分析 | Qwen2.5-72B | 产品规格+成本 | 利润/ROI分析 |
| **AdsStrategyAgent** | 广告策略建议 ★[V8] | Qwen2.5-72B | 产品+市场+预算 | 广告策略方案 |
| **RiskAssessmentAgent** | 风险评估 | DeepSeek-V3 | 全部分析 | 风险评估报告 |
| **ReviewAnalysisAgent** | 评论情感分析 | Qwen2.5-72B | 评论数据 | 痛点/机会 |
| **ReplenishmentAgent** | 补货建议 | Qwen2.5-72B | 库存+销量 | 补货方案 |
| **PriceOptimizationAgent** | 定价优化 | Qwen2.5-72B | 竞品+成本 | 定价建议 |

### 21.3 Agent编排工作流

```python
class AgentOrchestrator:

    async def run_selection_workflow(self, task_id: str, params: Dict) -> Dict:
        workflow = build_selection_workflow()
        initial_state = SelectionState(
            task_id=task_id, tenant_id=params.get("tenant_id"),
            category=params["category"], target_market=params["target_market"],
            budget_range=params.get("budget_range"), target_roi=params.get("target_roi", 0.3),
            current_step="validate_input", progress=0,
            collected_data={}, market_analysis={}, product_plan={},
            commercial_analysis={}, ads_strategy={}, risk_assessment={},
            recommendations=[], errors=[], erp_queries_log=[]
        )
        final_state = await workflow.ainvoke(initial_state)
        return final_state

async def data_collection_node(state: SelectionState) -> SelectionState:
    agent = DataCollectionAgent()
    collected = await agent.collect(state["category"], state["target_market"])
    state["collected_data"] = collected
    state["current_step"] = "data_collection"
    state["progress"] = 15
    state["erp_queries_log"].append({"step": "data_collection", "queries": collected.get("erp_queries", [])})
    return state

async def ads_strategy_node(state: SelectionState) -> SelectionState:
    agent = AdsStrategyAgent()
    strategy = await agent.analyze(
        category=state["category"], market=state["target_market"],
        product_plan=state["product_plan"], commercial=state["commercial_analysis"],
        budget=state.get("budget_range", {})
    )
    state["ads_strategy"] = strategy
    state["current_step"] = "ads_strategy"
    state["progress"] = 75
    return state
```

------

## 22. 知识域服务详细设计

### 22.1 服务概述

知识域服务管理企业知识库，支持文档上传、向量化、混合检索和知识图谱查询。

### 22.2 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/knowledge/documents` | 上传文档 |
| GET | `/api/v1/knowledge/documents` | 获取文档列表 |
| DELETE | `/api/v1/knowledge/documents/{id}` | 删除文档 |
| POST | `/api/v1/knowledge/search` | 混合检索 |
| POST | `/api/v1/knowledge/graph/query` | 知识图谱查询 |

### 22.3 混合检索实现

```python
class HybridRetriever:

    async def search(self, query: str, top_k: int = 10, filters: Dict = None) -> List[SearchResult]:
        vector_results = await self.qdrant_client.search(collection_name="knowledge", query_vector=await self.embed(query), limit=top_k * 2)
        keyword_results = await self.es_client.search(index="knowledge", body={"query": {"multi_match": {"query": query, "fields": ["title^2", "content"]}}, "size": top_k * 2})
        merged = self._merge_results(vector_results, keyword_results)
        reranked = await self.reranker.rerank(query, merged, top_k=top_k)
        return reranked
```

------

## 23. AI域服务详细设计

### 23.1 服务概述

AI域服务封装LLM推理、Embedding计算和多模态分析能力，为其他服务提供统一的AI能力调用接口。

### 23.2 LLM网关设计

```python
class LLMGateway:

    def __init__(self):
        self.models = {
            "qwen2.5-72b": VLLMClient(base_url="http://vllm-qwen:8000"),
            "deepseek-v3": VLLMClient(base_url="http://vllm-deepseek:8001"),
            "phi-3-mini": OllamaClient(base_url="http://ollama:11434"),
        }
        self.router = ModelRouter()

    async def generate(self, prompt: str, model: str = None, **kwargs) -> str:
        if model is None:
            model = self.router.select(prompt, kwargs)
        client = self.models.get(model)
        if client is None:
            raise ValueError(f"Model {model} not available")
        try:
            return await client.generate(prompt, **kwargs)
        except Exception as e:
            fallback = self.router.get_fallback(model)
            return await self.models[fallback].generate(prompt, **kwargs)

class ModelRouter:

    def select(self, prompt: str, kwargs: Dict) -> str:
        if kwargs.get("max_tokens", 0) > 2000:
            return "qwen2.5-72b"
        if kwargs.get("task_type") == "classification":
            return "phi-3-mini"
        return "qwen2.5-72b"

    def get_fallback(self, model: str) -> str:
        fallbacks = {"qwen2.5-72b": "deepseek-v3", "deepseek-v3": "qwen2.5-72b", "phi-3-mini": "qwen2.5-72b"}
        return fallbacks.get(model, "qwen2.5-72b")
```

------

## 24. 数据域服务详细设计

### 24.1 服务概述

数据域服务负责数据采集、特征工程和数据同步，为AI分析提供高质量的数据支撑。

### 24.2 数据采集管道

```python
class DataCollectionPipeline:

    async def collect_amazon_data(self, category: str, marketplace: str) -> Dict:
        tasks = [
            self._collect_product_list(category, marketplace),
            self._collect_bsr_data(category, marketplace),
            self._collect_review_data(category, marketplace),
            self._collect_keyword_data(category, marketplace),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {"products": results[0], "bsr": results[1], "reviews": results[2], "keywords": results[3]}

    async def _collect_product_list(self, category: str, marketplace: str) -> List[Dict]:
        return await self.scraper.scrape(category=category, marketplace=marketplace, page_limit=20)
```

### 24.3 ERP CDC数据消费

```python
class ERPCDCConsumer:

    async def consume(self, topic: str, message: Dict):
        domain = topic.split(".")[-2]
        handler = self.handlers.get(domain)
        if handler:
            await handler(message)

    async def handle_oms_order(self, message: Dict):
        order = message["after"]
        await self.feature_store.update_feature("sales_volume", order["asin"], {"daily_orders": order["quantity"]})
        await self.cache.set(f"oms:order:{order['asin']}", order, ttl=3600)

    async def handle_wms_inventory(self, message: Dict):
        inventory = message["after"]
        await self.feature_store.update_feature("inventory_level", inventory["sku"], {"quantity": inventory["quantity"]})
        await self.cache.set(f"wms:inventory:{inventory['sku']}", inventory, ttl=1800)

    async def handle_ads_campaign(self, message: Dict):
        campaign = message["after"]
        await self.feature_store.update_feature("ad_performance", campaign["campaign_id"], campaign)
        await self.cache.set(f"ads:campaign:{campaign['campaign_id']}", campaign, ttl=1800)
```

------

## 25. 集成域服务详细设计

### 25.1 服务概述

集成域服务是PMS与ERP 14域的统一交互门面，封装所有ERP客户端调用、CDC消费和事件发布。

### 25.2 BaseERPClient设计

```python
class BaseERPClient:
    def __init__(self, domain: str, base_url: str, api_key: str, timeout: int = 30000):
        self.domain = domain
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = httpx.AsyncClient(timeout=timeout / 1000)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        self.rate_limiter = RateLimiter(requests_per_second=10)
        self.retry_policy = RetryPolicy(max_retries=3, backoff_ms=1000)

    async def _request(self, method: str, path: str, data: Dict = None, params: Dict = None) -> Dict:
        await self.rate_limiter.acquire()
        url = f"{self.base_url}{path}"
        headers = self._build_headers()
        for attempt in range(self.retry_policy.max_retries):
            try:
                if not self.circuit_breaker.is_open():
                    response = await self.session.request(method, url, json=data, params=params, headers=headers)
                    response.raise_for_status()
                    self.circuit_breaker.record_success()
                    return response.json()
                else:
                    await asyncio.sleep(self.circuit_breaker.remaining_timeout())
            except httpx.HTTPStatusError as e:
                self.circuit_breaker.record_failure()
                if attempt == self.retry_policy.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_policy.backoff_ms * (2 ** attempt) / 1000)
        raise RuntimeError(f"Request to {self.domain} failed after {self.retry_policy.max_retries} retries")

    def _build_headers(self) -> Dict:
        timestamp = str(int(time.time()))
        signature = hmac.new(self.api_key.encode(), f"{timestamp}".encode(), hashlib.sha256).hexdigest()
        return {"X-API-Key": self.api_key, "X-Timestamp": timestamp, "X-Signature": signature, "Content-Type": "application/json"}
```

### 25.3 ERPIntegrationService

```python
class ERPIntegrationService:
    def __init__(self, db: AsyncSession, sys_client: SYSClient):
        self.db = db
        self.sys_client = sys_client
        self._clients: Dict[str, BaseERPClient] = {}

    async def get_client(self, domain: str) -> BaseERPClient:
        if domain not in self._clients:
            params = await self.sys_client.get_integration_params(domain)
            client_class = self._client_registry.get(domain, BaseERPClient)
            self._clients[domain] = client_class(
                domain=domain, base_url=params["base_url"],
                api_key=params["api_key"], timeout=params.get("timeout_ms", 30000)
            )
        return self._clients[domain]

    _client_registry = {
        "DASHBOARD": DashboardClient, "IAM": IAMClient, "PDM": PDMClient,
        "SOM": SOMClient, "ADS": ADSClient, "OMS": OMSClient,
        "SCM": SCMClient, "WMS": WMSClient, "FBA": FBAClient,
        "TMS": TMSClient, "CRM": CRMClient, "FMS": FMSClient,
        "BI": BIClient, "SYS": SYSClient,
    }

    async def execute_adoption(self, execution_id: UUID) -> Dict:
        execution = await self._get_execution(execution_id)
        recommendation = await self._get_recommendation(execution.recommendation_id)
        execution.status = "executing"
        execution.started_at = datetime.utcnow()
        await self.db.commit()
        completed_steps = []
        try:
            for i, step in enumerate(execution.erp_steps):
                client = await self.get_client(step["domain"])
                method = getattr(client, step["action"])
                result = await method(**step["data"])
                completed_steps.append({"step": i, "domain": step["domain"], "result": result})
                execution.current_step = i + 1
                await self.db.commit()
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            await self.db.commit()
            await self._push_to_dashboard(recommendation, execution)
            return {"execution_id": str(execution.id), "status": "completed", "steps": completed_steps}
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            await self.db.commit()
            await self._compensate(completed_steps)
            raise

    async def _push_to_dashboard(self, recommendation, execution):
        dashboard = await self.get_client("DASHBOARD")
        await dashboard.push_ai_insight({
            "insight_type": "adoption_completed",
            "title": f"选品采纳完成: {recommendation.product_title}",
            "summary": f"已成功执行{len(execution.erp_steps)}个ERP步骤",
            "priority": "high",
            "detail": {"recommendation_id": str(recommendation.id), "execution_id": str(execution.id)}
        })

    async def _compensate(self, completed_steps: List[Dict]):
        for step in reversed(completed_steps):
            try:
                client = await self.get_client(step["domain"])
                if hasattr(client, "rollback"):
                    await client.rollback(step["result"])
            except Exception:
                pass
```

------

## 26. 报告域服务详细设计

### 26.1 服务概述

报告域服务负责生成选品报告、市场分析报告和商业化报告，支持PDF、Excel和PPT格式导出。

### 26.2 核心接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| POST | `/api/v1/reports/generate` | 生成报告 |
| GET | `/api/v1/reports/{id}` | 获取报告详情 |
| GET | `/api/v1/reports/{id}/download` | 下载报告文件 |
| GET | `/api/v1/reports` | 获取报告列表 |

### 26.3 报告模板

| 模板 | 说明 | 包含章节 |
| :--- | :--- | :--- |
| `selection_report` | 选品分析报告 | 市场洞察、产品规划、商业化分析、风险评估、广告策略★[V8] |
| `market_report` | 市场分析报告 | 市场规模、趋势、竞品格局 |
| `commercial_report` | 商业化分析报告 | 成本、利润、ROI、定价 |
| `ads_report` | 广告优化报告 ★[V8] | ACOS分析、关键词优化、预算分配 |

------

## 27. WebSocket接口详细设计

### 27.1 服务概述

WebSocket服务提供实时推送能力，用于Agent执行进度、选品任务状态变更和AI洞察推送。

### 27.2 事件类型

| 事件 | 说明 | 数据格式 |
| :--- | :--- | :--- |
| `task.progress` | 任务进度更新 | `{task_id, progress, current_step}` |
| `task.completed` | 任务完成 | `{task_id, recommendations_count}` |
| `task.failed` | 任务失败 | `{task_id, error}` |
| `recommendation.generated` | 推荐生成 | `{recommendation_id, score, title}` |
| `adoption.step_completed` | 采纳步骤完成 | `{execution_id, step, domain}` |
| `adoption.completed` | 采纳完成 | `{execution_id, results}` |
| `insight.pushed` | AI洞察推送 | `{insight_type, title, summary}` |
| `suggestion.generated` | 智能建议生成 | `{suggestion_id, type, priority}` |

### 27.3 WebSocket实现

```python
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.connections:
            self.connections[user_id].remove(websocket)

    async def broadcast_to_user(self, user_id: str, event: str, data: Dict):
        if user_id in self.connections:
            message = json.dumps({"event": event, "data": data, "timestamp": datetime.utcnow().isoformat()})
            for ws in self.connections[user_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    await self.disconnect(user_id, ws)
```

------

# 第五卷：PMS与ERP 14域交互设计

## 28. PMS-ERP集成架构

### 28.1 集成原则

| 原则 | 说明 |
| :--- | :--- |
| **松耦合** | PMS与ERP通过REST API和Kafka事件交互，不直接共享数据库 |
| **最终一致性** | 采纳执行采用Saga模式，保证最终一致性 |
| **幂等性** | 所有ERP调用支持幂等，避免重复执行 |
| **可观测性** | 每次ERP调用记录日志，含延迟、状态和错误信息 |
| **容错性** | 熔断+重试+降级，保障PMS核心功能不受ERP故障影响 |

### 28.2 集成拓扑

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              PMS-ERP 14域集成拓扑                                                    │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  PMS Services                                                                                 │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │  │
│  │  │  Selection   │  │    Agent     │  │     Ads      │  │   Report     │                       │  │
│  │  │  Service     │  │   Service    │  │   Service    │  │   Service    │                       │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                       │  │
│  └─────────┼─────────────────┼─────────────────┼─────────────────┼──────────────────────────────┘  │
│            │                 │                 │                 │                                   │
│  ┌─────────▼─────────────────▼─────────────────▼─────────────────▼──────────────────────────────┐  │
│  │  ERPIntegrationService (统一门面)                                                               │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────────────────┐   │  │
│  │  │  14 Domain Clients                                                                     │   │  │
│  │  │  DASHBOARD │ IAM │ PDM │ SOM │ ADS │ OMS │ SCM │ WMS │ FBA │ TMS │ CRM │ FMS │ BI │ SYS│   │  │
│  │  └────────────────────────────────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│            │                              │                              │                           │
│     ┌──────▼──────┐              ┌───────▼──────┐              ┌───────▼──────┐                    │
│     │  REST API   │              │    Kafka     │              │  WebSocket   │                    │
│     │  同步调用    │              │  异步事件     │              │  实时推送     │                    │
│     └─────────────┘              └──────────────┘              └──────────────┘                    │
│            │                              │                              │                           │
│  ┌─────────▼──────────────────────────────▼──────────────────────────────▼──────────────────────┐  │
│  │  ERP System (14 Domains)                                                                      │  │
│  │  ┌──────────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                              │  │
│  │  │DASHBOARD │ │ IAM │ │ PDM │ │ SOM │ │ ADS │ │ OMS │ │ SCM │                              │  │
│  │  └──────────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                              │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                                  │  │
│  │  │ WMS │ │ FBA │ │ TMS │ │ CRM │ │ FMS │ │ BI  │ │ SYS │                                  │  │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                                  │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

------

## 29. PMS数据输入设计（AI感知）

### 29.1 数据输入全景

PMS从ERP 14域获取数据，作为AI分析的基础输入。

| 数据源域 | 数据类型 | 同步方式 | 频率 | 用途 |
| :--- | :--- | :--- | :--- | :--- |
| DASHBOARD | KPI指标、看板配置 | REST API | 按需 | 看板数据展示 |
| IAM | 用户权限、租户配置 | REST API | 按需 | 权限校验、租户隔离 |
| PDM | 产品规格、竞品分析 | REST API | 按需 | 选品分析、产品规划 |
| SOM | Listing数据、BSR排名 | REST API | 按需 | 定价分析、销售预测 |
| ADS | 广告活动、关键词表现 | REST API | 按需 | 广告优化、ACOS分析 |
| OMS | 订单数据、销售趋势 | CDC | 实时 | 销量分析、风控 |
| SCM | 供应商数据、采购成本 | CDC | 实时 | 成本分析、风险评估 |
| WMS | 库存数据、库龄数据 | CDC | 实时 | 补货建议、库存预测 |
| FBA | FBA库存、费用估算 | REST API | 按需 | FBA成本分析、补货 |
| TMS | 运费数据、物流风险 | REST API | 按需 | 物流成本计算 |
| CRM | 评价数据、投诉数据 | CDC | 实时 | 情感分析、痛点挖掘 |
| FMS | 成本分解、利润分析 | REST API | 按需 | 商业化分析 |
| BI | KPI指标、市场趋势 | REST API | 按需 | 趋势分析、异常检测 |
| SYS | 系统配置、集成参数 | REST API | 按需 | 集成参数获取 |

### 29.2 CDC数据消费Topic

| Topic | 源域 | 消费逻辑 |
| :--- | :--- | :--- |
| `cdc.oms.orders` | OMS | 更新销量特征、触发风控检查 |
| `cdc.scm.purchase_orders` | SCM | 更新采购成本特征、供应商评分 |
| `cdc.wms.inventory` | WMS | 更新库存特征、触发补货建议 |
| `cdc.crm.reviews` | CRM | 更新评价特征、触发情感分析 |
| `cdc.ads.campaigns` | ADS ★[V8] | 更新广告表现特征、触发ACOS优化 |

------

## 30. PMS数据输出设计（AI驱动）

### 30.1 数据输出全景

PMS将AI决策结果下发ERP 14域执行。

| 目标域 | 输出类型 | 触发场景 | 接口 |
| :--- | :--- | :--- | :--- |
| PDM | 选品提报 | 采纳推荐 | `create_selection_proposal` |
| SCM | 采购订单 | 采纳推荐 | `create_purchase_order` |
| SCM | 补货计划 | 补货建议 | `create_replenishment_plan` |
| WMS | 库容预留 | 采纳推荐 | `reserve_capacity` |
| SOM | Listing草稿 | 采纳推荐 | `create_listing_draft` |
| SOM | 价格调整 | 定价建议 | `adjust_listing_price` |
| ADS | 广告策略 | 广告优化 | `adjust_ad_strategy` ★[V8] |
| ADS | 关键词竞价 | 关键词优化 | `adjust_keyword_bid` ★[V8] |
| ADS | 预算调整 | 预算优化 | `adjust_campaign_budget` ★[V8] |
| FBA | 入库货件 | 补货建议 | `create_inbound_shipment` ★[V8] |
| OMS | 风控标记 | 风险预警 | `mark_risk_order` |
| DASHBOARD | AI洞察卡片 | 洞察生成 | `push_ai_insight` ★[V8] |
| DASHBOARD | KPI更新 | 指标变更 | `update_kpi_widget` ★[V8] |
| SYS | 集成配置 | 配置变更 | `update_integration_params` ★[V8] |

### 30.2 采纳执行Saga流程

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              采纳执行Saga流程 (V8: 14域)                                              │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐           │
│  │  Step1  │───▶│  Step2  │───▶│  Step3  │───▶│  Step4  │───▶│  Step5  │───▶│  Step6  │           │
│  │  PDM    │    │  SCM    │    │  WMS    │    │  SOM    │    │  ADS    │    │  FBA    │           │
│  │选品提报  │    │采购订单  │    │库容预留  │    │Listing  │    │广告策略  │    │入库货件  │           │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘           │
│       │              │              │              │              │              │                   │
│       ▼              ▼              ▼              ▼              ▼              ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  Compensating Transactions (逆向补偿)                                                         │  │
│  │  PDM:取消提报 ◀── SCM:取消采购 ◀── WMS:释放库容 ◀── SOM:删除草稿 ◀── ADS:恢复策略 ◀── FBA:取消货件│  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
│  ┌─────────┐                                                                                        │
│  │  Step7  │ (可选)                                                                                  │
│  │DASHBOARD│                                                                                        │
│  │推送洞察  │                                                                                        │
│  └─────────┘                                                                                        │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

------

## 31. 闭环反馈设计

### 31.1 反馈闭环全景

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              闭环反馈全景 (V8: 14域)                                                  │
├────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  1. AI决策阶段                                                                                │  │
│  │     PMS Agent → 生成建议(选品/补货/定价/广告/风险)                                              │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                              │                                                     │
│                                              ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  2. ERP执行阶段                                                                               │  │
│  │     PMS → ERP 14域 → 执行业务操作(PDM提报/SCM采购/WMS入库/ADS广告/FBA入库...)                    │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                              │                                                     │
│                                              ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  3. 效果反馈阶段                                                                              │  │
│  │     ERP → PMS → 记录执行结果 + 业务指标                                                         │  │
│  │     OMS: 实际销量 vs 预测销量                                                                   │  │
│  │     ADS: 实际ACOS vs 预测ACOS ★[V8]                                                           │  │
│  │     WMS: 实际库存 vs 预测需求                                                                   │  │
│  │     FBA: 实际FBA库存 vs 补货计划 ★[V8]                                                         │  │
│  │     FMS: 实际利润 vs 预测利润                                                                   │  │
│  │     BI: 实际KPI vs 目标KPI                                                                     │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                              │                                                     │
│                                              ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  4. 模型优化阶段                                                                              │  │
│  │     PMS → 分析偏差 → 调整Agent参数 → 优化Prompt → 更新特征库                                    │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 31.2 反馈数据模型

```python
class SuggestionFeedback(Base):
    __tablename__ = "suggestion_feedback"

    id = Column(UUID, primary_key=True, default=uuid4)
    suggestion_id = Column(UUID, ForeignKey("suggestions.id"), nullable=False)
    tenant_id = Column(String(36), nullable=False)
    execution_status = Column(String(20))
    actual_roi = Column(Float)
    actual_sales = Column(Float)
    actual_acos = Column(Float)
    predicted_roi = Column(Float)
    predicted_sales = Column(Float)
    predicted_acos = Column(Float)
    deviation = Column(Float)
    feedback_source = Column(String(20))
    feedback_at = Column(DateTime, default=datetime.utcnow)
```

------

## 32. ERP 14域集成客户端详细设计

### 32.1 客户端注册表

| 域 | 客户端类 | 核心方法数 | AI增强 |
| :--- | :--- | :--- | :--- |
| DASHBOARD | DashboardClient | 4 | ★AI看板 |
| IAM | IAMClient | 4 | - |
| PDM | PDMClient | 5 | ★AI选品 |
| SOM | SOMClient | 5 | - |
| ADS | ADSClient | 6 | ★AI优化 |
| OMS | OMSClient | 5 | ★AI风控 |
| SCM | SCMClient | 5 | ★AI补货 |
| WMS | WMSClient | 4 | ★AI预测 |
| FBA | FBAClient | 4 | - |
| TMS | TMSClient | 4 | - |
| CRM | CRMClient | 3 | ★AI情感 |
| FMS | FMSClient | 3 | - |
| BI | BIClient | 4 | ★KPI |
| SYS | SYSClient | 4 | - |

### 32.2 客户端工厂

```python
class ERPClientFactory:

    _registry = {
        "DASHBOARD": DashboardClient, "IAM": IAMClient, "PDM": PDMClient,
        "SOM": SOMClient, "ADS": ADSClient, "OMS": OMSClient,
        "SCM": SCMClient, "WMS": WMSClient, "FBA": FBAClient,
        "TMS": TMSClient, "CRM": CRMClient, "FMS": FMSClient,
        "BI": BIClient, "SYS": SYSClient,
    }

    @classmethod
    async def create(cls, domain: str, sys_client: SYSClient) -> BaseERPClient:
        params = await sys_client.get_integration_params(domain)
        client_class = cls._registry.get(domain, BaseERPClient)
        return client_class(
            domain=domain, base_url=params["base_url"],
            api_key=params["api_key"], timeout=params.get("timeout_ms", 30000)
        )

    @classmethod
    async def create_all(cls, sys_client: SYSClient) -> Dict[str, BaseERPClient]:
        clients = {}
        for domain in cls._registry:
            try:
                clients[domain] = await cls.create(domain, sys_client)
            except Exception as e:
                logging.warning(f"Failed to create client for {domain}: {e}")
        return clients
```

------

## 33. 集成事件与异步通信

### 33.1 Kafka Topic设计

| Topic | 生产者 | 消费者 | 说明 |
| :--- | :--- | :--- | :--- |
| `cdc.oms.orders` | ERP OMS | PMS erp-sync | 订单变更 |
| `cdc.scm.purchase_orders` | ERP SCM | PMS erp-sync | 采购订单变更 |
| `cdc.wms.inventory` | ERP WMS | PMS erp-sync | 库存变更 |
| `cdc.crm.reviews` | ERP CRM | PMS erp-sync | 评价变更 |
| `cdc.ads.campaigns` | ERP ADS | PMS erp-sync | 广告活动变更 ★[V8] |
| `pms.adoption.steps` | PMS integration | ERP各域 | 采纳执行步骤 |
| `pms.suggestions.generated` | PMS agent | PMS integration | 建议生成事件 |
| `pms.feedback.collected` | PMS integration | PMS agent | 反馈收集事件 |
| `pms.insights.pushed` | PMS integration | ERP DASHBOARD | AI洞察推送 ★[V8] |

### 33.2 事件格式

```json
{
  "event_id": "uuid",
  "event_type": "cdc.oms.orders",
  "source_domain": "OMS",
  "tenant_id": "tenant-uuid",
  "timestamp": "2026-04-26T10:00:00Z",
  "before": null,
  "after": {
    "order_id": "ORD-2026-001",
    "asin": "B08N5WRWNW",
    "quantity": 10,
    "total_amount": 299.90,
    "order_status": "shipped"
  },
  "metadata": {
    "cdc_lsn": 12345,
    "table": "oms_orders"
  }
}
```

------

## 34. 集成异常处理与容错

### 34.1 异常分类

| 异常类型 | 处理策略 | 示例 |
| :--- | :--- | :--- |
| **网络超时** | 重试3次，指数退避 | ERP服务不可达 |
| **业务异常** | 记录日志，通知用户 | 采购单审批被拒 |
| **数据异常** | 降级处理，使用缓存数据 | 库存数据为空 |
| **熔断触发** | 快速失败，返回降级结果 | 连续5次调用失败 |
| **限流触发** | 排队等待，延迟重试 | ERP接口限流 |

### 34.2 熔断器设计

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"

    def is_open(self) -> bool:
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return False
            return True
        return False

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
```

### 34.3 降级策略

| 场景 | 降级策略 |
| :--- | :--- |
| ERP PDM不可用 | 使用本地缓存的产品数据 |
| ERP ADS不可用 | 暂停广告优化建议，使用历史策略 |
| ERP OMS不可用 | 使用缓存的销售数据 |
| ERP WMS不可用 | 使用缓存的库存数据 |
| ERP FBA不可用 | 使用缓存的FBA费用估算 |
| ERP DASHBOARD不可用 | 暂停洞察推送，本地缓存 |

------

# 第六卷：前端与运维

## 35. 前端架构设计

### 35.1 技术栈

| 技术 | 版本 | 用途 |
| :--- | :--- | :--- |
| Next.js | 14 | 前端框架 |
| React | 18 | UI库 |
| TypeScript | 5 | 类型安全 |
| Tailwind CSS | 3 | 样式框架 |
| Ant Design | 5 | UI组件库 |
| ECharts | 5 | 图表库 |
| Socket.IO | 4 | WebSocket客户端 |

### 35.2 页面列表

| 页面 | 路由 | 说明 | 对应ERP域 |
| :--- | :--- | :--- | :--- |
| AI看板 | `/dashboard` | AI洞察+KPI+待办 | DASHBOARD |
| 选品任务 | `/selection/tasks` | 任务列表+创建 | PDM |
| 选品详情 | `/selection/tasks/[id]` | 任务进度+推荐 | PDM |
| 市场洞察 | `/market-insight` | 市场分析 | BI |
| 产品规划 | `/product-planning` | 产品规格 | PDM |
| 商业化分析 | `/commercial-analysis` | 成本利润 | FMS |
| 广告优化 | `/ads-optimization` | 广告策略 ★[V8] | ADS |
| 风险评估 | `/risk-assessment` | 风险预警 | OMS/SCM |
| 智能建议 | `/suggestions` | 建议列表 | 全域 |
| 知识库 | `/knowledge` | 文档管理 | - |
| FBA库存 | `/fba-inventory` | FBA库存面板 ★[V8] | FBA |
| 系统设置 | `/settings` | 集成配置 ★[V8] | SYS |

------

## 36. 部署架构设计

### 36.1 环境规划

| 环境 | 用途 | 规模 |
| :--- | :--- | :--- |
| DEV | 开发测试 | 1节点K8s |
| STAGING | 预发布验证 | 3节点K8s |
| PROD | 生产环境 | 多AZ K8s集群 |

### 36.2 资源规划

| 服务 | CPU | 内存 | GPU | 副本数 |
| :--- | :--- | :--- | :--- | :--- |
| selection-service | 2核 | 4GB | - | 4 |
| agent-service | 4核 | 8GB | - | 4 |
| integration-service | 2核 | 4GB | - | 3 |
| ads-service | 2核 | 4GB | - | 2 |
| llm-service | 4核 | 16GB | 4×A100 | 1 |
| PostgreSQL | 4核 | 16GB | - | 3(Patroni) |
| Qdrant | 4核 | 16GB | - | 3 |
| Kafka | 4核 | 8GB | - | 3 |

------

## 37. 监控与运维设计

### 37.1 监控体系

| 层级 | 工具 | 监控内容 |
| :--- | :--- | :--- |
| 基础设施 | Prometheus + Grafana | CPU/内存/磁盘/网络 |
| 应用 | OpenTelemetry + Jaeger | 请求延迟/错误率/吞吐量 |
| AI模型 | MLflow | 模型精度/推理延迟/Token消耗 |
| ERP集成 | 自定义Dashboard | 各域调用延迟/成功率/熔断状态 |
| 业务 | Grafana | 选品任务数/采纳率/建议准确率 |

### 37.2 告警规则

| 告警 | 条件 | 级别 | 通知方式 |
| :--- | :--- | :--- | :--- |
| ERP调用超时 | P99 > 5s 持续5分钟 | WARNING | 飞书/邮件 |
| ERP调用失败率 | > 10% 持续3分钟 | CRITICAL | 飞书/电话 |
| 熔断触发 | 任意域熔断 | CRITICAL | 飞书/电话 |
| LLM推理超时 | P99 > 10s 持续5分钟 | WARNING | 飞书 |
| 选品任务积压 | 待处理 > 50 | WARNING | 飞书 |
| 磁盘使用率 | > 85% | WARNING | 飞书/邮件 |

------

## 38. 安全与权限设计

### 38.1 认证与授权

| 层级 | 机制 | 说明 |
| :--- | :--- | :--- |
| 用户认证 | JWT + OAuth2 | 通过IAM域统一认证 |
| 服务间认证 | API Key + HMAC签名 | PMS与ERP服务间调用 |
| 数据隔离 | 租户ID字段隔离 | 所有表含tenant_id |
| 接口权限 | RBAC | 基于角色的访问控制 |

### 38.2 数据安全

| 措施 | 说明 |
| :--- | :--- |
| 传输加密 | TLS 1.3 |
| 存储加密 | AES-256 (敏感字段) |
| API Key加密 | AES-256-GCM (SYS域存储) |
| 日志脱敏 | 敏感字段自动掩码 |
| 审计日志 | 所有ERP调用记录审计日志 |

### 38.3 ERP集成安全

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
            "X-Signature": signature
        }

    def verify_request(self, headers: Dict, method: str, path: str, body: str = "") -> bool:
        api_key = self._get_full_api_key(headers["X-API-Key"])
        expected = self.sign_request(api_key, method, path, body)
        return hmac.compare_digest(headers.get("X-Signature"), expected["X-Signature"])
```

------

# 附录

## 附录A：V7→V8变更记录

| 章节 | 变更类型 | 变更内容 |
| :--- | :--- | :--- |
| 1.4 | 新增 | V8版本变更说明表 |
| 2.3 | 修改 | 核心功能增加广告优化、看板展示、FBA库存 |
| 3.4 | 新增 | ERP 14域集成架构 |
| 4.2 | 新增 | ads_optimization_log, fba_inventory_sync, dashboard_widget_config, iam_role_mapping, sys_integration_config |
| 4.3 | 修改 | 数据流全景扩展到14域 |
| 6 | 新增 | 工作台域 (DASHBOARD) ★[AI看板] 完整设计 |
| 7 | 新增 | 组织权限域 (IAM) 完整设计 |
| 10 | 新增 | 广告管理域 (ADS) ★[AI优化] 完整设计 |
| 14 | 新增 | FBA/海外仓域 (FBA) 完整设计 |
| 19 | 新增 | 系统设置域 (SYS) 完整设计 |
| 21 | 修改 | Agent列表增加AdsStrategyAgent |
| 25 | 修改 | 集成服务扩展到14域客户端 |
| 28-34 | 新增 | PMS-ERP 14域交互设计完整章节 |
| 35 | 修改 | 前端页面增加广告优化、FBA库存、系统设置 |
| 附录A | 新增 | V7→V8变更记录 |
| 附录C | 新增 | ERP 14域接口对照表 |

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

## 附录C：ERP 14域接口对照表
- 附录D：V10交叉验证优化补充设计
- 附录E：PMS-ERP权限、接口、事件、数据主权矩阵

| 域 | PMS→ERP接口 | ERP→PMS接口 | CDC Topic |
| :--- | :--- | :--- | :--- |
| DASHBOARD | push_ai_insight, update_kpi_widget | query_selection_summary, query_suggestion_stats | - |
| IAM | register_service_account | verify_token, get_user_permissions, get_tenant_config | - |
| PDM | create_selection_proposal, update_product_data | query_product_specs, query_competitor_analysis, query_product_lifecycle | - |
| SOM | create_listing_draft, adjust_listing_price | query_listing_performance, query_category_bsr, query_pricing_benchmark | - |
| ADS | adjust_ad_strategy, adjust_keyword_bid, adjust_campaign_budget | query_campaign_performance, query_acos_analysis, query_keyword_performance | cdc.ads.campaigns |
| OMS | create_listing_draft, adjust_listing_price | query_sales_trend, query_order_statistics, query_compliance_risks | cdc.oms.orders |
| SCM | create_purchase_order, create_replenishment_plan | query_supplier_performance, query_supplier_risk, query_purchase_cost | cdc.scm.purchase_orders |
| WMS | reserve_capacity | query_inventory_status, query_inventory_risk, query_warehouse_capacity | cdc.wms.inventory |
| FBA | create_inbound_shipment | query_fba_inventory, query_fee_estimate, query_restock_recommendations | - |
| TMS | create_shipment_plan | query_shipping_cost, query_logistics_risk, query_delivery_performance | - |
| CRM | - | query_review_analysis, query_complaint_analysis, query_customer_insights | cdc.crm.reviews |
| FMS | - | query_cost_breakdown, query_profit_analysis, query_budget_status | - |
| BI | - | query_market_trend, query_category_bsr, query_product_performance, query_kpi_dashboard | - |
| SYS | update_integration_params | get_integration_params, get_system_config, health_check | - |

------

> **文档结束** — 跨境电商AI选品系统PMS详细设计说明书 V8.0
> 
> 本文档基于V7.0版本，扩展ERP集成从9域到14域，新增DASHBOARD/IAM/ADS/FBA/SYS五个域的完整设计，强化了PMS与ERP 14域的交互规范、闭环反馈和集成容错机制。
---

# 附录D：V10交叉验证优化补充设计

## D.1 PMS与ERP系统边界

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

## D.2 PMS不得直接写入ERP正式终态数据

PMS允许写入ERP的数据类型限定如下：

| 写入类型 | 是否允许 | 示例 | ERP承接域 |
|---|---|---|---|
| AI建议 | 允许 | 选品建议、广告优化建议、补货建议 | PDM/ADS/SCM/WMS/BI |
| 草稿单据 | 允许 | Listing草稿、采购计划草稿、补货计划草稿 | SOM/SCM/WMS/FBA |
| 待审批动作 | 允许 | 建议采纳申请、自动执行申请 | PDM/SOM/ADS/SCM |
| 正式业务单据 | 禁止直接写入 | 正式采购单、正式Listing、正式广告活动 | 由ERP审批后生成 |
| 财务终态数据 | 禁止写入 | 成本凭证、利润结果、付款状态 | FMS主控 |
| 库存终态数据 | 禁止写入 | 实际库存、出入库结果 | WMS/FBA主控 |

## D.3 PMS-ERP 14域交互矩阵

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

## D.4 PMS数据源可信等级

| 数据源 | 可信等级 | 使用规则 |
|---|---|---|
| ERP订单、库存、财务、采购、广告真实数据 | A | 作为经营判断主依据 |
| 官方平台API数据 | A/B | 需记录采集时间和平台限制 |
| 第三方数据服务 | B | 需记录供应商、更新时间和覆盖范围 |
| 爬虫数据 | C | 需去重、校验、限频、标注来源 |
| 社媒趋势数据 | C | 仅作为趋势信号，不单独作为执行依据 |
| LLM推断结果 | D | 必须附解释、证据和人工复核要求 |

## D.5 PMS AI建议标准输出结构

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

## D.6 建议执行状态机

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

## D.7 PMS权限与审计上下文

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

## D.8 PMS集成方式选择规则

| 数据类型 | 推荐方式 | 示例 |
|---|---|---|
| 实时查询 | ERP API | 可售库存、当前价格、当前广告预算 |
| 高频变化 | CDC/领域事件 | 库存变动、订单状态、广告消耗 |
| 汇总分析 | BI/数仓 | KPI、利润趋势、周转率、类目表现 |
| 外部趋势 | PMS采集任务 | Google Trends、社媒、竞品爬虫 |
| 模型特征 | 特征库 | 销售预测特征、补货特征、广告特征 |

## D.9 关键领域边界修正

1. PDM承接产品立项和产品开发；PMS负责选品机会识别和AI评分。
2. SOM负责Listing、渠道SKU和价格；PMS只能生成Listing草稿或优化建议。
3. ADS负责广告活动、关键词、预算和效果；PMS广告优化建议必须进入ADS。
4. OMS负责订单、履约、退款和风控结果；PMS不负责创建Listing。
5. SCM负责供应商、采购、报价和交期；PMS生成采购建议，不生成正式采购单。
6. WMS/FBA负责库存真实状态；PMS生成预测和补货建议，不修改实际库存。
7. FMS负责成本、费用、利润和对账真实结果；PMS只读取或生成风险提示。
8. BI负责经营指标和建议效果评估；PMS读取BI指标用于模型优化。
