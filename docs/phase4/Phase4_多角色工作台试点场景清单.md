# Phase4 多角色工作台试点场景清单

## 1. 文档目标

本清单用于收口 `N1-05 多角色工作台联动作业与本地回归集收口`，目标不是继续堆叠新页面，而是把当前已经具备的工作台能力组织成一条本地可演示、可回归、可复盘的业务链路。

## 2. 试点场景定义

### 2.1 场景名称

- 场景编号：`phase4-local-multi-role-bluetooth-headset`
- 场景名称：蓝牙耳机美国站多角色工作台联动作业

### 2.2 业务目标

- 用 1 条本地试点任务串起 `selection -> manager -> procurement -> finance -> operations` 五个角色视角。
- 验证的不只是接口可用，而是每个角色是否拿到了自己需要的业务信号。
- 以本地可回归工件为主，不引入新的外部运行时和不可控代码。

## 3. 角色职责与验收关注点

| 角色 | 核心动作 | 关键业务信号 |
| --- | --- | --- |
| `selection` | 创建试点任务、查看推荐结果 | 是否有推荐结论、ROI、推荐商品、风险摘要 |
| `manager` | 查看审批队列、完成终审 | 是否能看到待审批任务、终审后闭环状态是否回写 |
| `procurement` | 执行采纳、跟踪 SCM/WMS/OMS | 是否有采购单、库位预留、上架草稿与执行日志 |
| `finance` | 查看利润与 KPI | 是否有毛利润、每日 KPI、经营总览 |
| `operations` | 查看治理与审计 | 是否有配置/租户/安全/LLM/审计/实时通道状态 |

## 4. 标准试点流程

1. 运营创建“蓝牙耳机美国站试点”任务，系统生成推荐结论。
2. 运营初审通过，采购复审通过。
3. 管理者在 `manager overview` 中看到待处理终审队列。
4. 管理者终审通过，任务进入采纳执行。
5. 采购角色执行采纳，形成 `SCM / WMS / OMS` 执行状态。
6. 财务角色同步执行反馈，形成利润、评分与 KPI 快照。
7. 运维角色核验治理状态、审计日志与实时通道状态。

## 5. 回归工件要求

- 工件目录：`artifacts/local_multi_role_workbench/<run_id>/`
- 必备文件：
  - `selection_workbench.json`
  - `manager_overview.json`
  - `procurement_workbench.json`
  - `finance_workbench.json`
  - `operations_workbench.json`
  - `scenario_manifest.json`
  - `operation_records.json`
  - `audit_logs.json`
  - `summary.json`

## 6. 回归命令

```bash
rtk python scripts/run_local_multi_role_workbench_acceptance.py
rtk pytest tests/test_local_multi_role_workbench.py -q
```

## 7. 收口标准

- `summary.json.accepted=true`
- 管理者视图能同时证明“待审批存在过”和“闭环已完成”
- 采购视图能证明采纳执行状态已形成
- 财务视图能证明利润与 KPI 已形成
- 运维视图能证明治理与审计查询已形成
