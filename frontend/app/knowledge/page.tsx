'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { API_BASE, apiFetch } from '@/lib/api'
import { getToken } from '@/lib/auth'

type KnowledgeStats = {
  total_documents?: number
  indexed_documents?: number
  total_chunks?: number
  total_size_mb?: number
  average_chunks_per_doc?: number
}

type KnowledgeHealth = {
  total_documents?: number
  indexed_documents?: number
  index_coverage?: number
}

type RetrievalQuality = {
  status?: string
  metrics?: string[]
  artifact_path?: string
  default_evaluation?: {
    total_cases?: number
    hit_at_k?: number
    mrr?: number
    citation_match_rate?: number
  }
}

type FeedbackLearning = {
  feedback_case_count?: number
  static_baseline_case_count?: number
  combined_baseline_case_count?: number
  latest_updated_at?: string | null
  artifact_path?: string
  coverage_ratio?: number
}

type QualityDashboard = {
  knowledge_health?: KnowledgeHealth
  retrieval_quality?: RetrievalQuality
  feedback_learning?: FeedbackLearning
}

type SearchBackendStatus = {
  backend?: string
  effective_mode?: string
  fallback_mode?: string
  provider?: string
  configured?: boolean
}

type KnowledgeServiceModeStatus = {
  mode?: string
  fallback_enabled?: boolean
  gateway?: {
    mode?: string
    [key: string]: unknown
  }
}

type KnowledgeDocument = {
  doc_id: string
  filename: string
  file_size?: number
  chunk_count?: number
  status: string
  uploaded_at?: string
  content_preview?: string
  vector_status?: string
  provider_mode?: string
  status_reason?: string
  version?: number
  index_version?: number
  is_current_version?: boolean
  previous_document_id?: string | null
}

type KnowledgeDocumentDetail = KnowledgeDocument & {
  chunks?: Array<{
    chunk_index: number
    content: string
    vector_id?: string | null
    metadata?: Record<string, unknown>
  }>
}

type KnowledgeDocumentListResponse = {
  total: number
  documents: KnowledgeDocument[]
}

type KnowledgeDocumentVersionsResponse = {
  document_key?: string
  total?: number
  versions: KnowledgeDocument[]
}

type KnowledgeQueryResponse = {
  query: string
  total_found: number
  processing_time_ms: number
  results: Array<{
    content: string
    score: number
    source?: string
    document_id?: string
    chunk_index?: number
    ranking_stage?: string
    ranking_meta?: Record<string, unknown>
  }>
}

type KnowledgeEvaluateResponse = {
  total_cases?: number
  hit_at_k?: number
  mrr?: number
  citation_match_rate?: number
  avg_score?: number
  cases?: Array<Record<string, unknown>>
}

type UploadResult = {
  doc_id: string
  filename: string
  status: string
  message: string
  chunk_count?: number
  provider_mode?: string
  vector_status?: string
}

type RollbackResult = {
  doc_id: string
  version?: number
  status: string
  message: string
}

function formatSize(sizeMb?: number, bytes?: number): string {
  if (typeof sizeMb === 'number') {
    return `${sizeMb.toFixed(2)} MB`
  }
  if (typeof bytes === 'number') {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }
  return '-'
}

function buildStatusBadge(active?: boolean | null) {
  if (active === true) return { label: '通过', color: '#166534', bg: '#dcfce7' }
  if (active === false) return { label: '异常', color: '#991b1b', bg: '#fee2e2' }
  return { label: '未执行', color: '#374151', bg: '#e5e7eb' }
}

async function uploadKnowledgeFile(file: File): Promise<UploadResult> {
  const token = getToken()
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE}/knowledge/documents`, {
    method: 'POST',
    body: formData,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: 'no-store',
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload?.message || payload?.detail || '上传失败')
  }
  return (payload?.data ?? payload) as UploadResult
}

export default function KnowledgePage() {
  const [stats, setStats] = useState<KnowledgeStats | null>(null)
  const [quality, setQuality] = useState<QualityDashboard | null>(null)
  const [searchStatus, setSearchStatus] = useState<SearchBackendStatus | null>(null)
  const [serviceMode, setServiceMode] = useState<KnowledgeServiceModeStatus | null>(null)
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [selectedDocId, setSelectedDocId] = useState('')
  const [detail, setDetail] = useState<KnowledgeDocumentDetail | null>(null)
  const [versions, setVersions] = useState<KnowledgeDocument[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [query, setQuery] = useState('蓝牙耳机')
  const [queryResult, setQueryResult] = useState<KnowledgeQueryResponse | null>(null)
  const [evalKeywords, setEvalKeywords] = useState('蓝牙耳机,跨境电商')
  const [evalResult, setEvalResult] = useState<KnowledgeEvaluateResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const feedbackBadge = buildStatusBadge((quality?.feedback_learning?.feedback_case_count ?? 0) > 0)

  const fetchDocuments = useCallback(async () => {
    const suffix = statusFilter ? `?status=${encodeURIComponent(statusFilter)}&limit=20&offset=0` : '?limit=20&offset=0'
    const data = await apiFetch<KnowledgeDocumentListResponse>(`/knowledge/documents${suffix}`)
    const items = data.documents ?? []
    setDocuments(items)
    setSelectedDocId((current) => {
      if (current && items.some((item) => item.doc_id === current)) {
        return current
      }
      return items[0]?.doc_id ?? ''
    })
    return data
  }, [statusFilter])

  const loadOverview = useCallback(async () => {
    setError(null)
    try {
      await fetchDocuments()
    } catch (e) {
      setError(e instanceof Error ? e.message : '文档列表加载失败')
    }

    const [statsResult, qualityResult, searchResult, serviceModeResult] = await Promise.allSettled([
      apiFetch<KnowledgeStats>('/knowledge/stats'),
      apiFetch<QualityDashboard>('/knowledge/quality-dashboard'),
      apiFetch<SearchBackendStatus>('/knowledge/search-backend/status'),
      apiFetch<KnowledgeServiceModeStatus>('/knowledge/service-mode'),
    ])

    if (statsResult.status === 'fulfilled') {
      setStats(statsResult.value)
    }
    if (qualityResult.status === 'fulfilled') {
      setQuality(qualityResult.value)
    }
    if (searchResult.status === 'fulfilled') {
      setSearchStatus(searchResult.value)
    }
    if (serviceModeResult.status === 'fulfilled') {
      setServiceMode(serviceModeResult.value)
    }
  }, [fetchDocuments])

  const loadDocumentContext = useCallback(async (docId: string) => {
    if (!docId) {
      setDetail(null)
      setVersions([])
      return
    }
    try {
      const [detailData, versionData] = await Promise.all([
        apiFetch<KnowledgeDocumentDetail>(`/knowledge/documents/${docId}`),
        apiFetch<KnowledgeDocumentVersionsResponse>(`/knowledge/documents/${docId}/versions`),
      ])
      setDetail(detailData)
      setVersions(versionData.versions ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '文档详情加载失败')
    }
  }, [])

  useEffect(() => {
    void loadOverview()
  }, [loadOverview])

  useEffect(() => {
    void loadDocumentContext(selectedDocId)
  }, [selectedDocId, loadDocumentContext])

  const handleUpload = async () => {
    if (!uploadFile) {
      setMessage('请先选择一个 .txt / .md / .csv 文件')
      return
    }
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const result = await uploadKnowledgeFile(uploadFile)
      setMessage(`${result.message}（${result.filename}）`)
      await loadOverview()
      setSelectedDocId(result.doc_id)
      setUploadFile(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传失败')
    } finally {
      setLoading(false)
    }
  }

  const handleQuery = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const result = await apiFetch<KnowledgeQueryResponse>('/knowledge/query', {
        method: 'POST',
        body: JSON.stringify({ query, top_k: 5, threshold: 0.1 }),
      })
      setQueryResult(result)
      setMessage(`检索完成：命中 ${result.total_found} 条，耗时 ${result.processing_time_ms} ms`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '检索失败')
    } finally {
      setLoading(false)
    }
  }

  const handleEvaluate = async () => {
    const expectedKeywords = evalKeywords
      .split(/[，,\n]/)
      .map((item) => item.trim())
      .filter(Boolean)

    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const result = await apiFetch<KnowledgeEvaluateResponse>('/knowledge/evaluate', {
        method: 'POST',
        body: JSON.stringify({
          cases: [
            {
              query,
              expected_document_ids: detail?.doc_id ? [detail.doc_id] : [],
              expected_keywords: expectedKeywords,
              top_k: 5,
              threshold: 0.1,
            },
          ],
        }),
      })
      setEvalResult(result)
      setMessage(`评测完成：hit@k=${result.hit_at_k ?? '-'} / mrr=${result.mrr ?? '-'}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '评测失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRollback = async (docId: string) => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const result = await apiFetch<RollbackResult>(`/knowledge/documents/${docId}/rollback`, {
        method: 'POST',
      })
      setMessage(result.message)
      await loadOverview()
      setSelectedDocId(docId)
    } catch (e) {
      setError(e instanceof Error ? e.message : '版本回滚失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container">
        <div className="card">
          <h1>知识库工作台</h1>
          <p className="muted">面向知识运营角色，支持上传文档、切片预览、检索测试、评测与版本回滚。</p>
          <div className="nav">
            <Link href="/workbench/selection">选品工作台</Link>
            <Link href="/agents">Agent 平台</Link>
            <Link href="/reports">报告中心</Link>
            <Link href="/operations">运营台</Link>
            <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void loadOverview()}>刷新知识库</button>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}

        <div className="grid grid-3" style={{ marginBottom: 16 }}>
          <div className="metric-card">
            <div className="metric-label">文档总数</div>
            <div className="metric-value">{stats?.total_documents ?? 0}</div>
            <div className="metric-hint">已索引 {stats?.indexed_documents ?? 0}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">文本块总数</div>
            <div className="metric-value">{stats?.total_chunks ?? 0}</div>
            <div className="metric-hint">平均每文档 {stats?.average_chunks_per_doc ?? 0}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">检索后端</div>
            <div className="metric-value">{searchStatus?.backend ?? '-'}</div>
            <div className="metric-hint">effective={searchStatus?.effective_mode ?? '-'} / fallback={searchStatus?.fallback_mode ?? '-'}</div>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>上传文档</h2>
            <p className="muted">支持 .txt / .md / .csv，上传后自动切片并索引。</p>
            <div className="inline-form">
              <input
                className="input"
                type="file"
                accept=".txt,.md,.csv,text/plain,text/markdown,text/csv"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
              />
              <button className="btn btn-primary" type="button" disabled={loading || !uploadFile} onClick={() => void handleUpload()}>
                上传文档
              </button>
            </div>
            <div className="muted" style={{ marginTop: 12 }}>
              当前文件：{uploadFile?.name ?? '未选择'}
            </div>
          </div>

          <div className="card">
            <h2>质量与检索状态</h2>
            <div><strong>索引覆盖率：</strong>{quality?.knowledge_health?.index_coverage ?? '-'}</div>
            <div><strong>检索质量状态：</strong>{quality?.retrieval_quality?.status ?? '-'}</div>
            <div><strong>评估指标：</strong>{(quality?.retrieval_quality?.metrics ?? []).join(', ') || '-'}</div>
            <div><strong>默认评测：</strong>{quality?.retrieval_quality?.default_evaluation?.total_cases ?? 0} 条 / hit@k {quality?.retrieval_quality?.default_evaluation?.hit_at_k ?? '-'}</div>
            <div style={{ display: 'inline-flex', gap: 8, marginTop: 8, marginBottom: 8 }}>
              <span style={{ background: feedbackBadge.bg, color: feedbackBadge.color, padding: '2px 10px', borderRadius: 999 }}>反馈学习：{feedbackBadge.label}</span>
            </div>
            <div><strong>反馈样本：</strong>{quality?.feedback_learning?.feedback_case_count ?? 0} / 合并基线 {quality?.feedback_learning?.combined_baseline_case_count ?? 0}</div>
            <div><strong>反馈覆盖率：</strong>{quality?.feedback_learning?.coverage_ratio ?? '-'}</div>
            <div className="muted">反馈最近更新：{quality?.feedback_learning?.latest_updated_at ?? '-'}</div>
            <div className="muted">RAG评测工件：{quality?.retrieval_quality?.artifact_path ?? '-'}</div>
            <div><strong>总容量：</strong>{formatSize(stats?.total_size_mb)}</div>
            <div><strong>知识源模式：</strong>{serviceMode?.mode ?? '-'}</div>
            <div><strong>内外部知识库切换：</strong>{serviceMode?.fallback_enabled ? '已启用' : '未启用'}</div>
            <div><strong>RAG 网关模式：</strong>{serviceMode?.gateway?.mode ?? '-'}</div>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card">
            <h2>检索测试</h2>
            <div className="inline-form">
              <input className="input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入检索问题" />
              <button className="btn btn-primary" type="button" disabled={loading || !query.trim()} onClick={() => void handleQuery()}>
                执行检索测试
              </button>
            </div>
            {queryResult ? (
              <>
                <p className="muted">命中 {queryResult.total_found} 条，耗时 {queryResult.processing_time_ms} ms</p>
                <ul>
                  {queryResult.results.slice(0, 5).map((item, index) => (
                    <li key={`${item.document_id ?? 'doc'}-${item.chunk_index ?? index}`}>
                      <strong>{item.source ?? item.document_id ?? 'unknown'}</strong> / score={item.score} / chunk={item.chunk_index ?? '-'}
                      <div className="muted">{item.content.slice(0, 120)}</div>
                    </li>
                  ))}
                </ul>
              </>
            ) : <div className="muted">尚未执行检索测试。</div>}
          </div>

          <div className="card">
            <h2>评测</h2>
            <p className="muted">以当前查询和选中文档为基准执行最小评测。</p>
            <textarea
              className="textarea"
              rows={4}
              value={evalKeywords}
              onChange={(event) => setEvalKeywords(event.target.value)}
              placeholder="输入期望关键词，逗号分隔"
            />
            <div className="action-row">
              <button className="btn btn-secondary" type="button" disabled={loading || !query.trim()} onClick={() => void handleEvaluate()}>
                执行评测
              </button>
            </div>
            {evalResult ? (
              <div className="grid grid-2" style={{ marginTop: 12 }}>
                <div><strong>cases：</strong>{evalResult.total_cases ?? 0}</div>
                <div><strong>hit@k：</strong>{evalResult.hit_at_k ?? '-'}</div>
                <div><strong>mrr：</strong>{evalResult.mrr ?? '-'}</div>
                <div><strong>citation：</strong>{evalResult.citation_match_rate ?? '-'}</div>
              </div>
            ) : <div className="muted">尚未执行评测。</div>}
          </div>
        </div>

        {message ? <div className="card"><strong>执行结果：</strong>{message}</div> : null}

        <div className="grid grid-2">
          <div className="card">
            <h2>文档列表</h2>
            <div className="inline-form" style={{ marginBottom: 12 }}>
              <input
                className="input"
                placeholder="状态过滤，如 indexed"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              />
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void loadOverview()}>
                刷新列表
              </button>
            </div>
            <div className="inline-form">
              {documents.length ? documents.map((doc) => (
                <button
                  key={doc.doc_id}
                  type="button"
                  className="list-card"
                  style={{ textAlign: 'left', cursor: 'pointer', borderColor: selectedDocId === doc.doc_id ? '#2563eb' : '#e5e7eb' }}
                  onClick={() => setSelectedDocId(doc.doc_id)}
                >
                  <div><strong>{doc.filename}</strong> {doc.is_current_version ? '(current)' : ''}</div>
                  <div className="muted">v{doc.version ?? 1} / {doc.status} / chunks={doc.chunk_count ?? 0}</div>
                  <div className="muted">provider={doc.provider_mode ?? '-'} / vector={doc.vector_status ?? '-'}</div>
                </button>
              )) : <div className="list-card">暂无文档，请先上传。</div>}
            </div>
          </div>

          <div className="card">
            <h2>文档详情与切片预览</h2>
            {detail ? (
              <>
                <div><strong>文档ID：</strong>{detail.doc_id}</div>
                <div><strong>文件名：</strong>{detail.filename}</div>
                <div><strong>状态：</strong>{detail.status}</div>
                <div><strong>版本：</strong>v{detail.version ?? 1} / current={String(detail.is_current_version ?? false)}</div>
                <div><strong>文件大小：</strong>{formatSize(undefined, detail.file_size)}</div>
                <div><strong>状态原因：</strong>{detail.status_reason ?? '-'}</div>
                <p className="muted" style={{ marginTop: 12 }}>{detail.content_preview || '暂无预览'}</p>
                <strong>切片预览</strong>
                <ul>
                  {(detail.chunks ?? []).slice(0, 5).map((chunk) => (
                    <li key={`${detail.doc_id}-${chunk.chunk_index}`}>
                      #{chunk.chunk_index} / vector={chunk.vector_id ?? '-'}
                      <div className="muted">{chunk.content.slice(0, 160)}</div>
                    </li>
                  ))}
                </ul>
              </>
            ) : <div className="list-card">请选择文档查看详情。</div>}
          </div>
        </div>

        <div className="card">
          <h2>版本列表与版本回滚</h2>
          <div className="inline-form">
            {versions.length ? versions.map((doc) => (
              <div key={doc.doc_id} className="list-card">
                <div><strong>{doc.filename}</strong> / v{doc.version ?? 1}</div>
                <div className="muted">status={doc.status} / current={String(doc.is_current_version ?? false)} / index_version={doc.index_version ?? '-'}</div>
                <div className="action-row">
                  <button
                    className="btn btn-secondary"
                    type="button"
                    disabled={loading || doc.is_current_version}
                    onClick={() => void handleRollback(doc.doc_id)}
                  >
                    版本回滚
                  </button>
                </div>
              </div>
            )) : <div className="list-card">当前文档暂无版本列表。</div>}
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
