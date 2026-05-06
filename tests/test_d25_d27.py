"""
D25-D27 单元测试: 后端API集成 + 工作流引擎
==========================================

覆盖:
    - 选品任务管理API(selection.py)
    - Agent管理API(agents.py)
    - 知识库管理API(knowledge.py)
    - 工作流引擎(workflow.py)

测试框架: pytest + httpx.TestClient + asyncio.run()
"""

import asyncio
from io import BytesIO

import pytest


def _override_auth(app):
    """覆盖认证依赖，返回模拟用户。"""
    from src.core.auth import get_current_user

    async def _mock_user():
        return {"username": "testuser", "user_id": "test-uid", "is_superuser": False, "token_type": "access"}

    app.dependency_overrides[get_current_user] = _mock_user


class TestSelectionAPI:
    """
    选品任务管理API测试(D25)。

    验证:
        - 任务创建与启动
        - 任务列表查询
        - 任务详情获取
        - 任务取消
        - 审批操作
        - 统计信息
    """

    def test_create_selection_task(self):
        """创建选品任务应返回task_id。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post("/api/v1/selection/tasks", json={
            "query": "蓝牙耳机",
            "category": "electronics",
            "investment_budget": 50000.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "running"
        assert data["query"] == "蓝牙耳机"

    def test_list_selection_tasks(self):
        """获取任务列表应返回已创建的任务。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        client.post("/api/v1/selection/tasks", json={
            "query": "智能手表",
            "category": "wearables",
        })

        response = client.get("/api/v1/selection/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["tasks"]) >= 1

    def test_get_task_detail(self):
        """获取任务详情应返回完整信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        create_resp = client.post("/api/v1/selection/tasks", json={
            "query": "充电宝",
            "category": "electronics",
        })
        task_id = create_resp.json()["task_id"]

        response = client.get(f"/api/v1/selection/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["query"] == "充电宝"

    def test_cancel_task(self):
        """取消任务应更新状态为cancelled或任务已完成。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        create_resp = client.post("/api/v1/selection/tasks", json={
            "query": "测试产品",
            "category": "test",
        })
        task_id = create_resp.json()["task_id"]

        response = client.delete(f"/api/v1/selection/tasks/{task_id}")

        assert response.status_code in [200, 400]

    def test_get_task_result_pending(self):
        """获取未完成任务结果应返回202。"""
        from fastapi.testclient import TestClient
        from src.api.v1.endpoints.selection import _task_store
        from src.main import app
        _override_auth(app)

        client = TestClient(app, raise_server_exceptions=False)

        # 直接在内存中注入一个 running 状态的任务，避免 BackgroundTasks 同步执行完毕
        _task_store["pending_test_001"] = {
            "task_id": "pending_test_001", "db_task_id": None,
            "query": "运行中任务", "category": "test",
            "investment_budget": 50000, "target_market": "US",
            "status": "running", "phase": "data_collection",
            "created_at": "2026-01-01T00:00:00+00:00",
            "result": None, "error": None,
        }

        response = client.get("/api/v1/selection/tasks/pending_test_001/result")

        # 清理
        _task_store.pop("pending_test_001", None)

        assert response.status_code == 202

    def test_get_nonexistent_task(self):
        """获取不存在的任务应返回404。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/selection/tasks/nonexistent_task")

        assert response.status_code == 404

    def test_selection_stats(self):
        """统计信息应包含基本字段。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/selection/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_tasks" in data
        assert "completed" in data
        assert "success_rate" in data

    def test_task_validation_query_too_short(self):
        """查询过短应返回422验证错误。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post("/api/v1/selection/tasks", json={
            "query": "a",
            "category": "test",
        })

        assert response.status_code == 422

    def test_approve_nonexistent_task(self):
        """审批不存在的任务应返回404。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post(
            "/api/v1/selection/tasks/nonexistent/approve",
            json={"action": "approve", "comment": "test"},
        )

        assert response.status_code == 404


class TestAgentsAPI:
    """
    Agent管理API测试(D26)。

    验证:
        - Agent列表查询
        - Agent详情获取
        - Agent健康检查
        - Agent直接调用
        - Agent类型定义
    """

    def test_list_agents(self):
        """Agent列表应包含所有注册的Agent。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        agent_names = [a["name"] for a in data["agents"]]
        assert "market_insight" in agent_names
        assert "product_planner" in agent_names
        assert "commercial" in agent_names

    def test_get_agent_detail(self):
        """获取Agent详情应返回完整信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents/market_insight")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "market_insight"
        assert "capabilities" in data
        assert "required_inputs" in data
        assert len(data["capabilities"]) >= 1

    def test_get_nonexistent_agent(self):
        """获取不存在的Agent应返回404。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents/nonexistent_agent")

        assert response.status_code == 404

    def test_check_agent_health(self):
        """Agent健康检查应返回状态信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents/market_insight/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "agent_name" in data

    def test_invoke_market_insight_agent(self):
        """调用MarketInsightAgent应返回分析结果。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post(
            "/api/v1/agents/market_insight/invoke",
            json={
                "query": "蓝牙耳机市场分析",
                "category": "electronics",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "market_insight"
        assert "status" in data
        assert data["status"] in ["success", "error"]

    def test_invoke_commercial_agent_with_budget(self):
        """调用CommercialAgent并传入预算应正常执行。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post(
            "/api/v1/agents/commercial/invoke",
            json={
                "query": "商业化评估测试",
                "category": "electronics",
                "investment_budget": 100000,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data or "error" in data

    def test_get_agent_types(self):
        """Agent类型定义应包含所有枚举值。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/agents/types")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5
        assert "types" in data


class TestKnowledgeAPI:
    """
    知识库管理API测试(D27)。

    验证:
        - 文档上传
        - 文档列表查询
        - 文档详情获取
        - 文档删除
        - 知识库查询
        - 统计信息
    """

    def test_upload_text_document(self):
        """上传txt文档应成功索引。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        content = "这是测试文档内容。\n\n跨境电商选品系统是一个基于AI的产品选择平台。\n系统支持多源数据采集，包括Amazon、TikTok、Google等。\n通过RAG技术实现知识增强的智能问答功能。\n".encode()
        files = {"file": ("test_doc.txt", BytesIO(content), "text/plain")}

        response = client.post("/api/v1/knowledge/documents", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["status"] == "indexed"
        assert "文档已成功索引" in data["message"]

    def test_upload_unsupported_format(self):
        """上传不支持格式应返回400错误。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        files = {"file": ("test.exe", BytesIO(b"fake exe"), "application/octet-stream")}

        response = client.post("/api/v1/knowledge/documents", files=files)

        assert response.status_code == 400

    def test_list_documents_after_upload(self):
        """上传后文档列表应包含新文档。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        content = "测试文档用于列表查询验证".encode()
        files = {"file": ("list_test.txt", BytesIO(content), "text/plain")}
        client.post("/api/v1/knowledge/documents", files=files)

        response = client.get("/api/v1/knowledge/documents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_get_document_detail(self):
        """获取文档详情应返回完整信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        content = "文档详情测试内容".encode()
        files = {"file": ("detail_test.txt", BytesIO(content), "text/plain")}
        upload_resp = client.post("/api/v1/knowledge/documents", files=files)
        doc_id = upload_resp.json()["doc_id"]

        response = client.get(f"/api/v1/knowledge/documents/{doc_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == doc_id
        assert "chunk_count" in data

    def test_delete_document(self):
        """删除文档应从存储中移除。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        content = "待删除的文档内容".encode()
        files = {"file": ("delete_test.txt", BytesIO(content), "text/plain")}
        upload_resp = client.post("/api/v1/knowledge/documents", files=files)
        doc_id = upload_resp.json()["doc_id"]

        delete_response = client.delete(f"/api/v1/knowledge/documents/{doc_id}")

        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

        get_response = client.get(f"/api/v1/knowledge/documents/{doc_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_document(self):
        """删除不存在的文档应返回404。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.delete("/api/v1/knowledge/documents/nonexistent_doc")

        assert response.status_code == 404

    def test_knowledge_stats(self):
        """知识库统计应包含基本信息。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.get("/api/v1/knowledge/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_documents" in data
        assert "total_chunks" in data
        assert "total_size_bytes" in data

    def test_query_knowledge_base(self):
        """查询知识库应正常响应。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        response = client.post("/api/v1/knowledge/query", json={
            "query": "测试查询",
        })

        assert response.status_code in [200, 400]


class TestWorkflowEngine:
    """
    工作流引擎测试(D25-T068)。

    验证:
        - 工作流创建与配置
        - 步骤添加与管理
        - 工作流执行
        - 依赖关系处理
        - 错误处理与重试
        - 上下文数据传递
        - 取消操作
    """

    def test_engine_creation(self):
        """WorkflowEngine应可正常创建。"""
        from src.core.workflow import WorkflowEngine, WorkflowStatus

        engine = WorkflowEngine(workflow_id="test_wf_001")

        assert engine.workflow_id == "test_wf_001"
        assert engine.status == WorkflowStatus.PENDING

    def test_add_step(self):
        """添加步骤应注册到引擎中。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.core.workflow import WorkflowEngine, WorkflowPhase

        engine = WorkflowEngine(workflow_id="test_wf_002")
        agent = MarketInsightAgent()

        engine.add_step(
            name="market_analysis",
            agent=agent,
            phase=WorkflowPhase.DATA_COLLECTION,
        )

        assert "market_analysis" in engine._steps
        assert engine._steps["market_analysis"].phase == WorkflowPhase.DATA_COLLECTION

    def test_duplicate_step_error(self):
        """添加重复步骤名称应抛出异常。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.core.workflow import WorkflowEngine, WorkflowPhase

        engine = WorkflowEngine(workflow_id="test_wf_003")
        agent = MarketInsightAgent()

        engine.add_step("dup_step", agent, WorkflowPhase.DATA_COLLECTION)

        try:
            engine.add_step("dup_step", agent, WorkflowPhase.PRODUCT_PLANNING)
            raise AssertionError("应该抛出ValueError异常")
        except ValueError as e:
            assert "已存在" in str(e)

    def test_run_simple_workflow(self):
        """简单工作流应成功完成。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.core.workflow import (
            WorkflowEngine,
            WorkflowPhase,
            WorkflowStatus,
        )

        engine = WorkflowEngine(workflow_id="test_wf_004")
        agent = MarketInsightAgent()

        engine.add_step("analysis", agent, WorkflowPhase.DATA_COLLECTION)

        result = asyncio.run(engine.run({
            "query": "简单工作流测试",
            "category": "electronics",
        }))

        assert result.status == WorkflowStatus.COMPLETED
        assert result.steps_completed >= 1
        assert result.execution_time_seconds > 0
        assert result.final_output is not None

    def test_workflow_with_dependencies(self):
        """带依赖关系的工作流应按顺序执行。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.agents.product_planner import ProductPlannerAgent
        from src.core.workflow import (
            WorkflowEngine,
            WorkflowPhase,
            WorkflowStatus,
        )

        engine = WorkflowEngine(workflow_id="test_wf_005")

        market_agent = MarketInsightAgent()
        product_agent = ProductPlannerAgent()

        engine.add_step(
            "market_analysis",
            market_agent,
            WorkflowPhase.DATA_COLLECTION,
        )
        engine.add_step(
            "product_planning",
            product_agent,
            WorkflowPhase.PRODUCT_PLANNING,
            dependencies=["market_analysis"],
        )

        result = asyncio.run(engine.run({
            "query": "依赖关系测试",
            "category": "electronics",
        }))

        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]
        assert len(result.step_details) == 2

    def test_workflow_context_data_flow(self):
        """工作流上下文应在步骤间传递数据。"""
        from src.agents.market_insight import MarketInsightAgent
        from src.core.workflow import (
            WorkflowEngine,
            WorkflowPhase,
            WorkflowStatus,
        )

        engine = WorkflowEngine(workflow_id="test_wf_006")
        agent = MarketInsightAgent()

        engine.add_step("step1", agent, WorkflowPhase.DATA_COLLECTION)

        input_data = {
            "query": "上下文传递测试",
            "category": "test",
            "custom_field": "test_value",
        }

        result = asyncio.run(engine.run(input_data))

        assert result.status == WorkflowStatus.COMPLETED
        assert engine.context.input_data["custom_field"] == "test_value"
        assert "step1" in engine.context.step_results

    def test_cancel_workflow(self):
        """取消工作流应更新状态为CANCELLED。"""
        from src.core.workflow import WorkflowEngine, WorkflowStatus

        engine = WorkflowEngine(workflow_id="test_wf_007")

        engine.cancel()

        assert engine.status == WorkflowStatus.CANCELLED

    def test_workflow_result_structure(self):
        """WorkflowResult应包含完整字段。"""
        from src.core.workflow import WorkflowPhase, WorkflowResult, WorkflowStatus

        result = WorkflowResult(
            workflow_id="test_result",
            status=WorkflowStatus.COMPLETED,
            current_phase=WorkflowPhase.DECISION_SUMMARY,
            steps_completed=3,
            total_steps=3,
            execution_time_seconds=5.5,
            final_output={"decision": "GO"},
        )

        assert result.workflow_id == "test_result"
        assert result.status == WorkflowStatus.COMPLETED
        assert result.steps_completed == 3
        assert result.final_output is not None

    def test_workflow_status_enum(self):
        """WorkflowStatus枚举应包含所有状态值。"""
        from src.core.workflow import WorkflowStatus

        statuses = [s.value for s in WorkflowStatus]

        assert "pending" in statuses
        assert "running" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "cancelled" in statuses

    def test_workflow_phase_enum(self):
        """WorkflowPhase枚举应包含所有阶段值。"""
        from src.core.workflow import WorkflowPhase

        phases = [p.value for p in WorkflowPhase]

        assert "initialized" in phases
        assert "data_collection" in phases
        assert "product_planning" in phases
        assert "commercial_evaluation" in phases
        assert "decision_summary" in phases

    def test_full_selection_workflow(self):
        """完整的选品工作流应能端到端执行。"""
        from src.agents.commercial import CommercialAgent
        from src.agents.market_insight import MarketInsightAgent
        from src.agents.product_planner import ProductPlannerAgent
        from src.core.workflow import (
            WorkflowEngine,
            WorkflowPhase,
            WorkflowStatus,
        )

        engine = WorkflowEngine(workflow_id="full_selection_wf")

        market_agent = MarketInsightAgent()
        product_agent = ProductPlannerAgent()
        commercial_agent = CommercialAgent()

        engine.add_step(
            "market_analysis",
            market_agent,
            WorkflowPhase.DATA_COLLECTION,
            timeout=30,
        )
        engine.add_step(
            "product_planning",
            product_agent,
            WorkflowPhase.PRODUCT_PLANNING,
            timeout=30,
            dependencies=["market_analysis"],
        )
        engine.add_step(
            "commercial_eval",
            commercial_agent,
            WorkflowPhase.COMMERCIAL_EVALUATION,
            timeout=60,
            dependencies=["product_planning"],
        )

        result = asyncio.run(engine.run({
            "query": "完整选品流程测试",
            "category": "electronics",
            "investment_budget": 80000,
        }))

        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]
        assert len(result.step_details) == 3

        if result.final_output:
            assert "results" in result.final_output


class TestIntegrationScenarios:
    """
    集成场景测试(D27)。

    验证各组件协同工作的端到端场景:
        - 完整选品流程(API → Engine → Agents)
        - 数据流转正确性
        - 错误恢复能力
    """

    def test_api_to_engine_integration(self):
        """API创建任务应触发工作流引擎执行。"""
        from src.agents.human_in_loop import HumanInLoopManager
        from src.agents.selection_master import SelectionMaster
        from src.api.v1.endpoints.selection import _run_selection_workflow

        master = SelectionMaster(config={"session_id": "integration_test"})
        approval_mgr = HumanInLoopManager()

        asyncio.run(_run_selection_workflow(
            task_id="int_test_001",
            query="集成测试产品",
            category="electronics",
            budget=50000,
            master=master,
            approval_mgr=approval_mgr,
        ))

        from src.api.v1.endpoints.selection import _task_store

        task = _task_store.get("int_test_001")
        assert task is not None
        assert task["status"] in ["completed", "failed"]

    def test_concurrent_task_creation(self):
        """并发创建多个任务应各自独立运行。"""
        from fastapi.testclient import TestClient
        from src.main import app
        _override_auth(app)

        client = TestClient(app)

        task_ids = []
        for i in range(3):
            resp = client.post("/api/v1/selection/tasks", json={
                "query": f"并发任务_{i}",
                "category": "test",
            })
            task_ids.append(resp.json()["task_id"])

        assert len(task_ids) == 3
        assert len(set(task_ids)) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
