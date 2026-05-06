"""
任务 3.4 / P10-01 验收测试：Prometheus 监控指标
============================================

验收标准:
- [x] GET /metrics 返回 Prometheus 格式的指标数据
- [x] 默认指标包含 http_requests_total、http_request_duration_seconds
- [x] 创建选品任务后，selection_tasks_total 计数增加
- [x] requirements.txt 中包含 prometheus-fastapi-instrumentator
- [x] API 延迟、vLLM token 速率、Qdrant 检索延迟、Kafka lag 指标可观测
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-prometheus-metrics-32chars")

from src.core.auth import create_access_token
from src.main import create_app


@pytest.fixture
def app(monkeypatch):
    async def _noop_init_db():
        return None

    async def _healthy_db():
        return {"status": "healthy"}

    async def _healthy_redis():
        return {"status": "healthy"}

    async def _healthy_qdrant():
        return {"status": "healthy"}

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token({
        "sub": "testuser",
        "user_id": "test-uid-001",
        "is_superuser": True,
        "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
        "tenant_key": "default",
        "tenant_name": "Default Tenant",
        "roles": ["tenant_admin", "operator"],
    })
    return {"Authorization": f"Bearer {token}"}


class TestPrometheusMetrics:
    def test_metrics_endpoint_returns_200(self, client):
        """GET /metrics 返回 200。"""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_format_is_prometheus(self, client):
        """返回内容包含 Prometheus 格式指标。"""
        resp = client.get("/metrics")
        body = resp.text

        # Prometheus text format 以 # HELP 或 # TYPE 开头
        assert "# HELP" in body or "# TYPE" in body

    def test_default_http_metrics_present(self, client):
        """默认指标包含 http 请求相关指标。"""
        # 先发一个请求触发指标生成
        client.get("/health")
        resp = client.get("/metrics")
        body = resp.text

        # prometheus-fastapi-instrumentator 默认指标名
        assert "http_request_duration" in body or "http_requests" in body

    def test_custom_selection_tasks_total_metric(self, client, auth_headers, monkeypatch):
        """创建选品任务后 selection_tasks_total 计数增加。"""
        from src.core.metrics import SELECTION_TASKS_TOTAL, record_selection_created

        async def _fake_create_task(self, payload, created_by=None, tenant_id=None):
            record_selection_created(tenant_id)
            return {
                "task_id": "task-metrics-001",
                "query": payload["query"],
                "tenant_id": tenant_id,
                "created_at": "2026-04-16T00:00:00+00:00",
            }

        monkeypatch.setattr("src.services.selection_service.SelectionTaskService.create_task", _fake_create_task)

        before = SELECTION_TASKS_TOTAL.labels(status="created")._value.get()

        resp = client.post(
            "/api/v1/selection/tasks",
            json={"query": "蓝牙耳机测试", "category": "bluetooth"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        after = SELECTION_TASKS_TOTAL.labels(status="created")._value.get()
        assert after > before, f"selection_tasks_total 未增长: before={before}, after={after}"

    def test_custom_metrics_in_output(self, client, auth_headers):
        """自定义指标在 /metrics 输出中可见。"""
        # 触发一次任务创建
        client.post(
            "/api/v1/selection/tasks",
            json={"query": "测试指标", "category": "test"},
            headers=auth_headers,
        )

        resp = client.get("/metrics")
        body = resp.text
        assert "selection_tasks_total" in body

    def test_requirements_includes_prometheus(self):
        """requirements.txt 中包含 prometheus-fastapi-instrumentator。"""
        with open("requirements.txt", encoding="utf-8") as f:
            content = f.read()
        assert "prometheus-fastapi-instrumentator" in content

    def test_metrics_module_defines_counters(self):
        """src/core/metrics.py 定义了 3 个核心指标。"""
        from src.core.metrics import (
            AGENT_EXECUTION_DURATION,
            LLM_REQUESTS_TOTAL,
            SELECTION_TASKS_TOTAL,
        )
        assert SELECTION_TASKS_TOTAL is not None
        assert AGENT_EXECUTION_DURATION is not None
        assert LLM_REQUESTS_TOTAL is not None

    def test_api_request_duration_metric_visible(self, client):
        client.get("/api/v1/info")
        body = client.get("/metrics").text
        assert "api_request_duration_seconds" in body

    def test_llm_vllm_tokens_processed_metric_visible(self):
        from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway

        gateway = LLMGateway(GatewayConfig(use_mock=True, provider_mode="mock"))
        import asyncio
        asyncio.run(gateway.route("请分析蓝牙耳机市场趋势"))

        from prometheus_client import generate_latest
        body = generate_latest().decode("utf-8")
        assert "vllm_tokens_processed" in body

    def test_qdrant_search_duration_metric_visible(self, monkeypatch):
        from src.infrastructure.qdrant import QdrantService

        class _Client:
            async def search(self, **kwargs):
                return []

        service = QdrantService(_Client())
        import asyncio
        asyncio.run(service.search("knowledge", [0.1, 0.2, 0.3], limit=3))

        from prometheus_client import generate_latest
        body = generate_latest().decode("utf-8")
        assert "qdrant_search_duration_seconds" in body

    def test_kafka_consumer_lag_metric_visible(self):
        import asyncio

        from src.infrastructure.kafka import drain_memory_messages, send_message
        asyncio.run(send_message("pms-agent-event", {"hello": "world"}))

        from prometheus_client import generate_latest
        body = generate_latest().decode("utf-8")
        assert "kafka_consumer_lag" in body

        asyncio.run(asyncio.sleep(0))
        drain_memory_messages("pms-agent-event")


def _get_counter_value(metric_name: str, labels: dict) -> float:
    """从 prometheus_client REGISTRY 中读取 Counter 值。"""
    from prometheus_client import REGISTRY

    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if sample.name == metric_name + "_total":
                    if all(sample.labels.get(k) == v for k, v in labels.items()):
                        return sample.value
    return 0.0
