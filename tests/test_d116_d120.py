"""D116-D120 单元测试: 运维工具链与监控"""


import pytest
from src.infrastructure.ops_toolkit import (
    Alert,
    AlertLevel,
    AlertManager,
    AlertStatus,
    CheckStatus,
    CheckType,
    DashboardManager,
    InspectionItem,
    InspectionManager,
    KnowledgeArticle,
    KnowledgeBase,
    OpsScriptManager,
    ScriptExecution,
    ScriptStatus,
    ScriptType,
)


class TestScriptExecution:
    """测试脚本执行"""

    def test_execution_creation(self):
        execution = ScriptExecution(
            execution_id="EXEC_001",
            script_type=ScriptType.HEALTH_CHECK,
        )
        assert execution.execution_id == "EXEC_001"
        assert execution.status == ScriptStatus.PENDING

    def test_execution_to_dict(self):
        execution = ScriptExecution(
            execution_id="EXEC_001",
            script_type=ScriptType.LOG_ROTATE,
            status=ScriptStatus.SUCCESS,
            duration_seconds=30.5,
        )
        d = execution.to_dict()
        assert d["status"] == "success"


class TestAlert:
    """测试告警"""

    def test_alert_creation(self):
        alert = Alert(
            alert_id="ALERT_001",
            level=AlertLevel.P0,
            title="服务宕机",
        )
        assert alert.alert_id == "ALERT_001"
        assert alert.status == AlertStatus.FIRING

    def test_alert_to_dict(self):
        alert = Alert(
            alert_id="ALERT_001",
            level=AlertLevel.P1,
            title="错误率过高",
            notified_channels=["dingtalk", "email"],
        )
        d = alert.to_dict()
        assert d["level"] == "P1"


class TestInspectionItem:
    """测试巡检项"""

    def test_item_creation(self):
        item = InspectionItem(
            item_id="CHECK_001",
            name="服务健康检查",
            check_type=CheckType.DAILY,
        )
        assert item.item_id == "CHECK_001"
        assert item.status == CheckStatus.PASS

    def test_item_to_dict(self):
        item = InspectionItem(
            item_id="CHECK_001",
            name="磁盘空间",
            check_type=CheckType.WEEKLY,
            status=CheckStatus.WARN,
        )
        d = item.to_dict()
        assert d["status"] == "warn"


class TestKnowledgeArticle:
    """测试知识库文章"""

    def test_article_creation(self):
        article = KnowledgeArticle(
            article_id="KB_001",
            title="GPU内存溢出处理",
            category="troubleshooting",
        )
        assert article.article_id == "KB_001"
        assert article.views == 0

    def test_article_to_dict(self):
        article = KnowledgeArticle(
            article_id="KB_001",
            title="部署手册",
            category="runbooks",
            tags=["deployment", "k8s"],
        )
        d = article.to_dict()
        assert d["category"] == "runbooks"


class TestOpsScriptManager:
    """测试运维脚本管理器(D116)"""

    def setup_method(self):
        self.ops = OpsScriptManager()

    @pytest.mark.asyncio
    async def test_run_script(self):
        execution = await self.ops.run_script(ScriptType.HEALTH_CHECK)
        assert execution.execution_id.startswith("EXEC_")
        assert execution.status in [ScriptStatus.SUCCESS, ScriptStatus.FAILED]

    @pytest.mark.asyncio
    async def test_run_all_scripts(self):
        executions = await self.ops.run_all_scripts()
        assert len(executions) == 5

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.ops.run_all_scripts()
        stats = self.ops.get_stats()
        assert stats["total_runs"] == 5


class TestDashboardManager:
    """测试监控大屏管理器(D117)"""

    def setup_method(self):
        self.dashboard = DashboardManager()

    @pytest.mark.asyncio
    async def test_refresh_metrics(self):
        metrics = await self.dashboard.refresh_metrics()
        assert "qps" in metrics
        assert "latency_ms" in metrics

    @pytest.mark.asyncio
    async def test_get_dashboard(self):
        await self.dashboard.refresh_metrics()
        result = await self.dashboard.get_dashboard("系统总览")
        assert result is not None
        assert result["name"] == "系统总览"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.dashboard.refresh_metrics()
        stats = self.dashboard.get_stats()
        assert stats["refresh_count"] == 1


class TestAlertManager:
    """测试告警管理器(D118)"""

    def setup_method(self):
        self.alert = AlertManager()

    @pytest.mark.asyncio
    async def test_send_alert(self):
        alert = await self.alert.send_alert(
            level=AlertLevel.P0,
            title="服务宕机",
            description="API服务不可用",
        )
        assert alert.alert_id.startswith("ALERT_")
        assert alert.level == AlertLevel.P0

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self):
        created = await self.alert.send_alert(AlertLevel.P1, "测试告警")
        result = await self.alert.acknowledge_alert(created.alert_id, "admin")
        assert result.acknowledged is True

    @pytest.mark.asyncio
    async def test_resolve_alert(self):
        created = await self.alert.send_alert(AlertLevel.P2, "测试告警")
        result = await self.alert.resolve_alert(created.alert_id)
        assert result.status == AlertStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_get_alert(self):
        created = await self.alert.send_alert(AlertLevel.P3, "测试")
        alert = await self.alert.get_alert(created.alert_id)
        assert alert.title == "测试"

    @pytest.mark.asyncio
    async def test_list_alerts(self):
        await self.alert.send_alert(AlertLevel.P0, "告警1")
        await self.alert.send_alert(AlertLevel.P1, "告警2")
        alerts = await self.alert.list_alerts(level=AlertLevel.P0)
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.alert.send_alert(AlertLevel.P0, "测试")
        stats = self.alert.get_stats()
        assert stats["total_alerts"] == 1


class TestInspectionManager:
    """测试巡检管理器(D119)"""

    def setup_method(self):
        self.inspect = InspectionManager()

    @pytest.mark.asyncio
    async def test_run_check(self):
        item = await self.inspect.run_check("服务健康", CheckType.DAILY)
        assert item.item_id.startswith("CHECK_")
        assert item.status in [CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL]

    @pytest.mark.asyncio
    async def test_run_daily_inspection(self):
        report = await self.inspect.run_daily_inspection()
        assert "report_id" in report
        assert report["type"] == "daily"
        assert len(report["items"]) == 4

    @pytest.mark.asyncio
    async def test_run_weekly_inspection(self):
        report = await self.inspect.run_weekly_inspection()
        assert report["type"] == "weekly"
        assert len(report["items"]) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.inspect.run_daily_inspection()
        stats = self.inspect.get_stats()
        assert stats["total_checks"] == 4


class TestKnowledgeBase:
    """测试运维知识库(D120)"""

    def setup_method(self):
        self.kb = KnowledgeBase()

    @pytest.mark.asyncio
    async def test_create_article(self):
        article = await self.kb.create_article(
            title="GPU内存溢出处理",
            category="troubleshooting",
            content="重启服务...",
            tags=["gpu", "oom"],
        )
        assert article.article_id.startswith("KB_")

    @pytest.mark.asyncio
    async def test_get_article(self):
        created = await self.kb.create_article("测试文章", "faq")
        article = await self.kb.get_article(created.article_id)
        assert article.views == 1

    @pytest.mark.asyncio
    async def test_search_articles(self):
        await self.kb.create_article("GPU问题", "troubleshooting", tags=["gpu"])
        await self.kb.create_article("CPU问题", "troubleshooting", tags=["cpu"])
        results = await self.kb.search_articles("GPU")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_list_by_category(self):
        await self.kb.create_article("文章1", "troubleshooting")
        await self.kb.create_article("文章2", "faq")
        articles = await self.kb.list_by_category("troubleshooting")
        assert len(articles) == 1

    @pytest.mark.asyncio
    async def test_mark_helpful(self):
        created = await self.kb.create_article("测试", "faq")
        result = await self.kb.mark_helpful(created.article_id)
        assert result.helpful_count == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.kb.create_article("文章", "faq")
        stats = self.kb.get_stats()
        assert stats["total_articles"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_ops_workflow(self):
        ops = OpsScriptManager()
        dashboard = DashboardManager()
        alert = AlertManager()
        inspect = InspectionManager()
        kb = KnowledgeBase()

        execution = await ops.run_script(ScriptType.HEALTH_CHECK)

        if execution.status == ScriptStatus.FAILED:
            await alert.send_alert(AlertLevel.P1, "健康检查失败")

        metrics = await dashboard.refresh_metrics()
        report = await inspect.run_daily_inspection()

        if report["summary"]["failed"] > 0:
            await kb.create_article(
                "故障处理",
                "troubleshooting",
                "处理步骤...",
            )

        assert execution.status in [ScriptStatus.SUCCESS, ScriptStatus.FAILED]
        assert "qps" in metrics
        assert report["type"] == "daily"


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
