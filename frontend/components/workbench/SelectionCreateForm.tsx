'use client'

import { useState } from 'react'

import { apiFetch } from '@/lib/api'

export default function SelectionCreateForm() {
  const [query, setQuery] = useState('蓝牙耳机')
  const [targetMarket, setTargetMarket] = useState('US')
  const [message, setMessage] = useState<string | null>(null)

  const handleCreate = async () => {
    try {
      const result = await apiFetch<{ task_id: string; status: string }>(`/bff/workbench/selection/tasks`, {
        method: 'POST',
        body: JSON.stringify({
          query,
          category: 'electronics',
          investment_budget: 50000,
          target_market: targetMarket,
          auto_approve: false,
        }),
      })
      setMessage(`任务创建成功：${result.task_id}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '创建失败')
    }
  }

  return (
    <div className="card">
      <h2>创建任务</h2>
      <p className="muted">通过 BFF 创建任务并保持前后端契约统一。</p>
      <div className="grid grid-2">
        <input className="input" placeholder="产品关键词" value={query} onChange={(e) => setQuery(e.target.value)} />
        <input className="input" placeholder="目标市场" value={targetMarket} onChange={(e) => setTargetMarket(e.target.value)} />
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
        <button className="btn btn-primary" type="button" onClick={() => void handleCreate()}>通过 BFF 创建任务</button>
        {message ? <span className="muted">{message}</span> : null}
      </div>
    </div>
  )
}
