type DashboardChart = {
  type?: string
  title?: string
  xAxis?: string[]
  series?: number[]
  items?: Array<{ name: string; value: number }>
}

function BarChartCard({ title, labels = [], values = [] }: { title: string; labels?: string[]; values?: number[] }) {
  const max = Math.max(...values, 1)
  return (
    <div className="card chart-card">
      <h2>{title}</h2>
      <div className="bar-chart">
        {labels.map((label, index) => {
          const value = values[index] ?? 0
          const width = `${Math.max((value / max) * 100, value > 0 ? 8 : 0)}%`
          return (
            <div key={`${label}-${index}`} className="bar-row">
              <div className="bar-label">{label}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width }} />
              </div>
              <div className="bar-value">{value}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LineTrendCard({ title, labels = [], values = [] }: { title: string; labels?: string[]; values?: number[] }) {
  const max = Math.max(...values, 1)
  return (
    <div className="card chart-card">
      <h2>{title}</h2>
      <div className="spark-grid">
        {labels.map((label, index) => {
          const value = values[index] ?? 0
          const height = `${Math.max((value / max) * 100, value > 0 ? 12 : 0)}%`
          return (
            <div key={`${label}-${index}`} className="spark-col">
              <div className="spark-value">{value}</div>
              <div className="spark-bar-wrap">
                <div className="spark-bar" style={{ height }} />
              </div>
              <div className="spark-label">{label}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PieLikeCard({ title, items = [] }: { title: string; items?: Array<{ name: string; value: number }> }) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1
  return (
    <div className="card chart-card">
      <h2>{title}</h2>
      <div className="stack-list">
        {items.map((item) => {
          const width = `${Math.max((item.value / total) * 100, 8)}%`
          return (
            <div key={item.name} className="stack-row">
              <div className="stack-header">
                <span>{item.name}</span>
                <span>{item.value}</span>
              </div>
              <div className="stack-track">
                <div className="stack-fill" style={{ width }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RankingChartCard({ title, items = [] }: { title: string; items?: Array<{ name: string; value: number }> }) {
  const sorted = [...items].sort((left, right) => right.value - left.value)
  const max = Math.max(...sorted.map((item) => item.value), 1)
  return (
    <div className="card chart-card">
      <h2>{title}</h2>
      <div className="ranking-list">
        {sorted.map((item, index) => {
          const width = `${Math.max((item.value / max) * 100, 12)}%`
          return (
            <div key={item.name} className="ranking-row">
              <div className="ranking-rank">#{index + 1}</div>
              <div className="ranking-name">{item.name}</div>
              <div className="ranking-track">
                <div className="ranking-fill" style={{ width }} />
              </div>
              <div className="ranking-value">{item.value}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ProgressChartCard({ title, items = [] }: { title: string; items?: Array<{ name: string; value: number }> }) {
  return (
    <div className="card chart-card">
      <h2>{title}</h2>
      <div className="progress-list">
        {items.map((item) => {
          const width = `${Math.min(Math.max(item.value, 0), 100)}%`
          return (
            <div key={item.name} className="progress-row">
              <div className="progress-header">
                <span>{item.name}</span>
                <span>{item.value}%</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function DashboardCharts({ charts }: { charts: Record<string, DashboardChart | undefined> }) {
  const orderedCharts = [
    charts.trend_chart,
    charts.profit_chart,
    charts.risk_chart,
    charts.competitor_chart,
    charts.execution_chart,
  ].filter(Boolean) as DashboardChart[]

  return (
    <div className="grid grid-2">
      {orderedCharts.map((chart, index) => {
        const key = `${chart.title ?? 'chart'}-${index}`
        if (chart.type === 'line') {
          return <LineTrendCard key={key} title={chart.title ?? '趋势热度'} labels={chart.xAxis} values={chart.series} />
        }
        if (chart.type === 'pie') {
          return <PieLikeCard key={key} title={chart.title ?? '风险分布'} items={chart.items} />
        }
        if (chart.type === 'ranking') {
          return <RankingChartCard key={key} title={chart.title ?? '榜单'} items={chart.items} />
        }
        if (chart.type === 'progress') {
          return <ProgressChartCard key={key} title={chart.title ?? '进度总览'} items={chart.items} />
        }
        return <BarChartCard key={key} title={chart.title ?? '柱状图'} labels={chart.xAxis} values={chart.series} />
      })}
    </div>
  )
}
