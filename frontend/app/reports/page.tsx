'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { API_BASE, apiFetch } from '@/lib/api'
import { getToken } from '@/lib/auth'

type ReportItem = {
  report_id: string
  report_type: string
  title: string
  summary?: string
  format?: string
  created_at?: string
  generated_at?: string
  download_url: string
  download_format?: string
  archived?: boolean
  shared?: boolean
  audit_flags?: string[]
}

type ReportListResponse = {
  total: number
  items: ReportItem[]
  filters?: {
    report_type?: string | null
    created_after?: string | null
    created_before?: string | null
  }
  summary?: {
    report_count?: number
    total_gmv?: number
    avg_completion_rate?: number
    latest_generated_at?: string | null
    data_source?: string
  }
}

type ShareResult = {
  share_token: string
  share_url: string
  report_id: string
  expires_at: string
}

const REPORT_TYPES = ['daily', 'weekly', 'monthly'] as const
const REPORT_FORMATS = ['pdf', 'xlsx', 'ppt', 'html'] as const

export default function ReportsPage() {
  const [reportType, setReportType] = useState<(typeof REPORT_TYPES)[number]>('weekly')
  const [format, setFormat] = useState<(typeof REPORT_FORMATS)[number]>('pdf')
  const [reports, setReports] = useState<ReportItem[]>([])
  const [selected, setSelected] = useState<ReportItem | null>(null)
  const [reportSummary, setReportSummary] = useState<ReportListResponse['summary'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [shareResult, setShareResult] = useState<ShareResult | null>(null)
  const [loading, setLoading] = useState(false)

  const loadReports = useCallback(async (preferredReportId?: string) => {
    try {
      setError(null)
      const data = await apiFetch<ReportListResponse>(`/reports?report_type=${reportType}`)
      setReports(data.items ?? [])
      setReportSummary(data.summary ?? null)
      setSelected((current) => {
        if (preferredReportId) {
          return data.items?.find((item) => item.report_id === preferredReportId) ?? data.items?.[0] ?? null
        }
        if (!current) return data.items?.[0] ?? null
        return data.items?.find((item) => item.report_id === current.report_id) ?? data.items?.[0] ?? null
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : '报告中心加载失败')
    }
  }, [reportType])

  useEffect(() => {
    void loadReports()
  }, [loadReports])

  const generateReport = async () => {
    setLoading(true)
    setMessage(null)
    try {
      const generated = await apiFetch<ReportItem>(`/reports/generate?report_type=${reportType}&format=${format}` , {
        method: 'POST',
      })
      setMessage('报告已生成')
      await loadReports(generated.report_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  const downloadReport = async (report: ReportItem) => {
    const token = getToken()
    const response = await fetch(`${API_BASE}/reports/${report.report_id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload?.detail || '下载失败')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.report_id}.${report.download_format ?? 'html'}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const createShare = async (report: ReportItem) => {
    setLoading(true)
    setMessage(null)
    try {
      const data = await apiFetch<ShareResult>(`/reports/${report.report_id}/share`, {
        method: 'POST',
        body: JSON.stringify({ expires_in_hours: 24 }),
      })
      setShareResult(data)
      setMessage(`分享链接已创建：${data.share_token}`)
      await loadReports()
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建分享失败')
    } finally {
      setLoading(false)
    }
  }

  const archiveReport = async (report: ReportItem) => {
    setLoading(true)
    setMessage(null)
    try {
      await apiFetch(`/reports/${report.report_id}`, {
        method: 'DELETE',
      })
      setMessage(`报告 ${report.report_id} 已归档`)
      await loadReports()
    } catch (e) {
      setError(e instanceof Error ? e.message : '归档失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container">
        <div className="card">
          <h1>报告中心</h1>
          <p className="muted">支持查看、下载、分享、归档的正式报告入口。</p>
          <div className="nav">
            <Link href="/workbench/selection">选品工作台</Link>
            <Link href="/dashboard">数据大盘</Link>
            <Link href="/agents">Agent 平台</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}

        <div className="grid grid-4" style={{ marginBottom: 16 }}>
          <div className="metric-card">
            <div className="metric-label">报告数</div>
            <div className="metric-value">{reportSummary?.report_count ?? reports.length}</div>
            <div className="metric-hint">当前筛选结果</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">总 GMV</div>
            <div className="metric-value">{reportSummary?.total_gmv?.toLocaleString?.('zh-CN') ?? 0}</div>
            <div className="metric-hint">来自报告指标汇总</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">平均完成率</div>
            <div className="metric-value">{`${(((reportSummary?.avg_completion_rate ?? 0) as number) * 100).toFixed(1)}%`}</div>
            <div className="metric-hint">经营任务整体完成情况</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">数据来源</div>
            <div className="metric-value">{reportSummary?.data_source ?? 'report_center_state'}</div>
            <div className="metric-hint">最近生成：{reportSummary?.latest_generated_at ?? '-'}</div>
          </div>
        </div>

        <div className="card">
          <h2>生成报告</h2>
          <div className="grid grid-2">
            <select className="select" value={reportType} onChange={(event) => setReportType(event.target.value as (typeof REPORT_TYPES)[number])}>
              {REPORT_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="select" value={format} onChange={(event) => setFormat(event.target.value as (typeof REPORT_FORMATS)[number])}>
              {REPORT_FORMATS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <div className="action-row">
            <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void generateReport()}>生成报告</button>
            <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void loadReports()}>刷新列表</button>
          </div>
          {message ? <p className="muted">{message}</p> : null}
          {shareResult ? <pre className="code-panel">{JSON.stringify(shareResult, null, 2)}</pre> : null}
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>报告列表</h2>
            <div className="inline-form">
              {reports.length ? reports.map((item) => (
                <button
                  key={item.report_id}
                  type="button"
                  className="list-card"
                  style={{ textAlign: 'left', cursor: 'pointer', borderColor: selected?.report_id === item.report_id ? '#2563eb' : '#e5e7eb' }}
                  onClick={() => setSelected(item)}
                >
                  <div><strong>{item.title}</strong></div>
                  <div className="muted">{item.report_id} / {item.report_type} / {item.download_format ?? item.format ?? '-'}</div>
                  <div className="muted">shared={String(item.shared ?? false)} / archived={String(item.archived ?? false)}</div>
                </button>
              )) : <div className="list-card">当前类型暂无报告，请先生成。</div>}
            </div>
          </div>

          <div className="card">
            <h2>报告详情</h2>
            {selected ? (
              <>
                <div><strong>标题：</strong>{selected.title}</div>
                <div><strong>报告ID：</strong>{selected.report_id}</div>
                <div><strong>类型：</strong>{selected.report_type}</div>
                <div><strong>格式：</strong>{selected.download_format ?? selected.format ?? '-'}</div>
                <div><strong>生成时间：</strong>{selected.generated_at ?? selected.created_at ?? '-'}</div>
                <div><strong>审计标记：</strong>{(selected.audit_flags ?? []).join(', ') || '-'}</div>
                <p className="muted" style={{ marginTop: 12 }}>{selected.summary ?? '暂无摘要'}</p>
                <div className="action-row">
                  <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void downloadReport(selected)}>下载</button>
                  <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void createShare(selected)}>分享</button>
                  <button className="btn btn-danger" type="button" disabled={loading || selected.archived} onClick={() => void archiveReport(selected)}>归档</button>
                </div>
              </>
            ) : (
              <div className="list-card">请选择一个报告查看详情。</div>
            )}
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
