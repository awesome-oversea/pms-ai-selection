"""D86-D90 单元测试: UAT测试管理 + 缺陷追踪"""


import pytest
from src.infrastructure.uat_management import (
    Bug,
    BugSeverity,
    BugStatus,
    BugTracker,
    TestCase,
    TestPriority,
    TestStatus,
    UATManager,
    UATReport,
)


class TestTestCase:
    """测试测试用例"""

    def test_case_creation(self):
        case = TestCase(
            case_id="TC_001",
            module="选品工作流",
            title="创建选品任务",
            description="验证创建选品任务功能",
            priority=TestPriority.P0,
        )
        assert case.case_id == "TC_001"
        assert case.status == TestStatus.PENDING

    def test_case_to_dict(self):
        case = TestCase(
            case_id="TC_001",
            module="选品工作流",
            title="创建选品任务",
            description="验证功能",
            priority=TestPriority.P0,
            steps=["步骤1", "步骤2"],
        )
        d = case.to_dict()
        assert d["priority"] == "P0"
        assert len(d["steps"]) == 2


class TestBug:
    """测试缺陷"""

    def test_bug_creation(self):
        bug = Bug(
            bug_id="BUG_001",
            title="登录失败",
            description="用户无法登录系统",
            severity=BugSeverity.HIGH,
        )
        assert bug.bug_id == "BUG_001"
        assert bug.status == BugStatus.OPEN

    def test_bug_to_dict(self):
        bug = Bug(
            bug_id="BUG_001",
            title="登录失败",
            description="用户无法登录",
            severity=BugSeverity.CRITICAL,
            module="认证模块",
        )
        d = bug.to_dict()
        assert d["severity"] == "critical"
        assert d["module"] == "认证模块"


class TestUATReport:
    """测试UAT报告"""

    def test_report_creation(self):
        report = UATReport(
            report_id="UAT_RPT_001",
            round_number=1,
            total_cases=100,
            passed_cases=85,
            failed_cases=10,
            blocked_cases=5,
        )
        report.calculate_pass_rate()
        assert report.pass_rate == 85 / 100

    def test_report_to_dict(self):
        report = UATReport(
            report_id="UAT_RPT_001",
            round_number=1,
            total_cases=100,
            passed_cases=90,
            failed_cases=10,
        )
        report.calculate_pass_rate()
        d = report.to_dict()
        assert "pass_rate" in d


class TestUATManager:
    """测试UAT管理器(D86-D87)"""

    def setup_method(self):
        self.uat = UATManager()

    @pytest.mark.asyncio
    async def test_create_test_case(self):
        case = await self.uat.create_test_case(
            module="选品工作流",
            title="创建选品任务",
            description="验证创建功能",
            priority=TestPriority.P0,
        )
        assert case.case_id.startswith("TC_")
        assert case.module == "选品工作流"

    @pytest.mark.asyncio
    async def test_generate_test_cases(self):
        cases = await self.uat.generate_test_cases()
        assert len(cases) == 100

    @pytest.mark.asyncio
    async def test_execute_test_passed(self):
        case = await self.uat.create_test_case(
            module="选品工作流",
            title="测试用例",
            description="描述",
        )
        result = await self.uat.execute_test(
            case.case_id,
            passed=True,
            executor="tester",
            actual_result="符合预期",
        )
        assert result.status == TestStatus.PASSED

    @pytest.mark.asyncio
    async def test_execute_test_failed(self):
        case = await self.uat.create_test_case(
            module="选品工作流",
            title="测试用例",
            description="描述",
        )
        result = await self.uat.execute_test(
            case.case_id,
            passed=False,
            executor="tester",
            actual_result="功能异常",
        )
        assert result.status == TestStatus.FAILED

    @pytest.mark.asyncio
    async def test_batch_execute(self):
        await self.uat.generate_test_cases()
        result = await self.uat.batch_execute(pass_rate=0.9)
        assert result["total"] == 100
        assert result["passed"] > 0

    @pytest.mark.asyncio
    async def test_get_case(self):
        created = await self.uat.create_test_case(
            module="选品工作流",
            title="测试用例",
            description="描述",
        )
        case = await self.uat.get_case(created.case_id)
        assert case.title == "测试用例"

    @pytest.mark.asyncio
    async def test_list_cases_by_module(self):
        await self.uat.create_test_case(module="选品工作流", title="用例1", description="")
        await self.uat.create_test_case(module="Agent协同", title="用例2", description="")
        cases = await self.uat.list_cases(module="选品工作流")
        assert len(cases) == 1

    @pytest.mark.asyncio
    async def test_list_cases_by_status(self):
        case = await self.uat.create_test_case(module="选品工作流", title="用例", description="")
        await self.uat.execute_test(case.case_id, passed=True)
        cases = await self.uat.list_cases(status=TestStatus.PASSED)
        assert len(cases) == 1

    @pytest.mark.asyncio
    async def test_generate_report(self):
        await self.uat.generate_test_cases()
        await self.uat.batch_execute()
        report = await self.uat.generate_report(round_number=1)
        assert report.total_cases == 100
        assert report.pass_rate > 0

    @pytest.mark.asyncio
    async def test_report_conclusion_pass(self):
        await self.uat.generate_test_cases()
        await self.uat.batch_execute(pass_rate=0.95)
        report = await self.uat.generate_report()
        assert report.conclusion == "通过"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.uat.create_test_case(module="选品工作流", title="用例", description="")
        stats = self.uat.get_stats()
        assert stats["total_cases"] == 1


class TestBugTracker:
    """测试缺陷追踪器(D88)"""

    def setup_method(self):
        self.tracker = BugTracker()

    @pytest.mark.asyncio
    async def test_report_bug(self):
        bug = await self.tracker.report_bug(
            title="登录失败",
            description="用户无法登录",
            severity=BugSeverity.HIGH,
            module="认证模块",
        )
        assert bug.bug_id.startswith("BUG_")
        assert bug.severity == BugSeverity.HIGH

    @pytest.mark.asyncio
    async def test_update_bug_status(self):
        bug = await self.tracker.report_bug(
            title="缺陷",
            description="描述",
            severity=BugSeverity.MEDIUM,
        )
        updated = await self.tracker.update_bug_status(
            bug.bug_id,
            BugStatus.IN_PROGRESS,
            assignee="developer",
        )
        assert updated.status == BugStatus.IN_PROGRESS
        assert updated.assignee == "developer"

    @pytest.mark.asyncio
    async def test_update_bug_to_fixed(self):
        bug = await self.tracker.report_bug(
            title="缺陷",
            description="描述",
        )
        updated = await self.tracker.update_bug_status(bug.bug_id, BugStatus.FIXED)
        assert updated.resolved_at is not None

    @pytest.mark.asyncio
    async def test_get_bug(self):
        created = await self.tracker.report_bug(
            title="缺陷",
            description="描述",
        )
        bug = await self.tracker.get_bug(created.bug_id)
        assert bug.title == "缺陷"

    @pytest.mark.asyncio
    async def test_list_bugs_by_severity(self):
        await self.tracker.report_bug(title="缺陷1", description="", severity=BugSeverity.CRITICAL)
        await self.tracker.report_bug(title="缺陷2", description="", severity=BugSeverity.LOW)
        bugs = await self.tracker.list_bugs(severity=BugSeverity.CRITICAL)
        assert len(bugs) == 1

    @pytest.mark.asyncio
    async def test_list_bugs_by_status(self):
        bug = await self.tracker.report_bug(title="缺陷", description="")
        await self.tracker.update_bug_status(bug.bug_id, BugStatus.FIXED)
        bugs = await self.tracker.list_bugs(status=BugStatus.FIXED)
        assert len(bugs) == 1

    @pytest.mark.asyncio
    async def test_get_open_bugs(self):
        bug1 = await self.tracker.report_bug(title="缺陷1", description="")
        await self.tracker.report_bug(title="缺陷2", description="")
        await self.tracker.update_bug_status(bug1.bug_id, BugStatus.CLOSED)
        open_bugs = await self.tracker.get_open_bugs()
        assert len(open_bugs) == 1

    @pytest.mark.asyncio
    async def test_get_critical_bugs(self):
        await self.tracker.report_bug(title="严重缺陷", description="", severity=BugSeverity.CRITICAL)
        await self.tracker.report_bug(title="普通缺陷", description="", severity=BugSeverity.MEDIUM)
        critical = await self.tracker.get_critical_bugs()
        assert len(critical) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.tracker.report_bug(title="缺陷", description="")
        stats = self.tracker.get_stats()
        assert stats["total_bugs"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_uat_bug_workflow(self):
        uat = UATManager()
        tracker = BugTracker()

        case = await uat.create_test_case(
            module="选品工作流",
            title="创建选品任务",
            description="验证功能",
            priority=TestPriority.P0,
        )

        await uat.execute_test(case.case_id, passed=False, actual_result="功能异常")

        bug = await tracker.report_bug(
            title="选品任务创建失败",
            description="无法创建选品任务",
            severity=BugSeverity.HIGH,
            module="选品工作流",
            case_id=case.case_id,
        )

        await tracker.update_bug_status(bug.bug_id, BugStatus.FIXED)
        await tracker.update_bug_status(bug.bug_id, BugStatus.VERIFIED)

        await uat.execute_test(case.case_id, passed=True, actual_result="已修复")

        report = await uat.generate_report()
        assert report.passed_cases >= 1


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
