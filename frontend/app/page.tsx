'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'
import { getToken } from '@/lib/auth'

const workbenches = [
  { href: '/workbench/selection', title: '选品工作台', role: '运营 / 选品', desc: '创建任务、审批、反馈回流与执行闭环。' },
  { href: '/dashboard', title: '利润中枢', role: '管理层 / 经营分析', desc: '查看利润、ROI、风险与闭环进度。' },
  { href: '/manager', title: '管理者工作台', role: '管理者 / 审批 / 团队绩效', desc: '查看团队绩效、审批流、准确率趋势与关键KPI。' },
  { href: '/analyst', title: '分析师工作台', role: '分析师 / 趋势研究 / 报告定制', desc: '进行数据探索、案例评测、标注与定制报告生成。' },
  { href: '/agents', title: 'Agent 平台', role: '平台 / 管理员', desc: '查看拓扑、日志、人工介入与恢复。' },
  { href: '/knowledge', title: '知识库工作台', role: '知识运营 / AI 工程', desc: '上传文档、检索测试、评测与版本回滚。' },
  { href: '/reports', title: '报告中心', role: '运营 / 管理层', desc: '生成、下载、分享与归档正式报告。' },
  { href: '/operations', title: '运营台', role: '值班 / 管理员', desc: '统一查看配置、配额、审计、安全与发布门禁。' },
]

type SummaryBlock = {
  label: string
  value: string
  hint: string
  tone?: 'default' | 'good' | 'warn'
}

type HomeStatus = {
  loading: boolean
  error: string | null
  summary: SummaryBlock[]
  serviceModes: Array<{ name: string; mode: string; manifest: string; status: string }>
  dataPipeline: Array<{ name: string; mode: string; latest: string }>
  delivery: {
    deployReady: boolean
    cutoverReady: boolean
    gateStatus: string
    drillStatus: string
  }
  risks: string[]
}

const initialStatus: HomeStatus = {
  loading: true,
  error: null,
  summary: [],
  serviceModes: [],
  dataPipeline: [],
  delivery: {
    deployReady: false,
    cutoverReady: false,
    gateStatus: '-',
    drillStatus: '-',
  },
  risks: [],
}

export default function HomePage() {
  const [status, setStatus] = useState<HomeStatus>(initialStatus)

  useEffect(() => {
    const load = async () => {
      const token = getToken()
      if (!token) {
        setStatus({
          loading: false,
          error: null,
          summary: [
            {
              label: '蓝图模式',
              value: 'preview',
              hint: '未登录时展示统一入口与工程蓝图，不请求受保护状态接口。',
              tone: 'default',
            },
            {
              label: 'AI 中台边界',
              value: '4 / 4',
              hint: 'llm / rag / agent / embedding 已形成独立边界与部署清单。',
              tone: 'good',
            },
            {
              label: '流批作业',
              value: 'batch / stream',
              hint: '已具备本地真实作业脚本与运行工件。',
              tone: 'good',
            },
            {
              label: 'GraphRAG 后端',
              value: 'LocalGraphStore',
              hint: '默认已切到本地持久化图索引。',
              tone: 'good',
            },
            {
              label: '发布门禁',
              value: 'preview',
              hint: '登录后可查看真实发布门禁、灰度与演练状态。',
              tone: 'warn',
            },
            {
              label: '当前阻塞',
              value: 'T3-02 / T6-01',
              hint: '剩余主要是 Triton 与 Kong 真实环境接入。',
              tone: 'warn',
            },
          ],
          serviceModes: [
            { name: 'llm', mode: 'remote-service-ready', manifest: 'k8s/llm-service.yml', status: '可独立部署' },
            { name: 'rag', mode: 'remote-service-ready', manifest: 'k8s/rag-service.yml', status: '可独立部署' },
            { name: 'agent', mode: 'remote-service-ready', manifest: 'k8s/agent-service.yml', status: '可独立部署' },
            { name: 'embedding', mode: 'remote-service-ready', manifest: 'k8s/embedding-service.yml', status: '可独立部署' },
          ],
          dataPipeline: [
            { name: 'Batch', mode: 'spark-compatible', latest: 'completed' },
            { name: 'Stream', mode: 'flink-compatible', latest: 'completed' },
          ],
          delivery: {
            deployReady: false,
            cutoverReady: false,
            gateStatus: 'login-required',
            drillStatus: 'preview',
          },
          risks: ['登录后可查看真实状态；当前剩余高价值阻塞主要是 Triton 与 Kong 环境接入。'],
        })
        return
      }

      try {
        const [serviceSplit, dataPlatform, releaseStatus, haStatus, graphStatus, tritonStatus] = await Promise.all([
          apiFetch<Record<string, any>>('/service-split-status'),
          apiFetch<Record<string, any>>('/data-platform/runtime'),
          apiFetch<Record<string, any>>('/release/status'),
          apiFetch<Record<string, any>>('/ha-topology/status'),
          apiFetch<Record<string, any>>('/graph/status'),
          apiFetch<Record<string, any>>('/triton/status'),
        ])

        const boundedServices = ['llm', 'rag', 'agent', 'embedding'] as const
        const serviceModes = boundedServices.map((name) => {
          const item = serviceSplit?.[name] ?? {}
          const deployment = item.deployment ?? {}
          return {
            name,
            mode: String(item.mode ?? 'unknown'),
            manifest: String(deployment.manifest ?? '-'),
            status: item.mode === 'remote-service' ? '可独立部署' : '当前以内嵌模式运行',
          }
        })

        const jobs = dataPlatform?.jobs ?? {}
        const dataPipeline = [
          {
            name: 'Batch',
            mode: String(jobs?.batch?.engine ?? 'unknown'),
            latest: String(jobs?.batch?.status ?? 'missing'),
          },
          {
            name: 'Stream',
            mode: String(jobs?.stream?.engine ?? 'unknown'),
            latest: String(jobs?.stream?.status ?? 'missing'),
          },
        ]

        const releaseReadiness = releaseStatus?.delivery_readiness ?? {}
        const disasterRecovery = haStatus?.disaster_recovery ?? {}
        const summary: SummaryBlock[] = [
          {
            label: 'AI 中台边界',
            value: `${serviceModes.filter((item) => item.status === '可独立部署').length} / ${serviceModes.length}`,
            hint: 'llm / rag / agent / embedding 已形成独立服务边界',
            tone: 'good',
          },
          {
            label: '流批作业',
            value: dataPipeline.map((item) => item.latest).join(' / '),
            hint: '本地 batch 与 stream 工件已接入状态面',
            tone: dataPipeline.every((item) => item.latest === 'completed') ? 'good' : 'warn',
          },
          {
            label: 'GraphRAG 后端',
            value: String(graphStatus?.storage_backend ?? 'UnknownGraphStore'),
            hint: '默认已切到持久化图索引，而非纯内存 mock',
            tone: graphStatus?.storage_backend === 'LocalGraphStore' ? 'good' : 'warn',
          },
          {
            label: 'Triton 状态',
            value: tritonStatus?.enabled ? '已启用' : '待接入',
            hint: tritonStatus?.endpoint ? `endpoint: ${String(tritonStatus.endpoint)}` : '缺真实 Triton 运行环境',
            tone: tritonStatus?.enabled ? 'warn' : 'warn',
          },
          {
            label: '发布门禁',
            value: String(releaseReadiness.latest_gate_status ?? '-'),
            hint: '统一发布门禁、监控 smoke 与交付状态聚合',
            tone: releaseReadiness.ready_for_deploy ? 'good' : 'warn',
          },
          {
            label: '灾备演练',
            value: disasterRecovery?.drill_ready ? '已演练' : '待继续',
            hint: 'deploy / rollback 本地演练工件已接入 HA 状态面',
            tone: disasterRecovery?.drill_ready ? 'good' : 'warn',
          },
        ]

        const risks = [
          !tritonStatus?.enabled ? 'T3-02 仍缺真实 Triton 服务实例。' : '',
          releaseReadiness?.ready_for_cutover ? '' : 'T6-01 仍缺 Kong 多环境真实接入与切流证据。',
          !releaseReadiness?.ready_for_deploy ? '发布门禁仍存在阻塞项，需要补环境或交付证据。' : '',
        ].filter(Boolean)

        setStatus({
          loading: false,
          error: null,
          summary,
          serviceModes,
          dataPipeline,
          delivery: {
            deployReady: Boolean(releaseReadiness.ready_for_deploy),
            cutoverReady: Boolean(releaseReadiness.ready_for_cutover),
            gateStatus: String(releaseReadiness.latest_gate_status ?? '-'),
            drillStatus: disasterRecovery?.drill_ready ? 'ready' : 'partial',
          },
          risks,
        })
      } catch (error) {
        setStatus({
          ...initialStatus,
          loading: false,
          error: error instanceof Error ? error.message : '蓝图总览加载失败',
        })
      }
    }

    void load()
  }, [])

  const keyMessage = useMemo(() => {
    if (status.loading) {
      return '正在汇总 AI 中台、数据平台与交付运维状态。'
    }
    if (status.error) {
      return '当前未拿到全部真状态，仍可继续浏览蓝图结构。'
    }
    return '现在可以直接从首页看到系统蓝图、状态面和剩余高价值阻塞。'
  }, [status.error, status.loading])

  return (
    <main className="blueprint-page">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">适用角色：运营 / 管理层 / 平台 / 管理员</span>
          <h1>企业级 AI 选品中枢蓝图</h1>
          <p className="hero-lead">
            把选品工作台、利润中枢、Agent 平台、知识库、报告中心和运营台收敛到同一前端壳层，
            并直接透出 AI 中台、数据平台、交付运维的真实状态。
          </p>
          <div className="hero-actions">
            <Link href="/workbench/selection" className="btn btn-primary">进入选品工作台</Link>
            <Link href="/dashboard" className="btn btn-secondary">查看利润中枢</Link>
          </div>
          <p className="hero-note">{keyMessage}</p>
        </div>

        <div className="hero-visual" aria-label="系统蓝图概览">
          <div className="visual-grid">
            <div className="visual-node visual-node-strong">
              <span>统一入口</span>
              <strong>Next.js App Shell</strong>
            </div>
            <div className="visual-node">
              <span>业务作业面</span>
              <strong>Selection / Reports</strong>
            </div>
            <div className="visual-node">
              <span>平台治理面</span>
              <strong>Agent / Operations</strong>
            </div>
            <div className="visual-node">
              <span>AI 能力层</span>
              <strong>LLM / RAG / Agent / Embedding</strong>
            </div>
            <div className="visual-node">
              <span>数据底座</span>
              <strong>Lakehouse / Batch / Stream</strong>
            </div>
            <div className="visual-node">
              <span>交付运维</span>
              <strong>Release / HA / Security</strong>
            </div>
          </div>
        </div>
      </section>

      {status.error ? <ErrorState message={status.error} /> : null}

      <section className="section-block">
        <div className="section-heading">
          <span className="eyebrow">状态总览</span>
          <h2>高价值任务状态面</h2>
          <p>优先展示你现在最关心的蓝图可见度、AI 中台拆分、数据平台作业和交付运维状态。</p>
        </div>
        <div className="summary-grid">
          {status.summary.map((item) => (
            <article key={item.label} className={`summary-tile summary-${item.tone ?? 'default'}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.hint}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block blueprint-columns">
        <div>
          <div className="section-heading compact">
            <span className="eyebrow">服务边界</span>
            <h2>AI 中台四分离</h2>
          </div>
          <div className="plain-list">
            {status.serviceModes.map((item) => (
              <div key={item.name} className="plain-row">
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.manifest}</p>
                </div>
                <div className="plain-meta">
                  <span>{item.mode}</span>
                  <span>{item.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="section-heading compact">
            <span className="eyebrow">数据平台</span>
            <h2>流批运行证据</h2>
          </div>
          <div className="plain-list">
            {status.dataPipeline.map((item) => (
              <div key={item.name} className="plain-row">
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.mode}</p>
                </div>
                <div className="plain-meta">
                  <span>{item.latest}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="delivery-strip">
            <div>
              <span>部署就绪</span>
              <strong>{status.delivery.deployReady ? 'ready' : 'blocked'}</strong>
            </div>
            <div>
              <span>切流就绪</span>
              <strong>{status.delivery.cutoverReady ? 'ready' : 'blocked'}</strong>
            </div>
            <div>
              <span>门禁状态</span>
              <strong>{status.delivery.gateStatus}</strong>
            </div>
            <div>
              <span>演练状态</span>
              <strong>{status.delivery.drillStatus}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <span className="eyebrow">正式入口</span>
          <h2>工作台矩阵</h2>
          <p>选品、利润、Agent、知识、报告、运营六类入口统一挂在同一工程壳层下，便于先看到完整蓝图。</p>
        </div>
        <div className="workbench-grid">
          {workbenches.map((item) => (
            <Link key={item.href} href={item.href} className="workbench-link">
              <span>{item.role}</span>
              <strong>{item.title}</strong>
              <p>{item.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="section-block final-block">
        <div>
          <span className="eyebrow">当前阻塞</span>
          <h2>剩余两类高价值卡点</h2>
        </div>
        <div className="risk-list">
          {status.risks.length > 0 ? status.risks.map((item) => <div key={item} className="risk-item">{item}</div>) : <div className="risk-item risk-good">当前高价值卡点已清空。</div>}
        </div>
      </section>
    </main>
  )
}
