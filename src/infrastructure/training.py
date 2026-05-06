"""
用户培训与试运行
===============

提供用户培训与试运行能力(D121-D125):
    - 培训材料开发
    - 培训实施
    - 试运行启动
    - 问题收集与修复
    - 试运行总结

使用方式:
    from src.infrastructure.training import TrainingManager, TrialRunManager

    training = TrainingManager()
    course = await training.create_course("系统概述", "全员", 2)

    trial = TrialRunManager()
    await trial.start_trial_run()
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class CourseType(StrEnum):
    """课程类型。"""
    OVERVIEW = "overview"
    OPERATION = "operation"
    MONITORING = "monitoring"
    DATA_MANAGEMENT = "data_management"
    OPERATIONS = "operations"


class MaterialType(StrEnum):
    """材料类型。"""
    PPT = "ppt"
    VIDEO = "video"
    MANUAL = "manual"
    QUIZ = "quiz"


class SessionStatus(StrEnum):
    """培训状态。"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class IssueType(StrEnum):
    """问题类型。"""
    BUG = "bug"
    EXPERIENCE = "experience"
    FEATURE = "feature"


class IssuePriority(StrEnum):
    """问题优先级。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(StrEnum):
    """问题状态。"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class TrainingMaterial:
    """培训材料。"""
    material_id: str
    title: str
    material_type: MaterialType
    course_type: CourseType
    content: str = ""
    duration_minutes: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "title": self.title,
            "material_type": self.material_type.value,
            "course_type": self.course_type.value,
            "content": self.content,
            "duration_minutes": self.duration_minutes,
            "created_at": self.created_at,
        }


@dataclass
class TrainingSession:
    """培训场次。"""
    session_id: str
    course_type: CourseType
    title: str
    target_audience: str
    duration_hours: float = 0.0
    status: SessionStatus = SessionStatus.SCHEDULED
    attendees: int = 0
    completed_attendees: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "course_type": self.course_type.value,
            "title": self.title,
            "target_audience": self.target_audience,
            "duration_hours": self.duration_hours,
            "status": self.status.value,
            "attendees": self.attendees,
            "completed_attendees": self.completed_attendees,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


@dataclass
class Issue:
    """问题。"""
    issue_id: str
    title: str
    issue_type: IssueType
    priority: IssuePriority = IssuePriority.MEDIUM
    status: IssueStatus = IssueStatus.OPEN
    description: str = ""
    reporter: str = ""
    assignee: str = ""
    resolution: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "issue_type": self.issue_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "description": self.description,
            "reporter": self.reporter,
            "assignee": self.assignee,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class TrialRunStats:
    """试运行统计。"""
    active_users: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    feature_usage: dict[str, int] = field(default_factory=dict)
    satisfaction_score: float = 0.0
    issues_reported: int = 0
    issues_resolved: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_users": self.active_users,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "feature_usage": self.feature_usage,
            "satisfaction_score": round(self.satisfaction_score, 2),
            "issues_reported": self.issues_reported,
            "issues_resolved": self.issues_resolved,
        }


class TrainingManager:
    """
    培训管理器(D121-D122)。

    功能:
        1. 课程管理
        2. 材料开发
        3. 培训实施
    """

    COURSES = {
        CourseType.OVERVIEW: {"title": "系统概述", "audience": "全员", "hours": 2},
        CourseType.OPERATION: {"title": "选品操作", "audience": "运营人员", "hours": 4},
        CourseType.MONITORING: {"title": "Agent监控", "audience": "技术人员", "hours": 3},
        CourseType.DATA_MANAGEMENT: {"title": "数据管理", "audience": "数据人员", "hours": 3},
        CourseType.OPERATIONS: {"title": "系统运维", "audience": "运维人员", "hours": 4},
    }

    def __init__(self):
        self._materials: dict[str, TrainingMaterial] = {}
        self._sessions: dict[str, TrainingSession] = {}
        self._stats = {
            "total_courses": 0,
            "total_sessions": 0,
            "total_attendees": 0,
        }
        logger.info("TrainingManager初始化完成")

    async def create_material(
        self,
        title: str,
        material_type: MaterialType,
        course_type: CourseType,
        content: str = "",
        duration_minutes: int = 0,
    ) -> TrainingMaterial:
        """创建培训材料。"""
        material_id = f"MATERIAL_{uuid.uuid4().hex[:6].upper()}"

        material = TrainingMaterial(
            material_id=material_id,
            title=title,
            material_type=material_type,
            course_type=course_type,
            content=content,
            duration_minutes=duration_minutes,
        )

        self._materials[material_id] = material
        logger.info(f"创建培训材料: {title}")
        return material

    async def create_course(self, course_type: CourseType) -> TrainingSession:
        """创建课程。"""
        config = self.COURSES.get(course_type, {})
        session_id = f"SESSION_{uuid.uuid4().hex[:6].upper()}"

        session = TrainingSession(
            session_id=session_id,
            course_type=course_type,
            title=config.get("title", ""),
            target_audience=config.get("audience", ""),
            duration_hours=config.get("hours", 0),
        )

        self._sessions[session_id] = session
        self._stats["total_courses"] += 1

        logger.info(f"创建课程: {session.title}")
        return session

    async def start_session(self, session_id: str, attendees: int) -> TrainingSession | None:
        """开始培训。"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        session.status = SessionStatus.IN_PROGRESS
        session.attendees = attendees
        session.started_at = datetime.now(UTC).isoformat()
        self._stats["total_sessions"] += 1
        self._stats["total_attendees"] += attendees

        logger.info(f"开始培训: {session.title} - {attendees}人")
        return session

    async def complete_session(self, session_id: str) -> TrainingSession | None:
        """完成培训。"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        session.status = SessionStatus.COMPLETED
        session.completed_attendees = session.attendees
        session.completed_at = datetime.now(UTC).isoformat()

        logger.info(f"完成培训: {session.title}")
        return session

    async def get_session(self, session_id: str) -> TrainingSession | None:
        return self._sessions.get(session_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "materials_count": len(self._materials),
        }


class TrialRunManager:
    """
    试运行管理器(D123-D125)。

    功能:
        1. 试运行启动
        2. 问题收集
        3. 统计报告
    """

    ISSUE_SLA = {
        IssueType.BUG: {"hours": 24, "priority": IssuePriority.HIGH},
        IssueType.EXPERIENCE: {"hours": 168, "priority": IssuePriority.MEDIUM},
        IssueType.FEATURE: {"hours": 336, "priority": IssuePriority.LOW},
    }

    def __init__(self):
        self._issues: dict[str, Issue] = {}
        self._stats = TrialRunStats()
        self._trial_started = False
        self._trial_start_time: str | None = None
        logger.info("TrialRunManager初始化完成")

    async def start_trial_run(self, participants: int = 20) -> dict[str, Any]:
        """启动试运行。"""
        self._trial_started = True
        self._trial_start_time = datetime.now(UTC).isoformat()
        self._stats.active_users = participants

        logger.info(f"启动试运行: {participants}人参与")
        return {
            "status": "started",
            "participants": participants,
            "started_at": self._trial_start_time,
        }

    async def report_issue(
        self,
        title: str,
        issue_type: IssueType,
        description: str = "",
        reporter: str = "",
    ) -> Issue:
        """报告问题。"""
        issue_id = f"ISSUE_{uuid.uuid4().hex[:6].upper()}"

        config = self.ISSUE_SLA.get(issue_type, {})
        priority = config.get("priority", IssuePriority.MEDIUM)

        issue = Issue(
            issue_id=issue_id,
            title=title,
            issue_type=issue_type,
            priority=priority,
            description=description,
            reporter=reporter,
        )

        self._issues[issue_id] = issue
        self._stats.issues_reported += 1

        logger.info(f"报告问题: [{issue_type.value}] {title}")
        return issue

    async def resolve_issue(self, issue_id: str, resolution: str) -> Issue | None:
        """解决问题。"""
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        issue.status = IssueStatus.RESOLVED
        issue.resolution = resolution
        issue.resolved_at = datetime.now(UTC).isoformat()
        self._stats.issues_resolved += 1

        logger.info(f"解决问题: {issue_id}")
        return issue

    async def get_issue(self, issue_id: str) -> Issue | None:
        return self._issues.get(issue_id)

    async def list_issues(
        self,
        issue_type: IssueType | None = None,
        status: IssueStatus | None = None,
    ) -> list[Issue]:
        """列出问题。"""
        results = list(self._issues.values())
        if issue_type:
            results = [i for i in results if i.issue_type == issue_type]
        if status:
            results = [i for i in results if i.status == status]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    async def update_stats(
        self,
        tasks: int = 0,
        completed: int = 0,
        feature_usage: dict[str, int] | None = None,
        satisfaction: float = 0.0,
    ) -> TrialRunStats:
        """更新统计。"""
        self._stats.total_tasks = tasks
        self._stats.completed_tasks = completed
        if feature_usage:
            self._stats.feature_usage = feature_usage
        self._stats.satisfaction_score = satisfaction

        return self._stats

    async def generate_summary(self) -> dict[str, Any]:
        """生成总结报告。"""
        issues_by_type = defaultdict(int)
        issues_by_status = defaultdict(int)
        for issue in self._issues.values():
            issues_by_type[issue.issue_type.value] += 1
            issues_by_status[issue.status.value] += 1

        return {
            "trial_started": self._trial_started,
            "trial_start_time": self._trial_start_time,
            "stats": self._stats.to_dict(),
            "issues_summary": {
                "by_type": dict(issues_by_type),
                "by_status": dict(issues_by_status),
            },
            "ready_for_production": self._stats.satisfaction_score >= 80
            and self._stats.issues_resolved >= self._stats.issues_reported * 0.9,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def get_stats(self) -> dict[str, Any]:
        return self._stats.to_dict()
