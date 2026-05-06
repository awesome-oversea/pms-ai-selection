'use client'

type OperationsData = {
  status_reason_samples?: Array<{ task_id: string; status: string; status_reason: string; trace_id?: string; request_id?: string }>
  retry_history?: Array<{ task_id: string; retry_count: number; dead_letter: boolean; trace_id?: string }>
  recent_interventions?: Array<{ task_id: string; action: string; comment?: string; operator?: string; trace_id?: string; request_id?: string }>
}

export default function LogPanel({ data }: { data: OperationsData }) {
  const statusReasonSamples = data.status_reason_samples ?? []
  const retryHistory = data.retry_history ?? []
  const recentInterventions = data.recent_interventions ?? []

  return (
    <div className="card">
      <h2>日志与历史</h2>
      <p className="muted">展示状态原因、重试历史、人工介入记录以及 Trace ID / Request ID，作为 Agent 平台日志面板。</p>
      <div className="grid grid-3">
        <div>
          <strong>状态原因日志</strong>
          <ul>
            {statusReasonSamples.length ? statusReasonSamples.map((item) => (
              <li key={`${item.task_id}-${item.status}`}>{item.task_id} / {item.status} / {item.status_reason} / trace={item.trace_id ?? '-'} / request={item.request_id ?? '-'}</li>
            )) : <li>暂无状态原因日志</li>}
          </ul>
        </div>
        <div>
          <strong>重试历史日志</strong>
          <ul>
            {retryHistory.length ? retryHistory.map((item) => (
              <li key={item.task_id}>{item.task_id} / retry={item.retry_count} / dead_letter={String(item.dead_letter)} / trace={item.trace_id ?? '-'}</li>
            )) : <li>暂无重试历史</li>}
          </ul>
        </div>
        <div>
          <strong>人工介入日志</strong>
          <ul>
            {recentInterventions.length ? recentInterventions.map((item, index) => (
              <li key={`${item.task_id}-${index}`}>{item.task_id} / {item.action} / {item.operator ?? '-'} / {item.comment ?? '-'} / trace={item.trace_id ?? '-'} / request={item.request_id ?? '-'}</li>
            )) : <li>暂无人工介入日志</li>}
          </ul>
        </div>
      </div>
    </div>
  )
}
