'use client'

import { useEffect, useRef, useState } from 'react'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import SelectionCreateForm from '@/components/workbench/SelectionCreateForm'
import SelectionTaskTable from '@/components/workbench/SelectionTaskTable'
import { API_BASE, apiFetch } from '@/lib/api'
import { getToken } from '@/lib/auth'
import type {
  SelectionAccuracyTrendPoint,
  SelectionSummaryResponse,
  SelectionTaskListResponse,
  SelectionWorkbenchAgentStep,
  SelectionWorkbenchSignal,
  SelectionWorkbenchStreamEvent,
} from '@/lib/contracts'

const DEFAULT_RETRY_MS = 3000

function AccuracyTrendChart({ points }: { points: SelectionAccuracyTrendPoint[] }) {
  const visible = points.slice(-12)
  const fallback = visible.length ? visible : [
    { date: '暂无数据', total: 0, correct: 0, accuracy: 0, cumulative_accuracy: 0 },
  ]
  return (
    <div className="card">
      <h2>ECharts趋势图 / 准确率趋势</h2>
      <p className="muted">无新增依赖的 ECharts-compatible 趋势渲染，数据来自 BFF accuracy_trend。</p>
      <div className="spark-grid">
        {fallback.map((item, index) => {
          const value = Math.round((item.cumulative_accuracy ?? item.accuracy ?? 0) * 100)
          const height = `${Math.max(value, value > 0 ? 12 : 4)}%`
          return (
            <div key={`${item.date}-${index}`} className="spark-col">
              <div className="spark-value">{value}%</div>
              <div className="spark-bar-wrap"><div className="spark-bar" style={{ height }} /></div>
              <div className="spark-label">{item.date}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function SelectionWorkbenchPage() {
  const [summary, setSummary] = useState<SelectionSummaryResponse | null>(null)
  const [tasks, setTasks] = useState<SelectionTaskListResponse | null>(null)
  const [signals, setSignals] = useState<SelectionWorkbenchSignal[]>([])
  const [agentSteps, setAgentSteps] = useState<SelectionWorkbenchAgentStep[]>([])
  const [streamMeta, setStreamMeta] = useState<SelectionWorkbenchStreamEvent['reconnect'] | null>(null)
  const [streamStatus, setStreamStatus] = useState<'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected'>('idle')
  const [error, setError] = useState<string | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setError(null)
        const [summaryData, taskData] = await Promise.all([
          apiFetch<SelectionSummaryResponse>('/bff/workbench/selection/summary'),
          apiFetch<SelectionTaskListResponse>('/bff/workbench/selection/tasks'),
        ])
        setSummary(summaryData)
        setTasks(taskData)
      } catch (e) {
        setError(e instanceof Error ? e.message : '未知错误')
      }
    }

    void load()
  }, [])

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setStreamStatus('disconnected')
      return
    }

    let cancelled = false
    let controller: AbortController | null = null
    let ws: WebSocket | null = null
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null

    const applyPayload = (payload: SelectionWorkbenchStreamEvent) => {
      setSummary(payload.summary)
      setTasks(payload.tasks)
      setSignals(payload.signals ?? [])
      setAgentSteps(payload.agent_steps ?? [])
      setStreamMeta(payload.reconnect ?? null)
    }

    const cleanupTimer = () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
    }

    const scheduleReconnect = (retryMs: number) => {
      cleanupTimer()
      if (cancelled) return
      setStreamStatus('reconnecting')
      retryTimerRef.current = setTimeout(() => {
        if (!cancelled) {
          void connect(retryMs)
        }
      }, retryMs)
    }

    const connectViaSSE = async (retryMs: number) => {
      controller?.abort()
      controller = new AbortController()
      try {
        const response = await fetch(`${API_BASE}/bff/workbench/selection/stream`, {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'text/event-stream',
          },
          cache: 'no-store',
          signal: controller.signal,
        })

        if (!response.ok || !response.body) {
          throw new Error('实时流连接失败')
        }

        setStreamStatus('connected')
        setError(null)

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let nextRetryMs = retryMs

        while (!cancelled) {
          const { value, done } = await reader.read()
          if (done) {
            scheduleReconnect(nextRetryMs)
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() ?? ''

          for (const chunk of chunks) {
            const dataLine = chunk
              .split('\n')
              .find((line) => line.startsWith('data: '))
            if (!dataLine) continue

            const payload = JSON.parse(dataLine.slice(6)) as SelectionWorkbenchStreamEvent
            applyPayload(payload)
            nextRetryMs = payload.reconnect?.retry_ms ?? DEFAULT_RETRY_MS
          }
        }
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : '实时流连接失败')
        scheduleReconnect(streamMeta?.retry_ms ?? retryMs)
      }
    }

    const connect = async (retryMs: number) => {
      controller?.abort()
      ws?.close()
      cleanupTimer()
      setStreamStatus((current) => (current === 'connected' ? 'reconnecting' : 'connecting'))

      const wsUrl = API_BASE.replace(/^http/i, 'ws') + `/bff/workbench/selection/ws?token=${encodeURIComponent(token)}`
      try {
        await new Promise<void>((resolve, reject) => {
          ws = new WebSocket(wsUrl)

          ws.onopen = () => {
            setStreamStatus('connected')
            setError(null)
            heartbeatTimer = setInterval(() => {
              try {
                ws?.send(JSON.stringify({ action: 'heartbeat' }))
              } catch {
                // ignore and let onclose handle reconnect
              }
            }, 30000)
            resolve()
          }

          ws.onmessage = (event) => {
            const payload = JSON.parse(String(event.data)) as SelectionWorkbenchStreamEvent & { type?: string }
            if (payload.type === 'heartbeat') return
            applyPayload(payload)
          }

          ws.onerror = () => {
            reject(new Error('WebSocket连接失败'))
          }

          ws.onclose = () => {
            if (!cancelled) {
              scheduleReconnect(streamMeta?.retry_ms ?? retryMs)
            }
          }
        })
      } catch {
        await connectViaSSE(retryMs)
      }
    }

    void connect(DEFAULT_RETRY_MS)

    return () => {
      cancelled = true
      cleanupTimer()
      controller?.abort()
      ws?.close()
    }
  }, [streamMeta?.retry_ms])

  return (
    <AuthGuard>
      <main className="container">
        <div className="card">
          <h1>正式选品工作台</h1>
          <p className="muted">Next.js + BFF 正式工作台入口</p>
          <div className="grid grid-3">
            <div className="metric-card">
              <div className="metric-label">当前用户</div>
              <div className="metric-value">{summary?.username ?? '-'}</div>
              <div className="metric-hint">当前工作台操作者</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">总任务数</div>
              <div className="metric-value">{summary?.total ?? 0}</div>
              <div className="metric-hint">当前租户任务总量</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">待审批</div>
              <div className="metric-value">{summary?.pending_approval_count ?? 0}</div>
              <div className="metric-hint">等待人工审批的任务数</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">高风险任务</div>
              <div className="metric-value">{summary?.high_risk_count ?? 0}</div>
              <div className="metric-hint">存在风险提示的任务数</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">平均 ROI</div>
              <div className="metric-value">{summary?.avg_roi_year1_percent != null ? `${summary.avg_roi_year1_percent}%` : '-'}</div>
              <div className="metric-hint">基于当前任务利润测算</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">GO 决策数</div>
              <div className="metric-value">{summary?.go_decision_count ?? 0}</div>
              <div className="metric-hint">已形成明确进入决策的任务数</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">流状态</div>
              <div className="metric-value">{streamStatus}</div>
              <div className="metric-hint">实时事件流连接状态</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">数据来源</div>
              <div className="metric-value">{summary?.data_source ?? 'selection_task_service'}</div>
              <div className="metric-hint">当前摘要聚合来源</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">最近更新时间</div>
              <div className="metric-value">{summary?.updated_at ?? '-'}</div>
              <div className="metric-hint">最近任务更新时间</div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <strong>状态分布：</strong>
            {Object.entries(summary?.by_status ?? {})
              .map(([status, count]) => `${status}:${count}`)
              .join(' / ') || '-'}
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}

        <div className="card">
          <div className="grid grid-2">
            <div>
              <strong>实时信号：</strong>
              {signals.length}
            </div>
            <div>
              <strong>重连策略：</strong>
              {streamMeta?.strategy ?? '-'} / {streamMeta?.retry_ms ?? DEFAULT_RETRY_MS}ms
            </div>
          </div>
          <div className="grid grid-2" style={{ marginTop: 12 }}>
            <div>
              <strong>关键趋势/决策</strong>
              <ul>
                {signals.length > 0 ? (
                  signals.slice(0, 5).map((item) => (
                    <li key={item.task_id}>
                      {item.task_id} / {item.trend_direction ?? '-'} / {item.decision ?? '-'} / 风险 {item.risk_count ?? 0}
                    </li>
                  ))
                ) : (
                  <li>暂无实时信号</li>
                )}
              </ul>
            </div>
            <div>
              <strong>Agent 步骤</strong>
              <ul>
                {agentSteps.length > 0 ? (
                  agentSteps.slice(0, 5).map((item) => (
                    <li key={item.task_id}>
                      {item.task_id} / 步骤数 {(item.steps ?? []).length}
                    </li>
                  ))
                ) : (
                  <li>暂无 Agent 步骤</li>
                )}
              </ul>
            </div>
          </div>
        </div>

        <AccuracyTrendChart points={summary?.accuracy_trend ?? []} />
        <SelectionCreateForm />
        {tasks ? <SelectionTaskTable data={tasks} /> : <div className="card">正在加载任务列表...</div>}
      </main>
    </AuthGuard>
  )
}
