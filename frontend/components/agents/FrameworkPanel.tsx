export default function FrameworkPanel({ data }: { data: { frameworks?: Record<string, { type?: string; status?: string; use_cases?: string[]; notes?: string }>; workflow_registry?: Record<string, { active_framework?: string; fallback_framework?: string; runtime_mode?: string }> } }) {
  const frameworks = data.frameworks ?? {}
  const workflows = data.workflow_registry ?? {}

  return (
    <div className="card">
      <h2>编排框架生态</h2>
      <p className="muted">展示当前原生编排与外部兼容框架的接入状态。</p>
      <div className="grid grid-2">
        <div>
          <strong>框架注册表</strong>
          <ul>
            {Object.entries(frameworks).map(([key, value]) => (
              <li key={key}>{key} / {value.type ?? '-'} / {value.status ?? '-'} / {(value.use_cases ?? []).join(', ')}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>工作流映射</strong>
          <ul>
            {Object.entries(workflows).map(([key, value]) => (
              <li key={key}>{key} → {value.active_framework ?? '-'}（fallback: {value.fallback_framework ?? '-'}）</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
