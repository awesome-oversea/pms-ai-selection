'use client'

type OperationsData = {
  running_total: number
  dead_letter_total: number
  retryable_total: number
  manual_intervention_total: number
  failed_reasons: Record<string, number>
  status_reason_samples: Array<{ task_id: string; status: string; status_reason: string }>
  retry_history: Array<{ task_id: string; retry_count: number; dead_letter: boolean }>
  recent_interventions: Array<{ task_id: string; action: string; comment?: string; operator?: string }>
  lifecycle_summary?: Record<string, number>
  lifecycle_actions?: string[]
  agent_instance_lifecycle?: {
    total?: number
    by_status?: Record<string, number>
    auto_restart_ready?: boolean
    queue_dispatch_ready?: boolean
  }
  workflow_cost_summary?: {
    totals?: { tokens_used?: number; cost_usd?: number }
  }
}

export default function OperationsPanel({ data }: { data: OperationsData }) {
  return (
    <div className="card">
      <h2>运行诊断</h2>
      <div className="grid grid-2">
        <div><strong>运行中：</strong>{data.running_total}</div>
        <div><strong>死信：</strong>{data.dead_letter_total}</div>
        <div><strong>可重试：</strong>{data.retryable_total}</div>
        <div><strong>人工介入：</strong>{data.manual_intervention_total}</div>
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div>
          <strong>Token/成本实时统计</strong>
          <div className="metric-card" style={{ marginTop: 8 }}>
            <div className="metric-label">工作流累计</div>
            <div className="metric-value">{data.workflow_cost_summary?.totals?.tokens_used ?? 0} / ${data.workflow_cost_summary?.totals?.cost_usd ?? 0}</div>
            <div className="metric-hint">实时 Token/成本统计</div>
          </div>
        </div>
        <div>
          <strong>Agent生命周期管理</strong>
          <ul>
            {Object.entries(data.agent_instance_lifecycle?.by_status ?? {}).map(([status, count]) => (
              <li key={status}>{status}: {count}</li>
            ))}
          </ul>
          <div className="muted">自动重启：{data.agent_instance_lifecycle?.auto_restart_ready ? 'ready' : 'not-ready'} / 队列调度：{data.agent_instance_lifecycle?.queue_dispatch_ready ? 'ready' : 'not-ready'}</div>
        </div>
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div>
          <strong>失败原因</strong>
          <ul>
            {Object.entries(data.failed_reasons).map(([reason, count]) => (
              <li key={reason}>{reason}: {count}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>生命周期</strong>
          <ul>
            {Object.entries(data.lifecycle_summary ?? {}).map(([status, count]) => (
              <li key={status}>{status}: {count}</li>
            ))}
          </ul>
          <div className="muted">支持动作：{(data.lifecycle_actions ?? []).join(', ') || '-'}</div>
        </div>
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div>
          <strong>状态原因样例</strong>
          <ul>
            {data.status_reason_samples.map((item) => (
              <li key={item.task_id}>{item.task_id} / {item.status} / {item.status_reason}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>最近人工介入</strong>
          <ul>
            {data.recent_interventions.map((item, idx) => (
              <li key={`${item.task_id}-${idx}`}>{item.task_id} / {item.action} / {item.operator ?? '-'} / {item.comment ?? '-'}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
