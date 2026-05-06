"""D121-D125 单元测试: 用户培训与试运行"""


import pytest
from src.infrastructure.training import (
    CourseType,
    Issue,
    IssuePriority,
    IssueStatus,
    IssueType,
    MaterialType,
    SessionStatus,
    TrainingManager,
    TrainingMaterial,
    TrainingSession,
    TrialRunManager,
    TrialRunStats,
)


class TestTrainingMaterial:
    """测试培训材料"""

    def test_material_creation(self):
        material = TrainingMaterial(
            material_id="MATERIAL_001",
            title="系统概述PPT",
            material_type=MaterialType.PPT,
            course_type=CourseType.OVERVIEW,
        )
        assert material.material_id == "MATERIAL_001"
        assert material.material_type == MaterialType.PPT

    def test_material_to_dict(self):
        material = TrainingMaterial(
            material_id="MATERIAL_001",
            title="操作视频",
            material_type=MaterialType.VIDEO,
            course_type=CourseType.OPERATION,
            duration_minutes=30,
        )
        d = material.to_dict()
        assert d["material_type"] == "video"


class TestTrainingSession:
    """测试培训场次"""

    def test_session_creation(self):
        session = TrainingSession(
            session_id="SESSION_001",
            course_type=CourseType.OVERVIEW,
            title="系统概述",
            target_audience="全员",
        )
        assert session.session_id == "SESSION_001"
        assert session.status == SessionStatus.SCHEDULED

    def test_session_to_dict(self):
        session = TrainingSession(
            session_id="SESSION_001",
            course_type=CourseType.OPERATION,
            title="选品操作",
            target_audience="运营人员",
            duration_hours=4,
            attendees=20,
        )
        d = session.to_dict()
        assert d["duration_hours"] == 4


class TestIssue:
    """测试问题"""

    def test_issue_creation(self):
        issue = Issue(
            issue_id="ISSUE_001",
            title="登录失败",
            issue_type=IssueType.BUG,
        )
        assert issue.issue_id == "ISSUE_001"
        assert issue.status == IssueStatus.OPEN

    def test_issue_to_dict(self):
        issue = Issue(
            issue_id="ISSUE_001",
            title="界面卡顿",
            issue_type=IssueType.EXPERIENCE,
            priority=IssuePriority.HIGH,
            reporter="user1",
        )
        d = issue.to_dict()
        assert d["issue_type"] == "experience"


class TestTrialRunStats:
    """测试试运行统计"""

    def test_stats_creation(self):
        stats = TrialRunStats()
        assert stats.active_users == 0
        assert stats.satisfaction_score == 0.0

    def test_stats_to_dict(self):
        stats = TrialRunStats(
            active_users=20,
            total_tasks=100,
            completed_tasks=80,
            satisfaction_score=85.5,
        )
        d = stats.to_dict()
        assert d["active_users"] == 20


class TestTrainingManager:
    """测试培训管理器(D121-D122)"""

    def setup_method(self):
        self.training = TrainingManager()

    @pytest.mark.asyncio
    async def test_create_material(self):
        material = await self.training.create_material(
            title="系统概述PPT",
            material_type=MaterialType.PPT,
            course_type=CourseType.OVERVIEW,
            duration_minutes=120,
        )
        assert material.material_id.startswith("MATERIAL_")

    @pytest.mark.asyncio
    async def test_create_course(self):
        session = await self.training.create_course(CourseType.OVERVIEW)
        assert session.session_id.startswith("SESSION_")
        assert session.title == "系统概述"

    @pytest.mark.asyncio
    async def test_start_session(self):
        session = await self.training.create_course(CourseType.OPERATION)
        result = await self.training.start_session(session.session_id, 15)
        assert result.status == SessionStatus.IN_PROGRESS
        assert result.attendees == 15

    @pytest.mark.asyncio
    async def test_complete_session(self):
        session = await self.training.create_course(CourseType.MONITORING)
        await self.training.start_session(session.session_id, 10)
        result = await self.training.complete_session(session.session_id)
        assert result.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_session(self):
        created = await self.training.create_course(CourseType.DATA_MANAGEMENT)
        session = await self.training.get_session(created.session_id)
        assert session.title == "数据管理"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.training.create_course(CourseType.OVERVIEW)
        stats = self.training.get_stats()
        assert stats["total_courses"] == 1


class TestTrialRunManager:
    """测试试运行管理器(D123-D125)"""

    def setup_method(self):
        self.trial = TrialRunManager()

    @pytest.mark.asyncio
    async def test_start_trial_run(self):
        result = await self.trial.start_trial_run(20)
        assert result["status"] == "started"
        assert result["participants"] == 20

    @pytest.mark.asyncio
    async def test_report_issue(self):
        await self.trial.start_trial_run()
        issue = await self.trial.report_issue(
            title="登录失败",
            issue_type=IssueType.BUG,
            description="无法登录系统",
            reporter="user1",
        )
        assert issue.issue_id.startswith("ISSUE_")
        assert issue.priority == IssuePriority.HIGH

    @pytest.mark.asyncio
    async def test_resolve_issue(self):
        await self.trial.start_trial_run()
        created = await self.trial.report_issue("测试问题", IssueType.BUG)
        result = await self.trial.resolve_issue(created.issue_id, "已修复")
        assert result.status == IssueStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_get_issue(self):
        await self.trial.start_trial_run()
        created = await self.trial.report_issue("问题", IssueType.EXPERIENCE)
        issue = await self.trial.get_issue(created.issue_id)
        assert issue.title == "问题"

    @pytest.mark.asyncio
    async def test_list_issues(self):
        await self.trial.start_trial_run()
        await self.trial.report_issue("Bug1", IssueType.BUG)
        await self.trial.report_issue("体验1", IssueType.EXPERIENCE)
        issues = await self.trial.list_issues(issue_type=IssueType.BUG)
        assert len(issues) == 1

    @pytest.mark.asyncio
    async def test_update_stats(self):
        await self.trial.start_trial_run()
        stats = await self.trial.update_stats(
            tasks=100,
            completed=80,
            feature_usage={"选品": 50, "报告": 30},
            satisfaction=85.0,
        )
        assert stats.total_tasks == 100
        assert stats.satisfaction_score == 85.0

    @pytest.mark.asyncio
    async def test_generate_summary(self):
        await self.trial.start_trial_run()
        await self.trial.report_issue("问题1", IssueType.BUG)
        await self.trial.update_stats(satisfaction=85.0)
        summary = await self.trial.generate_summary()
        assert "stats" in summary
        assert "issues_summary" in summary

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.trial.start_trial_run()
        stats = self.trial.get_stats()
        assert stats["active_users"] == 20


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_training_and_trial_workflow(self):
        training = TrainingManager()
        trial = TrialRunManager()

        for course_type in [CourseType.OVERVIEW, CourseType.OPERATION]:
            session = await training.create_course(course_type)
            await training.start_session(session.session_id, 10)
            await training.complete_session(session.session_id)

        await trial.start_trial_run(20)

        await trial.report_issue("登录问题", IssueType.BUG, reporter="user1")
        await trial.report_issue("界面优化", IssueType.EXPERIENCE, reporter="user2")

        await trial.update_stats(tasks=50, completed=45, satisfaction=88.0)

        summary = await trial.generate_summary()

        assert training.get_stats()["total_courses"] == 2
        assert summary["stats"]["active_users"] == 20
        assert summary["stats"]["issues_reported"] == 2


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
