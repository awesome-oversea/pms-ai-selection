'use client'

import { useEffect, useMemo, useState } from 'react'

import { API_BASE, apiFetch } from '@/lib/api'
import type { SelectionTaskListResponse } from '@/lib/contracts'

type TaskDetail = {
  task_id: string
  query: string
  status: string
  phase?: string
  category?: string
  target_market?: string
  investment_budget?: number
  result_summary?: string
  status_reason?: string
  decision_output?: Record<string, any>
  approval?: Record<string, any>
  adoption?: Record<string, any>
}

type TaskResult = {
  task_id: string
  status: string
  result_summary?: string
  go_no_go_decision?: string
  decision_output?: Record<string, any>
  similar_history_cases?: Record<string, unknown>
  review_cases?: Record<string, unknown>
  historical_performance?: Record<string, unknown>
}

type TopRecommendation = {
  rank?: number
  product_name?: string
  name?: string
  score?: number
  expected_roi?: number
  confidence?: number
  target_price?: number
  supplier?: string
  [key: string]: unknown
}

type FeedbackResult = {
  task_id: string
  status?: string
  feedback_entry?: Record<string, unknown>
}

type AdoptionResult = {
  task_id: string
  status?: string
  message?: string
  adoption?: Record<string, unknown>
  scm_receipt?: Record<string, unknown>
  wms_reservation?: Record<string, unknown>
  oms_listing_draft?: Record<string, unknown>
  execution_status?: Record<string, unknown>
}

type CloseLoopResult = {
  task_id: string
  trace_id: string
  summary?: {
    close_loop_completed?: boolean
    steps?: string[]
  }
  route_status?: Record<string, boolean>
}

type CloseLoopOverview = {
  task_id: string
  overview_ready?: boolean
  feedback_loop_status?: Record<string, unknown>
  profit_trace?: Record<string, unknown>
  feature_asset?: Record<string, unknown> | null
  execution_feedback_snapshot?: Record<string, unknown> | null
  similar_history_cases?: Record<string, unknown> | null
  review_cases?: Record<string, unknown> | null
  historical_performance?: Record<string, unknown> | null
}

type ExecutionFeedbackSyncResult = {
  task_id: string
  execution_feedback_snapshot?: Record<string, unknown>
  rescore_payload?: Record<string, unknown>
  rescore_result?: Record<string, unknown> | null
  feature_asset?: Record<string, unknown> | null
}

type HistoryCaseIngestResult = {
  task_id?: string
  doc_id?: string
  filename?: string
  status?: string
  chunk_count?: number
  case_type?: string
}

type HistoryCaseQueryResult = {
  query: string
  total_found: number
  results: Array<Record<string, unknown>>
}

type ReviewCaseIngestResult = {
  task_id?: string
  matched_review_count?: number
  case_type?: string
  ingested_cases?: Array<Record<string, unknown>>
  published_events?: Array<Record<string, unknown>>
}

type ReviewCaseQueryResult = {
  query: string
  total_found: number
  results: Array<Record<string, unknown>>
}

export default function SelectionTaskTable({ data }: { data: SelectionTaskListResponse }) {
  const [items, setItems] = useState(data.tasks)
  const [message, setMessage] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string>(data.tasks[0]?.task_id ?? '')
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [result, setResult] = useState<TaskResult | null>(null)
  const [adoptionResult, setAdoptionResult] = useState<AdoptionResult | null>(null)
  const [executionFeedbackResult, setExecutionFeedbackResult] = useState<ExecutionFeedbackSyncResult | null>(null)
  const [historyCaseIngestResult, setHistoryCaseIngestResult] = useState<HistoryCaseIngestResult | null>(null)
  const [historyCaseQueryResult, setHistoryCaseQueryResult] = useState<HistoryCaseQueryResult | null>(null)
  const [historyCaseQuery, setHistoryCaseQuery] = useState('蓝牙耳机 执行后 销量 评价')
  const [reviewCaseIngestResult, setReviewCaseIngestResult] = useState<ReviewCaseIngestResult | null>(null)
  const [reviewCaseQueryResult, setReviewCaseQueryResult] = useState<ReviewCaseQueryResult | null>(null)
  const [reviewCaseQuery, setReviewCaseQuery] = useState('蓝牙耳机 投诉 差评 包装')
  const [closeLoopResult, setCloseLoopResult] = useState<CloseLoopResult | null>(null)
  const [closeLoopOverview, setCloseLoopOverview] = useState<CloseLoopOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [feedbackComment, setFeedbackComment] = useState('客户反馈较好，建议继续跟进')
  const [feedbackSentiment, setFeedbackSentiment] = useState('positive')
  const [feedbackSource, setFeedbackSource] = useState('crm')
  const [interventionAction, setInterventionAction] = useState('pause_and_review')
  const [interventionComment, setInterventionComment] = useState('工作台发起人工复核，请补充判断依据')

  useEffect(() => {
    setItems(data.tasks)
    if (!selectedTaskId && data.tasks[0]?.task_id) {
      setSelectedTaskId(data.tasks[0].task_id)
    }
  }, [data, selectedTaskId])

  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedTaskId) {
        setDetail(null)
        setResult(null)
        return
      }
      setLoading(true)
      try {
        const [detailData, resultData, overviewData] = await Promise.all([
          apiFetch<TaskDetail>(`/bff/workbench/selection/tasks/${selectedTaskId}`),
          apiFetch<TaskResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/result`).catch(() => null),
          apiFetch<CloseLoopOverview>(`/bff/workbench/selection/tasks/${selectedTaskId}/close-loop-overview`).catch(() => null),
        ])
        setDetail(detailData)
        setResult(resultData)
        setCloseLoopOverview(overviewData)
      } catch (error) {
        setMessage(error instanceof Error ? error.message : '加载任务详情失败')
      } finally {
        setLoading(false)
      }
    }

    void loadDetail()
  }, [selectedTaskId])

  const selectedTask = useMemo(
    () => items.find((task) => task.task_id === selectedTaskId) ?? null,
    [items, selectedTaskId],
  )
  const topRecommendations = useMemo<TopRecommendation[]>(() => {
    const raw = ((result?.decision_output as any)?.top_recommendations ?? (detail?.decision_output as any)?.top_recommendations ?? []) as TopRecommendation[]
    return Array.isArray(raw) ? raw.slice(0, 50) : []
  }, [detail?.decision_output, result?.decision_output])

  const cancelTask = async (taskId: string) => {
    try {
      const response = await apiFetch<{ task_id: string; status: string; message: string }>(`/bff/workbench/selection/tasks/${taskId}`, {
        method: 'DELETE',
      })
      setItems((current) => current.map((task) => (task.task_id === taskId ? { ...task, status: response.status } : task)))
      setMessage(response.message)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '取消失败')
    }
  }

  const approveTask = async (action: 'approve' | 'reject') => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<{ status?: string; action: string }>(`/bff/workbench/selection/tasks/${selectedTaskId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ action, reviewer: 'workbench_user', comment: action === 'approve' ? '工作台审批通过' : '工作台审批拒绝' }),
      })
      setMessage(`任务 ${selectedTaskId} 已${response.action === 'approve' ? '审批通过' : '审批拒绝'}`)
      setDetail((current) => (current ? { ...current, approval: { action: response.action, status: response.status } } : current))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '审批失败')
    } finally {
      setLoading(false)
    }
  }

  const submitFeedback = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<FeedbackResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          source: feedbackSource,
          sentiment: feedbackSentiment,
          tags: ['workbench_feedback'],
          comment: feedbackComment,
        }),
      })
      setMessage(`任务 ${selectedTaskId} 已录入反馈：${String(response.feedback_entry?.['sentiment'] ?? feedbackSentiment)}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '反馈录入失败')
    } finally {
      setLoading(false)
    }
  }

  const interveneTask = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<TaskDetail>(`/bff/workbench/selection/tasks/${selectedTaskId}/intervene`, {
        method: 'POST',
        body: JSON.stringify({
          action: interventionAction,
          comment: interventionComment,
        }),
      })
      setDetail(response)
      setMessage(`任务 ${selectedTaskId} 已登记人工干预：${interventionAction}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '人工干预失败')
    } finally {
      setLoading(false)
    }
  }

  const interveneTaskViaRealtime = async () => {
    if (!selectedTaskId) return
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('pms_workbench_token') : null
    if (!token) {
      setMessage('缺少登录凭证，无法通过实时通道发起人工干预')
      return
    }
    setLoading(true)
    try {
      const wsUrl = API_BASE.replace(/^http/i, 'ws') + `/bff/workbench/selection/ws?token=${encodeURIComponent(token)}`
      await new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(wsUrl)
        let settled = false
        socket.onopen = () => {
          socket.send(JSON.stringify({
            action: 'intervene',
            task_id: selectedTaskId,
            intervention_action: interventionAction,
            comment: interventionComment,
          }))
        }
        socket.onmessage = () => {
          if (!settled) {
            settled = true
            socket.close()
            resolve()
          }
        }
        socket.onerror = () => {
          if (!settled) {
            settled = true
            socket.close()
            reject(new Error('实时通道人工干预失败'))
          }
        }
        socket.onclose = () => {
          if (!settled) {
            settled = true
            reject(new Error('实时通道人工干预失败'))
          }
        }
      })
      setMessage(`任务 ${selectedTaskId} 已通过实时通道登记人工干预：${interventionAction}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '实时通道人工干预失败')
    } finally {
      setLoading(false)
    }
  }

  const adoptRecommendation = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<AdoptionResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/adopt`, {
        method: 'POST',
        body: JSON.stringify({
          scm_name: 'default',
          wms_name: 'default',
          oms_name: 'default',
          quantity: 200,
          notes: '工作台采纳推荐并执行SCM/WMS/OMS联动',
        }),
      })
      setAdoptionResult(response)
      setDetail((current) => (current ? { ...current, adoption: response.adoption } : current))
      setMessage(`任务 ${selectedTaskId} 已采纳推荐并生成采购建议`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '采纳推荐失败')
    } finally {
      setLoading(false)
    }
  }

  const syncExecutionFeedback = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<ExecutionFeedbackSyncResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/execution-feedback-sync`, {
        method: 'POST',
        body: JSON.stringify({
          oms_name: 'default',
          crm_name: 'default',
          fms_name: 'default',
          wms_name: 'default',
          auto_rescore: true,
        }),
      })
      setExecutionFeedbackResult(response)
      const overviewData = await apiFetch<CloseLoopOverview>(`/bff/workbench/selection/tasks/${selectedTaskId}/close-loop-overview`).catch(() => null)
      setCloseLoopOverview(overviewData)
      setMessage(`任务 ${selectedTaskId} 已同步执行反馈并完成再评分`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '同步执行反馈失败')
    } finally {
      setLoading(false)
    }
  }

  const ingestHistoryCase = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<HistoryCaseIngestResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/history-case-ingest`, {
        method: 'POST',
      })
      setHistoryCaseIngestResult(response)
      setMessage(`任务 ${selectedTaskId} 已入库为历史选品案例`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '历史选品案例入库失败')
    } finally {
      setLoading(false)
    }
  }

  const queryHistoryCases = async () => {
    setLoading(true)
    try {
      const response = await apiFetch<HistoryCaseQueryResult>('/bff/workbench/selection/history-cases/query', {
        method: 'POST',
        body: JSON.stringify({ query: historyCaseQuery, top_k: 5, threshold: 0.1 }),
      })
      setHistoryCaseQueryResult(response)
      setMessage(`历史选品案例检索完成，共 ${response.total_found} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '历史选品案例检索失败')
    } finally {
      setLoading(false)
    }
  }

  const ingestReviewCase = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<ReviewCaseIngestResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/review-case-ingest`, {
        method: 'POST',
        body: JSON.stringify({ crm_name: 'default', publish_events: true }),
      })
      setReviewCaseIngestResult(response)
      const overviewData = await apiFetch<CloseLoopOverview>(`/bff/workbench/selection/tasks/${selectedTaskId}/close-loop-overview`).catch(() => null)
      setCloseLoopOverview(overviewData)
      setMessage(`任务 ${selectedTaskId} 已入库 CRM 好评/差评案例 ${response.matched_review_count ?? 0} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'CRM评价案例入库失败')
    } finally {
      setLoading(false)
    }
  }

  const queryReviewCases = async () => {
    setLoading(true)
    try {
      const response = await apiFetch<ReviewCaseQueryResult>('/bff/workbench/selection/review-cases/query', {
        method: 'POST',
        body: JSON.stringify({ query: reviewCaseQuery, top_k: 5, threshold: 0.1 }),
      })
      setReviewCaseQueryResult(response)
      setMessage(`CRM评价案例检索完成，共 ${response.total_found} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'CRM评价案例检索失败')
    } finally {
      setLoading(false)
    }
  }

  const closeLoopTask = async () => {
    if (!selectedTaskId) return
    setLoading(true)
    try {
      const response = await apiFetch<CloseLoopResult>(`/bff/workbench/selection/tasks/${selectedTaskId}/close-loop`, {
        method: 'POST',
        body: JSON.stringify({
          oms_name: 'default',
          scm_name: 'default',
          wms_name: 'default',
          fms_name: 'default',
          limit: 20,
        }),
      })
      setCloseLoopResult(response)
      setMessage(`任务 ${selectedTaskId} 已触发执行闭环：${response.summary?.close_loop_completed ? '完成' : '进行中'}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '执行闭环失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid grid-2">
      <div className="card">
        <h2>最近任务</h2>
        {message ? <p className="muted">{message}</p> : null}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>任务ID</th>
                <th>查询</th>
                <th>状态</th>
                <th>阶段</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((task) => (
                <tr key={task.task_id} style={{ background: task.task_id === selectedTaskId ? '#eff6ff' : 'transparent' }}>
                  <td>{task.task_id}</td>
                  <td>{task.query}</td>
                  <td><span className="badge">{task.status}</span></td>
                  <td>{task.phase ?? '-'}</td>
                  <td>{task.created_at ?? '-'}</td>
                  <td>
                    <div className="action-row">
                      <button className="btn btn-secondary" type="button" onClick={() => setSelectedTaskId(task.task_id)}>
                        详情
                      </button>
                      <button className="btn btn-danger" type="button" onClick={() => void cancelTask(task.task_id)}>
                        取消
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>任务详情 / 结果 / 审批 / 反馈</h2>
        {selectedTask ? (
          <>
            <div><strong>任务ID：</strong>{selectedTask.task_id}</div>
            <div><strong>查询：</strong>{detail?.query ?? selectedTask.query}</div>
            <div><strong>状态：</strong>{detail?.status ?? selectedTask.status}</div>
            <div><strong>阶段：</strong>{detail?.phase ?? selectedTask.phase ?? '-'}</div>
            <div><strong>目标市场：</strong>{detail?.target_market ?? '-'}</div>
            <div><strong>状态原因：</strong>{detail?.status_reason ?? '-'}</div>
            <div><strong>结果摘要：</strong>{result?.result_summary ?? detail?.result_summary ?? '-'}</div>
            <div><strong>Go/No-Go：</strong>{result?.go_no_go_decision ?? (result?.decision_output as any)?.decision?.decision ?? '-'}</div>
            <div><strong>采纳状态：</strong>{String(detail?.adoption?.status ?? adoptionResult?.adoption?.status ?? '-')}</div>

            <div className="action-row" style={{ marginTop: 12 }}>
              <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void approveTask('approve')}>
                审批通过
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void adoptRecommendation()}>
                采纳推荐
              </button>
              <button className="btn btn-danger" type="button" disabled={loading} onClick={() => void approveTask('reject')}>
                审批拒绝
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void syncExecutionFeedback()}>
                同步执行反馈
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void ingestHistoryCase()}>
                入库历史案例
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void queryHistoryCases()}>
                检索历史案例
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void ingestReviewCase()}>
                入库评价案例
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void queryReviewCases()}>
                检索评价案例
              </button>
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void closeLoopTask()}>
                执行闭环
              </button>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>反馈录入</strong>
              <div className="inline-form">
                <input className="input" value={feedbackSource} onChange={(event) => setFeedbackSource(event.target.value)} placeholder="反馈来源" />
                <select className="select" value={feedbackSentiment} onChange={(event) => setFeedbackSentiment(event.target.value)}>
                  <option value="positive">positive</option>
                  <option value="neutral">neutral</option>
                  <option value="negative">negative</option>
                </select>
                <textarea className="textarea" rows={4} value={feedbackComment} onChange={(event) => setFeedbackComment(event.target.value)} />
                <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void submitFeedback()}>
                  提交反馈
                </button>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>人工干预</strong>
              <div className="inline-form">
                <select className="select" value={interventionAction} onChange={(event) => setInterventionAction(event.target.value)}>
                  <option value="pause_and_review">pause_and_review</option>
                  <option value="resume">resume</option>
                  <option value="override_decision">override_decision</option>
                </select>
                <textarea className="textarea" rows={4} value={interventionComment} onChange={(event) => setInterventionComment(event.target.value)} />
                <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void interveneTask()}>
                  提交人工干预
                </button>
                <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void interveneTaskViaRealtime()}>
                  通过实时通道人工干预
                </button>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>结果面板</strong>
              <pre className="code-panel">{JSON.stringify(result ?? detail?.decision_output ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>Top50 推荐商品列表</strong>
              <div className="table-wrap" style={{ marginTop: 8 }}>
                <table className="table compact-table">
                  <thead>
                    <tr>
                      <th>排名</th>
                      <th>商品</th>
                      <th>评分</th>
                      <th>ROI/置信度</th>
                      <th>目标价</th>
                      <th>供应商</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topRecommendations.length ? topRecommendations.map((item, index) => (
                      <tr key={`${String(item.product_name ?? item.name ?? 'item')}-${index}`}>
                        <td>{item.rank ?? index + 1}</td>
                        <td>{String(item.product_name ?? item.name ?? '-')}</td>
                        <td>{item.score ?? '-'}</td>
                        <td>{item.expected_roi ?? item.confidence ?? '-'}</td>
                        <td>{String(item.target_price ?? '-')}</td>
                        <td>{String(item.supplier ?? '-')}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={6}>暂无 Top50 推荐商品列表</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>相似历史案例 / RAG复用</strong>
              <pre className="code-panel">{JSON.stringify(result?.similar_history_cases ?? closeLoopOverview?.similar_history_cases ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>CRM好评/差评案例 / 知识复用</strong>
              <pre className="code-panel">{JSON.stringify(result?.review_cases ?? closeLoopOverview?.review_cases ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>联合历史表现 / OMS CRM SCM WMS</strong>
              <pre className="code-panel">{JSON.stringify(result?.historical_performance ?? closeLoopOverview?.historical_performance ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>采纳推荐 / 采购建议</strong>
              <pre className="code-panel">{JSON.stringify(adoptionResult ?? detail?.adoption ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>采纳执行状态看板</strong>
              <pre className="code-panel">{JSON.stringify((adoptionResult?.execution_status ?? detail?.adoption?.execution_status ?? {
                scm: adoptionResult?.scm_receipt ?? detail?.adoption?.execution_status?.scm,
                wms: adoptionResult?.wms_reservation ?? detail?.adoption?.execution_status?.wms,
                oms: adoptionResult?.oms_listing_draft ?? detail?.adoption?.execution_status?.oms,
              }), null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>执行反馈回流 / 自动再评分</strong>
              <pre className="code-panel">{JSON.stringify(executionFeedbackResult ?? closeLoopOverview?.execution_feedback_snapshot ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>历史选品案例入库 / 检索</strong>
              <div className="inline-form">
                <input className="input" value={historyCaseQuery} onChange={(event) => setHistoryCaseQuery(event.target.value)} placeholder="输入历史案例检索关键词" />
                <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void queryHistoryCases()}>
                  检索历史案例
                </button>
              </div>
              <pre className="code-panel">{JSON.stringify({ ingest: historyCaseIngestResult, query: historyCaseQueryResult }, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>CRM好评/差评案例入库 / 检索</strong>
              <div className="inline-form">
                <input className="input" value={reviewCaseQuery} onChange={(event) => setReviewCaseQuery(event.target.value)} placeholder="输入评价案例检索关键词" />
                <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void queryReviewCases()}>
                  检索评价案例
                </button>
              </div>
              <pre className="code-panel">{JSON.stringify({ ingest: reviewCaseIngestResult, query: reviewCaseQueryResult }, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>执行闭环</strong>
              <pre className="code-panel">{JSON.stringify(closeLoopResult ?? {}, null, 2)}</pre>
            </div>

            <div style={{ marginTop: 16 }}>
              <strong>闭环总览 / Profit Trace / 特征资产</strong>
              <pre className="code-panel">{JSON.stringify(closeLoopOverview ?? {}, null, 2)}</pre>
            </div>
          </>
        ) : (
          <div className="list-card">请选择一个任务查看详情。</div>
        )}
      </div>
    </div>
  )
}
