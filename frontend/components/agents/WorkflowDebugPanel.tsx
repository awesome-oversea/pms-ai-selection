'use client'

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'

type SnapshotListItem = {
  snapshot_id: string
  framework?: string
  current_node?: string
  next_node?: string
  status?: string
}

type SnapshotDetail = {
  snapshot_id?: string
  framework?: string
  current_node?: string
  next_node?: string
  status?: string
  human_input?: Record<string, unknown>
  [key: string]: unknown
}

type StepResumeResult = {
  snapshot?: SnapshotDetail
  status?: string
  single_step?: boolean
  human_input?: Record<string, unknown>
  rolled_back?: boolean
  target_node?: string
}

export default function WorkflowDebugPanel() {
  const [snapshots, setSnapshots] = useState<SnapshotListItem[]>([])
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('')
  const [detail, setDetail] = useState<SnapshotDetail | null>(null)
  const [humanAction, setHumanAction] = useState('approve')
  const [humanComment, setHumanComment] = useState('人工确认继续执行')
  const [rollbackTargetNode, setRollbackTargetNode] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const loadSnapshots = async () => {
    const data = await apiFetch<{ total?: number; items?: SnapshotListItem[] }>('/agents/platform/workflows/snapshots?limit=20')
    const items = data.items ?? []
    setSnapshots(items)
    setSelectedSnapshotId((current) => current || items[0]?.snapshot_id || '')
  }

  const loadDetail = async (snapshotId: string) => {
    if (!snapshotId) {
      setDetail(null)
      return
    }
    const data = await apiFetch<SnapshotDetail>(`/agents/platform/workflows/snapshots/${snapshotId}`)
    setDetail(data)
  }

  useEffect(() => {
    void loadSnapshots()
  }, [])

  useEffect(() => {
    void loadDetail(selectedSnapshotId)
  }, [selectedSnapshotId])

  useEffect(() => {
    setRollbackTargetNode(String(detail?.current_node ?? detail?.next_node ?? ''))
  }, [detail])

  const stepSnapshot = async () => {
    if (!selectedSnapshotId) return
    setLoading(true)
    setMessage(null)
    try {
      const data = await apiFetch<StepResumeResult>(`/agents/platform/workflows/snapshots/${selectedSnapshotId}/step`, {
        method: 'POST',
      })
      setDetail(data.snapshot ?? detail)
      setMessage(`快照 ${selectedSnapshotId} 已单步推进`)
      await loadSnapshots()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '单步执行失败')
    } finally {
      setLoading(false)
    }
  }

  const resumeSnapshot = async () => {
    if (!selectedSnapshotId) return
    setLoading(true)
    setMessage(null)
    try {
      const data = await apiFetch<StepResumeResult>(`/agents/platform/workflows/snapshots/${selectedSnapshotId}/resume`, {
        method: 'POST',
        body: JSON.stringify({ human_input: { action: humanAction, comment: humanComment } }),
      })
      setDetail((data.snapshot ?? detail) as SnapshotDetail)
      setRollbackTargetNode(String(data.snapshot?.current_node ?? data.snapshot?.next_node ?? detail?.current_node ?? ''))
      setMessage(`快照 ${selectedSnapshotId} 已注入人工决策并恢复执行`)
      await loadSnapshots()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '恢复执行失败')
    } finally {
      setLoading(false)
    }
  }

  const rollbackSnapshot = async () => {
    if (!selectedSnapshotId) return
    setLoading(true)
    setMessage(null)
    try {
      const data = await apiFetch<StepResumeResult>(`/agents/platform/workflows/snapshots/${selectedSnapshotId}/rollback`, {
        method: 'POST',
        body: JSON.stringify({ target_node: rollbackTargetNode || undefined }),
      })
      setDetail((data.snapshot ?? detail) as SnapshotDetail)
      setRollbackTargetNode(String(data.target_node ?? rollbackTargetNode))
      setMessage(`快照 ${selectedSnapshotId} 已回滚到 ${data.target_node ?? rollbackTargetNode ?? '当前节点'}`)
      await loadSnapshots()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '回滚失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>工作流断点调试 / Human-in-the-loop / 状态回滚</h2>
      <p className="muted">覆盖 B13-22 / B1-05：查看工作流快照、单步执行、注入人工决策、回滚到指定节点并恢复后续流程。</p>
      <div className="grid grid-2">
        <div>
          <strong>快照列表</strong>
          <div className="inline-form" style={{ marginTop: 12 }}>
            {snapshots.length ? snapshots.map((item) => (
              <button
                key={item.snapshot_id}
                type="button"
                className="list-card"
                style={{ textAlign: 'left', cursor: 'pointer', borderColor: selectedSnapshotId === item.snapshot_id ? '#2563eb' : undefined }}
                onClick={() => setSelectedSnapshotId(item.snapshot_id)}
              >
                <div><strong>{item.snapshot_id}</strong></div>
                <div className="muted">framework={item.framework ?? '-'} / current={item.current_node ?? '-'} / next={item.next_node ?? '-'}</div>
                <div className="muted">status={item.status ?? '-'}</div>
              </button>
            )) : <div className="list-card">暂无工作流快照，可先从框架调用入口产生断点快照。</div>}
          </div>
        </div>

        <div>
          <strong>人工决策注入 / 状态回滚</strong>
          <div className="inline-form" style={{ marginTop: 12 }}>
            <input className="input" value={selectedSnapshotId} onChange={(e) => setSelectedSnapshotId(e.target.value)} placeholder="snapshot_id" />
            <select className="select" value={humanAction} onChange={(e) => setHumanAction(e.target.value)}>
              <option value="approve">approve</option>
              <option value="retry">retry</option>
              <option value="pause_for_review">pause_for_review</option>
              <option value="reject">reject</option>
            </select>
            <textarea className="textarea" rows={4} value={humanComment} onChange={(e) => setHumanComment(e.target.value)} />
            <input className="input" value={rollbackTargetNode} onChange={(e) => setRollbackTargetNode(e.target.value)} placeholder="回滚目标节点，如 market_analysis" />
            <div className="action-row">
              <button className="btn btn-secondary" type="button" disabled={loading || !selectedSnapshotId} onClick={() => void stepSnapshot()}>单步执行</button>
              <button className="btn btn-secondary" type="button" disabled={loading || !selectedSnapshotId} onClick={() => void rollbackSnapshot()}>状态回滚</button>
              <button className="btn btn-primary" type="button" disabled={loading || !selectedSnapshotId} onClick={() => void resumeSnapshot()}>注入并恢复</button>
            </div>
          </div>
          {message ? <p className="muted" style={{ marginTop: 12 }}>{message}</p> : null}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <strong>快照详情</strong>
        <pre className="code-panel">{JSON.stringify(detail ?? {}, null, 2)}</pre>
      </div>
    </div>
  )
}
