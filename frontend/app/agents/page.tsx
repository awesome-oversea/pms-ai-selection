'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'

import ActionCenterPanel from '@/components/agents/ActionCenterPanel'
import FrameworkPanel from '@/components/agents/FrameworkPanel'
import OperationsPanel from '@/components/agents/OperationsPanel'
import StrategyPanel from '@/components/agents/StrategyPanel'
import TopologyPanel from '@/components/agents/TopologyPanel'
import LogPanel from '@/components/agents/LogPanel'
import WorkflowDebugPanel from '@/components/agents/WorkflowDebugPanel'
import AuthGuard from '@/components/common/AuthGuard'
import ErrorState from '@/components/common/ErrorState'
import { apiFetch } from '@/lib/api'

export default function AgentsPage() {
  const [topology, setTopology] = useState<any>(null)
  const [operations, setOperations] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const [topologyData, operationsData] = await Promise.all([
        apiFetch('/agents/platform/topology'),
        apiFetch('/agents/platform/operations'),
      ])
      setTopology(topologyData)
      setOperations(operationsData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent 平台加载失败')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <AuthGuard>
      <main className="container">
        <div className="card">
          <h1>Agent 平台</h1>
          <p className="muted">平台/管理员角色的 Agent 运行诊断、人工介入与策略治理入口。</p>
          <div className="nav">
            <Link href="/workbench/selection">返回选品工作台</Link>
            <Link href="/dashboard">查看数据大盘</Link>
            <Link href="/operations">查看运营台</Link>
            <button className="btn btn-secondary" type="button" onClick={() => void load()}>刷新平台状态</button>
          </div>
        </div>
        {error ? <ErrorState message={error} /> : null}
        {topology ? <TopologyPanel data={topology} /> : <div className="card">正在加载拓扑...</div>}
        {operations ? <OperationsPanel data={operations} /> : <div className="card">正在加载诊断...</div>}
        {operations ? <LogPanel data={operations} /> : null}
        <WorkflowDebugPanel />
        {operations ? <ActionCenterPanel data={operations} onChanged={load} /> : null}
        {topology ? <FrameworkPanel data={topology} /> : null}
        {topology ? <StrategyPanel data={topology} /> : null}
      </main>
    </AuthGuard>
  )
}
