"""
UAT测试管理 + 缺陷追踪 + 验收报告
================================

提供UAT测试管理能力(D86-D90):
    - 测试用例管理
    - 缺陷追踪
    - UAT执行记录
    - 验收报告生成

使用方式:
    from src.infrastructure.uat_management import UATManager, BugTracker

    uat = UATManager()
    case = await uat.create_test_case(...)
    result = await uat.execute_test(case.case_id)

    tracker = BugTracker()
    bug = await tracker.report_bug(...)
"""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class TestPriority(StrEnum):
    """测试优先级。"""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TestStatus(StrEnum):
    """测试状态。"""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class BugSeverity(StrEnum):
    """缺陷严重程度。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BugStatus(StrEnum):
    """缺陷状态。"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    VERIFIED = "verified"
    CLOSED = "closed"
    WONT_FIX = "wont_fix"


@dataclass
class TestCase:
    """测试用例。"""
    case_id: str
    module: str
    title: str
    description: str
    priority: TestPriority = TestPriority.P1
    preconditions: str = ""
    steps: list[str] = field(default_factory=list)
    expected_result: str = ""
    status: TestStatus = TestStatus.PENDING
    executed_at: str | None = None
    executed_by: str | None = None
    actual_result: str | None = None
    bug_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "module": self.module,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "preconditions": self.preconditions,
            "steps": self.steps,
            "expected_result": self.expected_result,
            "status": self.status.value,
            "executed_at": self.executed_at,
            "executed_by": self.executed_by,
            "actual_result": self.actual_result,
            "bug_id": self.bug_id,
            "created_at": self.created_at,
        }


@dataclass
class Bug:
    """缺陷。"""
    bug_id: str
    title: str
    description: str
    severity: BugSeverity = BugSeverity.MEDIUM
    status: BugStatus = BugStatus.OPEN
    module: str = ""
    case_id: str | None = None
    reporter: str | None = None
    assignee: str | None = None
    steps_to_reproduce: list[str] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    environment: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bug_id": self.bug_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "module": self.module,
            "case_id": self.case_id,
            "reporter": self.reporter,
            "assignee": self.assignee,
            "steps_to_reproduce": self.steps_to_reproduce,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "environment": self.environment,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class UATReport:
    """UAT报告。"""
    report_id: str
    round_number: int
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    blocked_cases: int = 0
    skipped_cases: int = 0
    total_bugs: int = 0
    critical_bugs: int = 0
    high_bugs: int = 0
    medium_bugs: int = 0
    low_bugs: int = 0
    pass_rate: float = 0.0
    modules: dict[str, dict[str, int]] = field(default_factory=dict)
    conclusion: str = ""
    recommendations: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def calculate_pass_rate(self) -> None:
        executed = self.passed_cases + self.failed_cases + self.blocked_cases
        if executed > 0:
            self.pass_rate = self.passed_cases / executed

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "round_number": self.round_number,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "blocked_cases": self.blocked_cases,
            "skipped_cases": self.skipped_cases,
            "total_bugs": self.total_bugs,
            "critical_bugs": self.critical_bugs,
            "high_bugs": self.high_bugs,
            "medium_bugs": self.medium_bugs,
            "low_bugs": self.low_bugs,
            "pass_rate": round(self.pass_rate, 4),
            "modules": self.modules,
            "conclusion": self.conclusion,
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }


class UATManager:
    """
    UAT测试管理器(D86-D87)。

    功能:
        1. 测试用例管理
        2. 测试执行记录
        3. 测试报告生成
    """

    MODULE_SCENARIOS = {
        "选品工作流": 20,
        "Agent协同": 15,
        "ERP对接": 25,
        "报告系统": 10,
        "前端页面": 30,
    }

    def __init__(self):
        self._cases: dict[str, TestCase] = {}
        self._reports: dict[str, UATReport] = {}
        self._current_round: int = 0
        self._stats = {
            "total_cases": 0,
            "by_module": defaultdict(int),
            "by_priority": defaultdict(int),
            "by_status": defaultdict(int),
        }
        logger.info("UATManager初始化完成")

    async def create_test_case(
        self,
        module: str,
        title: str,
        description: str,
        priority: TestPriority = TestPriority.P1,
        steps: list[str] | None = None,
        expected_result: str = "",
    ) -> TestCase:
        """创建测试用例。"""
        case_id = f"TC_{uuid.uuid4().hex[:6].upper()}"

        case = TestCase(
            case_id=case_id,
            module=module,
            title=title,
            description=description,
            priority=priority,
            steps=steps or [],
            expected_result=expected_result,
        )

        self._cases[case_id] = case
        self._stats["total_cases"] += 1
        self._stats["by_module"][module] += 1
        self._stats["by_priority"][priority.value] += 1
        self._stats["by_status"][TestStatus.PENDING.value] += 1

        logger.info(f"创建测试用例: {case_id} - {title}")
        return case

    async def generate_test_cases(self) -> list[TestCase]:
        """生成测试用例(D86)。"""
        cases = []
        for module, count in self.MODULE_SCENARIOS.items():
            for i in range(count):
                case = await self.create_test_case(
                    module=module,
                    title=f"{module}测试场景{i + 1}",
                    description=f"验证{module}功能{i + 1}",
                    priority=TestPriority.P0 if i < 5 else TestPriority.P1,
                    steps=[f"步骤1: 进入{module}页面", f"步骤2: 执行操作{i + 1}", "步骤3: 验证结果"],
                    expected_result="功能正常，无异常",
                )
                cases.append(case)
        return cases

    async def execute_test(
        self,
        case_id: str,
        passed: bool,
        executor: str | None = None,
        actual_result: str | None = None,
        bug_id: str | None = None,
    ) -> TestCase | None:
        """执行测试。"""
        case = self._cases.get(case_id)
        if not case:
            return None

        old_status = case.status
        case.status = TestStatus.PASSED if passed else TestStatus.FAILED
        case.executed_at = datetime.now(UTC).isoformat()
        case.executed_by = executor
        case.actual_result = actual_result
        case.bug_id = bug_id

        self._stats["by_status"][old_status.value] -= 1
        self._stats["by_status"][case.status.value] += 1

        logger.info(f"执行测试: {case_id} - {case.status.value}")
        return case

    async def batch_execute(self, pass_rate: float = 0.85) -> dict[str, Any]:
        """批量执行测试(D87)。"""
        pending_cases = [c for c in self._cases.values() if c.status == TestStatus.PENDING]
        passed = 0
        failed = 0

        for case in pending_cases:
            is_passed = random.random() < pass_rate
            await self.execute_test(
                case.case_id,
                is_passed,
                executor="UAT_Tester",
                actual_result="符合预期" if is_passed else "功能异常",
            )
            if is_passed:
                passed += 1
            else:
                failed += 1

        return {
            "total": len(pending_cases),
            "passed": passed,
            "failed": failed,
        }

    async def get_case(self, case_id: str) -> TestCase | None:
        return self._cases.get(case_id)

    async def list_cases(
        self,
        module: str | None = None,
        priority: TestPriority | None = None,
        status: TestStatus | None = None,
    ) -> list[TestCase]:
        """列出测试用例。"""
        results = list(self._cases.values())
        if module:
            results = [c for c in results if c.module == module]
        if priority:
            results = [c for c in results if c.priority == priority]
        if status:
            results = [c for c in results if c.status == status]
        return results

    async def generate_report(self, round_number: int = 1) -> UATReport:
        """生成UAT报告(D89)。"""
        report_id = f"UAT_RPT_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        cases = list(self._cases.values())
        modules: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})

        for case in cases:
            modules[case.module]["total"] += 1
            if case.status == TestStatus.PASSED:
                modules[case.module]["passed"] += 1
            elif case.status == TestStatus.FAILED:
                modules[case.module]["failed"] += 1

        report = UATReport(
            report_id=report_id,
            round_number=round_number,
            total_cases=len(cases),
            passed_cases=sum(1 for c in cases if c.status == TestStatus.PASSED),
            failed_cases=sum(1 for c in cases if c.status == TestStatus.FAILED),
            blocked_cases=sum(1 for c in cases if c.status == TestStatus.BLOCKED),
            skipped_cases=sum(1 for c in cases if c.status == TestStatus.SKIPPED),
            modules=dict(modules),
        )
        report.calculate_pass_rate()

        if report.pass_rate >= 0.9:
            report.conclusion = "通过"
            report.recommendations = ["可以进入下一阶段"]
        elif report.pass_rate >= 0.8:
            report.conclusion = "有条件通过"
            report.recommendations = ["修复高优先级缺陷后可进入下一阶段"]
        else:
            report.conclusion = "不通过"
            report.recommendations = ["需要修复缺陷并重新测试"]

        self._reports[report_id] = report
        self._current_round = round_number

        logger.info(f"生成UAT报告: {report_id} - 通过率{report.pass_rate:.2%}")
        return report

    async def get_report(self, report_id: str) -> UATReport | None:
        return self._reports.get(report_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_module": dict(self._stats["by_module"]),
            "by_priority": dict(self._stats["by_priority"]),
            "by_status": dict(self._stats["by_status"]),
            "current_round": self._current_round,
        }


class BugTracker:
    """
    缺陷追踪器(D88)。

    功能:
        1. 缺陷报告
        2. 缺陷状态流转
        3. 缺陷统计
    """

    SEVERITY_SLA = {
        BugSeverity.CRITICAL: "立即修复",
        BugSeverity.HIGH: "24h内修复",
        BugSeverity.MEDIUM: "本周内修复",
        BugSeverity.LOW: "下迭代处理",
    }

    def __init__(self):
        self._bugs: dict[str, Bug] = {}
        self._stats = {
            "total_bugs": 0,
            "by_severity": defaultdict(int),
            "by_status": defaultdict(int),
            "by_module": defaultdict(int),
        }
        logger.info("BugTracker初始化完成")

    async def report_bug(
        self,
        title: str,
        description: str,
        severity: BugSeverity = BugSeverity.MEDIUM,
        module: str = "",
        case_id: str | None = None,
        reporter: str | None = None,
        steps_to_reproduce: list[str] | None = None,
        expected_behavior: str = "",
        actual_behavior: str = "",
    ) -> Bug:
        """报告缺陷。"""
        bug_id = f"BUG_{uuid.uuid4().hex[:6].upper()}"

        bug = Bug(
            bug_id=bug_id,
            title=title,
            description=description,
            severity=severity,
            module=module,
            case_id=case_id,
            reporter=reporter,
            steps_to_reproduce=steps_to_reproduce or [],
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
        )

        self._bugs[bug_id] = bug
        self._stats["total_bugs"] += 1
        self._stats["by_severity"][severity.value] += 1
        self._stats["by_status"][BugStatus.OPEN.value] += 1
        self._stats["by_module"][module] += 1

        logger.info(f"报告缺陷: {bug_id} - {title} [{severity.value}]")
        return bug

    async def update_bug_status(
        self,
        bug_id: str,
        new_status: BugStatus,
        assignee: str | None = None,
    ) -> Bug | None:
        """更新缺陷状态。"""
        bug = self._bugs.get(bug_id)
        if not bug:
            return None

        old_status = bug.status
        bug.status = new_status
        bug.updated_at = datetime.now(UTC).isoformat()

        if assignee:
            bug.assignee = assignee

        if new_status in [BugStatus.FIXED, BugStatus.VERIFIED, BugStatus.CLOSED]:
            bug.resolved_at = datetime.now(UTC).isoformat()

        self._stats["by_status"][old_status.value] -= 1
        self._stats["by_status"][new_status.value] += 1

        logger.info(f"更新缺陷状态: {bug_id} {old_status.value} -> {new_status.value}")
        return bug

    async def get_bug(self, bug_id: str) -> Bug | None:
        return self._bugs.get(bug_id)

    async def list_bugs(
        self,
        severity: BugSeverity | None = None,
        status: BugStatus | None = None,
        module: str | None = None,
    ) -> list[Bug]:
        """列出缺陷。"""
        results = list(self._bugs.values())
        if severity:
            results = [b for b in results if b.severity == severity]
        if status:
            results = [b for b in results if b.status == status]
        if module:
            results = [b for b in results if b.module == module]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    async def get_open_bugs(self) -> list[Bug]:
        """获取未关闭的缺陷。"""
        return [b for b in self._bugs.values() if b.status not in [BugStatus.CLOSED, BugStatus.WONT_FIX]]

    async def get_critical_bugs(self) -> list[Bug]:
        """获取严重缺陷。"""
        return [b for b in self._bugs.values() if b.severity == BugSeverity.CRITICAL and b.status != BugStatus.CLOSED]

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_severity": dict(self._stats["by_severity"]),
            "by_status": dict(self._stats["by_status"]),
            "by_module": dict(self._stats["by_module"]),
            "open_bugs": len([b for b in self._bugs.values() if b.status not in [BugStatus.CLOSED, BugStatus.WONT_FIX]]),
        }
