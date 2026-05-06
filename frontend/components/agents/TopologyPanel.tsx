'use client'

type TopologyNode = { id: string; label: string; phase?: string; framework?: string; execution_mode?: string }
type TopologyEdge = { from: string; to: string; condition?: string }

const workflowNodeOrder = ['data_collection', 'market_analysis', 'product_planning', 'commercial_evaluation', 'risk_assessment', 'report_generation']

type TopologyData = {
  topology: { nodes: TopologyNode[]; edges: TopologyEdge[] }
  state_graph?: { supports?: string[] }
  agent_cost_summary?: { totals?: { tokens_used?: number; cost_usd?: number }; agents?: Array<{ agent?: string; tokens_used?: number; cost_usd?: number }> }
}

export default function TopologyPanel({ data }: { data: TopologyData }) {
  const nodes = data.topology.nodes
  const edges = data.topology.edges
  const costTotals = data.agent_cost_summary?.totals
  return (
    <div className="card">
      <h2>运行拓扑</h2>
      <div className="muted">LangGraph DAG 可视化</div>
      <p className="muted">当前 Agent 节点与流程边关系，覆盖断点、单步、Human-in-the-loop 与 Token/成本实时统计。</p>
      <div className="dag-canvas">
        {nodes.map((node, index) => (
          <div key={node.id} className="dag-node" style={{ gridColumn: (index % 3) + 1, gridRow: Math.floor(index / 3) + 1 }}>
            <strong>{node.label}</strong>
            <span>{node.phase ?? node.id}</span>
            <small>node_id={node.id}</small>
            <small>{node.framework ?? '-'} / {node.execution_mode ?? '-'}</small>
          </div>
        ))}
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div>
          <strong>边</strong>
          <ul>
            {edges.map((edge, idx) => (
              <li key={`${edge.from}-${edge.to}-${idx}`}>{edge.from} → {edge.to} / {edge.condition ?? 'success'}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>Token/成本实时统计</strong>
          <div className="metric-card" style={{ marginTop: 8 }}>
            <div className="metric-label">总 Token / 成本</div>
            <div className="metric-value">{costTotals?.tokens_used ?? 0} / ${costTotals?.cost_usd ?? 0}</div>
            <div className="metric-hint">agent_cost_summary</div>
          </div>
          <ul>
            {(data.agent_cost_summary?.agents ?? []).map((item) => (
              <li key={item.agent}>{item.agent}: {item.tokens_used ?? 0} tokens / ${item.cost_usd ?? 0}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="muted">支持能力：{data.state_graph?.supports?.join(', ') || '-'}</div>
    </div>
  )
}
