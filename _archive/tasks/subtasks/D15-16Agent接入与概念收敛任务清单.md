# D15-16 Agent接入与概念收敛任务清单

> 来源文档: [问题与建议.md](../../问题与建议.md)
> 总清单: [子任务清单.md](../../子任务清单.md)
> 时间范围: D15-D16
> 目标: 让各 Agent 通过 provider 运行，并收敛重复概念与多套实现

## D15 Agent 接入 provider

- 为 `DataCollectionAgent`、`MarketInsightAgent`、`ProductPlannerAgent`、`CommercialAgent` 接入 provider。
- 保留 fallback，但限定为 real provider 异常时触发。
- 输出统一的日志与错误处理策略，方便追踪真实/模拟路径切换。
- 减少核心业务逻辑中的随机结论生成。

## D16 重复概念收敛

- 统一 `AgentType` 的定义来源。
- 统一 `HybridRetriever` 的实现来源。
- 清理重复或平行模块，明确哪些属于 `domain`，哪些属于 `infrastructure`。
- 补充迁移说明，避免后续再引入双份实现。

## 产出物

- provider 化的 Agent 链路
- 收敛后的枚举与检索实现
- 重复模块清理清单

## 本段验收

- [ ] Agent 核心逻辑不再直接依赖大量随机结果。
- [ ] 关键概念只保留一套主实现。
- [ ] 代码导航与后续扩展成本明显降低。
