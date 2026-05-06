"""
D22-D24 单元测试: 商业化Agent + 人机协作 + 消息协议
========================================================

覆盖:
    - D22-T064: CommercialAgent商业化评估
    - D25-T060: Human-in-the-Loop审批
    - D26-T064: 多Agent消息协议

执行:
    pytest tests/test_d22_d24.py -v
"""

import asyncio

import pytest


class TestCommercialAgent:
    """
    CommercialAgent测试(D22)。

    验证:
        - 财务模型构建(收入/毛利率/LTV-CAC)
        - 风险评估(市场/运营/财务三维度)
        - Go/No-Go决策(阈值判定)
        - 商业计划书生成
        - 输入校验
        - 完整执行流程
    """

    def test_agent_creation(self):
        """CommercialAgent应可正常创建。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()

        assert agent.name == "commercial"
        assert agent.GO_THRESHOLD == 70.0
        assert agent.NO_GO_THRESHOLD == 40.0

    def test_required_input_keys(self):
        """应定义必填字段query+category。"""
        from src.agents.commercial import CommercialAgent

        assert {"query", "category"} == CommercialAgent.REQUIRED_INPUT_KEYS

    def test_missing_category_fails(self):
        """缺少category应导致失败。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({"query": "评估商业化"}))

        assert result.success is False
        assert "category" in result.error

    def test_full_execution(self):
        """完整执行应返回结构化评估结果。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "评估蓝牙耳机商业化可行性",
            "category": "bluetooth_earbuds",
            "target_market": "US",
            "investment_budget": 50000,
        }))

        assert result.success is True
        data = result.output["data"]

        assert "financial_projection" in data
        assert "risk_assessment" in data
        assert "go_no_go" in data
        assert "business_plan" in data

    def test_financial_projection_structure(self):
        """财务预测应包含完整字段。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "finance test",
            "category": "cat",
            "investment_budget": 30000,
        }))

        fp = result.output["data"]["financial_projection"]

        assert "monthly_revenue_m12" in fp
        assert "monthly_revenue_m24" in fp
        assert "yearly_revenue_y1" in fp
        assert "gross_margin" in fp
        assert "ltv_cac_ratio" in fp

    def test_risk_assessment_structure(self):
        """风险评估应包含三维度风险。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "risk test",
            "category": "cat",
        }))

        risks = result.output["data"]["risk_assessment"]

        assert "overall_risk_score" in risks
        assert "market_risk" in risks
        assert "operational_risk" in risks
        assert "financial_risk" in risks
        assert "risk_level" in risks
        assert risks["risk_level"] in {"low", "medium", "high", "critical"}

    def test_go_no_go_decision(self):
        """Go/No-Go决策应为三种之一。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "gng test",
            "category": "cat",
            "investment_budget": 50000,
        }))

        gng = result.output["data"]["go_no_go"]

        valid_decisions = {"GO", "CONDITIONAL_GO", "NO_GO"}
        assert gng["decision"] in valid_decisions
        assert 0 <= gng["score"] <= 100
        assert 0 <= gng["confidence"] <= 100

    def test_decision_rules_override(self):
        """决策规则覆盖后应反映到输出中。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "gng test",
            "category": "cat",
            "investment_budget": 50000,
            "commercial_rules": {
                "thresholds": {"go": 95, "no_go": 80},
                "weights": {"margin": 0.1, "risk": 0.6, "market": 0.1, "budget": 0.2},
            },
        }))

        data = result.output["data"]
        assert data["decision_rules"]["thresholds"]["go"] == 95
        assert data["decision_rules"]["thresholds"]["no_go"] == 80
        assert round(sum(data["decision_rules"]["weights"].values()), 6) == 1.0

    def test_invalid_decision_rules_fallback(self):
        """非法规则应回退到默认阈值。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "gng test",
            "category": "cat",
            "investment_budget": 50000,
            "commercial_rules": {
                "thresholds": {"go": 20, "no_go": 80},
                "weights": {"margin": -1, "risk": 2},
            },
        }))

        rules = result.output["data"]["decision_rules"]
        assert rules["thresholds"]["go"] == 70.0
        assert rules["thresholds"]["no_go"] == 40.0
        assert round(sum(rules["weights"].values()), 6) == 1.0

    def test_business_plan_structure(self):
        """商业计划书应包含完整章节。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "plan test",
            "category": "cat",
            "target_market": "EU",
        }))

        plan = result.output["data"]["business_plan"]

        assert "executive_summary" in plan
        assert "market_opportunity" in plan
        assert "revenue_model" in plan
        assert "go_to_market_strategy" in plan
        assert "team_requirements" in plan
        assert "timeline_milestones" in plan
        assert "investment_ask" in plan

    def test_output_has_summary(self):
        """输出应含决策emoji和摘要。"""
        from src.agents.commercial import CommercialAgent

        agent = CommercialAgent()
        result = asyncio.run(agent.run({
            "query": "summary test",
            "category": "cat",
        }))

        summary = result.output.get("summary")
        decision = result.output.get("decision")

        assert summary is not None
        assert decision in {"GO", "CONDITIONAL_GO", "NO_GO"}


class TestCommercialDataModels:
    """
    商业化数据模型测试。
    """

    def test_financial_projection_to_dict(self):
        """FinancialProjection.to_dict()应格式化金额。"""
        from src.agents.commercial import FinancialProjection

        fp = FinancialProjection(
            monthly_revenue_12m=50000,
            monthly_revenue_24m=120000,
            yearly_revenue_y1=600000,
            gross_margin_pct=35.0,
            net_margin_pct=15.0,
            cac=25.0,
            ltv=90.0,
        )

        d = fp.to_dict()

        assert "$" in d["monthly_revenue_m12"]
        assert "%" in d["gross_margin"]

    def test_risk_assessment_to_dict(self):
        """RiskAssessment.to_dict()应包含Top5风险。"""
        from src.agents.commercial import RiskAssessment

        r = RiskAssessment(
            overall_risk_score=45.5,
            market_risk=50,
            operational_risk=40,
            financial_risk=45,
            risk_level="medium",
            top_risks=[
                {"name": "价格战", "score": 70},
                {"name": "供应链", "score": 55},
            ],
        )

        d = r.to_dict()

        assert d["overall_risk_score"] == 45.5
        assert len(d["top_risks"]) <= 5

    def test_go_no_go_decision_to_dict(self):
        """GoNoGoDecision.to_dict()应包含决策+条件。"""
        from src.agents.commercial import GoNoGoDecision

        g = GoNoGoDecision(
            decision="CONDITIONAL_GO",
            confidence=72.5,
            score=58.0,
            conditions=["满足条件A", "满足条件B"],
            recommendation="有条件推进",
        )

        d = g.to_dict()

        assert d["decision"] == "CONDITIONAL_GO"
        assert len(d["conditions"]) == 2

    def test_business_plan_to_dict(self):
        """BusinessPlan.to_dict()应包含里程碑。"""
        from src.agents.commercial import BusinessPlan

        b = BusinessPlan(
            executive_summary="测试摘要",
            timeline_milestones=[
                {"phase": "M1", "milestone": "产品定义"},
                {"phase": "M3", "milestone": "样品生产"},
            ],
            investment_ask={"initial_investment": 50000},
        )

        d = b.to_dict()

        assert d["executive_summary"] == "测试摘要"
        assert len(d["timeline_milestones"]) == 2


class TestHumanInLoopManager:
    """
    HumanInLoopManager测试(D25-T060)。

    验证:
        - 审批请求创建
        - 自动批准/拒绝(基于阈值)
        - 人工审批/拒绝
        - 超时处理
        - 历史记录查询
    """

    def test_manager_creation(self):
        """HumanInLoopManager应可正常创建。"""
        from src.agents.human_in_loop import ApprovalConfig, HumanInLoopManager

        config = ApprovalConfig(auto_approve_threshold=80)
        manager = HumanInLoopManager(config=config)

        assert manager.config.auto_approve_threshold == 80

    @pytest.mark.asyncio
    async def test_request_approval_creates_request(self):
        """request_approval()应返回ApprovalRequest。"""
        import asyncio

        from src.agents.human_in_loop import HumanInLoopManager

        manager = HumanInLoopManager()

        async def _do_req():
            return await manager.request_approval(
                session_id="sess_001",
                agent_name="MarketInsight",
                action="proceed_to_planning",
                context={"score": 65},
            )

        request = asyncio.run(_do_req())

        assert request.request_id.startswith("apr_")
        assert request.status.value == "pending"
        assert request.agent_name == "MarketInsight"

    @pytest.mark.asyncio
    async def test_auto_approve_high_score(self):
        """高分请求应自动批准。"""
        import asyncio

        from src.agents.human_in_loop import ApprovalConfig, ApprovalType, HumanInLoopManager

        config = ApprovalConfig(auto_approve_threshold=80)
        manager = HumanInLoopManager(config=config)

        async def _do_req():
            return await manager.request_approval(
                session_id="sess",
                agent_name="TestAgent",
                action="auto_test",
                approval_type=ApprovalType.PHASE_TRANSITION,
                context={"score": 90},
            )

        request = asyncio.run(_do_req())

        assert request.status.value == "approved"

    @pytest.mark.asyncio
    async def test_manual_approve(self):
        """人工批准应更新状态。"""
        import asyncio

        from src.agents.human_in_loop import HumanInLoopManager

        manager = HumanInLoopManager()

        async def _do_req():
            return await manager.request_approval(
                session_id="sess",
                agent_name="Agent",
                action="manual_test",
                context={"score": 50},
            )

        request = asyncio.run(_do_req())

        async def _do_appr():
            return await manager.approve_request(request.request_id, reviewer="admin", comment="同意推进")

        success = asyncio.run(_do_appr())

        assert success is True
        assert request.status.value == "approved"

    @pytest.mark.asyncio
    async def test_manual_reject(self):
        """人工拒绝应更新状态。"""
        import asyncio

        from src.agents.human_in_loop import HumanInLoopManager

        manager = HumanInLoopManager()

        async def _do_req():
            return await manager.request_approval(
                session_id="sess",
                agent_name="Agent",
                action="reject_test",
                context={"score": 30},
            )

        request = asyncio.run(_do_req())

        async def _do_rej():
            return await manager.reject_request(request.request_id, reviewer="pm", comment="暂不通过")

        success = asyncio.run(_do_rej())

        assert success is True
        assert request.status.value == "rejected"

    def test_get_pending_requests(self):
        """get_pending_requests()应返回待审批列表。"""
        import asyncio as aio

        from src.agents.human_in_loop import HumanInLoopManager

        manager = HumanInLoopManager()
        aio.run(manager.request_approval("s", "A", "a1", context={"score": 40}))
        aio.run(manager.request_approval("s", "B", "a2", context={"score": 35}))

        pending = manager.get_pending_requests()

        assert len(pending) >= 1

    def test_stats_property(self):
        """stats属性应返回统计信息。"""
        import asyncio as aio

        from src.agents.human_in_loop import HumanInLoopManager

        manager = HumanInLoopManager()
        aio.run(manager.request_approval("s", "A", "a"))

        stats = manager.stats

        assert "total_requests" in stats
        assert "approved" in stats
        assert "pending" in stats

    def test_approval_request_to_dict(self):
        """ApprovalRequest.to_dict()应包含完整信息。"""
        from src.agents.human_in_loop import ApprovalRequest, ApprovalStatus

        r = ApprovalRequest(
            session_id="sess_123",
            agent_name="TestAgent",
            status=ApprovalStatus.APPROVED,
            reviewed_by="admin",
            comment="OK",
        )

        d = r.to_dict()

        assert d["status"] == "approved"
        assert d["reviewed_by"] == "admin"


class TestMessageProtocol:
    """
    消息协议测试(D26-T064)。

    验证:
        - AgentMessage创建与序列化
        - 消息验证
        - MessageBus发送与接收
        - 广播消息
        - 消息查询
    """

    def test_message_creation(self):
        """AgentMessage应可正常创建。"""
        from src.agents.message_protocol import AgentMessage

        msg = AgentMessage(
            sender="DataCollector",
            receiver="MarketAnalyst",
            content={"products": []},
        )

        assert msg.message_id.startswith("msg_")
        assert msg.sender == "DataCollector"

    def test_from_agent_convenience(self):
        """from_agent()应便捷创建消息。"""
        from src.agents.message_protocol import AgentMessage, MessageType

        msg = AgentMessage.from_agent(
            sender="Jaxx",
            receiver="Jobs",
            content={"data": [1, 2, 3]},
            message_type=MessageType.DATA_TRANSFER,
        )

        assert msg.sender == "Jaxx"
        assert msg.receiver == "Jobs"
        assert msg.message_type == MessageType.DATA_TRANSFER

    def test_message_serialization(self):
        """to_json/from_json应正确序列化和反序列化。"""
        from src.agents.message_protocol import AgentMessage

        original = AgentMessage(
            sender="A",
            receiver="B",
            content={"key": "value"},
        )

        json_str = original.to_json()
        restored = AgentMessage.from_json(json_str)

        assert restored.sender == "A"
        assert restored.content == {"key": "value"}
        assert restored.message_id == original.message_id

    def test_message_validation_valid(self):
        """有效消息应通过验证。"""
        from src.agents.message_protocol import AgentMessage

        msg = AgentMessage(sender="X", receiver="Y", content={"data": 1})

        is_valid, errors = msg.validate()

        assert is_valid is True
        assert len(errors) == 0

    def test_message_validation_invalid_sender(self):
        """空sender应验证失败。"""
        from src.agents.message_protocol import AgentMessage

        msg = AgentMessage(sender="", receiver="Y", content={})

        is_valid, errors = msg.validate()

        assert is_valid is False
        assert any("sender" in e for e in errors)

    def test_message_bus_send_and_receive(self):
        """发送后接收者应能收到消息。"""
        import asyncio as aio

        from src.agents.message_protocol import AgentMessage, MessageBus

        bus = MessageBus()
        msg = AgentMessage(sender="Sender", receiver="Receiver", content={"hello": "world"})

        success = aio.run(bus.send(msg))
        received = aio.run(bus.receive("Receiver"))

        assert success is True
        assert len(received) >= 1
        assert received[0].sender == "Sender"

    def test_broadcast_message(self):
        """广播消息应被所有注册接收者收到。"""
        import asyncio as aio

        from src.agents.message_protocol import AgentMessage, MessageBus

        bus = MessageBus()
        bus.register_receiver("Agent1")
        bus.register_receiver("Agent2")

        msg = AgentMessage(sender="Broadcaster", receiver="*", content={"alert": "test"})

        aio.run(bus.send(msg))

        recv1 = aio.run(bus.receive("Agent1"))
        recv2 = aio.run(bus.receive("Agent2")
                        )

        assert len(recv1) >= 1
        assert len(recv2) >= 1

    def test_message_bus_stats(self):
        """stats属性应返回总线统计。"""
        import asyncio as aio

        from src.agents.message_protocol import AgentMessage, MessageBus

        bus = MessageBus()
        aio.run(bus.send(AgentMessage(sender="A", receiver="B", content={})))

        stats = bus.stats

        assert stats["total_messages"] >= 1
        assert "by_type" in stats
        assert "last_offset" in stats

    def test_message_bus_persistence_and_replay(self, tmp_path):
        """消息总线应支持本地持久化、offset 顺序和历史回放。"""
        import asyncio as aio

        from src.agents.message_protocol import AgentMessage, MessageBus

        persistence_path = tmp_path / "agent-messages.jsonl"
        bus = MessageBus(persistence_path=persistence_path)
        aio.run(bus.send(AgentMessage(sender="A", receiver="B", content={"step": 1})))
        aio.run(bus.send(AgentMessage(sender="A", receiver="B", content={"step": 2})))

        first_batch = aio.run(bus.receive("B"))
        assert [item.content["step"] for item in first_batch] == [1, 2]
        assert first_batch[0].metadata["bus_offset"] < first_batch[1].metadata["bus_offset"]

        restored_bus = MessageBus(persistence_path=persistence_path)
        replay = restored_bus.replay(receiver="B", after_offset=0, limit=10)
        assert [item.content["step"] for item in replay["items"]] == [1, 2]
        assert replay["next_offset"] == 2
        assert restored_bus.stats["persistence_enabled"] is True

    def test_is_broadcast_and_reply(self):
        """is_broadcast()/is_reply()方法应正确判断。"""
        from src.agents.message_protocol import AgentMessage

        broadcast_msg = AgentMessage(sender="S", receiver="*", content={})
        reply_msg = AgentMessage(sender="S", receiver="R", reply_to="msg_prev", content={})
        normal_msg = AgentMessage(sender="S", receiver="R", content={})

        assert broadcast_msg.is_broadcast() is True
        assert reply_msg.is_reply() is True
        assert normal_msg.is_broadcast() is False
        assert normal_msg.is_reply() is False


class TestModuleImportsD22D24:
    """
    模块导入测试(D22-D24)。
    """

    def test_commercial_importable(self):
        """CommercialAgent及其组件应可导入。"""
        from src.agents import (
            CommercialAgent,
            create_commercial_agent,
        )

        assert CommercialAgent is not None
        assert callable(create_commercial_agent)

    def test_human_in_loop_importable(self):
        """HumanInLoopManager及其组件应可导入。"""
        from src.agents import (
            HumanInLoopManager,
            create_human_in_loop_manager,
        )

        assert HumanInLoopManager is not None
        assert callable(create_human_in_loop_manager)

    def test_message_protocol_importable(self):
        """AgentMessage和MessageBus应可导入。"""
        from src.agents import (
            AgentMessage,
            MessageBus,
            create_message_bus,
        )

        assert AgentMessage is not None
        assert MessageBus is not None
        assert callable(create_message_bus)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
