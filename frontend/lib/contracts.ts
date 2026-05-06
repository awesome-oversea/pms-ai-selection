export type TaskSummary = {
  task_id: string
  query: string
  status: string
  phase?: string
  created_at?: string
}

export type SelectionAccuracyTrendPoint = {
  date: string
  total: number
  correct: number
  accuracy: number
  cumulative_accuracy?: number
}

export type SelectionSummaryResponse = {
  tenant_id?: string
  username?: string
  total: number
  by_status: Record<string, number>
  recent_tasks: TaskSummary[]
  pending_approval_count?: number
  high_risk_count?: number
  avg_roi_year1_percent?: number | null
  go_decision_count?: number
  data_source?: string
  updated_at?: string | null
  accuracy_trend?: SelectionAccuracyTrendPoint[]
}

export type SelectionTaskListResponse = {
  total: number
  tasks: TaskSummary[]
}

export type SelectionWorkbenchSignal = {
  task_id: string
  trend_direction?: string
  decision?: string
  risk_count?: number
}

export type HistoricalPerformanceSummary = Record<string, unknown>

export type SelectionWorkbenchAgentStep = {
  task_id: string
  steps: Array<Record<string, unknown>>
}

export type SelectionWorkbenchStreamEvent = {
  summary: SelectionSummaryResponse
  tasks: SelectionTaskListResponse
  signals: SelectionWorkbenchSignal[]
  agent_steps: SelectionWorkbenchAgentStep[]
  reconnect: {
    retry_ms: number
    strategy: string
  }
  timestamp: string
}

export type TaskResult = {
  historical_performance?: HistoricalPerformanceSummary
  [key: string]: unknown
}

export type CloseLoopOverview = {
  historical_performance?: HistoricalPerformanceSummary
  [key: string]: unknown
}
