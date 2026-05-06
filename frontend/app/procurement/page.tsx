'use client'

import { useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

type StatusResponse = Record<string, unknown>
type LogResponse = { total?: number; logs?: Array<Record<string, unknown>> }

export default function ProcurementPage() {
  const [taskId, setTaskId] = useState('task-close-loop-001')
  const [scmStatus, setScmStatus] = useState<StatusResponse | null>(null)
  const [wmsStatus, setWmsStatus] = useState<StatusResponse | null>(null)
  const [omsStatus, setOmsStatus] = useState<StatusResponse | null>(null)
  const [adoptionStatus, setAdoptionStatus] = useState<Record<string, unknown> | null>(null)
  const [scmLogs, setScmLogs] = useState<LogResponse | null>(null)
  const [wmsLogs, setWmsLogs] = useState<LogResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [scm, wms, oms, adoption, scmLogData, wmsLogData] = await Promise.all([
        apiFetch<StatusResponse>('/integration/scm/status?name=default'),
        apiFetch<StatusResponse>('/integration/wms/status?name=default'),
        apiFetch<StatusResponse>('/integration/oms/status?name=default'),
        apiFetch<Record<string, unknown>>(`/integration/selection/${taskId}/adoption-status`),
        apiFetch<LogResponse>('/integration/scm/logs?limit=10'),
        apiFetch<LogResponse>('/integration/wms/logs?limit=10'),
      ])
      setScmStatus(scm)
      setWmsStatus(wms)
      setOmsStatus(oms)
      setAdoptionStatus(adoption)
      setScmLogs(scmLogData)
      setWmsLogs(wmsLogData)
      setMessage('采购工作台已刷新。')
    } catch (e) {
      setError(e instanceof Error ? e.message : '采购工作台加载失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>采购工作台</h1>
          <p className="muted">覆盖 B13-13：供应商管理、采购单跟踪、库容预留、OMS 上架草稿与采纳执行链路可视化。</p>
          <div className="nav">
            <Link href="/workbench/selection">选品工作台</Link>
            <Link href="/finance">财务工作台</Link>
            <Link href="/operations">运营台</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="card">
          <h2>采纳任务跟踪</h2>
          <div className="form-grid">
            <input className="input" value={taskId} onChange={(e) => setTaskId(e.target.value)} placeholder="采纳任务ID" />
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void load()}>{loading ? '加载中...' : '刷新采购状态'}</button>
          </div>
        </div>

        <div className="grid grid-4">
          <div className="metric-card">
            <div className="metric-label">SCM状态</div>
            <div className="metric-value">{String((scmStatus?.status as string | undefined) ?? (scmStatus?.system_type as string | undefined) ?? '-')}</div>
            <div className="metric-hint">采购/供应状态</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">WMS状态</div>
            <div className="metric-value">{String((wmsStatus?.fulfillment_status as { status?: string } | undefined)?.status ?? (wmsStatus?.system_type as string | undefined) ?? '-')}</div>
            <div className="metric-hint">库容/履约状态</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">OMS状态</div>
            <div className="metric-value">{String((omsStatus?.system_type as string | undefined) ?? '-')}</div>
            <div className="metric-hint">上架/销售侧状态</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">采纳状态</div>
            <div className="metric-value">{String((adoptionStatus?.status as string | undefined) ?? '-')}</div>
            <div className="metric-hint">选品采纳执行进度</div>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>SCM / WMS 日志</h2>
            <pre className="code-panel">{JSON.stringify({ scmLogs, wmsLogs }, null, 2)}</pre>
          </div>
          <div className="card">
            <h2>执行状态面板</h2>
            <pre className="code-panel">{JSON.stringify({ scmStatus, wmsStatus, omsStatus, adoptionStatus }, null, 2)}</pre>
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
