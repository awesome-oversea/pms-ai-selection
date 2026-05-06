import fs from 'node:fs'
import path from 'node:path'

import { expect, test, type Page, type Route } from '@playwright/test'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://127.0.0.1:18000/api/v1'
const artifactsDir = path.resolve(process.cwd(), '../artifacts/frontend')

const operatorUser = {
  user_id: 'user-operator',
  username: 'operator-e2e',
  tenant_id: 'tenant-default',
  tenant_key: 'default',
  tenant_name: '默认租户',
  roles: ['operator'],
  is_superuser: false,
}

const superUser = {
  ...operatorUser,
  user_id: 'user-admin',
  username: 'admin-e2e',
  roles: ['admin', 'superuser'],
  is_superuser: true,
}

type MockUser = typeof operatorUser

type MockSession = {
  user: MockUser
  username: string
  password: string
  token: string
}

type MockState = ReturnType<typeof createMockState>

const operatorSession: MockSession = {
  user: operatorUser,
  username: 'operator-e2e',
  password: 'Operator123!',
  token: 'token-operator-e2e',
}

const superUserSession: MockSession = {
  user: superUser,
  username: 'admin-e2e',
  password: 'Admin123!',
  token: 'token-admin-e2e',
}

function ensureArtifactsDir() {
  fs.mkdirSync(artifactsDir, { recursive: true })
}

async function capture(page: Page, name: string) {
  ensureArtifactsDir()
  await page.screenshot({ path: path.join(artifactsDir, name), fullPage: true })
}

async function loginViaWorkbench(
  page: Page,
  session: MockSession,
  nextPath = '/workbench/selection',
  expectedPath = nextPath,
) {
  await page.goto(`/login?next=${encodeURIComponent(nextPath)}`)
  await page.getByPlaceholder('用户名').fill(session.username)
  await page.getByPlaceholder('密码').fill(session.password)
  await Promise.all([
    page.waitForURL(`http://127.0.0.1:3100${expectedPath}`),
    page.getByRole('button', { name: '登录' }).click(),
  ])
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem('pms_workbench_token'))).not.toBeNull()
}

async function registerRealUser(session: MockSession) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: session.username,
      email: `${session.username}@example.com`,
      password: session.password,
      full_name: session.user.username,
    }),
  })
  if (response.status !== 200 && response.status !== 409) {
    throw new Error(`failed to register real user: ${response.status} ${await response.text()}`)
  }
}

function createMockState(user: MockUser) {
  const now = '2026-04-13T12:00:00Z'
  const selectionTaskId = 'task-e2e-001'
  const selectionTasks = [
    {
      task_id: selectionTaskId,
      query: '蓝牙耳机',
      status: 'running',
      phase: 'analysis',
      created_at: now,
    },
  ]

  const selection = {
    summary: {
      tenant_id: user.tenant_id,
      username: user.username,
      total: selectionTasks.length,
      by_status: { running: 1 } as Record<string, number>,
      recent_tasks: selectionTasks,
    },
    tasks: selectionTasks,
    detail: {
      task_id: selectionTaskId,
      query: '蓝牙耳机',
      status: 'running',
      phase: 'analysis',
      category: 'electronics',
      target_market: 'US',
      investment_budget: 50000,
      result_summary: '建议进入复核',
      status_reason: 'agent_review_required',
      decision_output: {
        decision: { decision: 'GO' },
        reasoning: ['需求稳定', '利润空间可控'],
      },
      approval: { action: 'pending', status: 'pending' },
    },
    result: {
      task_id: selectionTaskId,
      status: 'completed',
      result_summary: '建议进入复核',
      go_no_go_decision: 'GO',
      decision_output: {
        decision: { decision: 'GO' },
        confidence: 0.82,
      },
    },
    closeLoopOverview: {
      task_id: selectionTaskId,
      overview_ready: true,
      feedback_loop_status: { crm_feedback_ready: true, rescore_ready: true },
      profit_trace: { trace_id: 'trace-e2e-001', roi_year1_percent: 23.5 },
      feature_asset: { ready: true, asset_key: 'feature-e2e-001' },
    },
  }

  const knowledgeDocuments = [
    {
      doc_id: 'doc-e2e-001',
      filename: 'bluetooth-market.md',
      file_size: 4096,
      chunk_count: 3,
      status: 'indexed',
      uploaded_at: now,
      content_preview: '蓝牙耳机市场在北美持续增长。',
      vector_status: 'ready',
      provider_mode: 'hybrid-search',
      status_reason: 'indexed',
      version: 2,
      index_version: 2,
      is_current_version: true,
      previous_document_id: 'doc-e2e-000',
    },
    {
      doc_id: 'doc-e2e-000',
      filename: 'bluetooth-market.md',
      file_size: 2048,
      chunk_count: 2,
      status: 'archived',
      uploaded_at: '2026-04-12T08:00:00Z',
      content_preview: '旧版蓝牙耳机市场摘要。',
      vector_status: 'ready',
      provider_mode: 'hybrid-search',
      status_reason: 'rolled_back_source',
      version: 1,
      index_version: 1,
      is_current_version: false,
      previous_document_id: null,
    },
  ]

  const reports = {
    total: 1,
    filters: {
      report_type: 'weekly',
      created_after: null,
      created_before: null,
    },
    summary: {
      report_count: 1,
      total_gmv: 196258.39,
      avg_completion_rate: 0.81,
      latest_generated_at: now,
      data_source: 'report_center_state',
    },
    items: [
      {
        report_id: 'report-e2e-001',
        report_type: 'weekly',
        title: '蓝牙耳机周报',
        summary: '展示利润、风险与闭环状态。',
        format: 'pdf',
        created_at: now,
        generated_at: now,
        download_url: '/reports/report-e2e-001/download',
        download_format: 'pdf',
        archived: false,
        shared: false,
        audit_flags: ['share_ready', 'download_ready'],
      },
    ],
  }

  const dashboard = {
    summary: {
      overall_status: 'healthy-with-watchpoints',
      bi_asset_count: 3,
      loop_closed: true,
      data_source: 'artifacts',
      updated_at: now,
      report_title: '蓝牙耳机经营看板',
      report_count: 1,
      gmv: 125000,
      completion_rate: 91,
    },
    charts: {
      trend_chart: {
        type: 'line',
        title: '趋势机会',
        xAxis: ['7d', '14d', '30d'],
        series: [82, 84, 79],
      },
      profit_chart: {
        type: 'bar',
        title: '利润 / ROI',
        xAxis: ['毛利润', '毛利率', 'ROI'],
        series: [125000, 22, 42],
      },
      risk_chart: {
        type: 'pie',
        title: '库存 / 供应风险',
        items: [
          { name: '库存风险', value: 1 },
          { name: '供应风险', value: 0 },
          { name: '回流缺口', value: 1 },
        ],
      },
      competitor_chart: {
        type: 'ranking',
        title: 'BI资产可用性榜单',
        items: [
          { name: 'profit_ads', value: 100 },
          { name: 'risk_summary', value: 92 },
          { name: 'close_loop_trace', value: 88 },
        ],
      },
      execution_chart: {
        type: 'progress',
        title: '执行闭环进度',
        items: [
          { name: '飞轮闭环', value: 100 },
          { name: 'BI资产', value: 60 },
          { name: '系统就绪', value: 80 },
        ],
      },
    },
  }

  const topology = {
    topology: {
      nodes: [
        { id: 'collect', label: 'DataCollectionAgent', phase: 'collect' },
        { id: 'plan', label: 'ProductPlannerAgent', phase: 'plan' },
      ],
      edges: [{ from: 'collect', to: 'plan' }],
    },
    frameworks: {
      native: { type: 'python', status: 'active', use_cases: ['selection'], notes: '主编排框架' },
      langgraph: { type: 'compatible', status: 'ready', use_cases: ['graph-rag'] },
    },
    workflow_registry: {
      selection: { active_framework: 'native', fallback_framework: 'langgraph', runtime_mode: 'local' },
    },
    strategy_version: 3,
    strategy: {
      approval_mode: 'human-review',
      retry_policy: 'bounded',
    },
  }

  const operations = {
    running_total: 2,
    dead_letter_total: 0,
    retryable_total: 1,
    manual_intervention_total: 1,
    failed_reasons: { timeout: 1 },
    status_reason_samples: [{ task_id: selectionTaskId, status: 'running', status_reason: 'agent_review_required' }],
    retry_history: [{ task_id: selectionTaskId, retry_count: 1, dead_letter: false }],
    recent_interventions: [{ task_id: selectionTaskId, action: 'pause_and_review', comment: '请补充供应链信息', operator: 'ops-admin' }],
    lifecycle_summary: { running: 2, paused: 1, completed: 3 },
    lifecycle_actions: ['pause_and_review', 'resume', 'retry_with_context'],
    retryable_tasks: [{ task_id: selectionTaskId, status: 'paused', status_reason: 'waiting_for_review', retry_count: 1, dead_letter: false }],
  }

  return {
    selection,
    knowledge: {
      stats: {
        total_documents: 2,
        indexed_documents: 1,
        total_chunks: 5,
        total_size_mb: 1.2,
        average_chunks_per_doc: 2.5,
      },
      quality: {
        knowledge_health: {
          total_documents: 2,
          indexed_documents: 1,
          index_coverage: 0.5,
        },
        retrieval_quality: {
          status: 'ready',
          metrics: ['hit@k', 'mrr', 'citation_match_rate'],
        },
      },
      searchStatus: {
        backend: 'opensearch',
        effective_mode: 'real-first',
        fallback_mode: 'memory',
        provider: 'local',
        configured: true,
      },
      documents: knowledgeDocuments,
    },
    reports,
    dashboard,
    topology,
    operations,
    configOperations: {
      config_total: 12,
      feature_flag_total: 4,
      recent_versions: [{ config_key: 'selection.close_loop', version: 3, description: '启用闭环总览' }],
    },
    tenantOperations: {
      total: 1,
      tenants: [{
        tenant_id: user.tenant_id,
        tenant_key: user.tenant_key,
        name: user.tenant_name,
        status: 'active',
        is_active: true,
        quota_status: [{ quota_type: 'llm_cost_usd', remaining: 870, limit_value: 1000, used_value: 130 }],
        isolation_summary: { tenant_scoped: true, quota_governed: true },
      }],
    },
    auditOperations: {
      total: 3,
      recent_actions: [{ action: 'auth.login', username: user.username, result: 'success', occurred_at: now }],
      supported_filters: ['request_id', 'trace_id', 'username'],
      trace_query_ready: true,
    },
    releaseStatus: {
      delivery_readiness: {
        ready_for_deploy: true,
        ready_for_cutover: false,
        latest_gate_status: 'passed-with-kong-blocker',
        blocking_reasons: ['kong_environment_not_connected'],
      },
    },
    securityStatus: {
      explicit_tenant_required: true,
      llm_protection: {
        ip_allowlist_enabled: true,
        prompt_guard_enabled: true,
      },
    },
    llmGovernanceStatus: {
      quota: {
        configured: true,
        limit_value: 1000,
        used_value: 130,
        remaining: 870,
      },
      prompt_governance: {
        prompt_total: 6,
        recent_versions: [{ prompt_key: 'selection.system', version: 5, description: '加强风险提示' }],
      },
      route_policy: {
        configured: true,
        version: 4,
        gray_rollout_percent: 10,
        default_force_tier: 'HEAVY',
      },
    },
  }
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify({ data }),
  })
}

async function registerMockApi(page: Page, session: MockSession, options?: { passthroughAuth?: boolean }) {
  const state = createMockState(session.user)
  const passthroughAuth = options?.passthroughAuth ?? false

  await page.route(`${API_BASE}/**`, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const apiPath = url.pathname.replace('/api/v1', '')
    const method = request.method().toUpperCase()
    const authHeader = request.headers()['authorization']
    const authenticated = authHeader === `Bearer ${session.token}`

    if (apiPath === '/auth/login' && method === 'POST') {
      if (passthroughAuth) {
        await route.continue()
        return
      }
      const payload = request.postDataJSON() as { username?: string; password?: string }
      if (payload.username === session.username && payload.password === session.password) {
        await fulfillJson(route, {
          access_token: session.token,
          refresh_token: `${session.token}-refresh`,
          tenant_id: session.user.tenant_id,
          tenant_key: session.user.tenant_key,
          tenant_name: session.user.tenant_name,
          expires_in: 3600,
        })
        return
      }
      await route.fulfill({
        status: 401,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify({ detail: '用户名或密码错误' }),
      })
      return
    }

    if (apiPath === '/auth/me' && method === 'GET') {
      if (passthroughAuth) {
        await route.continue()
        return
      }
      if (!authenticated) {
        await route.fulfill({
          status: 401,
          contentType: 'application/json; charset=utf-8',
          body: JSON.stringify({ detail: '未登录' }),
        })
        return
      }
      await fulfillJson(route, session.user)
      return
    }

    if (apiPath === '/bff/workbench/selection/summary' && method === 'GET') {
      await fulfillJson(route, state.selection.summary)
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks' && method === 'GET') {
      await fulfillJson(route, { total: state.selection.tasks.length, tasks: state.selection.tasks })
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks' && method === 'POST') {
      const payload = request.postDataJSON() as { query?: string; target_market?: string }
      const taskId = `task-created-${state.selection.tasks.length + 1}`
      state.selection.tasks.unshift({
        task_id: taskId,
        query: payload.query ?? '新建任务',
        status: 'created',
        phase: 'created',
        created_at: '2026-04-13T12:05:00Z',
      })
      state.selection.summary.total = state.selection.tasks.length
      state.selection.summary.by_status = {
        ...state.selection.summary.by_status,
        created: (state.selection.summary.by_status.created ?? 0) + 1,
      }
      await fulfillJson(route, { task_id: taskId, status: 'created', target_market: payload.target_market ?? 'US' })
      return
    }

    if (apiPath === '/bff/workbench/selection/stream' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: `event: snapshot\ndata: ${JSON.stringify({
          summary: state.selection.summary,
          tasks: { total: state.selection.tasks.length, tasks: state.selection.tasks },
          signals: [{ task_id: 'task-e2e-001', trend_direction: 'up', decision: 'GO', risk_count: 1 }],
          agent_steps: [{ task_id: 'task-e2e-001', steps: [{ name: 'collect' }, { name: 'plan' }] }],
          reconnect: { retry_ms: 3000, strategy: 'client_reconnect' },
          timestamp: '2026-04-13T12:00:00Z',
        })}\n\n`,
      })
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001' && method === 'GET') {
      await fulfillJson(route, state.selection.detail)
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/result' && method === 'GET') {
      await fulfillJson(route, state.selection.result)
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/close-loop-overview' && method === 'GET') {
      await fulfillJson(route, state.selection.closeLoopOverview)
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/approve' && method === 'POST') {
      const payload = request.postDataJSON() as { action?: 'approve' | 'reject' }
      const nextStatus = payload.action === 'reject' ? 'rejected' : 'approved'
      state.selection.detail.status = nextStatus
      state.selection.detail.approval = { action: payload.action ?? 'approve', status: nextStatus }
      await fulfillJson(route, { status: nextStatus, action: payload.action ?? 'approve' })
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/feedback' && method === 'POST') {
      const payload = request.postDataJSON() as { sentiment?: string; source?: string; comment?: string }
      await fulfillJson(route, {
        task_id: 'task-e2e-001',
        status: 'feedback-recorded',
        feedback_entry: {
          sentiment: payload.sentiment ?? 'positive',
          source: payload.source ?? 'crm',
          comment: payload.comment ?? '反馈已记录',
        },
      })
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/adopt' && method === 'POST') {
      const payload = request.postDataJSON() as { quantity?: number; scm_name?: string; wms_name?: string; oms_name?: string }
      await fulfillJson(route, {
        task_id: 'task-e2e-001',
        status: 'completed',
        message: '采纳推荐并完成SCM/WMS/OMS执行编排',
        scm_receipt: { purchase_order_id: 'PO-task-e2e-001', status: 'pending_review' },
        wms_reservation: { reservation_id: 'RSV-task-e2e-001', status: 'reserved', location_code: 'WH-A-01' },
        oms_listing_draft: { listing_draft_id: 'LST-task-e2e-001', status: 'draft_created' },
        execution_status: {
          scm: { status: 'pending_review', config_name: payload.scm_name ?? 'default' },
          wms: { status: 'reserved', config_name: payload.wms_name ?? 'default' },
          oms: { status: 'draft_created', config_name: payload.oms_name ?? 'default' },
        },
        adoption: {
          status: 'executed',
          quantity: payload.quantity ?? 200,
          scm_name: payload.scm_name ?? 'default',
          supplier_code: 'SUP-001',
          execution_status: {
            scm: { status: 'pending_review' },
            wms: { status: 'reserved' },
            oms: { status: 'draft_created' },
          },
        },
      })
      return
    }

    if (apiPath === '/bff/workbench/selection/tasks/task-e2e-001/close-loop' && method === 'POST') {
      await fulfillJson(route, {
        task_id: 'task-e2e-001',
        trace_id: 'trace-e2e-001',
        summary: { close_loop_completed: true, steps: ['scm', 'wms', 'oms'] },
        route_status: { scm: true, wms: true, oms: true, fms: true },
      })
      return
    }

    if (apiPath === '/knowledge/stats' && method === 'GET') {
      await fulfillJson(route, state.knowledge.stats)
      return
    }

    if (apiPath === '/knowledge/quality-dashboard' && method === 'GET') {
      await fulfillJson(route, state.knowledge.quality)
      return
    }

    if (apiPath === '/knowledge/search-backend/status' && method === 'GET') {
      await fulfillJson(route, state.knowledge.searchStatus)
      return
    }

    if (apiPath === '/knowledge/documents' && method === 'GET') {
      await fulfillJson(route, { total: state.knowledge.documents.length, documents: state.knowledge.documents })
      return
    }

    if (apiPath === '/knowledge/documents' && method === 'POST') {
      const newDoc = {
        doc_id: 'doc-uploaded-001',
        filename: 'uploaded-e2e.md',
        file_size: 1024,
        chunk_count: 2,
        status: 'indexed',
        uploaded_at: '2026-04-13T12:10:00Z',
        content_preview: '上传后的知识文档预览。',
        vector_status: 'ready',
        provider_mode: 'hybrid-search',
        status_reason: 'indexed',
        version: 1,
        index_version: 1,
        is_current_version: true,
        previous_document_id: null,
      }
      state.knowledge.documents.unshift(newDoc)
      await fulfillJson(route, {
        doc_id: newDoc.doc_id,
        filename: newDoc.filename,
        status: newDoc.status,
        message: '上传成功',
        chunk_count: newDoc.chunk_count,
        provider_mode: newDoc.provider_mode,
        vector_status: newDoc.vector_status,
      })
      return
    }

    if (apiPath === '/knowledge/documents/doc-e2e-001' && method === 'GET') {
      await fulfillJson(route, {
        ...state.knowledge.documents[0],
        chunks: [
          { chunk_index: 0, content: '蓝牙耳机市场在北美持续增长。', vector_id: 'vec-001', metadata: { source: 'weekly-report' } },
          { chunk_index: 1, content: '利润空间保持在 20% 以上。', vector_id: 'vec-002', metadata: { source: 'cost-trace' } },
        ],
      })
      return
    }

    if (apiPath === '/knowledge/documents/doc-e2e-001/versions' && method === 'GET') {
      await fulfillJson(route, { document_key: 'bluetooth-market', total: state.knowledge.documents.length, versions: state.knowledge.documents })
      return
    }

    if (apiPath === '/knowledge/query' && method === 'POST') {
      await fulfillJson(route, {
        query: '蓝牙耳机',
        total_found: 1,
        processing_time_ms: 18,
        results: [
          {
            content: '蓝牙耳机市场在北美持续增长。',
            score: 0.91,
            source: 'bluetooth-market.md',
            document_id: 'doc-e2e-001',
            chunk_index: 0,
            ranking_stage: 'rerank',
            ranking_meta: { backend: 'opensearch' },
          },
        ],
      })
      return
    }

    if (apiPath === '/knowledge/evaluate' && method === 'POST') {
      await fulfillJson(route, {
        total_cases: 1,
        hit_at_k: 1,
        mrr: 1,
        citation_match_rate: 1,
        avg_score: 0.95,
        cases: [{ case_id: 'case-e2e-001', matched: true }],
      })
      return
    }

    if (apiPath === '/knowledge/documents/doc-e2e-001/rollback' && method === 'POST') {
      await fulfillJson(route, {
        doc_id: 'doc-e2e-001',
        version: 2,
        status: 'rolled_back',
        message: '版本回滚成功',
      })
      return
    }

    if (apiPath === '/reports' && method === 'GET') {
      await fulfillJson(route, { total: state.reports.items.length, items: state.reports.items })
      return
    }

    if (apiPath === '/reports/generate' && method === 'POST') {
      const newReport = {
        report_id: `report-generated-${state.reports.items.length + 1}`,
        report_type: url.searchParams.get('report_type') ?? 'weekly',
        title: '新生成报告',
        summary: '生成后的正式报告摘要。',
        format: url.searchParams.get('format') ?? 'pdf',
        created_at: '2026-04-13T12:15:00Z',
        generated_at: '2026-04-13T12:15:00Z',
        download_url: '/reports/generated/download',
        download_format: url.searchParams.get('format') ?? 'pdf',
        archived: false,
        shared: false,
        audit_flags: ['generated'],
      }
      state.reports.items.unshift(newReport)
      await fulfillJson(route, newReport)
      return
    }

    if (apiPath === '/reports/report-e2e-001/share' && method === 'POST') {
      state.reports.items[0].shared = true
      await fulfillJson(route, {
        share_token: 'share-token-e2e-001',
        share_url: 'https://example.test/reports/share/share-token-e2e-001',
        report_id: 'report-e2e-001',
        expires_at: '2026-04-14T12:00:00Z',
      })
      return
    }

    if (apiPath === '/reports/report-e2e-001' && method === 'DELETE') {
      state.reports.items[0].archived = true
      await fulfillJson(route, { report_id: 'report-e2e-001', archived: true })
      return
    }

    if (apiPath === '/reports/report-e2e-001/download' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: 'mock-report-binary',
        headers: {
          'Content-Disposition': 'attachment; filename="report-e2e-001.pdf"',
        },
      })
      return
    }

    if (apiPath === '/dashboard/selection-overview' && method === 'GET') {
      await fulfillJson(route, state.dashboard)
      return
    }

    if (apiPath === '/agents/platform/topology' && method === 'GET') {
      await fulfillJson(route, state.topology)
      return
    }

    if (apiPath === '/agents/platform/operations' && method === 'GET') {
      await fulfillJson(route, state.operations)
      return
    }

    if (apiPath === '/agents/platform/tasks/task-e2e-001/resume' && method === 'POST') {
      await fulfillJson(route, {
        task_id: 'task-e2e-001',
        status: 'running',
        status_reason: 'resumed_by_operator',
        dead_letter: false,
      })
      return
    }

    if (apiPath === '/agents/platform/tasks/task-e2e-001/intervene' && method === 'POST') {
      await fulfillJson(route, {
        task_id: 'task-e2e-001',
        status: 'paused',
        status_reason: 'manual_intervention_recorded',
        dead_letter: false,
        config: { intervention: 'pause_and_review' },
      })
      return
    }

    if (apiPath === '/config-operations' && method === 'GET') {
      await fulfillJson(route, state.configOperations)
      return
    }

    if (apiPath === '/tenant-operations' && method === 'GET') {
      await fulfillJson(route, state.tenantOperations)
      return
    }

    if (apiPath === '/audit-operations' && method === 'GET') {
      await fulfillJson(route, state.auditOperations)
      return
    }

    if (apiPath === '/audit/logs' && method === 'GET') {
      const queryLogs = [
        {
          timestamp: '2026-04-13T12:20:00Z',
          action: url.searchParams.get('action') || 'auth.login',
          actor: { username: session.user.username, tenant_id: session.user.tenant_id },
          target_type: 'session',
          target_id: 'session-e2e-001',
          result: 'success',
          detail: {
            request_id: url.searchParams.get('request_id') || 'req-ops-001',
            trace_id: url.searchParams.get('trace_id') || 'tr-ops-001',
          },
          request_id: url.searchParams.get('request_id') || 'req-ops-001',
          trace_id: url.searchParams.get('trace_id') || 'tr-ops-001',
        },
      ]
      await fulfillJson(route, {
        total: queryLogs.length,
        source: 'memory',
        logs: queryLogs,
        filters: {
          username: url.searchParams.get('username'),
          action: url.searchParams.get('action'),
          request_id: url.searchParams.get('request_id'),
          trace_id: url.searchParams.get('trace_id'),
          limit: Number(url.searchParams.get('limit') || '20'),
        },
      })
      return
    }

    if (apiPath === '/release/status' && method === 'GET') {
      await fulfillJson(route, state.releaseStatus)
      return
    }

    if (apiPath === '/security/status' && method === 'GET') {
      await fulfillJson(route, state.securityStatus)
      return
    }

    if (apiPath === '/llm-governance/status' && method === 'GET') {
      await fulfillJson(route, state.llmGovernanceStatus)
      return
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json; charset=utf-8',
      body: JSON.stringify({ message: `Unhandled mock endpoint: ${method} ${apiPath}` }),
    })
  })
}

test('blueprint home is visible and protected routes redirect to login', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: '企业级 AI 选品中枢蓝图' })).toBeVisible()
  await expect(page.getByText('高价值任务状态面')).toBeVisible()
  await expect(page.getByText('工作台矩阵')).toBeVisible()
  await capture(page, 'blueprint-home.png')

  await page.goto('/workbench/selection')
  await expect(page).toHaveURL(/\/login\?next=%2Fworkbench%2Fselection/)
  await expect(page.getByRole('heading', { name: '工作台登录' })).toBeVisible()
})

test('login page performs real credential flow before entering protected workbench', async ({ page }) => {
  await registerRealUser(operatorSession)
  await registerMockApi(page, operatorSession, { passthroughAuth: true })

  await page.goto('/login?next=%2Fworkbench%2Fselection')
  await page.getByPlaceholder('用户名').fill(operatorSession.username)
  await page.getByPlaceholder('密码').fill(operatorSession.password)
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL('http://127.0.0.1:3100/workbench/selection')
  await expect(page.getByText('operator-e2e')).toBeVisible()
  await expect(page.getByRole('heading', { name: '正式选品工作台' })).toBeVisible()
  await expect.poll(async () => page.evaluate(() => window.localStorage.getItem('pms_workbench_token'))).not.toBeNull()
})

test('selection workbench smoke covers create approve feedback and close-loop actions', async ({ page }) => {
  await registerMockApi(page, operatorSession)
  await loginViaWorkbench(page, operatorSession)

  await expect(page.getByRole('heading', { name: '正式选品工作台' })).toBeVisible()
  await expect(page.getByText('operator-e2e')).toBeVisible()
  await expect(page.getByText('待审批')).toBeVisible()
  await expect(page.getByText('高风险任务')).toBeVisible()
  await expect(page.getByText('平均 ROI')).toBeVisible()
  await expect(page.getByText('数据来源')).toBeVisible()
  await expect(page.getByText('关键趋势/决策')).toBeVisible()

  await page.getByRole('button', { name: '通过 BFF 创建任务' }).click()
  await expect(page.getByText(/任务创建成功：task-created-2/)).toBeVisible()

  await page.getByRole('button', { name: '审批通过' }).click()
  await expect(page.getByText(/任务 task-e2e-001 已审批通过/)).toBeVisible()

  await page.getByRole('button', { name: '采纳推荐' }).click()
  await expect(page.getByText(/任务 task-e2e-001 已采纳推荐并生成采购建议/)).toBeVisible()

  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByText(/任务 task-e2e-001 已录入反馈/)).toBeVisible()

  await page.getByRole('button', { name: '执行闭环' }).click()
  await expect(page.getByText(/任务 task-e2e-001 已触发执行闭环：完成/)).toBeVisible()
  await expect(page.getByText('闭环总览 / Profit Trace / 特征资产')).toBeVisible()

  await capture(page, 'workbench-selection-smoke.png')
})

test('knowledge workbench smoke covers upload query evaluate and rollback', async ({ page }) => {
  await registerMockApi(page, operatorSession)
  await loginViaWorkbench(page, operatorSession, '/knowledge')

  await expect(page.getByRole('heading', { name: '知识库工作台' })).toBeVisible()
  await expect(page.getByRole('button', { name: '执行检索测试' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '版本列表与版本回滚' })).toBeVisible()

  await page.setInputFiles('input[type="file"]', {
    name: 'knowledge-e2e.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# 蓝牙耳机\n北美市场增长稳定。', 'utf-8'),
  })
  await page.getByRole('button', { name: '上传文档' }).click()
  await expect(page.getByText(/执行结果：上传成功/)).toBeVisible()

  await page.getByRole('button', { name: '执行检索测试' }).click()
  await expect(page.getByText(/检索完成：命中 1 条，耗时 18 ms/)).toBeVisible()

  await page.getByRole('button', { name: '执行评测' }).click()
  await expect(page.getByText('评测完成：hit@k=1 / mrr=1')).toBeVisible()

  await expect(page.getByRole('button', { name: '版本回滚' }).nth(1)).toBeVisible()

  await capture(page, 'knowledge-workbench-smoke.png')
})

test('dashboard page renders profit and close-loop evidence panels', async ({ page }) => {
  await registerMockApi(page, superUserSession)
  await loginViaWorkbench(page, superUserSession, '/dashboard')

  await expect(page.getByRole('heading', { name: '利润中枢看板' })).toBeVisible()
  await expect(page.getByText('利润 / ROI / 库存风险 / 供应风险 / 趋势机会 / 飞轮状态')).toBeVisible()
  await expect(page.getByText('总状态')).toBeVisible()
  await expect(page.getByText('healthy-with-watchpoints')).toBeVisible()
  await expect(page.getByText('闭环状态')).toBeVisible()
  await expect(page.getByText('已闭环')).toBeVisible()
  await expect(page.getByText('数据来源')).toBeVisible()
  await expect(page.getByText('GMV')).toBeVisible()
  await expect(page.getByText('完成率')).toBeVisible()
  await expect(page.getByRole('heading', { name: '利润 / ROI' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '执行闭环进度' })).toBeVisible()

  await capture(page, 'dashboard-profit-smoke.png')
})

test('reports and agent platform pages render formal secured panels', async ({ page }) => {
  await registerRealUser(operatorSession)
  await loginViaWorkbench(page, operatorSession, '/reports')

  await expect(page.getByRole('heading', { name: '报告中心' })).toBeVisible()
  await expect(page.getByText('总 GMV')).toBeVisible()
  await expect(page.getByText('平均完成率')).toBeVisible()
  await expect(page.getByText('数据来源')).toBeVisible()
  await expect(page.getByText('report_center_state')).toBeVisible()

  await page.getByRole('button', { name: '生成报告' }).click()
  await expect(page.getByText('报告已生成')).toBeVisible()
  await expect(page.locator('main')).toContainText('RPT_')

  await page.getByRole('button', { name: '分享' }).click()
  await expect(page.getByText(/分享链接已创建：/)).toBeVisible()
  await expect(page.locator('pre.code-panel')).toContainText('share_token')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^RPT_.*\.pdf$/)

  await page.getByRole('button', { name: '归档' }).click()
  await expect(page.getByText(/已归档/)).toBeVisible()

  await capture(page, 'reports-center-smoke.png')

  await page.route(`${API_BASE}/agents/platform/topology`, async (route) => {
    await fulfillJson(route, createMockState(operatorSession.user).topology)
  })
  await page.route(`${API_BASE}/agents/platform/operations`, async (route) => {
    await fulfillJson(route, createMockState(operatorSession.user).operations)
  })
  await page.route(`${API_BASE}/agents/platform/tasks/task-e2e-001/resume`, async (route) => {
    await fulfillJson(route, {
      task_id: 'task-e2e-001',
      status: 'running',
      status_reason: 'resumed_by_operator',
      dead_letter: false,
    })
  })

  await page.goto('/agents')
  await expect(page.getByRole('heading', { name: 'Agent 平台' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '运行拓扑' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '运行诊断' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '日志与历史' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '操作中心' })).toBeVisible()

  await page.getByRole('button', { name: '恢复任务' }).click()
  await expect(page.getByText(/任务 task-e2e-001 已恢复/)).toBeVisible()

  await capture(page, 'agent-platform-smoke.png')
})

test('operations page redirects non-superuser back to home', async ({ page }) => {
  await registerMockApi(page, operatorSession)
  await loginViaWorkbench(page, operatorSession, '/operations', '/')

  await expect(page).toHaveURL('http://127.0.0.1:3100/')
  await expect(page.getByRole('heading', { name: '企业级 AI 选品中枢蓝图' })).toBeVisible()
})

test('operations page renders admin panels for superuser session', async ({ page }) => {
  await registerMockApi(page, superUserSession)
  await page.goto('/login?next=%2Foperations')
  await page.getByPlaceholder('用户名').fill(superUserSession.username)
  await page.getByPlaceholder('密码').fill(superUserSession.password)
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL('http://127.0.0.1:3100/operations')
  await expect(page.getByRole('heading', { name: '运营台' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '配置治理' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '租户与配额' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '审计与追踪' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '安全与 LLM 治理' })).toBeVisible()
  await expect(page.getByRole('button', { name: '导出配额快照' })).toBeVisible()
  await expect(page.getByRole('button', { name: '导出治理快照' })).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出治理快照' }).click()
  const download = await downloadPromise
  await expect(download.suggestedFilename()).toBe('llm-governance-snapshot.json')

  await page.getByPlaceholder('动作，例如 auth.login').fill('auth.login')
  await page.getByPlaceholder('request_id').fill('req-ops-001')
  await page.getByPlaceholder('trace_id').fill('tr-ops-001')
  await page.getByRole('button', { name: '查询审计' }).click()
  await expect(page.getByText(/审计查询完成：1 条 \/ 来源 memory/)).toBeVisible()
  await expect(page.getByText(/auth.login \/ admin-e2e \/ success \/ req-ops-001/)).toBeVisible()

  await capture(page, 'operations-admin-smoke.png')
})
