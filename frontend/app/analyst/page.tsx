'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { DashboardCharts } from '@/components/common/DashboardCharts'
import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { API_BASE, apiFetch } from '@/lib/api'
import { getToken } from '@/lib/auth'

type AccuracyTrendResponse = {
  total_tasks?: number
  correct_tasks?: number
  accuracy?: number
  trend?: Array<{ date: string; total?: number; correct?: number; accuracy?: number; cumulative_accuracy?: number }>
}

type KnowledgeQueryResponse = {
  query?: string
  total_found?: number
  results?: Array<{ content?: string; source?: string; score?: number; document_id?: string }>
}

type EvalResponse = {
  total_cases?: number
  hit_at_k?: number
  mrr?: number
  citation_match_rate?: number
  avg_score?: number
}

type DashboardChart = {
  type?: string
  title?: string
  xAxis?: string[]
  series?: number[]
  items?: Array<{ name: string; value: number }>
}

type LocalLabel = {
  id: string
  source: string
  label: string
  note: string
}

type ReportTemplate = {
  name: string
  display_name: string
  description?: string
  default_report_type?: string
  default_sections?: string[]
  default_metrics?: string[]
  default_chart_keys?: string[]
}

type ReportMetric = {
  key: string
  label: string
}

type ReportTemplateResponse = {
  templates: ReportTemplate[]
  metric_catalog: ReportMetric[]
  chart_catalog: Array<{ key: string; label: string }>
}

type GeneratedReport = {
  report_id: string
  title: string
  summary?: string
  download_url: string
  download_format?: string
  metadata?: Record<string, unknown>
  metrics?: Record<string, unknown>
}

const REPORT_FORMATS = ['html', 'pdf', 'xlsx', 'ppt'] as const

export default function AnalystPage() {
  const [query, setQuery] = useState('蓝牙耳机')
  const [historyCases, setHistoryCases] = useState<KnowledgeQueryResponse | null>(null)
  const [reviewCases, setReviewCases] = useState<KnowledgeQueryResponse | null>(null)
  const [accuracy, setAccuracy] = useState<AccuracyTrendResponse | null>(null)
  const [evaluation, setEvaluation] = useState<EvalResponse | null>(null)
  const [labels, setLabels] = useState<LocalLabel[]>([])
  const [templates, setTemplates] = useState<ReportTemplate[]>([])
  const [metricCatalog, setMetricCatalog] = useState<ReportMetric[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState('market_insight')
  const [reportType, setReportType] = useState('weekly')
  const [reportFormat, setReportFormat] = useState<(typeof REPORT_FORMATS)[number]>('pdf')
  const [reportTitle, setReportTitle] = useState('蓝牙耳机分析师洞察报告')
  const [reportSummary, setReportSummary] = useState('聚焦趋势变化、竞品动态与机会判断')
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(['gmv', 'conversion_rate', 'opportunities'])
  const [generatedReport, setGeneratedReport] = useState<GeneratedReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const [accuracyData, historyData, reviewData, evalData, templateData] = await Promise.all([
        apiFetch<AccuracyTrendResponse>('/selection/accuracy-trend?limit=100'),
        apiFetch<KnowledgeQueryResponse>('/knowledge/selection-cases/query', {
          method: 'POST',
          body: JSON.stringify({ query, top_k: 5, threshold: 0.1 }),
        }),
        apiFetch<KnowledgeQueryResponse>('/knowledge/review-cases/query', {
          method: 'POST',
          body: JSON.stringify({ query, top_k: 5, threshold: 0.1 }),
        }),
        apiFetch<EvalResponse>('/knowledge/evaluate', {
          method: 'POST',
          body: JSON.stringify({ cases: [{ query, expected_keywords: query.split(/\s+/).filter(Boolean), top_k: 5, threshold: 0.1 }] }),
        }),
        apiFetch<ReportTemplateResponse>('/reports/templates'),
      ])
      setAccuracy(accuracyData)
      setHistoryCases(historyData)
      setReviewCases(reviewData)
      setEvaluation(evalData)
      setTemplates(templateData.templates ?? [])
      setMetricCatalog(templateData.metric_catalog ?? [])
      setMessage('分析师工作台数据已刷新。')
    } catch (e) {
      setError(e instanceof Error ? e.message : '分析师工作台加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    const template = templates.find((item) => item.name === selectedTemplate)
    if (!template) return
    if (template.default_report_type) {
      setReportType(template.default_report_type)
    }
    if ((template.default_metrics ?? []).length > 0) {
      setSelectedMetrics(template.default_metrics ?? [])
    }
  }, [selectedTemplate, templates])

  const addLabel = (source: string, label: string) => {
    setLabels((items) => [...items, { id: `${source}-${items.length + 1}`, source, label, note: query }])
    setMessage(`已标注：${source} -> ${label}`)
  }

  const exportLabels = () => {
    const blob = new Blob([`${JSON.stringify({ query, labels }, null, 2)}\n`], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'analyst-feedback-labels.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setMessage('已导出标注结果 analyst-feedback-labels.json')
  }

  const generateCustomReport = async () => {
    try {
      setLoading(true)
      const result = await apiFetch<GeneratedReport>(`/reports/generate?report_type=${reportType}&format=${reportFormat}&task_id=analyst-${encodeURIComponent(query)}`, {
        method: 'POST',
        body: JSON.stringify({
          template_name: selectedTemplate,
          title: reportTitle,
          summary: reportSummary,
          sections: ['趋势变化', '竞品动态', '行动建议'],
          metrics_filter: selectedMetrics,
          chart_keys: ['sales_trend'],
          params: {
            gmv: historyCases?.total_found ?? 0,
            conversion_rate: evaluation?.avg_score ?? 0,
            opportunities: reviewCases?.total_found ?? 0,
            accuracy: accuracy?.accuracy ?? 0,
          },
        }),
      })
      setGeneratedReport(result)
      setMessage(`已生成定制报告：${result.report_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成定制报告失败')
    } finally {
      setLoading(false)
    }
  }

  const downloadGeneratedReport = async () => {
    if (!generatedReport) return
    const token = getToken()
    const response = await fetch(`${API_BASE}/reports/${generatedReport.report_id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload?.message || payload?.detail || '下载失败')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${generatedReport.report_id}.${generatedReport.download_format ?? 'html'}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setMessage(`已下载定制报告 ${generatedReport.report_id}`)
  }

  const toggleMetric = (metricKey: string) => {
    setSelectedMetrics((current) => current.includes(metricKey) ? current.filter((item) => item !== metricKey) : [...current, metricKey])
  }

  const trendPoints = accuracy?.trend ?? []
  const charts: Record<string, DashboardChart | undefined> = {
    trend_chart: {
      type: 'line',
      title: '选品准确率趋势',
      xAxis: trendPoints.map((item) => item.date),
      series: trendPoints.map((item) => Number((item.accuracy ?? 0) * 100)),
    },
    profit_chart: {
      type: 'bar',
      title: '评测指标',
      xAxis: ['hit@k', 'mrr', 'citation', 'avg_score'],
      series: [
        Number(evaluation?.hit_at_k ?? 0),
        Number(evaluation?.mrr ?? 0),
        Number(evaluation?.citation_match_rate ?? 0),
        Number(evaluation?.avg_score ?? 0),
      ],
    },
    competitor_chart: {
      type: 'ranking',
      title: '评价案例命中榜',
      items: (reviewCases?.results ?? []).map((item, index) => ({ name: item.source ?? item.document_id ?? `review-${index + 1}`, value: Number(item.score ?? 0) * 100 })),
    },
  }

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>分析师工作台</h1>
          <p className="muted">覆盖数据探索、趋势分析、报告定制、案例评测与标注导出。</p>
          <div className="nav">
            <Link href="/models">模型调优</Link>
            <Link href="/agents">Agent 平台</Link>
            <Link href="/knowledge">知识库工作台</Link>
            <Link href="/reports">报告中心</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="card">
          <h2>分析查询</h2>
          <div className="form-grid">
            <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入分析关键词" />
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void load()}>{loading ? '加载中...' : '刷新分析'}</button>
            <button className="btn btn-secondary" type="button" disabled={!labels.length} onClick={exportLabels}>导出标注</button>
          </div>
        </div>

        <div className="grid grid-4">
          <div className="metric-card">
            <div className="metric-label">总任务数</div>
            <div className="metric-value">{accuracy?.total_tasks ?? 0}</div>
            <div className="metric-hint">已纳入准确率趋势统计</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">准确率</div>
            <div className="metric-value">{accuracy?.accuracy != null ? `${(accuracy.accuracy * 100).toFixed(1)}%` : '-'}</div>
            <div className="metric-hint">预测决策 vs 执行反馈</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">历史案例命中</div>
            <div className="metric-value">{historyCases?.total_found ?? 0}</div>
            <div className="metric-hint">selection-cases query</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">评价案例命中</div>
            <div className="metric-value">{reviewCases?.total_found ?? 0}</div>
            <div className="metric-hint">review-cases query</div>
          </div>
        </div>

        <DashboardCharts charts={charts} />

        <div className="card">
          <h2>报告定制</h2>
          <p className="muted">自定义报告模板和指标，直接走正式报告中心生成与下载链路。</p>
          <div className="grid grid-2">
            <select className="select" value={selectedTemplate} onChange={(e) => setSelectedTemplate(e.target.value)}>
              {templates.map((item) => <option key={item.name} value={item.name}>{item.display_name}</option>)}
            </select>
            <select className="select" value={reportFormat} onChange={(e) => setReportFormat(e.target.value as (typeof REPORT_FORMATS)[number])}>
              {REPORT_FORMATS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <div className="inline-form">
            <input className="input" value={reportTitle} onChange={(e) => setReportTitle(e.target.value)} placeholder="自定义报告标题" />
            <textarea className="textarea" value={reportSummary} onChange={(e) => setReportSummary(e.target.value)} placeholder="自定义报告摘要" rows={3} />
          </div>
          <div className="card" style={{ padding: 16, marginTop: 12 }}>
            <strong>可选指标</strong>
            <div className="action-row">
              {metricCatalog.map((item) => (
                <button
                  key={item.key}
                  className={`btn ${selectedMetrics.includes(item.key) ? 'btn-primary' : 'btn-secondary'}`}
                  type="button"
                  onClick={() => toggleMetric(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading || selectedMetrics.length === 0} onClick={() => void generateCustomReport()}>生成定制报告</button>
            <button className="btn btn-secondary" type="button" disabled={!generatedReport} onClick={() => void downloadGeneratedReport()}>下载定制报告</button>
          </div>
          {generatedReport ? <pre className="code-panel">{JSON.stringify(generatedReport, null, 2)}</pre> : null}
        </div>

        <div className="card">
          <h2>报告蓝图预览</h2>
          <pre className="code-panel">{JSON.stringify({
            query,
            selectedTemplate,
            reportType,
            reportFormat,
            reportTitle,
            reportSummary,
            selectedMetrics,
          }, null, 2)}</pre>
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>历史案例标注</h2>
            <div className="inline-form">
              {(historyCases?.results ?? []).length ? (historyCases?.results ?? []).map((item, index) => (
                <div key={`${item.document_id ?? 'history'}-${index}`} className="list-card">
                  <div><strong>{item.source ?? item.document_id ?? '-'}</strong></div>
                  <div className="muted">score={item.score ?? '-'}</div>
                  <div className="muted">{item.content?.slice(0, 120) ?? '-'}</div>
                  <div className="action-row">
                    <button className="btn btn-secondary" type="button" onClick={() => addLabel(item.source ?? `history-${index}`, 'high_value')}>标注高价值</button>
                    <button className="btn btn-secondary" type="button" onClick={() => addLabel(item.source ?? `history-${index}`, 'needs_review')}>标注待复核</button>
                  </div>
                </div>
              )) : <div className="list-card">暂无历史案例检索结果</div>}
            </div>
          </div>

          <div className="card">
            <h2>评价反馈标注</h2>
            <div className="inline-form">
              {(reviewCases?.results ?? []).length ? (reviewCases?.results ?? []).map((item, index) => (
                <div key={`${item.document_id ?? 'review'}-${index}`} className="list-card">
                  <div><strong>{item.source ?? item.document_id ?? '-'}</strong></div>
                  <div className="muted">score={item.score ?? '-'}</div>
                  <div className="muted">{item.content?.slice(0, 120) ?? '-'}</div>
                  <div className="action-row">
                    <button className="btn btn-secondary" type="button" onClick={() => addLabel(item.source ?? `review-${index}`, 'positive_signal')}>标注正向信号</button>
                    <button className="btn btn-secondary" type="button" onClick={() => addLabel(item.source ?? `review-${index}`, 'risk_signal')}>标注风险信号</button>
                  </div>
                </div>
              )) : <div className="list-card">暂无评价案例检索结果</div>}
            </div>
          </div>
        </div>

        <div className="card">
          <h2>本地标注结果</h2>
          <pre className="code-panel">{JSON.stringify(labels, null, 2)}</pre>
        </div>
      </main>
    </AuthGuard>
  )
}
