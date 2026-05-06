"""D76-D80 单元测试: 自动报告 + 知识库增强 + 数据看板

验证报告引擎、知识库更新器、数据看板的行为逻辑:
    - 报告生成流程(状态流转/指标填充/摘要生成)
    - 知识库增量更新(版本递增/变更检测/同步)
    - 数据看板(KPI更新/告警管理/状态计算)
"""

from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import pytest
from src.infrastructure.report_dashboard import (
    DashboardManager,
    KnowledgeBaseUpdater,
    Report,
    ReportEngine,
    ReportStatus,
    ReportType,
)


class TestReport:
    """报告数据模型行为测试"""

    def test_default_status_is_pending(self):
        report = Report(report_id="RPT_001", report_type=ReportType.DAILY, title="日报", content="内容")
        assert report.status == ReportStatus.PENDING

    def test_to_dict_serializes_enum_values(self):
        report = Report(
            report_id="RPT_001", report_type=ReportType.WEEKLY,
            title="周报", content="内容", status=ReportStatus.COMPLETED,
        )
        d = report.to_dict()
        assert d["report_type"] == "weekly"
        assert d["status"] == "completed"
        assert d["format"] == "html"

    def test_to_dict_preserves_metrics_and_charts(self):
        report = Report(
            report_id="RPT_002", report_type=ReportType.MONTHLY,
            title="月报", content="",
            metrics={"task_count": 100},
            charts=[{"chart_id": "c1"}],
        )
        d = report.to_dict()
        assert d["metrics"]["task_count"] == 100
        assert len(d["charts"]) == 1


class TestReportEngine:
    """报告引擎行为测试(D76-D77): 验证生成流程和状态流转"""

    @pytest.mark.asyncio
    async def test_generate_report_transitions_to_completed(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert report.status == ReportStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_daily_report_title_contains_date(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert "日报" in report.title

    @pytest.mark.asyncio
    async def test_weekly_report_title_contains_weekly(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.WEEKLY)
        assert "周报" in report.title

    @pytest.mark.asyncio
    async def test_monthly_report_title_contains_monthly(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.MONTHLY)
        assert "月报" in report.title

    @pytest.mark.asyncio
    async def test_report_contains_required_metrics(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert "task_count" in report.metrics
        assert "completion_rate" in report.metrics
        assert "gmv" in report.metrics

    @pytest.mark.asyncio
    async def test_report_contains_charts(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert len(report.charts) >= 1

    @pytest.mark.asyncio
    async def test_report_has_non_empty_summary(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert len(report.summary) > 0

    @pytest.mark.asyncio
    async def test_report_has_non_empty_content(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.DAILY)
        assert len(report.content) > 0

    @pytest.mark.asyncio
    async def test_custom_metrics_merge_into_report(self):
        engine = ReportEngine()
        report = await engine.generate_report(
            ReportType.DAILY, metrics={"custom_key": 42},
        )
        assert report.metrics["custom_key"] == 42
        assert "task_count" in report.metrics

    @pytest.mark.asyncio
    async def test_get_report_retrieves_created_report(self):
        engine = ReportEngine()
        created = await engine.generate_report(ReportType.DAILY)
        retrieved = await engine.get_report(created.report_id)
        assert retrieved is not None
        assert retrieved.report_id == created.report_id

    @pytest.mark.asyncio
    async def test_list_reports_returns_all(self):
        engine = ReportEngine()
        await engine.generate_report(ReportType.DAILY)
        await engine.generate_report(ReportType.WEEKLY)
        reports = await engine.list_reports()
        assert len(reports) == 2

    @pytest.mark.asyncio
    async def test_stats_track_generation(self):
        engine = ReportEngine()
        await engine.generate_report(ReportType.DAILY)
        stats = engine.get_stats()
        assert stats["total_reports"] == 1
        assert stats["by_type"]["daily"] == 1
        assert stats["by_status"]["completed"] == 1

    @pytest.mark.asyncio
    async def test_weekly_report_includes_trend_metrics(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.WEEKLY)
        assert "trend_change" in report.metrics
        assert "competitor_updates" in report.metrics

    @pytest.mark.asyncio
    async def test_monthly_report_includes_roi_metrics(self):
        engine = ReportEngine()
        report = await engine.generate_report(ReportType.MONTHLY)
        assert "kpi_achievement" in report.metrics
        assert "roi" in report.metrics


class TestKnowledgeBaseUpdater:
    """知识库更新器行为测试(D78): 验证版本管理和变更检测"""

    @pytest.mark.asyncio
    async def test_add_document_assigns_id_and_version(self):
        updater = KnowledgeBaseUpdater()
        doc = await updater.add_document(title="产品手册", content="说明", category="manual")
        assert doc.doc_id.startswith("DOC_")
        assert doc.version == 1
        assert doc.embedding_hash is not None

    @pytest.mark.asyncio
    async def test_update_document_increments_version(self):
        updater = KnowledgeBaseUpdater()
        doc = await updater.add_document(title="文档", content="v1")
        updated = await updater.update_document(doc.doc_id, "v2内容已更新")
        assert updated.version == 2
        assert updated.content == "v2内容已更新"

    @pytest.mark.asyncio
    async def test_update_same_content_does_not_increment_version(self):
        updater = KnowledgeBaseUpdater()
        doc = await updater.add_document(title="文档", content="不变的内容")
        updated = await updater.update_document(doc.doc_id, "不变的内容")
        assert updated.version == 1

    @pytest.mark.asyncio
    async def test_detect_changes_returns_all_without_since(self):
        updater = KnowledgeBaseUpdater()
        await updater.add_document(title="文档1", content="内容1")
        await updater.add_document(title="文档2", content="内容2")
        changes = await updater.detect_changes()
        assert len(changes) == 2

    @pytest.mark.asyncio
    async def test_sync_updates_reports_synced_count(self):
        updater = KnowledgeBaseUpdater()
        await updater.add_document(title="文档", content="内容")
        result = await updater.sync_updates()
        assert result["synced"] == 1
        assert result["last_sync"] is not None

    @pytest.mark.asyncio
    async def test_version_history_tracks_all_versions(self):
        updater = KnowledgeBaseUpdater()
        doc = await updater.add_document(title="文档", content="v1")
        await updater.update_document(doc.doc_id, "v2")
        await updater.update_document(doc.doc_id, "v3")
        history = await updater.get_version_history(doc.doc_id)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_document_returns_created_doc(self):
        updater = KnowledgeBaseUpdater()
        created = await updater.add_document(title="文档", content="内容")
        retrieved = await updater.get_document(created.doc_id)
        assert retrieved is not None
        assert retrieved.title == "文档"

    @pytest.mark.asyncio
    async def test_stats_reflect_document_count(self):
        updater = KnowledgeBaseUpdater()
        await updater.add_document(title="文档", content="内容")
        stats = updater.get_stats()
        assert stats["total_docs"] == 1


class TestDashboardManager:
    """数据看板行为测试(D80): 验证KPI更新和告警管理"""

    @pytest.mark.asyncio
    async def test_initial_kpis_include_core_metrics(self):
        dashboard = DashboardManager()
        kpis = await dashboard.get_kpis()
        kpi_names = {k.name for k in kpis}
        assert "GMV" in kpi_names
        assert len(kpis) == 4

    @pytest.mark.asyncio
    async def test_get_kpi_by_id(self):
        dashboard = DashboardManager()
        kpi = await dashboard.get_kpi("gmv")
        assert kpi is not None
        assert kpi.name == "GMV"

    @pytest.mark.asyncio
    async def test_update_kpi_changes_value_and_trend(self):
        dashboard = DashboardManager()
        await dashboard.get_kpi("gmv")
        updated = await dashboard.update_kpi("gmv", 200000)
        assert updated.value == 200000
        assert updated.trend == "up"

    @pytest.mark.asyncio
    async def test_update_kpi_below_target_sets_warning(self):
        dashboard = DashboardManager()
        await dashboard.update_kpi("gmv", 1)
        kpi = await dashboard.get_kpi("gmv")
        assert kpi.status == "warning"

    @pytest.mark.asyncio
    async def test_update_kpi_meets_target_sets_success(self):
        dashboard = DashboardManager()
        await dashboard.update_kpi("gmv", 999999)
        kpi = await dashboard.get_kpi("gmv")
        assert kpi.status == "success"

    @pytest.mark.asyncio
    async def test_initial_charts_include_required_types(self):
        dashboard = DashboardManager()
        charts = await dashboard.get_charts()
        chart_types = {c.chart_type for c in charts}
        assert "line" in chart_types
        assert "pie" in chart_types

    @pytest.mark.asyncio
    async def test_add_alert_creates_unacknowledged_alert(self):
        dashboard = DashboardManager()
        alert = await dashboard.add_alert(level="high", message="库存不足", source="wms")
        assert alert["level"] == "high"
        assert alert["acknowledged"] is False
        assert alert["alert_id"].startswith("ALERT_")

    @pytest.mark.asyncio
    async def test_get_alerts_returns_all(self):
        dashboard = DashboardManager()
        await dashboard.add_alert(level="high", message="告警1")
        await dashboard.add_alert(level="low", message="告警2")
        alerts = await dashboard.get_alerts()
        assert len(alerts) == 2

    @pytest.mark.asyncio
    async def test_get_alerts_filters_by_level(self):
        dashboard = DashboardManager()
        await dashboard.add_alert(level="high", message="高告警")
        await dashboard.add_alert(level="low", message="低告警")
        alerts = await dashboard.get_alerts(level="high")
        assert len(alerts) == 1
        assert alerts[0]["level"] == "high"

    @pytest.mark.asyncio
    async def test_acknowledge_alert_changes_status(self):
        dashboard = DashboardManager()
        alert = await dashboard.add_alert(level="high", message="告警")
        result = await dashboard.acknowledge_alert(alert["alert_id"])
        assert result["acknowledged"] is True

    @pytest.mark.asyncio
    async def test_stats_track_kpis_and_alerts(self):
        dashboard = DashboardManager()
        await dashboard.add_alert(level="high", message="告警")
        stats = dashboard.get_stats()
        assert stats["total_kpis"] == 4
        assert stats["total_alerts"] == 1


class TestIntegration:
    """报告-知识库-看板联动集成测试"""

    @pytest.mark.asyncio
    async def test_report_knowledge_dashboard_workflow(self):
        engine = ReportEngine()
        updater = KnowledgeBaseUpdater()
        dashboard = DashboardManager()

        doc = await updater.add_document(
            title="选品报告模板", content="报告模板内容", category="template",
        )
        assert doc.version == 1

        report = await engine.generate_report(
            ReportType.DAILY, metrics={"doc_count": 1},
        )
        assert report.status == ReportStatus.COMPLETED

        await dashboard.add_alert(
            level="info", message=f"报告已生成: {report.title}", source="report_engine",
        )
        alerts = await dashboard.get_alerts()
        assert len(alerts) == 1
        assert "报告已生成" in alerts[0]["message"]
