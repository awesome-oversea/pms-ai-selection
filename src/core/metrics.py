"""
Prometheus 自定义业务指标
========================

定义选品系统专用指标:
    - selection_tasks_total: 选品任务总数 (Counter, 标签: status)
    - agent_execution_duration_seconds: Agent 执行耗时 (Histogram)
    - llm_requests_total: LLM 调用次数 (Counter, 标签: model, status)

使用方式:
    from src.core.metrics import SELECTION_TASKS_TOTAL, AGENT_EXECUTION_DURATION

    SELECTION_TASKS_TOTAL.labels(status="created").inc()
    with AGENT_EXECUTION_DURATION.labels(agent="data_collection").time():
        await agent.run(...)
"""

from prometheus_client import Counter, Gauge, Histogram, Info


def _normalize_tenant_label(tenant_id: str | None) -> str:
    return tenant_id or "unknown"


_SELECTION_TERMINAL_RUNTIME: dict[str, dict[str, int]] = {}

# ---------------------------------------------------------------------------
# 选品任务指标
# ---------------------------------------------------------------------------

SELECTION_TASKS_TOTAL = Counter(
    "selection_tasks_total",
    "选品任务总数",
    labelnames=["status"],
)

SELECTION_TASK_DURATION_SECONDS = Histogram(
    "selection_task_duration_seconds",
    "选品任务端到端执行耗时(秒)",
    labelnames=["category"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

# ---------------------------------------------------------------------------
# Agent 执行指标
# ---------------------------------------------------------------------------

AGENT_EXECUTION_DURATION = Histogram(
    "agent_execution_duration_seconds",
    "Agent 单阶段执行耗时(秒)",
    labelnames=["agent"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

AGENT_EXECUTIONS_TOTAL = Counter(
    "agent_executions_total",
    "Agent 执行次数",
    labelnames=["agent", "status"],
)

# ---------------------------------------------------------------------------
# LLM 调用指标
# ---------------------------------------------------------------------------

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "LLM 调用次数",
    labelnames=["model", "status"],
)

LLM_REQUEST_DURATION_SECONDS = Histogram(
    "llm_request_duration_seconds",
    "LLM 单次调用耗时(秒)",
    labelnames=["model"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "LLM 消耗 token 总量",
    labelnames=["model", "type"],  # label values: prompt / completion
)

LLM_COST_USD_TOTAL = Counter(
    "llm_cost_usd_total",
    "LLM 成本累计(USD)",
    labelnames=["tenant_id", "provider", "model"],
)

LLM_BUDGET_REJECTED_TOTAL = Counter(
    "llm_budget_rejected_total",
    "因租户预算不足被拒绝的 LLM 调用次数",
    labelnames=["tenant_id", "quota_type"],
)

# ---------------------------------------------------------------------------
# 系统信息
# ---------------------------------------------------------------------------

APP_INFO = Info(
    "pms_app",
    "PMS 应用基本信息",
)

ACTIVE_TASKS_GAUGE = Gauge(
    "selection_active_tasks",
    "当前正在执行的选品任务数",
)

SELECTION_TASK_RUNNING_GAUGE = Gauge(
    "selection_task_running_by_tenant",
    "按租户统计的运行中选品任务数",
    labelnames=["tenant_id"],
)

SELECTION_TASK_BACKLOG_GAUGE = Gauge(
    "selection_task_backlog_by_tenant",
    "按租户统计的待执行/可重试选品任务堆积数",
    labelnames=["tenant_id"],
)

SELECTION_TASK_THROTTLED_TOTAL = Counter(
    "selection_task_throttled_total",
    "因并发治理被限流跳过的任务次数",
    labelnames=["tenant_id", "reason"],
)

API_REQUEST_ERRORS_TOTAL = Counter(
    "api_request_errors_total",
    "API 错误响应总数",
    labelnames=["path", "method", "status"],
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "api_request_duration_seconds",
    "API 请求耗时(秒)",
    labelnames=["path", "method", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

VLLM_TOKENS_PROCESSED = Counter(
    "vllm_tokens_processed",
    "vLLM 路由累计处理 token 数",
    labelnames=["tier", "provider", "model"],
)

QDRANT_SEARCH_DURATION_SECONDS = Histogram(
    "qdrant_search_duration_seconds",
    "Qdrant 检索耗时(秒)",
    labelnames=["collection", "mode", "status"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

KAFKA_CONSUMER_LAG = Gauge(
    "kafka_consumer_lag",
    "Kafka 消费堆积/待消费消息数",
    labelnames=["topic", "consumer_group"],
)

SELECTION_SUCCESS_RATE = Gauge(
    "selection_success_rate",
    "选品任务成功率",
    labelnames=["tenant_id"],
)

SELECTION_ACCURACY = Gauge(
    "selection_accuracy",
    "选品准确率",
    labelnames=["tenant_id"],
)

DEPENDENCY_HEALTH_GAUGE = Gauge(
    "dependency_health_gauge",
    "依赖健康状态(healthy=1/unhealthy=0)",
    labelnames=["name"],
)

WORKER_PROCESSED_TOTAL = Counter(
    "worker_processed_total",
    "Worker 处理任务总数",
    labelnames=["status"],
)

KNOWLEDGE_QUERY_TOTAL = Counter(
    "knowledge_query_total",
    "知识库查询总数",
    labelnames=["mode", "status"],
)

KNOWLEDGE_QUERY_HIT_RATE = Gauge(
    "knowledge_query_hit_rate",
    "知识库查询命中率",
)

SELECTION_GO_DECISION_TOTAL = Counter(
    "selection_go_decision_total",
    "选品 GO/NO-GO 决策总数",
    labelnames=["decision"],
)

TENANT_TASK_TOTAL = Counter(
    "tenant_task_total",
    "租户维度任务总量",
    labelnames=["tenant_id", "status"],
)

TENANT_LLM_COST_USD_TOTAL = Counter(
    "tenant_llm_cost_usd_total",
    "租户维度 LLM 成本累计",
    labelnames=["tenant_id"],
)

TENANT_LLM_TOKENS_TOTAL = Counter(
    "tenant_llm_tokens_total",
    "租户维度 LLM tokens 累计",
    labelnames=["tenant_id"],
)

AGENT_TOKENS_TOTAL = Counter(
    "agent_tokens_total",
    "Agent 维度 token 累计",
    labelnames=["agent", "tenant_id"],
)

AGENT_COST_USD_TOTAL = Counter(
    "agent_cost_usd_total",
    "Agent 维度成本累计(USD)",
    labelnames=["agent", "tenant_id"],
)

AGENT_ACTIVE_WORKFLOWS = Gauge(
    "agent_active_workflows",
    "Agent 工作流活跃数量",
    labelnames=["framework"],
)

INFERENCE_ROUTE_HEALTH = Gauge(
    "inference_route_health",
    "推理路由健康分值(healthy=1/degraded=0.5/evicted=0)",
    labelnames=["route"],
)

DATA_PLATFORM_JOB_RECORDS = Gauge(
    "data_platform_job_records",
    "数据平台作业记录数/事件数",
    labelnames=["job_type", "asset"],
)


def observe_api_request(path: str, method: str, status: int, duration_seconds: float) -> None:
    API_REQUEST_DURATION_SECONDS.labels(
        path=path,
        method=method,
        status=str(status),
    ).observe(max(duration_seconds, 0.0))
    if status >= 400:
        API_REQUEST_ERRORS_TOTAL.labels(
            path=path,
            method=method,
            status=str(status),
        ).inc()


def observe_qdrant_search(collection: str, mode: str, status: str, duration_seconds: float) -> None:
    QDRANT_SEARCH_DURATION_SECONDS.labels(
        collection=collection,
        mode=mode,
        status=status,
    ).observe(max(duration_seconds, 0.0))


def set_kafka_consumer_lag(topic: str, consumer_group: str, lag: int) -> None:
    KAFKA_CONSUMER_LAG.labels(topic=topic, consumer_group=consumer_group).set(max(0, lag))


def record_selection_created(tenant_id: str | None) -> None:
    resolved_tenant = _normalize_tenant_label(tenant_id)
    SELECTION_TASKS_TOTAL.labels(status="created").inc()
    TENANT_TASK_TOTAL.labels(tenant_id=resolved_tenant, status="created").inc()


def update_selection_running_metrics(tenant_id: str | None, running: int, backlog: int | None = None) -> None:
    resolved_tenant = _normalize_tenant_label(tenant_id)
    SELECTION_TASK_RUNNING_GAUGE.labels(tenant_id=resolved_tenant).set(max(0, running))
    ACTIVE_TASKS_GAUGE.set(max(0, running))
    if backlog is not None:
        SELECTION_TASK_BACKLOG_GAUGE.labels(tenant_id=resolved_tenant).set(max(0, backlog))


def record_selection_terminal_status(tenant_id: str | None, status: str) -> None:
    resolved_tenant = _normalize_tenant_label(tenant_id)
    normalized_status = status if status in {"completed", "failed", "cancelled"} else "failed"
    TENANT_TASK_TOTAL.labels(tenant_id=resolved_tenant, status=normalized_status).inc()
    runtime = _SELECTION_TERMINAL_RUNTIME.setdefault(resolved_tenant, {"completed": 0, "failed": 0, "cancelled": 0})
    runtime[normalized_status] = runtime.get(normalized_status, 0) + 1
    total = sum(runtime.values())
    success = runtime.get("completed", 0)
    SELECTION_SUCCESS_RATE.labels(tenant_id=resolved_tenant).set(round(success / total, 6) if total else 0.0)


def set_selection_accuracy_metric(tenant_id: str | None, accuracy: float) -> None:
    resolved_tenant = _normalize_tenant_label(tenant_id)
    bounded = max(0.0, min(1.0, accuracy))
    SELECTION_ACCURACY.labels(tenant_id=resolved_tenant).set(bounded)


def init_app_info(name: str, version: str, environment: str):
    """在应用启动时设置一次性信息指标。"""
    APP_INFO.info({
        "name": name,
        "version": version,
        "environment": environment,
    })
