'use client'

export default function StrategyPanel({ data }: { data: { strategy_version?: number; strategy?: Record<string, unknown> } }) {
  return (
    <div className="card">
      <h2>策略视图</h2>
      <p className="muted">展示当前策略版本与生效内容。</p>
      <div><strong>当前版本：</strong>{data.strategy_version ?? 0}</div>
      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#f3f4f6', padding: 12, borderRadius: 8, marginTop: 12 }}>
        {JSON.stringify(data.strategy ?? {}, null, 2)}
      </pre>
    </div>
  )
}
