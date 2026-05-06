'use client'

import { useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'

type RetryableTask = {
  task_id: string
  status?: string
  status_reason?: string
  retry_count?: number
  dead_letter?: boolean
}

type OperationsData = {
  retryable_tasks?: RetryableTask[]
}

type TaskActionResult = {
  task_id: string
  status?: string
  status_reason?: string
  dead_letter?: boolean
  config?: Record<string, unknown>
}

export default function ActionCenterPanel({ data, onChanged }: { data: OperationsData; onChanged?: () => Promise<void> | void }) {
  const retryableTasks = useMemo(() => data.retryable_tasks ?? [], [data.retryable_tasks])
  const [selectedTaskId, setSelectedTaskId] = useState<string>(retryableTasks[0]?.task_id ?? '')
  const [action, setAction] = useState('pause_and_review')
  const [comment, setComment] = useState('平台人工介入：请复核上下文与状态原因')
  const [message, setMessage] = useState<string | null>(null)
  const [result, setResult] = useState<TaskActionResult | null>(null)
  const [loading, setLoading] = useState(false)

  const handleResume = async (taskId: string) => {
    setLoading(true)
    setMessage(null)
    try {
      const payload = await apiFetch<TaskActionResult>(`/agents/platform/tasks/${taskId}/resume`, {
        method: 'POST',
      })
      setResult(payload)
      setMessage(`任务 ${taskId} 已恢复`) 
      await onChanged?.()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '恢复失败')
    } finally {
      setLoading(false)
    }
  }

  const handleIntervene = async () => {
    if (!selectedTaskId) {
      setMessage('请先选择任务')
      return
    }
    setLoading(true)
    setMessage(null)
    try {
      const payload = await apiFetch<TaskActionResult>(`/agents/platform/tasks/${selectedTaskId}/intervene`, {
        method: 'POST',
        body: JSON.stringify({ action, comment }),
      })
      setResult(payload)
      setMessage(`任务 ${selectedTaskId} 已登记人工介入`) 
      await onChanged?.()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '人工介入失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>操作中心</h2>
      <p className="muted">对可恢复任务执行恢复，对指定任务执行人工介入。</p>

      <div className="grid grid-2">
        <div>
          <strong>可恢复任务</strong>
          <div className="inline-form">
            {retryableTasks.length ? (
              retryableTasks.map((task) => (
                <div key={task.task_id} className="list-card">
                  <div><strong>{task.task_id}</strong></div>
                  <div className="muted">状态：{task.status ?? '-'} / dead_letter={String(task.dead_letter ?? false)} / retry={task.retry_count ?? 0}</div>
                  <div className="muted">原因：{task.status_reason ?? '-'}</div>
                  <div className="action-row">
                    <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void handleResume(task.task_id)}>
                      恢复任务
                    </button>
                    <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => setSelectedTaskId(task.task_id)}>
                      设为介入目标
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="list-card">暂无可恢复任务</div>
            )}
          </div>
        </div>

        <div>
          <strong>人工介入</strong>
          <div className="inline-form">
            <input
              className="input"
              placeholder="任务ID"
              value={selectedTaskId}
              onChange={(event) => setSelectedTaskId(event.target.value)}
            />
            <select className="select" value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="pause_and_review">pause_and_review</option>
              <option value="escalate">escalate</option>
              <option value="retry_with_context">retry_with_context</option>
            </select>
            <textarea
              className="textarea"
              rows={4}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
            <div className="action-row">
              <button className="btn btn-primary" type="button" disabled={loading || !selectedTaskId} onClick={() => void handleIntervene()}>
                提交人工介入
              </button>
            </div>
          </div>
        </div>
      </div>

      {message ? <p className="muted" style={{ marginTop: 12 }}>{message}</p> : null}
      {result ? (
        <pre className="code-panel">{JSON.stringify(result, null, 2)}</pre>
      ) : null}
    </div>
  )
}
