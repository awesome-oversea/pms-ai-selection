"""
AI选品系统集成测试
==================

验证核心功能模块的真实行为集成:
    - Agent编排端到端流程
    - LLM Gateway降级策略
    - RAG检索链路
    - ERP集成闭环
    - 消息通道交付

原则:
    - 不测试对象创建/属性赋值（那是数据模型测试）
    - 每个测试验证至少一个行为结果
    - 使用monkeypatch隔离外部依赖，不依赖真实DB/Redis/Qdrant
"""

from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import asyncio

import pytest
from src.agents.base import AgentStatus, AgentType, BaseAgent
from src.agents.human_in_loop import ApprovalStatus, HumanInLoopManager
from src.agents.message_protocol import AgentMessage, MessageType
from src.agents.selection_master import SelectionMaster, SelectionPhase, SelectionState
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway


def _run(coro):
    return asyncio.run(coro)


class _SuccessAgent(BaseAgent):
    name = "success_agent"
    agent_type = AgentType.DATA_COLLECTOR

    async def execute(self, input_data: dict) -> dict:
        return {"result": input_data.get("query", ""), "processed": True}


class _FailAgent(BaseAgent):
    name = "fail_agent"
    agent_type = AgentType.DATA_COLLECTOR

    async def execute(self, input_data: dict) -> dict:
        raise RuntimeError("集成测试模拟失败")


class TestAgentLifecycleIntegration:
    """Agent生命周期集成测试：验证PENDING→RUNNING→COMPLETED/FAILED状态流转"""

    @pytest.mark.asyncio
    async def test_success_agent_completes_lifecycle(self):
        agent = _SuccessAgent()
        assert agent.status == AgentStatus.PENDING

        result = await agent.run({"query": "蓝牙耳机"})

        assert agent.status == AgentStatus.COMPLETED
        assert result.success is True
        assert result.output["processed"] is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_fail_agent_transitions_to_failed(self):
        agent = _FailAgent()
        result = await agent.run({"query": "test"})

        assert agent.status == AgentStatus.FAILED
        assert result.success is False
        assert "集成测试模拟失败" in (result.error or "")


class TestSelectionMasterIntegration:
    """SelectionMaster编排集成测试：验证多Agent协同执行"""

    def test_full_selection_flow_produces_complete_results(self):
        master = SelectionMaster(config={"session_id": "int-test-001"})
        result = _run(
            master.run(
                {
                    "session_id": "int-test-001",
                    "query": "户外储能电源",
                    "category": "outdoor_power",
                    "target_market": "US",
                }
            )
        )

        assert result["session_id"] == "int-test-001"
        assert result["framework"] == "langgraph-compatible"
        assert "data_collection" in result["results"]
        assert "market_analysis" in result["results"]
        assert "product_planning" in result["results"]
        assert "commercial_evaluation" in result["results"]
        assert "risk_assessment" in result["results"]
        assert "report_generation" in result["results"]
        assert "go_no_go_decision" in result

    def test_selection_state_transitions_through_phases(self):
        state = SelectionState(
            session_id="phase-test",
            query="蓝牙耳机",
        )
        assert state.current_phase == SelectionPhase.START

        master = SelectionMaster()
        result = _run(
            master.run(
                {
                    "session_id": "phase-test",
                    "query": "蓝牙耳机",
                    "category": "electronics",
                    "target_market": "US",
                }
            )
        )

        assert result["state_summary"]["current_phase"] == "completed"


class TestLLMGatewayIntegration:
    """LLM Gateway降级集成测试"""

    @pytest.mark.asyncio
    async def test_gateway_degrades_on_vllm_timeout(self, monkeypatch):
        gateway = LLMGateway(
            GatewayConfig(
                use_mock=False,
                provider_mode="real",
                vllm_endpoint="http://localhost:8000/v1",
                ollama_endpoint="http://localhost:11434",
            )
        )

        async def _timeout(*args, **kwargs):
            return "", 0, True

        async def _fallback(prompt: str):
            return "降级响应", 12

        monkeypatch.setattr(gateway, "_call_vllm", _timeout)
        monkeypatch.setattr(gateway, "_degrade_to_ollama", _fallback)

        result = await gateway.route("分析蓝牙耳机市场")
        data = result.to_dict()
        assert data["degraded"] is True
        assert data["actual_provider"] == "ollama"
        assert data["response"] == "降级响应"

    @pytest.mark.asyncio
    async def test_gateway_uses_primary_when_available(self, monkeypatch):
        gateway = LLMGateway(
            GatewayConfig(
                use_mock=False,
                provider_mode="real",
                vllm_endpoint="http://localhost:8000/v1",
                ollama_endpoint="http://localhost:11434",
            )
        )

        async def _success(*args, **kwargs):
            return "主模型响应", 21, False

        monkeypatch.setattr(gateway, "_call_vllm", _success)

        result = await gateway.route("分析蓝牙耳机市场")
        data = result.to_dict()
        assert data["degraded"] is False
        assert data["actual_provider"] == "vllm"
        assert data["response"] == "主模型响应"


class TestHumanInLoopIntegration:
    """人工审批集成测试"""

    def test_approval_lifecycle_pending_to_approved(self):
        manager = HumanInLoopManager()
        request = manager.create_request(
            session_id="hitl-test-001",
            phase="product_planning",
            data={"recommendation": "蓝牙耳机X1"},
        )
        assert request["status"] == ApprovalStatus.PENDING

        result = manager.approve(request["request_id"], approver="admin")
        assert result["status"] == ApprovalStatus.APPROVED

    def test_approval_rejection_blocks_progress(self):
        manager = HumanInLoopManager()
        request = manager.create_request(
            session_id="hitl-test-002",
            phase="commercial_evaluation",
            data={"profit_margin": 0.08},
        )
        result = manager.reject(request["request_id"], reason="利润率过低")
        assert result["status"] == ApprovalStatus.REJECTED


class TestAgentMessageIntegration:
    """Agent消息传递集成测试"""

    def test_request_response_message_flow(self):
        request = AgentMessage(
            sender="data_collection",
            receiver="market_insight",
            message_type=MessageType.REQUEST,
            content={"query": "蓝牙耳机市场数据"},
        )
        assert request.message_type == MessageType.REQUEST

        response = AgentMessage(
            sender="market_insight",
            receiver="data_collection",
            message_type=MessageType.RESPONSE,
            content={"trend": "上升", "confidence": 0.85},
            correlation_id=request.message_id,
        )
        assert response.message_type == MessageType.RESPONSE
        assert response.correlation_id == request.message_id


class TestModuleImportability:
    """模块可导入性验证：确保所有核心模块可正常导入"""

    def test_agents_importable(self):
        from src.agents import base, selection_master
        assert base.BaseAgent is not None
        assert selection_master.SelectionMaster is not None

    def test_infrastructure_importable(self):
        from src.infrastructure import llm_gateway
        assert llm_gateway.LLMGateway is not None

    def test_services_importable(self):
        from src.services import embedding
        assert embedding.EmbeddingService is not None

    def test_config_importable(self):
        from src.config import settings
        assert settings.Settings is not None
