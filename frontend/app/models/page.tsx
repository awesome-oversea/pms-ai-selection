'use client'

import { useState } from 'react'
import Link from 'next/link'

import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

type ModelRegistryResponse = {
  version?: number
  active_model_version?: string
  active_api_model_name?: string
  models?: Array<{ version?: string; api_model_name?: string; status?: string }>
  description?: string
}

export default function ModelsPage() {
  const [registry, setRegistry] = useState<ModelRegistryResponse | null>(null)
  const [form, setForm] = useState({
    active_model_version: 'qwen2.5-72b-v3',
    active_api_model_name: 'Qwen2.5-72B-Instruct',
    description: '分析师调优发布',
    models_json: JSON.stringify([
      { version: 'qwen2.5-72b-v2', api_model_name: 'Qwen2.5-72B-Instruct', status: 'history' },
      { version: 'qwen2.5-72b-v3', api_model_name: 'Qwen2.5-72B-Instruct', status: 'active' },
    ], null, 2),
    train_goal: '提升选品准确率与评价案例召回',
    train_dataset: 'selection_cases + review_cases + execution_feedback',
  })
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const loadRegistry = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<ModelRegistryResponse>('/llm/model-registry/default')
      setRegistry(data)
      setMessage('模型注册中心已刷新。')
    } catch (e) {
      setError(e instanceof Error ? e.message : '模型注册中心加载失败')
    } finally {
      setLoading(false)
    }
  }

  const publishRegistry = async () => {
    setLoading(true)
    setError(null)
    try {
      const models = JSON.parse(form.models_json)
      const data = await apiFetch<ModelRegistryResponse>('/llm/model-registry/default/publish', {
        method: 'POST',
        body: JSON.stringify({
          active_model_version: form.active_model_version,
          active_api_model_name: form.active_api_model_name,
          models,
          description: form.description,
        }),
      })
      setRegistry(data)
      setMessage(`已发布模型版本：${data.active_model_version}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '发布模型版本失败')
    } finally {
      setLoading(false)
    }
  }

  const rollbackRegistry = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<ModelRegistryResponse>('/llm/model-registry/default/rollback', {
        method: 'POST',
      })
      setRegistry(data)
      setMessage(`已回滚到模型版本：${data.active_model_version}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '回滚模型版本失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <main className="container section-stack">
        <div className="card">
          <h1>模型训练 / 调优页面</h1>
          <p className="muted">覆盖 B13-24，并复用 B8-26 模型注册中心能力，提供训练计划记录、版本发布与回滚可视化。</p>
          <div className="nav">
            <Link href="/analyst">分析师工作台</Link>
            <Link href="/operations">运营台</Link>
            <Link href="/agents">Agent 平台</Link>
          </div>
        </div>

        {error ? <ErrorState message={error} /> : null}
        {message ? <div className="card"><div className="muted">{message}</div></div> : null}

        <div className="grid grid-2">
          <div className="card">
            <h2>训练计划</h2>
            <div className="form-grid">
              <input className="input" value={form.train_goal} onChange={(e) => setForm((s) => ({ ...s, train_goal: e.target.value }))} placeholder="训练目标" />
              <input className="input" value={form.train_dataset} onChange={(e) => setForm((s) => ({ ...s, train_dataset: e.target.value }))} placeholder="训练数据集" />
              <input className="input" value={form.active_model_version} onChange={(e) => setForm((s) => ({ ...s, active_model_version: e.target.value }))} placeholder="模型版本号" />
              <input className="input" value={form.active_api_model_name} onChange={(e) => setForm((s) => ({ ...s, active_api_model_name: e.target.value }))} placeholder="API模型名" />
            </div>
            <textarea className="textarea" rows={10} value={form.models_json} onChange={(e) => setForm((s) => ({ ...s, models_json: e.target.value }))} />
            <div className="action-row">
              <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void loadRegistry()}>查询注册中心</button>
              <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void publishRegistry()}>发布新版本</button>
              <button className="btn btn-danger" type="button" disabled={loading} onClick={() => void rollbackRegistry()}>回滚版本</button>
            </div>
          </div>

          <div className="card">
            <h2>当前模型注册中心</h2>
            <div className="grid grid-2">
              <div className="metric-card">
                <div className="metric-label">注册中心版本</div>
                <div className="metric-value">{registry?.version ?? 0}</div>
                <div className="metric-hint">配置中心版本号</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">激活模型版本</div>
                <div className="metric-value">{registry?.active_model_version ?? '-'}</div>
                <div className="metric-hint">当前生效模型</div>
              </div>
            </div>
            <div style={{ marginTop: 12 }}><strong>API模型名：</strong>{registry?.active_api_model_name ?? '-'}</div>
            <div style={{ marginTop: 12 }}><strong>说明：</strong>{registry?.description ?? '-'}</div>
            <pre className="code-panel">{JSON.stringify(registry?.models ?? [], null, 2)}</pre>
          </div>
        </div>
      </main>
    </AuthGuard>
  )
}
