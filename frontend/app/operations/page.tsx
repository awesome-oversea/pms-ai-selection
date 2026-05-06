'use client'

import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

type ConfigOperations = {
  config_total?: number
  feature_flag_total?: number
  recent_versions?: Array<{ config_key: string; version: number; description?: string }>
}

type TenantOperations = {
  total?: number
  tenants?: Array<{
    tenant_id: string
    tenant_key: string
    name: string
    status: string
    is_active: boolean
    quota_status?: Array<{ quota_type: string; remaining: number; limit_value: number; used_value: number }>
    isolation_summary?: { tenant_scoped?: boolean; quota_governed?: boolean }
  }>
}

type AuditOperations = {
  total?: number
  recent_actions?: Array<{ action: string; username: string; result: string; occurred_at?: string }>
  supported_filters?: string[]
  trace_query_ready?: boolean
}

type AuditLogItem = {
  timestamp?: string
  occurred_at?: string
  action: string
  actor?: { username?: string; tenant_id?: string }
  username?: string
  target_type?: string
  target_id?: string
  result: string
  detail?: Record<string, unknown>
  request_id?: string
  trace_id?: string
}

type AuditLogQueryResponse = {
  total?: number
  source?: string
  logs?: AuditLogItem[]
  filters?: Record<string, string | number | null | undefined>
}

type ReleaseStatus = {
  delivery_readiness?: {
    ready_for_deploy?: boolean
    ready_for_cutover?: boolean
    latest_gate_status?: string | null
    blocking_reasons?: string[]
  }
}

type SecurityStatus = {
  explicit_tenant_required?: boolean
  llm_protection?: {
    ip_allowlist_enabled?: boolean
    prompt_guard_enabled?: boolean
  }
}

type LLMGovernanceStatus = {
  quota?: {
    configured?: boolean
    quota_type?: string
    limit_value?: number
    used_value?: number
    remaining?: number
    reset_period?: string
    is_active?: boolean
  }
  prompt_governance?: {
    prompt_total?: number
    recent_versions?: Array<{ prompt_key: string; version: number; description?: string }>
  }
  route_policy?: {
    configured?: boolean
    version?: number
    gray_rollout_percent?: number
    default_force_tier?: string | null
  }
  audit?: {
    prompt_audit_ready?: boolean
    cost_trace_ready?: boolean
    quota_enforcement_ready?: boolean
  }
}

type GatewayGovernanceStatus = {
  canary_release?: {
    strategy?: string
    routes?: Array<{ route_name?: string; traffic_split?: { stable?: number; canary?: number } }>
  }
}

type MetricsDashboardStatus = {
  technical?: {
    observability_runtime?: {
      grafana_import?: {
        dashboard_tool?: string
        dashboards?: Array<{ title?: string; source_artifact?: string; import_mode?: string }>
      }
    }
  }
}

type InferenceHealthStatus = {
  healthy_route_count?: number
  gpu_observability_level?: string
  gpu_metrics_freshness_seconds?: number | null
  gpu_alerts?: Array<{ severity?: string; code?: string; message?: string }>
  routes?: Record<string, { status?: string; auto_evicted?: boolean; gpu_blocked?: boolean; alerts?: Array<{ code?: string; message?: string }> }>
}

type GPUStatus = {
  ready?: boolean
  observability_level?: string
  metrics_freshness_seconds?: number | null
  observed_at?: string | null
  alert_count?: number
  alerts?: Array<{ severity?: string; code?: string; message?: string; gpu_index?: number }>
  runtime?: {
    available?: boolean
    gpu_count?: number
    allocatable_gpu_count?: number
  }
  dcgm_exporter?: {
    installed?: boolean
    metrics_ready?: boolean
    blocking_reason?: string | null
  }
}

type ExternalCollectionReadinessStatus = {
  status?: string
  accepted?: boolean
  generated_at?: string | null
  readiness_snapshot?: {
    formal_api_ready_count?: number
    local_validation_only_count?: number
    blocked_source_count?: number
    next_actions?: string[]
  }
  business_readiness_overview?: {
    classification_breakdown?: Record<string, number>
    formal_ready_sources?: string[]
    local_validation_only_sources?: string[]
    blocked_sources?: string[]
    next_actions?: string[]
  }
  source_probes?: Record<string, {
    status?: string
    channel_classification?: string
    business_interpretation?: string
    formal_api_ready?: boolean
    recent_error?: string | null
    fallback_reason?: string | null
    last_success_at?: string | null
  }>
}

type DataPlatformStatus = {
  scheduler?: { scheduler?: string; jobs?: Array<{ job_key?: string }> }
  kettle?: {
    etl_engine?: string
    pipelines?: Array<{ pipeline_key?: string }>
    latest_run_quality_score?: number
    business_consumable?: boolean
    failure_summary?: string[]
  }
  ray_embedding?: { engine?: string; status?: string; target_qps?: number; runner?: string; workload?: string }
  processing_engines?: {
    etl_engine?: {
      latest_run_quality_score?: number
      business_consumable?: boolean
      failure_summary?: string[]
    }
    batch_engine?: {
      scheduler_manifest?: { scheduler?: string; jobs?: Array<{ job_key?: string }> }
      kettle_etl_manifest?: { etl_engine?: string; pipelines?: Array<{ pipeline_key?: string }> }
    }
  }
}

type RealtimeStatus = {
  websocket?: { total_connections?: number; active_connections?: number; subscribed_tasks?: number }
  erp_gateway?: { queue_size?: number; dead_letter_size?: number; sync_log_size?: number; supported_systems?: string[] }
  transport?: { sse_ready?: boolean; websocket_manager_ready?: boolean; client_reconnect_strategy?: string }
}

type OperationsGovernanceOverview = {
  status?: string
  business_config_governance?: {
    latest_execution?: {
      last_executed_at?: string | null
      last_result_ok?: boolean
      summary?: {
        exported_config_count?: number
        acceptance_ok?: boolean
        rollback_ok?: boolean
        verified_config_count?: number
      }
    }
  }
  rag_governance?: {
    latest_execution?: {
      last_executed_at?: string | null
      last_result_ok?: boolean
      summary?: {
        feedback_learning_ok?: boolean
        evaluation_ok?: boolean
        dashboard_ok?: boolean
        evaluated_case_count?: number
        feedback_case_count?: number
      }
    }
  }
}

type DeliveryReadinessStatus = {
  status?: string
  executed_at?: string
  summary?: {
    business_governance_ok?: boolean
    rag_governance_ok?: boolean
    main_chain_exceptions_ok?: boolean
    operations_overview_status?: string
    artifact_ready_count?: number
    artifact_total_count?: number
  }
  steps?: {
    main_chain_exceptions?: {
      ok?: boolean
      summary?: {
        status?: string
        check_count?: number
        passed_check_count?: number
      }
    }
  }
}

type DeliveryConclusionStatus = {
  status?: string
  executed_at?: string
  delivery_ready?: boolean
  acceptance_conclusion?: {
    summary_lines?: string[]
    next_action?: string
  }
}

type CaptchaOCRResponse = {
  recognized_text?: string
  mode?: string
  confidence?: number
}

function StatusCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {children}
    </div>
  )
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function buildStatusBadge(passed?: boolean | null) {
  if (passed === true) return { label: '通过', color: '#166534', bg: '#dcfce7' }
  if (passed === false) return { label: '异常', color: '#991b1b', bg: '#fee2e2' }
  return { label: '未执行', color: '#374151', bg: '#e5e7eb' }
}

export default function OperationsPage() {
  const [configOps, setConfigOps] = useState<ConfigOperations | null>(null)
  const [tenantOps, setTenantOps] = useState<TenantOperations | null>(null)
  const [auditOps, setAuditOps] = useState<AuditOperations | null>(null)
  const [releaseStatus, setReleaseStatus] = useState<ReleaseStatus | null>(null)
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null)
  const [llmGovernance, setLlmGovernance] = useState<LLMGovernanceStatus | null>(null)
  const [gatewayGovernance, setGatewayGovernance] = useState<GatewayGovernanceStatus | null>(null)
  const [metricsDashboard, setMetricsDashboard] = useState<MetricsDashboardStatus | null>(null)
  const [gpuStatus, setGpuStatus] = useState<GPUStatus | null>(null)
  const [inferenceHealth, setInferenceHealth] = useState<InferenceHealthStatus | null>(null)
  const [externalCollectionReadiness, setExternalCollectionReadiness] = useState<ExternalCollectionReadinessStatus | null>(null)
  const [dataPlatformStatus, setDataPlatformStatus] = useState<DataPlatformStatus | null>(null)
  const [realtimeStatus, setRealtimeStatus] = useState<RealtimeStatus | null>(null)
  const [governanceOverview, setGovernanceOverview] = useState<OperationsGovernanceOverview | null>(null)
  const [deliveryReadiness, setDeliveryReadiness] = useState<DeliveryReadinessStatus | null>(null)
  const [deliveryConclusion, setDeliveryConclusion] = useState<DeliveryConclusionStatus | null>(null)
  const [captchaHint, setCaptchaHint] = useState('a b-1 2 c')
  const [captchaResult, setCaptchaResult] = useState<CaptchaOCRResponse | null>(null)
  const [auditQueryResult, setAuditQueryResult] = useState<AuditLogQueryResponse | null>(null)
  const [auditQuery, setAuditQuery] = useState({
    username: '',
    action: '',
    requestId: '',
    traceId: '',
    limit: '20',
  })
  const [queryLoading, setQueryLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setError(null)
      const results = await Promise.allSettled([
        apiFetch<ConfigOperations>('/config-operations'),
        apiFetch<TenantOperations>('/tenant-operations'),
        apiFetch<AuditOperations>('/audit-operations'),
        apiFetch<ReleaseStatus>('/release/status'),
        apiFetch<SecurityStatus>('/security/status'),
        apiFetch<LLMGovernanceStatus>('/llm-governance/status'),
        apiFetch<GatewayGovernanceStatus>('/gateway-governance'),
        apiFetch<MetricsDashboardStatus>('/metrics-dashboard'),
        apiFetch<GPUStatus>('/llm/gpu/status'),
        apiFetch<InferenceHealthStatus>('/llm/inference/health'),
        apiFetch<ExternalCollectionReadinessStatus>('/external-collection/readiness'),
        apiFetch<DataPlatformStatus>('/data-platform/runtime'),
        apiFetch<RealtimeStatus>('/realtime/status'),
        apiFetch<OperationsGovernanceOverview>('/operations-governance-overview'),
        apiFetch<DeliveryReadinessStatus>('/delivery-readiness'),
        apiFetch<DeliveryConclusionStatus>('/delivery-conclusion'),
      ])

      const [configData, tenantData, auditData, releaseData, securityData, llmData, gatewayData, metricsData, gpuData, inferenceHealthData, externalCollectionData, dataPlatformData, realtimeData, governanceData, deliveryData, conclusionData] = results

      if (configData.status === 'fulfilled') setConfigOps(configData.value)
      if (tenantData.status === 'fulfilled') setTenantOps(tenantData.value)
      if (auditData.status === 'fulfilled') setAuditOps(auditData.value)
      if (releaseData.status === 'fulfilled') setReleaseStatus(releaseData.value)
      if (securityData.status === 'fulfilled') setSecurityStatus(securityData.value)
      if (llmData.status === 'fulfilled') setLlmGovernance(llmData.value)
      if (gatewayData.status === 'fulfilled') setGatewayGovernance(gatewayData.value)
      if (metricsData.status === 'fulfilled') setMetricsDashboard(metricsData.value)
      if (gpuData.status === 'fulfilled') setGpuStatus(gpuData.value)
      if (inferenceHealthData.status === 'fulfilled') setInferenceHealth(inferenceHealthData.value)
      if (externalCollectionData.status === 'fulfilled') setExternalCollectionReadiness(externalCollectionData.value)
      if (dataPlatformData.status === 'fulfilled') setDataPlatformStatus(dataPlatformData.value)
      if (realtimeData.status === 'fulfilled') setRealtimeStatus(realtimeData.value)
      if (governanceData.status === 'fulfilled') setGovernanceOverview(governanceData.value)
      if (deliveryData.status === 'fulfilled') setDeliveryReadiness(deliveryData.value)
      if (conclusionData.status === 'fulfilled') setDeliveryConclusion(conclusionData.value)

      const failed = results.filter((item) => item.status === 'rejected')
      if (failed.length === results.length) {
        setError('运营台加载失败')
        return
      }
      if (failed.length > 0) {
        setError(`部分模块加载失败（${failed.length}/${results.length}），其余数据已展示`)
      }
    }
    void load()
  }, [])

  const firstTenant = tenantOps?.tenants?.[0]
  const firstQuota = firstTenant?.quota_status?.[0]
  const promptVersions = llmGovernance?.prompt_governance?.recent_versions ?? []
  const businessBadge = buildStatusBadge(governanceOverview?.business_config_governance?.latest_execution?.last_result_ok)
  const ragBadge = buildStatusBadge(governanceOverview?.rag_governance?.latest_execution?.last_result_ok)
  const deliveryBadge = buildStatusBadge(deliveryReadiness?.status === 'ready' ? true : deliveryReadiness?.status === 'partial' ? false : null)
  const mainChainExceptionBadge = buildStatusBadge(deliveryReadiness?.steps?.main_chain_exceptions?.ok)
  const tenantQuotaRows = (tenantOps?.tenants ?? []).flatMap((tenant) =>
    (tenant.quota_status ?? []).map((quota) => ({
      tenant_key: tenant.tenant_key,
      quota_type: quota.quota_type,
      used_value: quota.used_value,
      limit_value: quota.limit_value,
      remaining: quota.remaining,
    })),
  )

  const runAuditQuery = async () => {
    setQueryLoading(true)
    setMessage(null)
    try {
      const params = new URLSearchParams()
      if (auditQuery.username.trim()) params.set('username', auditQuery.username.trim())
      if (auditQuery.action.trim()) params.set('action', auditQuery.action.trim())
      if (auditQuery.requestId.trim()) params.set('request_id', auditQuery.requestId.trim())
      if (auditQuery.traceId.trim()) params.set('trace_id', auditQuery.traceId.trim())
      params.set('limit', auditQuery.limit.trim() || '20')
      const data = await apiFetch<AuditLogQueryResponse>(`/audit/logs?${params.toString()}`)
      setAuditQueryResult(data)
      setMessage(`审计查询完成：${data.total ?? 0} 条 / 来源 ${data.source ?? 'unknown'}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '审计查询失败')
    } finally {
      setQueryLoading(false)
    }
  }

  const exportQuotaSnapshot = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      tenant_operations: tenantOps,
      llm_quota: llmGovernance?.quota ?? null,
    }
    downloadJson('tenant-quota-snapshot.json', payload)
    setMessage('已导出租户配额快照：tenant-quota-snapshot.json')
  }

  const exportGovernanceSnapshot = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      security_status: securityStatus,
      llm_governance: llmGovernance,
      prompt_versions: promptVersions,
      recent_audit_actions: auditOps?.recent_actions ?? [],
    }
    downloadJson('llm-governance-snapshot.json', payload)
    setMessage('已导出治理快照：llm-governance-snapshot.json')
  }

  const exportDeliveryReadinessSnapshot = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      delivery_readiness: deliveryReadiness,
      governance_overview: governanceOverview,
    }
    downloadJson('delivery-readiness-snapshot.json', payload)
    setMessage('已导出交付巡检快照：delivery-readiness-snapshot.json')
  }

  const exportAuditQueryResult = () => {
    if (!auditQueryResult) return
    downloadJson('audit-query-result.json', auditQueryResult)
    setMessage('已导出审计结果：audit-query-result.json')
  }

  const runCaptchaOCR = async () => {
    try {
      const data = await apiFetch<CaptchaOCRResponse>('/security/captcha-ocr', {
        method: 'POST',
        body: JSON.stringify({ image_text_hint: captchaHint }),
      })
      setCaptchaResult(data)
      setMessage(`验证码识别完成：${data.recognized_text ?? '-'}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '验证码识别失败')
    }
  }

  return (
    <AuthGuard requireSuperuser>
      <main className="container">
        <div className="card">
          <h1>运营台</h1>
          <p className="muted">面向运维和值班角色，统一查看配置、租户/RBAC、审计、发布与 LLM 治理状态。</p>
          <div className="nav">
            <Link href="/agents">Agent 平台</Link>
            <Link href="/reports">报告中心</Link>
            <Link href="/dashboard">数据大盘</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="grid grid-3">
          <StatusCard title="配置治理">
            <div><strong>配置数：</strong>{configOps?.config_total ?? 0}</div>
            <div><strong>Feature Flag：</strong>{configOps?.feature_flag_total ?? 0}</div>
            <div className="muted">最近版本：{configOps?.recent_versions?.[0]?.config_key ?? '-'}</div>
          </StatusCard>
          <StatusCard title="租户与配额">
            <div><strong>租户数：</strong>{tenantOps?.total ?? 0}</div>
            <div><strong>首租户：</strong>{firstTenant?.tenant_key ?? '-'}</div>
            <div><strong>LLM 成本配额：</strong>{llmGovernance?.quota?.configured ? '已配置' : '未配置'}</div>
            <div className="muted">{firstQuota ? `${firstQuota.quota_type} 已用 ${firstQuota.used_value} / 上限 ${firstQuota.limit_value} / 剩余 ${firstQuota.remaining}` : '暂无配额'}</div>
            <div className="action-row" style={{ marginTop: 12 }}>
              <button className="btn btn-secondary" type="button" onClick={exportQuotaSnapshot}>导出配额快照</button>
            </div>
            <div className="inline-form" style={{ marginTop: 12 }}>
              {tenantQuotaRows.length ? tenantQuotaRows.slice(0, 5).map((row) => (
                <div key={`${row.tenant_key}-${row.quota_type}`} className="list-card" style={{ minWidth: 220 }}>
                  <div><strong>{row.tenant_key}</strong> / {row.quota_type}</div>
                  <div className="muted">已用 {row.used_value} / 上限 {row.limit_value} / 剩余 {row.remaining}</div>
                </div>
              )) : <div className="list-card">暂无租户配额数据</div>}
            </div>
          </StatusCard>
          <StatusCard title="发布门禁">
            <div><strong>可部署：</strong>{releaseStatus?.delivery_readiness?.ready_for_deploy ? '是' : '否'}</div>
            <div><strong>可切流：</strong>{releaseStatus?.delivery_readiness?.ready_for_cutover ? '是' : '否'}</div>
            <div className="muted">最新门禁：{releaseStatus?.delivery_readiness?.latest_gate_status ?? '-'}</div>
            <div className="muted">阻塞：{releaseStatus?.delivery_readiness?.blocking_reasons?.join(', ') || '-'}</div>
          </StatusCard>
          <StatusCard title="治理执行摘要">
            <div><strong>总览状态：</strong>{governanceOverview?.status ?? '-'}</div>
            <div style={{ display: 'inline-flex', gap: 8, marginTop: 8, marginBottom: 8, flexWrap: 'wrap' }}>
              <span style={{ background: deliveryBadge.bg, color: deliveryBadge.color, padding: '2px 10px', borderRadius: 999 }}>交付巡检：{deliveryBadge.label}</span>
              <span style={{ background: mainChainExceptionBadge.bg, color: mainChainExceptionBadge.color, padding: '2px 10px', borderRadius: 999 }}>主链异常：{mainChainExceptionBadge.label}</span>
              <span style={{ background: businessBadge.bg, color: businessBadge.color, padding: '2px 10px', borderRadius: 999 }}>配置治理：{businessBadge.label}</span>
              <span style={{ background: ragBadge.bg, color: ragBadge.color, padding: '2px 10px', borderRadius: 999 }}>RAG治理：{ragBadge.label}</span>
            </div>
            <div className="muted">交付快照：{deliveryReadiness?.executed_at ?? '-'}</div>
            <div className="muted">交付工件：{deliveryReadiness?.summary?.artifact_ready_count ?? 0} / {deliveryReadiness?.summary?.artifact_total_count ?? 0}</div>
            <div className="muted">主链异常验收：通过 {deliveryReadiness?.steps?.main_chain_exceptions?.summary?.passed_check_count ?? 0} / {deliveryReadiness?.steps?.main_chain_exceptions?.summary?.check_count ?? 0}</div>
            <div className="muted">配置最近执行：{governanceOverview?.business_config_governance?.latest_execution?.last_executed_at ?? '-'}</div>
            <div className="muted">导出 {governanceOverview?.business_config_governance?.latest_execution?.summary?.exported_config_count ?? 0} 项 / 校验 {governanceOverview?.business_config_governance?.latest_execution?.summary?.verified_config_count ?? 0} 项</div>
            <div className="muted">RAG最近执行：{governanceOverview?.rag_governance?.latest_execution?.last_executed_at ?? '-'}</div>
            <div className="muted">评测 {governanceOverview?.rag_governance?.latest_execution?.summary?.evaluated_case_count ?? 0} 条 / 反馈样本 {governanceOverview?.rag_governance?.latest_execution?.summary?.feedback_case_count ?? 0} 条</div>
            <div className="muted">交付结论：{deliveryConclusion?.acceptance_conclusion?.next_action ?? '-'}</div>
            <div className="muted">结论摘要：{(deliveryConclusion?.acceptance_conclusion?.summary_lines ?? []).slice(0, 2).join(' / ') || '-'}</div>
            <div className="action-row" style={{ marginTop: 12 }}>
              <button className="btn btn-secondary" type="button" onClick={exportDeliveryReadinessSnapshot}>导出交付巡检快照</button>
            </div>
          </StatusCard>
        </div>

        <div className="grid grid-2">
          <StatusCard title="审计与追踪">
            <div><strong>最近动作数：</strong>{auditOps?.total ?? 0}</div>
            <div><strong>Trace 查询：</strong>{auditOps?.trace_query_ready ? '已就绪' : '未就绪'}</div>
            <div><strong>支持过滤：</strong>{auditOps?.supported_filters?.join(', ') || '-'}</div>
            <div className="inline-form" style={{ marginTop: 12 }}>
              <input
                className="input"
                value={auditQuery.action}
                onChange={(event) => setAuditQuery((current) => ({ ...current, action: event.target.value }))}
                placeholder="动作，例如 auth.login"
              />
              <input
                className="input"
                value={auditQuery.requestId}
                onChange={(event) => setAuditQuery((current) => ({ ...current, requestId: event.target.value }))}
                placeholder="request_id"
              />
              <input
                className="input"
                value={auditQuery.traceId}
                onChange={(event) => setAuditQuery((current) => ({ ...current, traceId: event.target.value }))}
                placeholder="trace_id"
              />
              <input
                className="input"
                value={auditQuery.limit}
                onChange={(event) => setAuditQuery((current) => ({ ...current, limit: event.target.value }))}
                placeholder="limit"
              />
            </div>
            <div className="action-row">
              <button className="btn btn-primary" type="button" disabled={queryLoading} onClick={() => void runAuditQuery()}>查询审计</button>
              <button className="btn btn-secondary" type="button" disabled={!auditQueryResult} onClick={exportAuditQueryResult}>导出审计结果</button>
            </div>
            {auditQueryResult ? (
              <>
                <div className="muted">查询结果 {auditQueryResult.total ?? 0} 条 / 来源 {auditQueryResult.source ?? '-'}</div>
                <pre className="code-panel">{JSON.stringify(auditQueryResult.filters ?? {}, null, 2)}</pre>
                <ul>
                  {(auditQueryResult.logs ?? []).slice(0, 5).map((item, index) => (
                    <li key={`${item.action}-${index}`}>
                      {item.action} / {(item.actor?.username ?? item.username ?? 'system')} / {item.result} /
                      {' '}{item.request_id ?? String(item.detail?.request_id ?? '-')}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <ul>
                {(auditOps?.recent_actions ?? []).slice(0, 5).map((item, index) => (
                  <li key={`${item.action}-${index}`}>{item.action} / {item.username} / {item.result}</li>
                ))}
              </ul>
            )}
          </StatusCard>

          <StatusCard title="安全与 LLM 治理">
            <div><strong>显式租户：</strong>{securityStatus?.explicit_tenant_required ? '开启' : '关闭'}</div>
            <div><strong>IP 白名单：</strong>{securityStatus?.llm_protection?.ip_allowlist_enabled ? '开启' : '关闭'}</div>
            <div><strong>Prompt 防护：</strong>{securityStatus?.llm_protection?.prompt_guard_enabled ? '开启' : '关闭'}</div>
            <div><strong>Prompt 审计：</strong>{llmGovernance?.audit?.prompt_audit_ready ? '已就绪' : '未就绪'}</div>
            <div><strong>成本追踪：</strong>{llmGovernance?.audit?.cost_trace_ready ? '已就绪' : '未就绪'}</div>
            <div><strong>配额执行：</strong>{llmGovernance?.audit?.quota_enforcement_ready ? '已就绪' : '未就绪'}</div>
            <div className="muted">
              {llmGovernance?.quota
                ? `已用 ${llmGovernance.quota.used_value ?? 0} / 上限 ${llmGovernance.quota.limit_value ?? 0} / 剩余 ${llmGovernance.quota.remaining ?? 0}`
                : '暂无 LLM 配额信息'}
            </div>
            <div className="muted">
              Prompt 模板 {llmGovernance?.prompt_governance?.prompt_total ?? 0} 个 / 路由策略版本 {llmGovernance?.route_policy?.version ?? 0} / 灰度 {llmGovernance?.route_policy?.gray_rollout_percent ?? 0}%
            </div>
            <div className="muted">默认模型层级：{llmGovernance?.route_policy?.default_force_tier ?? '-'}</div>
            <div className="action-row" style={{ marginTop: 12 }}>
              <button className="btn btn-secondary" type="button" onClick={exportGovernanceSnapshot}>导出治理快照</button>
            </div>
            <div className="inline-form" style={{ marginTop: 12 }}>
              {promptVersions.length ? promptVersions.slice(0, 6).map((item) => (
                <div key={`${item.prompt_key}-${item.version}`} className="list-card" style={{ minWidth: 220 }}>
                  <div><strong>{item.prompt_key}</strong> / v{item.version}</div>
                  <div className="muted">{item.description || '无说明'}</div>
                </div>
              )) : <div className="list-card">暂无 Prompt 版本信息</div>}
            </div>
          </StatusCard>

          <StatusCard title="网关灰度与仪表板导入">
            <div><strong>Canary 策略：</strong>{gatewayGovernance?.canary_release?.strategy ?? '-'}</div>
            <div><strong>Canary 流量：</strong>{gatewayGovernance?.canary_release?.routes?.[0]?.traffic_split?.canary ?? 0}%</div>
            <div><strong>Stable 流量：</strong>{gatewayGovernance?.canary_release?.routes?.[0]?.traffic_split?.stable ?? 0}%</div>
            <div><strong>Grafana 导入：</strong>{metricsDashboard?.technical?.observability_runtime?.grafana_import?.dashboard_tool ?? '-'}</div>
            <div className="muted">Dashboard：{metricsDashboard?.technical?.observability_runtime?.grafana_import?.dashboards?.[0]?.title ?? '-'}</div>
            <div className="muted">Source：{metricsDashboard?.technical?.observability_runtime?.grafana_import?.dashboards?.[0]?.source_artifact ?? '-'}</div>
          </StatusCard>

          <StatusCard title="外部数据联调 readiness">
            <div><strong>验收状态：</strong>{externalCollectionReadiness?.accepted ? '通过' : '未通过'}</div>
            <div><strong>正式 API 就绪数：</strong>{externalCollectionReadiness?.readiness_snapshot?.formal_api_ready_count ?? 0}</div>
            <div><strong>本地验证来源数：</strong>{externalCollectionReadiness?.readiness_snapshot?.local_validation_only_count ?? 0}</div>
            <div><strong>阻塞来源数：</strong>{externalCollectionReadiness?.readiness_snapshot?.blocked_source_count ?? 0}</div>
            <div className="muted">最近生成：{externalCollectionReadiness?.generated_at ?? '-'}</div>
            <div className="muted">下一步：{externalCollectionReadiness?.readiness_snapshot?.next_actions?.[0] ?? '-'}</div>
            <div className="inline-form" style={{ marginTop: 12 }}>
              {Object.entries(externalCollectionReadiness?.source_probes ?? {}).length
                ? Object.entries(externalCollectionReadiness?.source_probes ?? {}).map(([source, probe]) => (
                  <div key={source} className="list-card" style={{ minWidth: 240 }}>
                    <div><strong>{source}</strong> / {probe.channel_classification ?? '-'}</div>
                    <div className="muted">业务判定：{probe.business_interpretation ?? '-'}</div>
                    <div className="muted">正式 API：{probe.formal_api_ready ? '已就绪' : '未就绪'}</div>
                    <div className="muted">回退原因：{probe.fallback_reason ?? '-'}</div>
                    <div className="muted">最近错误：{probe.recent_error ?? '-'}</div>
                  </div>
                ))
                : <div className="list-card">暂无外部数据联调 readiness 信息</div>}
            </div>
          </StatusCard>

          <StatusCard title="调度与ETL">
            <div><strong>调度器：</strong>{dataPlatformStatus?.scheduler?.scheduler ?? dataPlatformStatus?.processing_engines?.batch_engine?.scheduler_manifest?.scheduler ?? '-'}</div>
            <div><strong>调度任务数：</strong>{dataPlatformStatus?.scheduler?.jobs?.length ?? dataPlatformStatus?.processing_engines?.batch_engine?.scheduler_manifest?.jobs?.length ?? 0}</div>
            <div><strong>ETL引擎：</strong>{dataPlatformStatus?.kettle?.etl_engine ?? dataPlatformStatus?.processing_engines?.batch_engine?.kettle_etl_manifest?.etl_engine ?? '-'}</div>
            <div><strong>业务可消费：</strong>{(dataPlatformStatus?.kettle?.business_consumable ?? dataPlatformStatus?.processing_engines?.etl_engine?.business_consumable) ? '是' : '否'}</div>
            <div><strong>质量评分：</strong>{dataPlatformStatus?.kettle?.latest_run_quality_score ?? dataPlatformStatus?.processing_engines?.etl_engine?.latest_run_quality_score ?? '-'}</div>
            <div className="muted">ETL 流水线：{dataPlatformStatus?.kettle?.pipelines?.length ?? dataPlatformStatus?.processing_engines?.batch_engine?.kettle_etl_manifest?.pipelines?.length ?? 0}</div>
            <div className="muted">Ray / 分布式接口：{dataPlatformStatus?.ray_embedding?.engine ?? '-'} / {dataPlatformStatus?.ray_embedding?.runner ?? '-'}</div>
            <div className="muted">失败摘要：{(dataPlatformStatus?.kettle?.failure_summary ?? dataPlatformStatus?.processing_engines?.etl_engine?.failure_summary ?? []).join('；') || '-'}</div>
          </StatusCard>

          <StatusCard title="实时推送通道">
            <div><strong>SSE：</strong>{realtimeStatus?.transport?.sse_ready ? '已就绪' : '未就绪'}</div>
            <div><strong>WebSocket管理器：</strong>{realtimeStatus?.transport?.websocket_manager_ready ? '已就绪' : '未就绪'}</div>
            <div><strong>重连策略：</strong>{realtimeStatus?.transport?.client_reconnect_strategy ?? '-'}</div>
            <div className="muted">连接数：{realtimeStatus?.websocket?.total_connections ?? 0} / 活跃 {realtimeStatus?.websocket?.active_connections ?? 0} / 订阅任务 {realtimeStatus?.websocket?.subscribed_tasks ?? 0}</div>
          </StatusCard>

          <StatusCard title="GPU监控状态">
            <div><strong>GPU Ready：</strong>{gpuStatus?.ready ? '是' : '否'}</div>
            <div><strong>GPU 数量：</strong>{gpuStatus?.runtime?.gpu_count ?? 0}</div>
            <div><strong>可分配 GPU：</strong>{gpuStatus?.runtime?.allocatable_gpu_count ?? 0}</div>
            <div><strong>可观测级别：</strong>{gpuStatus?.observability_level ?? '-'}</div>
            <div><strong>告警数：</strong>{gpuStatus?.alert_count ?? 0}</div>
            <div><strong>指标新鲜度：</strong>{gpuStatus?.metrics_freshness_seconds ?? '-'}s</div>
            <div><strong>DCGM Exporter：</strong>{gpuStatus?.dcgm_exporter?.installed ? '已安装' : '未安装'}</div>
            <div><strong>指标就绪：</strong>{gpuStatus?.dcgm_exporter?.metrics_ready ? '已就绪' : '未就绪'}</div>
            <div className="muted">阻塞：{gpuStatus?.dcgm_exporter?.blocking_reason ?? '-'}</div>
            <div className="muted">推理健康：可用路由 {inferenceHealth?.healthy_route_count ?? 0} / GPU 告警 {(inferenceHealth?.gpu_alerts ?? []).length}</div>
          </StatusCard>

          <StatusCard title="验证码识别">
            <div className="inline-form" style={{ marginTop: 12 }}>
              <input className="input" value={captchaHint} onChange={(event) => setCaptchaHint(event.target.value)} placeholder="输入验证码文本提示或样例" />
            </div>
            <div className="action-row">
              <button className="btn btn-secondary" type="button" onClick={() => void runCaptchaOCR()}>执行验证码识别</button>
            </div>
            <div className="muted" style={{ marginTop: 12 }}>mode={captchaResult?.mode ?? '-'} / confidence={captchaResult?.confidence ?? '-'}</div>
            <pre className="code-panel">{JSON.stringify(captchaResult ?? {}, null, 2)}</pre>
          </StatusCard>
        </div>
      </main>
    </AuthGuard>
  )
}
