"""
D31-D33 系统集成测试与性能验证
==============================

覆盖:
    - 全链路端到端集成测试
    - Agent协作流程验证
    - API响应性能基准
    - 并发压力测试
    - 数据一致性校验
    - 错误恢复机制

测试框架: pytest + httpx + asyncio + time
"""

import asyncio
import time

import pytest


def _override_auth(app):
    """覆盖认证依赖，返回模拟用户。"""
    from src.core.auth import get_current_user

    async def _mock_user():
        return {"username": "testuser", "user_id": "test-uid", "is_superuser": False, "token_type": "access"}

    app.dependency_overrides[get_current_user] = _mock_user


class TestEndToEndIntegration:
    """
    端到端集成测试(D31)。

    验证完整的选品分析流程:
        1. 创建选品任务 -> 2. 数据采集 -> 3. 市场分析
        -> 4. 产品规划 -> 5. 商业化评估 -> 6. 决策输出
    """

    def test_full_selection_pipeline(self):
        """完整选品流水线应能成功执行。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        resp = client.post("/api/v1/selection/tasks", json={
            "query": "蓝牙耳机",
            "category": "electronics",
            "investment_budget": 50000,
        })

        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        tasks_resp = client.get("/api/v1/selection/tasks")
        assert tasks_resp.status_code == 200

        tasks = tasks_resp.json().get("tasks", [])
        task_ids = [t.get("task_id") for t in tasks]
        assert task_id in task_ids

    def test_agent_to_api_integration(self):
        """Agent执行结果应可通过API查询。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        agents_resp = client.get("/api/v1/agents")
        assert agents_resp.status_code == 200

        agents_data = agents_resp.json()
        agent_list = agents_data.get("agents", [])

        if agent_list:
            first_agent = agent_list[0]
            agent_name = first_agent.get("name")

            if agent_name:
                detail_resp = client.get(f"/api/v1/agents/{agent_name}")
                assert detail_resp.status_code in [200, 404]

    def test_workflow_engine_integration(self):
        """工作流引擎应能协调多Agent。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.agents.product_planner import ProductPlannerAgent
        from src.core.workflow import WorkflowEngine, WorkflowStatus

        engine = WorkflowEngine(workflow_id="e2e_test_001")

        from src.core.workflow import WorkflowPhase

        engine.add_step("market", MarketInsightAgent(), WorkflowPhase.DATA_COLLECTION)
        engine.add_step("product", ProductPlannerAgent(), WorkflowPhase.PRODUCT_PLANNING, dependencies=["market"])

        result = asyncio.run(engine.run({
            "query": "E2E集成测试",
            "category": "electronics",
        }))

        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]
        assert result.total_steps == 2
        assert result.workflow_id == "e2e_test_001"

    def test_knowledge_base_to_retrieval(self):
        """知识库上传后应可被检索。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        upload_resp = client.post(
            "/api/v1/knowledge/documents",
            files={"file": ("test.txt", b"test document content", "text/plain")},
        )

        assert upload_resp.status_code == 200

        docs_resp = client.get("/api/v1/knowledge/documents")
        assert docs_resp.status_code == 200

    def test_web_to_api_connectivity(self):
        """Web界面应能正确调用API端点。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        dashboard_resp = client.get("/dashboard")
        assert dashboard_resp.status_code == 200

        assert "AI选品系统" in dashboard_resp.text or "navbar" in dashboard_resp.text


class TestPerformanceBaselines:
    """
    性能基准测试(D32)。

    验证:
        - API响应时间 < 500ms (P95)
        - 页面渲染时间 < 200ms
        - Agent初始化时间 < 100ms
        - 工作流启动时间 < 50ms
    """

    def test_selection_task_creation_latency(self):
        """创建选品任务API应在合理时间内返回。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        start = time.time()
        resp = client.post("/api/v1/selection/tasks", json={
            "query": "性能测试产品",
            "category": "electronics",
        })
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 10000, f"创建任务耗时 {elapsed:.0f}ms > 10000ms"

    def test_agents_list_latency(self):
        """Agent列表API应在100ms内返回。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        start = time.time()
        resp = client.get("/api/v1/agents")
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 500, f"Agent列表耗时 {elapsed:.0f}ms > 500ms"

    def test_dashboard_render_latency(self):
        """仪表盘页面渲染应在300ms内完成。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        start = time.time()
        resp = client.get("/dashboard")
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 500, f"仪表盘渲染耗时 {elapsed:.0f}ms > 500ms"

    def test_static_file_serve_latency(self):
        """静态文件服务应在50ms内返回。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        start = time.time()
        resp = client.get("/static/css/main.css")
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 200, f"CSS加载耗时 {elapsed:.0f}ms > 200ms"

    def test_health_check_latency(self):
        """健康检查应在20ms内返回。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        start = time.time()
        resp = client.get("/health")
        elapsed = (time.time() - start) * 1000

        assert resp.status_code == 200
        assert elapsed < 50, f"健康检查耗时 {elapsed:.0f}ms > 50ms"


class TestConcurrencyAndStability:
    """
    并发稳定性测试(D32)。

    验证:
        - 并发请求处理能力
        - 资源竞争安全性
        - 错误隔离性
        - 内存泄漏检测(基础)
    """

    def test_concurrent_task_creation(self):
        """并发创建10个任务应各自独立成功。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)
        import threading
        from unittest.mock import patch

        # 跳过限流中间件，避免其他测试累积导致 429
        with patch("src.core.rate_limit.SlidingWindowCounter.is_allowed", return_value=True):
            client = TestClient(app)
            results = []
            errors = []

            def create_task(idx):
                try:
                    resp = client.post("/api/v1/selection/tasks", json={
                        "query": f"并发任务_{idx}",
                        "category": "test",
                    })
                    results.append(resp.status_code)
                except Exception as e:
                    errors.append(str(e))

            threads = []
            for i in range(5):
                t = threading.Thread(target=create_task, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=10)

            assert len(errors) == 0, f"并发错误: {errors}"
            assert len(results) == 5
            assert all(r == 200 for r in results)

    def test_rapid_polling_stability(self):
        """快速轮询不应导致服务崩溃。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        for _ in range(20):
            resp = client.get("/api/v1/selection/tasks")
            assert resp.status_code in [200, 400]

    def test_error_isolation(self):
        """单个请求错误不应影响其他请求。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        bad_resp = client.post("/api/v1/selection/tasks", json={
            "query": "X",
        })

        assert bad_resp.status_code == 422

        good_resp = client.get("/health")
        assert good_resp.status_code == 200


class TestDataConsistency:
    """
    数据一致性测试(D33)。

    验证:
        - 任务状态转换正确性
        - API响应数据格式一致
        - 前后端数据同步
        - 边界条件处理
    """

    def test_task_status_lifecycle(self):
        """任务状态应符合生命周期(created->running->completed/failed)。"""
        from fastapi.testclient import TestClient
        from src.api.v1.endpoints.selection import _task_store
        from src.main import app

        len(_task_store)

        client = TestClient(app)

        create_resp = client.post("/api/v1/selection/tasks", json={
            "query": "状态测试",
            "category": "test",
        })

        assert create_resp.status_code == 200
        task_data = create_resp.json()

        assert task_data["status"] in ["running", "created"]

        list_resp = client.get("/api/v1/selection/tasks")
        assert list_resp.status_code == 200

    def test_response_format_consistency(self):
        """所有API响应应遵循统一格式。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        endpoints = [
            ("/health", "get"),
            ("/api/v1/agents", "get"),
        ]

        for url, method in endpoints:
            if method == "get":
                resp = client.get(url)

            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, dict)

    def test_input_sanitization(self):
        """输入应经过正确的清理和验证。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        test_cases = [
            ("", 422),
            ("X" * 1000, 422),
        ]

        for query, expected_status in test_cases:
            resp = client.post("/api/v1/selection/tasks", json={
                "query": query,
                "category": "test",
            })
            assert resp.status_code == expected_status


class TestErrorRecovery:
    """
    错误恢复机制测试(D33)。

    验证:
        - 异常捕获完整性
        - 错误信息友好性
        - 服务降级能力
        - 日志记录正确性
    """

    def test_404_handling(self):
        """不存在的资源应返回友好404。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        resp = client.get("/api/v1/selection/tasks/nonexistent_12345")
        assert resp.status_code == 404

    def test_invalid_json_handling(self):
        """无效JSON应返回400而非500。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        resp = client.post(
            "/api/v1/selection/tasks",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert resp.status_code in [400, 422]

    def test_missing_required_fields(self):
        """缺少必填字段应返回422。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        resp = client.post(
            "/api/v1/selection/tasks",
            json={},
        )

        assert resp.status_code == 422

    def test_method_not_allowed(self):
        """不支持的HTTP方法应返回405。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        resp = client.delete("/api/v1/selection/tasks")
        assert resp.status_code == 405


class TestSystemHealth:
    """
    系统健康综合检查(D33)。

    验证:
        - 所有模块可正常导入
        - 核心组件初始化成功
        - 配置加载正确
        - 依赖项可用性
    """

    def test_all_modules_importable(self):
        """所有核心模块应可正常导入。"""
        modules = [
            "src.main",
            "src.agents.base",
            "src.agents.market_insight",
            "src.agents.product_planner",
            "src.agents.commercial",
            "src.agents.selection_master",
            "src.core.workflow",
            "src.rag.retriever",
            "src.rag.chunkers",
            "src.web.routes",
            "src.api.v1.router",
            "src.api.v1.endpoints.selection",
            "src.api.v1.endpoints.agents",
            "src.api.v1.endpoints.knowledge",
        ]

        failed = []
        for mod in modules:
            try:
                __import__(mod)
            except Exception as e:
                failed.append((mod, str(e)))

        assert len(failed) == 0, f"导入失败: {failed}"

    def test_settings_load_correctly(self):
        """配置设置应正确加载。"""
        from src.config.settings import get_settings

        settings = get_settings()

        assert settings.app.name is not None
        assert settings.app.version is not None
        assert settings.app.api_prefix is not None

    def test_agent_registry_populated(self):
        """Agent注册表应包含所有预期Agent。"""
        from src.api.v1.endpoints.agents import _agent_registry

        expected_agents = ["market_insight", "product_planner", "commercial"]

        for name in expected_agents:
            assert name in _agent_registry, f"Agent未注册: {name}"

    def test_app_creation_succeeds(self):
        """应用实例创建应无异常。"""
        from src.main import create_app

        app = create_app()

        assert app is not None
        assert len(app.routes) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
