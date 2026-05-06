'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { DashboardCharts } from '@/components/common/DashboardCharts'
import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

type DashboardChart = {
  type?: string
  title?: string
  xAxis?: string[]
  series?: number[]
  items?: Array<{ name: string; value: number }>
}

type TeamPerformanceRow = {
  owner: string
  task_count: number
  completed_count: number
  pending_count: number
  go_count: number
  completion_rate: number
  go_rate: number
  avg_roi_year1_percent?: number | null
  performance_score: number
}

type ApprovalQueueItem = {
  task_id: string
  query: string
  current_stage?: string | null
  current_stage_order?: number | null
  approval_count?: number | null
  target_market?: string | null
  priority?: string | null
  created_at?: string | null
  updated_at?: string | null
  created_by_username?: string | null
}

type AccuracyTrendPoint = {
  date: string
  total: number
  correct: number
  accuracy: number
  cumulative_accuracy?: number
}

type DashboardResponse = {
  summary?: {
    overall_status?: string
    bi_asset_count?: number
    loop_closed?: boolean
    data_source?: string
    updated_at?: string | null
    report_title?: string | null
    report_count?: number
    gmv?: number
    completion_rate?: number
    pending_approval_count?: number
    avg_roi_year1_percent?: number | null
    accuracy?: number
    correct_tasks?: number
    total_accuracy_tasks?: number
  }
  charts?: {
    trend_chart?: DashboardChart
    profit_chart?: DashboardChart
    risk_chart?: DashboardChart
    competitor_chart?: DashboardChart
    execution_chart?: DashboardChart
  }
  team_performance?: TeamPerformanceRow[]
  approval_queue?: ApprovalQueueItem[]
  accuracy_trend?: AccuracyTrendPoint[]
}

function AccuracyTrendChart({ points }: { points: AccuracyTrendPoint[] }) {
  const visible = points.slice(-12)
  const fallback = visible.length ? visible : [
    { date: '暂无数据', total: 0, correct: 0, accuracy: 0, cumulative_accuracy: 0 },
  ]

  return (
    <div className="card">
      <h2>准确率趋势</h2>
      <p className="muted">管理者查看选品预测与实际执行效果的一致性趋势。</p>
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

export default function KpiPage() {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setError(null)
      const result = await apiFetch<DashboardResponse>('/bff/workbench/manager/overview')
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : '管理者 KPI 看板加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const approveTask = async (taskId: string, action: 'approve' | 'reject') => {
    try {
      setLoading(true)
      await apiFetch(`/bff/workbench/selection/tasks/${taskId}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          action,
          reviewer: 'manager_workbench',
          comment: action === 'approve' ? '管理者工作台审批通过' : '管理者工作台审批拒绝',
          stage: 'manager_review',
          stage_order: 3,
        }),
      })
      setMessage(`任务 ${taskId} 已${action === 'approve' ? '审批通过' : '审批拒绝'}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '审批操作失败')
    } finally {
      setLoading(false)
    }
  }

  const summary = data?.summary ?? {}
  const charts = data?.charts ?? {}
  const teamPerformance = data?.team_performance ?? []
  const approvalQueue = data?.approval_queue ?? []
  const accuracyTrend = data?.accuracy_trend ?? []

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>管理者 KPI 看板</h1>
          <p className="muted">覆盖管理者工作台：选品KPI看板、团队绩效、审批流、准确率趋势。</p>
          <div className="nav">
            <Link href="/dashboard">利润中枢</Link>
            <Link href="/competitors">竞品监控</Link>
            <Link href="/trends">趋势榜单</Link>
            <Link href="/workbench/selection">选品工作台</Link>
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void load()}>
              {loading ? '刷新中...' : '刷新管理看板'}
            </button>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="grid grid-4">
          <div className="metric-card">
            <div className="metric-label">任务完成率</div>
            <div className="metric-value">{summary.completion_rate != null ? `${summary.completion_rate}%` : '-'}</div>
            <div className="metric-hint">团队任务执行完成度</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">待审批任务</div>
            <div className="metric-value">{summary.pending_approval_count ?? 0}</div>
            <div className="metric-hint">等待管理者处理</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">平均 ROI</div>
            <div className="metric-value">{summary.avg_roi_year1_percent != null ? `${summary.avg_roi_year1_percent}%` : '-'}</div>
            <div className="metric-hint">当前租户选品收益均值</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">准确率</div>
            <div className="metric-value">{summary.accuracy != null ? `${Math.round(summary.accuracy * 100)}%` : '-'}</div>
            <div className="metric-hint">预测与实际表现一致度</div>
          </div>
        </div>

        <div className="card">
          <h2>管理摘要</h2>
          <div className="plain-list">
            <div className="plain-row">
              <div>
                <strong>总体状态</strong>
                <p>{summary.overall_status ?? '-'}</p>
              </div>
              <div className="plain-meta">
                <span className={summary.loop_closed ? 'status-pill status-pill-good' : 'status-pill status-pill-warn'}>
                  {summary.loop_closed ? '飞轮闭环' : '待闭环'}
                </span>
                <span>{summary.data_source ?? 'services'}</span>
              </div>
            </div>
            <div className="plain-row">
              <div>
                <strong>最近关注任务</strong>
                <p>{summary.report_title ?? '-'}</p>
              </div>
              <div className="plain-meta">
                <span>{summary.report_count ?? 0} 个任务</span>
                <span>{summary.updated_at ?? '暂无更新时间'}</span>
              </div>
            </div>
          </div>
        </div>

        <DashboardCharts charts={charts} />

        <AccuracyTrendChart points={accuracyTrend} />

        <div className="grid grid-2">
          <div className="card">
            <h2>团队绩效排名</h2>
            <div className="action-row">
              <span className="status-pill status-pill-good">Top1：{teamPerformance[0]?.owner ?? '暂无'}</span>
              <span className="status-pill status-pill-warn">待处理审批：{approvalQueue.length}</span>
            </div>
            <p className="muted">按完成率、GO率、平均ROI综合计算绩效分。</p>
            <table className="table compact-table">
              <thead>
                <tr>
                  <th>成员</th>
                  <th>任务数</th>
                  <th>完成率</th>
                  <th>GO率</th>
                  <th>平均ROI</th>
                  <th>绩效分</th>
                </tr>
              </thead>
              <tbody>
                {teamPerformance.length > 0 ? teamPerformance.map((item) => (
                  <tr key={item.owner}>
                    <td>{item.owner}</td>
                    <td>{item.task_count}</td>
                    <td>{item.completion_rate}%</td>
                    <td>{item.go_rate}%</td>
                    <td>{item.avg_roi_year1_percent != null ? `${item.avg_roi_year1_percent}%` : '-'}</td>
                    <td>{item.performance_score}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={6}>暂无团队绩效数据</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h2>审批流待办</h2>
            <p className="muted">管理者可直接处理终审待办，缩短选品到执行的决策链路。</p>
            <table className="table compact-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>发起人</th>
                  <th>阶段</th>
                  <th>市场</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {approvalQueue.length > 0 ? approvalQueue.map((item) => (
                  <tr key={item.task_id}>
                    <td>
                      <strong>{item.query}</strong>
                      <div className="muted">{item.task_id}</div>
                    </td>
                    <td>{item.created_by_username ?? '-'}</td>
                    <td>{item.current_stage ?? '-'} / {item.current_stage_order ?? '-'}</td>
                    <td>{item.target_market ?? '-'}</td>
                    <td>
                      <div className="action-row">
                        <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void approveTask(item.task_id, 'approve')}>审批通过</button>
                        <button className="btn btn-danger" type="button" disabled={loading} onClick={() => void approveTask(item.task_id, 'reject')}>审批拒绝</button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5}>暂无待审批任务</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
