'use client'

import { useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

type ChangeSignal = {
  type?: string
  severity?: string
  description?: string
  metric?: { delta?: number; unit?: string }
}

type CompetitorProfile = {
  competitor_name?: string
  name?: string
  price?: number
  rating?: number
  rank?: number
  strengths?: string[]
}

type MonitorResponse = {
  product_name?: string
  category?: string
  target_market?: string
  monitoring?: {
    enabled?: boolean
    schedule?: string
    watch_fields?: string[]
    competitor_count?: number
  }
  price_comparison?: {
    average_competitor_price?: number
    profiles?: CompetitorProfile[]
  }
  change_signals?: ChangeSignal[]
  auto_report?: {
    summary?: string
    top_alerts?: ChangeSignal[]
    recommended_actions?: string[]
  }
  alerts?: {
    enabled?: boolean
    channel?: string
    count?: number
    items?: ChangeSignal[]
  }
  monitor_job?: {
    job_type?: string
    schedule?: string
    trigger_mode?: string
    executed?: boolean
  }
  notification?: {
    channel?: string
    delivered?: boolean
    delivery_result?: Record<string, unknown> | null
  }
}

function severityClass(severity?: string): string {
  if (severity === 'high') return 'status-pill status-pill-danger'
  if (severity === 'medium') return 'status-pill status-pill-warn'
  return 'status-pill status-pill-good'
}

export default function CompetitorsPage() {
  const [form, setForm] = useState({
    product_name: '蓝牙耳机',
    category: 'electronics',
    target_market: 'US',
    schedule: 'daily',
    alert_channel: 'in_app',
    webhook_url: '',
  })
  const [result, setResult] = useState<MonitorResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const runAnalyze = async (runMonitor: boolean) => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const path = runMonitor ? '/competitors/monitor/run' : '/competitors/analyze'
      const data = await apiFetch<MonitorResponse>(path, {
        method: 'POST',
        body: JSON.stringify({
          product_name: form.product_name,
          category: form.category,
          target_market: form.target_market,
          monitor_config: {
            schedule: form.schedule,
            alert_channel: form.alert_channel,
            webhook_url: form.webhook_url || undefined,
            watch_fields: ['price', 'rating', 'rank'],
            trigger_mode: runMonitor ? 'manual' : 'preview',
          },
        }),
      })
      setResult(data)
      setMessage(runMonitor ? '已执行竞品监控任务并生成预警摘要。' : '已完成竞品分析预览。')
    } catch (e) {
      setError(e instanceof Error ? e.message : '竞品监控执行失败')
    } finally {
      setLoading(false)
    }
  }

  const alertItems = result?.alerts?.items ?? []
  const profiles = result?.price_comparison?.profiles ?? []

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>竞品监控配置与预警通知</h1>
          <p className="muted">覆盖 B13-17 / B13-18：配置监控策略、执行监控任务、查看预警与自动报告。</p>
          <div className="nav">
            <Link href="/trends">趋势榜单</Link>
            <Link href="/kpi">管理者 KPI</Link>
            <Link href="/dashboard">利润中枢</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="grid grid-2">
          <div className="card">
            <h2>监控配置</h2>
            <div className="form-grid">
              <input className="input" value={form.product_name} onChange={(e) => setForm((s) => ({ ...s, product_name: e.target.value }))} placeholder="商品名" />
              <input className="input" value={form.category} onChange={(e) => setForm((s) => ({ ...s, category: e.target.value }))} placeholder="类目" />
              <input className="input" value={form.target_market} onChange={(e) => setForm((s) => ({ ...s, target_market: e.target.value }))} placeholder="目标市场" />
              <select className="select" value={form.schedule} onChange={(e) => setForm((s) => ({ ...s, schedule: e.target.value }))}>
                <option value="hourly">hourly</option>
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
              </select>
              <select className="select" value={form.alert_channel} onChange={(e) => setForm((s) => ({ ...s, alert_channel: e.target.value }))}>
                <option value="in_app">in_app</option>
                <option value="email">email</option>
                <option value="dingtalk">dingtalk</option>
              </select>
              <input className="input" value={form.webhook_url} onChange={(e) => setForm((s) => ({ ...s, webhook_url: e.target.value }))} placeholder="Webhook URL（钉钉时可填）" />
            </div>
            <div className="action-row">
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void runAnalyze(false)}>预览分析</button>
              <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void runAnalyze(true)}>{loading ? '执行中...' : '执行监控'}</button>
            </div>
            <p className="panel-note">默认监控字段：价格、评分、排名。执行监控后会返回预警摘要、通知投递结果和建议动作。</p>
          </div>

          <div className="card">
            <h2>监控摘要</h2>
            <div className="grid grid-2">
              <div className="metric-card">
                <div className="metric-label">监控周期</div>
                <div className="metric-value">{result?.monitoring?.schedule ?? '-'}</div>
                <div className="metric-hint">任务调度频率</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">竞品数量</div>
                <div className="metric-value">{result?.monitoring?.competitor_count ?? 0}</div>
                <div className="metric-hint">纳入监控的竞品数</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">预警数量</div>
                <div className="metric-value">{result?.alerts?.count ?? 0}</div>
                <div className="metric-hint">中高等级变化信号</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">通知通道</div>
                <div className="metric-value">{result?.notification?.channel ?? result?.alerts?.channel ?? '-'}</div>
                <div className="metric-hint">delivered={String(result?.notification?.delivered ?? false)}</div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>预警通知面板</h2>
            {alertItems.length ? (
              <div className="plain-list">
                {alertItems.map((item, index) => (
                  <div key={`${item.type ?? 'alert'}-${index}`} className="plain-row">
                    <div>
                      <strong>{item.type ?? 'signal'}</strong>
                      <p>{item.description ?? '无描述'}</p>
                    </div>
                    <div className="plain-meta">
                      <span className={severityClass(item.severity)}>{item.severity ?? 'low'}</span>
                      <span>{item.metric?.delta ?? '-'} {item.metric?.unit ?? ''}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="list-card">暂无预警，先执行一次监控。</div>
            )}
          </div>

          <div className="card">
            <h2>自动报告与建议动作</h2>
            <div><strong>摘要：</strong>{result?.auto_report?.summary ?? '-'}</div>
            <div style={{ marginTop: 12 }}><strong>推荐动作：</strong></div>
            <ul>
              {(result?.auto_report?.recommended_actions ?? []).map((item) => <li key={item}>{item}</li>)}
            </ul>
            <div style={{ marginTop: 12 }}><strong>作业信息：</strong></div>
            <pre className="code-panel">{JSON.stringify(result?.monitor_job ?? {}, null, 2)}</pre>
          </div>
        </div>

        <div className="card">
          <h2>竞品画像与价格对比</h2>
          <div className="muted" style={{ marginBottom: 12 }}>平均竞品价格：{result?.price_comparison?.average_competitor_price ?? 0}</div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>竞品</th>
                  <th>价格</th>
                  <th>评分</th>
                  <th>排名</th>
                  <th>优势</th>
                </tr>
              </thead>
              <tbody>
                {profiles.length ? profiles.map((item, index) => (
                  <tr key={`${item.competitor_name ?? item.name ?? 'profile'}-${index}`}>
                    <td>{item.competitor_name ?? item.name ?? '-'}</td>
                    <td>{item.price ?? '-'}</td>
                    <td>{item.rating ?? '-'}</td>
                    <td>{item.rank ?? '-'}</td>
                    <td>{(item.strengths ?? []).join(' / ') || '-'}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5}>暂无竞品画像数据</td>
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
