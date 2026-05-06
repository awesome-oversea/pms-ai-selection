'use client'

import { useState } from 'react'
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

type FmsStatus = {
  profit_summary?: { gross_profit_total?: number; avg_margin_rate?: number }
  profit_trace_ready?: boolean
}

type DailyKpi = {
  kpi_date?: string
  summary?: { task_count?: number; [key: string]: number | string | undefined }
  rows?: Array<Record<string, unknown>>
}

type DashboardResponse = {
  summary?: { gmv?: number; completion_rate?: number; overall_status?: string; report_title?: string }
  charts?: Record<string, DashboardChart | undefined>
}

export default function FinancePage() {
  const [fmsStatus, setFmsStatus] = useState<FmsStatus | null>(null)
  const [dailyKpi, setDailyKpi] = useState<DailyKpi | null>(null)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [fms, kpi, dash] = await Promise.all([
        apiFetch<FmsStatus>('/integration/fms/status?name=default'),
        apiFetch<DailyKpi>('/integration/bi/kpis/daily/latest?name=default'),
        apiFetch<DashboardResponse>('/dashboard/selection-overview'),
      ])
      setFmsStatus(fms)
      setDailyKpi(kpi)
      setDashboard(dash)
      setMessage('财务工作台已刷新。')
    } catch (e) {
      setError(e instanceof Error ? e.message : '财务工作台加载失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>财务工作台</h1>
          <p className="muted">覆盖 B13-14：成本核算、利润分析、费用/KPI 追踪，聚合 FMS、BI 与经营看板数据。</p>
          <div className="nav">
            <Link href="/dashboard">利润中枢</Link>
            <Link href="/kpi">管理KPI</Link>
            <Link href="/procurement">采购工作台</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="card">
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void load()}>{loading ? '加载中...' : '刷新财务指标'}</button>
          </div>
        </div>

        <div className="grid grid-4">
          <div className="metric-card">
            <div className="metric-label">毛利润</div>
            <div className="metric-value">{fmsStatus?.profit_summary?.gross_profit_total ?? 0}</div>
            <div className="metric-hint">FMS profit_summary</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">平均毛利率</div>
            <div className="metric-value">{fmsStatus?.profit_summary?.avg_margin_rate != null ? `${((fmsStatus.profit_summary.avg_margin_rate ?? 0) * 100).toFixed(1)}%` : '-'}</div>
            <div className="metric-hint">利润率</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">GMV</div>
            <div className="metric-value">{dashboard?.summary?.gmv ?? 0}</div>
            <div className="metric-hint">经营汇总</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">KPI日期</div>
            <div className="metric-value">{dailyKpi?.kpi_date ?? '-'}</div>
            <div className="metric-hint">每日KPI快照日期</div>
          </div>
        </div>

        <DashboardCharts charts={dashboard?.charts ?? {}} />

        <div className="grid grid-2">
          <div className="card">
            <h2>BI 每日 KPI</h2>
            <pre className="code-panel">{JSON.stringify(dailyKpi ?? {}, null, 2)}</pre>
          </div>
          <div className="card">
            <h2>FMS 成本与利润状态</h2>
            <pre className="code-panel">{JSON.stringify(fmsStatus ?? {}, null, 2)}</pre>
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
