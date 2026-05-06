'use client'

import { useEffect, useState } from 'react'

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

type DashboardResponse = {
  summary?: {
    overall_status?: string
    bi_asset_count?: number
    loop_closed?: boolean
    data_source?: string
    updated_at?: string | null
    report_title?: string
    report_count?: number
    gmv?: number
    completion_rate?: number
  }
  charts?: {
    trend_chart?: DashboardChart
    profit_chart?: DashboardChart
    risk_chart?: DashboardChart
    competitor_chart?: DashboardChart
    execution_chart?: DashboardChart
  }
}

function SummaryCard({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{title}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  )
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setError(null)
        const result = await apiFetch<DashboardResponse>('/dashboard/selection-overview')
        setData(result)
      } catch (e) {
        setError(e instanceof Error ? e.message : '数据大盘加载失败')
      }
    }
    void load()
  }, [])

  const summary = data?.summary ?? {}
  const charts = data?.charts ?? {}

  return (
    <AuthGuard>
      <main className="container">
        <div className="card">
          <h1>利润中枢看板</h1>
          <p className="muted">利润 / ROI / 库存风险 / 供应风险 / 趋势机会 / 飞轮状态</p>
        </div>

        {error ? <ErrorState message={error} /> : null}

        <div className="grid grid-3" style={{ marginBottom: 16 }}>
          <SummaryCard title="总状态" value={summary.overall_status ?? '-'} hint="当前经营闭环总体判断" />
          <SummaryCard title="BI 资产数" value={summary.bi_asset_count ?? 0} hint="已进入 BI-ready 的资产数量" />
          <SummaryCard title="闭环状态" value={summary.loop_closed ? '已闭环' : '未闭环'} hint="反馈回流是否闭环" />
          <SummaryCard title="数据来源" value={summary.data_source ?? 'services'} hint="本地模拟数据 / 服务聚合" />
          <SummaryCard title="GMV" value={summary.gmv ?? 0} hint={summary.report_title ?? '最新报告'} />
          <SummaryCard title="完成率" value={summary.completion_rate != null ? `${summary.completion_rate}%` : '-'} hint={summary.updated_at ?? '暂无更新时间'} />
        </div>

        <DashboardCharts charts={charts} />
      </main>
    </AuthGuard>
  )
}
