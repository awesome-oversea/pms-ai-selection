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

type TrendAggregate = {
  dataset?: string
  growth?: { growth_7d_vs_30d?: number; peak_heat?: number }
  window_metrics?: { '7d'?: { avg_heat?: number }; '30d'?: { avg_heat?: number } }
}

type RatioData = {
  demand_supply_ratio?: number
  supply_count?: number
  demand_index?: number
}

type BenchmarkData = {
  benchmark_ratio?: number
  growth_gap_percent?: number
  own_store_sales_proxy?: number
  market_sales_proxy?: number
}

type TopicData = {
  topics?: Array<{ topic?: string; heat?: number }>
  topic_count?: number
}

type LifecycleData = {
  lifecycle_stage?: string
  demand_supply_ratio?: number
}

type RSSSignalData = {
  source?: string
  total_count?: number
  top_articles?: Array<{ title?: string; url?: string | null; source?: string | null; pub_date?: string | null }>
}

export default function TrendsPage() {
  const [form, setForm] = useState({ query: '蓝牙耳机', category: 'electronics', target_market: 'US' })
  const [charts, setCharts] = useState<Record<string, DashboardChart | undefined>>({})
  const [snapshot, setSnapshot] = useState<{
    aggregate?: TrendAggregate
    ratio?: RatioData
    benchmark?: BenchmarkData
    topics?: TopicData
    lifecycle?: LifecycleData
    rss?: RSSSignalData
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = JSON.stringify(form)
      const [aggregate, ratio, benchmark, topics, lifecycle, rss] = await Promise.all([
        apiFetch<TrendAggregate>('/market/trends/aggregate', { method: 'POST', body: payload }),
        apiFetch<RatioData>('/market/bsr-demand-ratio', { method: 'POST', body: payload }),
        apiFetch<BenchmarkData>('/market/oms-benchmark', { method: 'POST', body: payload }),
        apiFetch<TopicData>('/market/forum-topics', { method: 'POST', body: payload }),
        apiFetch<LifecycleData>('/market/lifecycle', { method: 'POST', body: payload }),
        apiFetch<RSSSignalData>('/market/signals/rss-real', { method: 'POST', body: JSON.stringify({ query: form.query, mode: 'auto' }) }),
      ])

      setSnapshot({ aggregate, ratio, benchmark, topics, lifecycle, rss })
      setCharts({
        trend_chart: {
          type: 'line',
          title: 'Google Trends 热度窗口',
          xAxis: ['7d avg', '30d avg', 'peak'],
          series: [
            aggregate.window_metrics?.['7d']?.avg_heat ?? 0,
            aggregate.window_metrics?.['30d']?.avg_heat ?? 0,
            aggregate.growth?.peak_heat ?? 0,
          ],
        },
        profit_chart: {
          type: 'bar',
          title: '销量基准对比',
          xAxis: ['自营销量代理', '市场销量代理', '基准比'],
          series: [
            benchmark.own_store_sales_proxy ?? 0,
            benchmark.market_sales_proxy ?? 0,
            benchmark.benchmark_ratio ?? 0,
          ],
        },
        risk_chart: {
          type: 'pie',
          title: '趋势风险拆解',
          items: [
            { name: '供需比', value: ratio.demand_supply_ratio ?? 0 },
            { name: '供给量', value: ratio.supply_count ?? 0 },
            { name: '销量缺口', value: Math.abs(benchmark.growth_gap_percent ?? 0) },
          ],
        },
        competitor_chart: {
          type: 'ranking',
          title: '论坛热点榜单',
          items: (topics.topics ?? []).map((item) => ({ name: item.topic ?? '-', value: item.heat ?? 0 })),
        },
        execution_chart: {
          type: 'progress',
          title: '趋势执行优先级',
          items: [
            { name: '热度增长', value: Math.min(Math.max(aggregate.growth?.growth_7d_vs_30d ?? 0, 0), 100) },
            { name: '供需机会', value: Math.min(Math.max((ratio.demand_supply_ratio ?? 0) * 10, 0), 100) },
            { name: '榜单热度', value: Math.min(topics.topics?.[0]?.heat ?? 0, 100) },
          ],
        },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : '趋势榜单加载失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>趋势榜单</h1>
          <p className="muted">覆盖 B13-19：聚合趋势热度、供需比、销量基准、论坛热词、生命周期阶段与 RSS 新闻热点。</p>
          <div className="nav">
            <Link href="/competitors">竞品监控</Link>
            <Link href="/kpi">管理者 KPI</Link>
            <Link href="/dashboard">利润中枢</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}

        <div className="card">
          <h2>榜单查询</h2>
          <div className="form-grid">
            <input className="input" value={form.query} onChange={(e) => setForm((s) => ({ ...s, query: e.target.value }))} placeholder="关键词" />
            <input className="input" value={form.category} onChange={(e) => setForm((s) => ({ ...s, category: e.target.value }))} placeholder="类目" />
            <input className="input" value={form.target_market} onChange={(e) => setForm((s) => ({ ...s, target_market: e.target.value }))} placeholder="市场" />
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void load()}>{loading ? '加载中...' : '刷新榜单'}</button>
          </div>
        </div>

        <div className="grid grid-4">
          <div className="metric-card">
            <div className="metric-label">7d vs 30d</div>
            <div className="metric-value">{snapshot?.aggregate?.growth?.growth_7d_vs_30d ?? 0}</div>
            <div className="metric-hint">近 7 天相对 30 天增速</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">供需比</div>
            <div className="metric-value">{snapshot?.ratio?.demand_supply_ratio ?? 0}</div>
            <div className="metric-hint">越高越值得关注</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">生命周期</div>
            <div className="metric-value">{snapshot?.lifecycle?.lifecycle_stage ?? '-'}</div>
            <div className="metric-hint">当前市场阶段</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">热词数量</div>
            <div className="metric-value">{snapshot?.topics?.topic_count ?? 0}</div>
            <div className="metric-hint">论坛/内容热点主题</div>
          </div>
        </div>

        <DashboardCharts charts={charts} />

        <div className="card">
          <h2>RSS 新闻热点</h2>
          <div className="muted" style={{ marginBottom: 12 }}>
            source={snapshot?.rss?.source ?? '-'} / total={snapshot?.rss?.total_count ?? 0}
          </div>
          <div className="plain-list">
            {(snapshot?.rss?.top_articles ?? []).length ? (
              (snapshot?.rss?.top_articles ?? []).map((item, index) => (
                <div key={`${item.url ?? item.title ?? 'rss'}-${index}`} className="plain-row">
                  <div>
                    <strong>{item.title ?? '-'}</strong>
                    <p>{item.source ?? '-'} / {item.pub_date ?? '-'}</p>
                  </div>
                  <div className="plain-meta">
                    <span>{item.url ?? '-'}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="list-card">暂无 RSS 热点，请先刷新榜单。</div>
            )}
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
