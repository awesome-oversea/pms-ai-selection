"""D81-D85 单元测试: Agent增强 + 性能测试 + 安全审计"""


import pytest
from src.infrastructure.agent_security import (
    Alert,
    AlertManager,
    AlertSeverity,
    AuditEvent,
    AuditEventType,
    ConversationMemory,
    ConversationMessage,
    ConversationSession,
    MessageRole,
    PerformanceResult,
    PerformanceTester,
    SecurityAuditor,
)


class TestConversationMessage:
    """测试对话消息"""

    def test_message_creation(self):
        msg = ConversationMessage(
            role=MessageRole.USER,
            content="查询储能电源",
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "查询储能电源"

    def test_message_to_dict(self):
        msg = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content="找到10个产品",
            metadata={"count": 10},
        )
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["metadata"]["count"] == 10


class TestConversationSession:
    """测试对话会话"""

    def test_session_creation(self):
        session = ConversationSession(
            session_id="SESS_001",
            user_id="U001",
        )
        assert session.session_id == "SESS_001"
        assert len(session.messages) == 0

    def test_session_to_dict(self):
        session = ConversationSession(
            session_id="SESS_001",
            user_id="U001",
            messages=[ConversationMessage(role=MessageRole.USER, content="test")],
        )
        d = session.to_dict()
        assert len(d["messages"]) == 1


class TestPerformanceResult:
    """测试性能结果"""

    def test_result_creation(self):
        result = PerformanceResult(
            test_id="PERF_001",
            test_type="api",
            concurrency=100,
            total_requests=1000,
            successful_requests=980,
            failed_requests=20,
            avg_latency_ms=50.5,
            p50_latency_ms=40.0,
            p95_latency_ms=100.0,
            p99_latency_ms=150.0,
            tps=100.0,
            duration_seconds=10.0,
        )
        assert result.test_id == "PERF_001"
        assert result.tps == 100.0

    def test_result_to_dict(self):
        result = PerformanceResult(
            test_id="PERF_001",
            test_type="api",
            concurrency=100,
            total_requests=1000,
            successful_requests=980,
            failed_requests=20,
            avg_latency_ms=50.5,
            p50_latency_ms=40.0,
            p95_latency_ms=100.0,
            p99_latency_ms=150.0,
            tps=100.0,
            duration_seconds=10.0,
        )
        d = result.to_dict()
        assert d["test_type"] == "api"
        assert "avg_latency_ms" in d


class TestAuditEvent:
    """测试审计事件"""

    def test_event_creation(self):
        event = AuditEvent(
            event_id="AUDIT_001",
            event_type=AuditEventType.LOGIN,
            user_id="U001",
            ip_address="192.168.1.1",
            resource="auth",
            action="login_success",
        )
        assert event.event_type == AuditEventType.LOGIN
        assert event.risk_level == "low"

    def test_event_to_dict(self):
        event = AuditEvent(
            event_id="AUDIT_001",
            event_type=AuditEventType.API_CALL,
            user_id="U001",
            ip_address="192.168.1.1",
            resource="products",
            action="read",
            risk_level="medium",
        )
        d = event.to_dict()
        assert d["event_type"] == "api_call"
        assert d["risk_level"] == "medium"


class TestAlert:
    """测试告警"""

    def test_alert_creation(self):
        alert = Alert(
            alert_id="ALERT_001",
            name="api_error_rate",
            severity=AlertSeverity.CRITICAL,
            condition="error_rate > 5%",
            current_value=8.5,
            threshold=5.0,
            message="API错误率过高",
        )
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.acknowledged is False

    def test_alert_to_dict(self):
        alert = Alert(
            alert_id="ALERT_001",
            name="disk_usage",
            severity=AlertSeverity.WARNING,
            condition="usage > 80%",
            current_value=85.0,
            threshold=80.0,
            message="磁盘使用率过高",
        )
        d = alert.to_dict()
        assert d["severity"] == "warning"


class TestConversationMemory:
    """测试对话记忆(D81)"""

    def setup_method(self):
        self.memory = ConversationMemory()

    @pytest.mark.asyncio
    async def test_create_session(self):
        session = await self.memory.create_session(user_id="U001")
        assert session.session_id.startswith("SESS_")
        assert session.user_id == "U001"

    @pytest.mark.asyncio
    async def test_add_message(self):
        session = await self.memory.create_session(user_id="U001")
        msg = await self.memory.add_message(
            session.session_id,
            MessageRole.USER,
            "查询储能电源",
        )
        assert msg.content == "查询储能电源"

    @pytest.mark.asyncio
    async def test_get_history(self):
        session = await self.memory.create_session(user_id="U001")
        await self.memory.add_message(session.session_id, MessageRole.USER, "消息1")
        await self.memory.add_message(session.session_id, MessageRole.ASSISTANT, "消息2")
        history = await self.memory.get_history(session.session_id)
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_context(self):
        session = await self.memory.create_session(user_id="U001", context={"lang": "zh"})
        ctx = await self.memory.get_context(session.session_id)
        assert ctx["lang"] == "zh"

    @pytest.mark.asyncio
    async def test_update_context(self):
        session = await self.memory.create_session(user_id="U001")
        result = await self.memory.update_context(session.session_id, {"topic": "储能"})
        assert result is True
        ctx = await self.memory.get_context(session.session_id)
        assert ctx["topic"] == "储能"

    @pytest.mark.asyncio
    async def test_user_preference(self):
        await self.memory.set_user_preference("U001", "category", "储能设备")
        pref = await self.memory.get_user_preference("U001", "category")
        assert pref == "储能设备"

    @pytest.mark.asyncio
    async def test_end_session(self):
        session = await self.memory.create_session(user_id="U001")
        result = await self.memory.end_session(session.session_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.memory.create_session(user_id="U001")
        stats = self.memory.get_stats()
        assert stats["total_sessions"] == 1


class TestPerformanceTester:
    """测试性能测试器(D82-D83)"""

    def setup_method(self):
        self.tester = PerformanceTester()

    @pytest.mark.asyncio
    async def test_run_api_test(self):
        result = await self.tester.run_test("api", concurrency=10, duration_seconds=1.0)
        assert result.test_type == "api"
        assert result.total_requests > 0
        assert result.tps > 0

    @pytest.mark.asyncio
    async def test_run_agent_test(self):
        result = await self.tester.run_test("agent", concurrency=5, duration_seconds=1.0)
        assert result.test_type == "agent"

    @pytest.mark.asyncio
    async def test_run_rag_test(self):
        result = await self.tester.run_test("rag", concurrency=20, duration_seconds=1.0)
        assert result.test_type == "rag"

    @pytest.mark.asyncio
    async def test_result_has_percentiles(self):
        result = await self.tester.run_test("api", concurrency=10, duration_seconds=1.0)
        assert result.p50_latency_ms >= 0
        assert result.p95_latency_ms >= result.p50_latency_ms
        assert result.p99_latency_ms >= result.p95_latency_ms

    @pytest.mark.asyncio
    async def test_get_result(self):
        created = await self.tester.run_test("api", concurrency=5, duration_seconds=0.5)
        result = await self.tester.get_result(created.test_id)
        assert result.test_id == created.test_id

    @pytest.mark.asyncio
    async def test_list_results(self):
        await self.tester.run_test("api", concurrency=5, duration_seconds=0.5)
        results = await self.tester.list_results()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.tester.run_test("api", concurrency=5, duration_seconds=0.5)
        stats = self.tester.get_stats()
        assert stats["total_tests"] == 1


class TestSecurityAuditor:
    """测试安全审计器(D84)"""

    def setup_method(self):
        self.auditor = SecurityAuditor()

    @pytest.mark.asyncio
    async def test_log_login_event(self):
        event = await self.auditor.log_event(
            AuditEventType.LOGIN,
            user_id="U001",
            ip_address="192.168.1.1",
            resource="auth",
            action="login_success",
        )
        assert event.event_type == AuditEventType.LOGIN

    @pytest.mark.asyncio
    async def test_log_api_call(self):
        event = await self.auditor.log_event(
            AuditEventType.API_CALL,
            user_id="U001",
            resource="products",
            action="read",
        )
        assert event.event_type == AuditEventType.API_CALL

    @pytest.mark.asyncio
    async def test_high_risk_detection(self):
        event = await self.auditor.log_event(
            AuditEventType.CONFIG_CHANGE,
            user_id="U001",
            resource="system",
            action="update_settings",
        )
        assert event.risk_level == "high"

    @pytest.mark.asyncio
    async def test_get_event(self):
        created = await self.auditor.log_event(AuditEventType.LOGIN, user_id="U001")
        event = await self.auditor.get_event(created.event_id)
        assert event.event_id == created.event_id

    @pytest.mark.asyncio
    async def test_query_events(self):
        await self.auditor.log_event(AuditEventType.LOGIN, user_id="U001")
        await self.auditor.log_event(AuditEventType.API_CALL, user_id="U001")
        events = await self.auditor.query_events(user_id="U001")
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_user_activity(self):
        await self.auditor.log_event(AuditEventType.LOGIN, user_id="U001")
        await self.auditor.log_event(AuditEventType.API_CALL, user_id="U001")
        activity = await self.auditor.get_user_activity("U001")
        assert len(activity) == 2

    @pytest.mark.asyncio
    async def test_detect_anomalies(self):
        for _ in range(10):
            await self.auditor.log_event(
                AuditEventType.LOGIN,
                user_id="U001",
                ip_address="192.168.1.1",
                action="failed_login",
            )
        anomalies = await self.auditor.detect_anomalies()
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.auditor.log_event(AuditEventType.LOGIN, user_id="U001")
        stats = self.auditor.get_stats()
        assert stats["total_events"] == 1


class TestAlertManager:
    """测试告警管理器(D85)"""

    def setup_method(self):
        self.manager = AlertManager()

    @pytest.mark.asyncio
    async def test_update_metric(self):
        await self.manager.update_metric("api_error_rate", 3.0)
        assert self.manager._metrics["api_error_rate"] == 3.0

    @pytest.mark.asyncio
    async def test_alert_on_high_error_rate(self):
        await self.manager.update_metric("api_error_rate", 8.0)
        alerts = await self.manager.get_active_alerts()
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_alert_on_high_disk_usage(self):
        await self.manager.update_metric("disk_usage", 85.0)
        alerts = await self.manager.list_alerts()
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(self):
        await self.manager.update_metric("api_error_rate", 2.0)
        alerts = await self.manager.get_active_alerts()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self):
        await self.manager.update_metric("api_error_rate", 10.0)
        alerts = await self.manager.get_active_alerts()
        if alerts:
            alert = await self.manager.acknowledge_alert(alerts[0].alert_id)
            assert alert.acknowledged is True

    @pytest.mark.asyncio
    async def test_list_alerts_by_severity(self):
        await self.manager.update_metric("api_error_rate", 10.0)
        await self.manager.update_metric("disk_usage", 85.0)
        critical = await self.manager.list_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.manager.update_metric("api_error_rate", 10.0)
        stats = self.manager.get_stats()
        assert stats["total_alerts"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_security_workflow(self):
        memory = ConversationMemory()
        auditor = SecurityAuditor()
        alerts = AlertManager()

        await memory.create_session(user_id="U001")
        await auditor.log_event(
            AuditEventType.LOGIN,
            user_id="U001",
            ip_address="192.168.1.1",
            resource="auth",
            action="login_success",
        )

        await alerts.update_metric("api_error_rate", 8.0)
        active_alerts = await alerts.get_active_alerts()
        assert len(active_alerts) == 1

        stats = auditor.get_stats()
        assert stats["total_events"] == 1


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
