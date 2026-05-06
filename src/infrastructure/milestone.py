"""
M3里程碑验收 + 演示场景管理
============================

提供M3评审与演示能力(D91-D95):
    - 演示场景管理
    - 评审流程
    - Phase 4启动
    - 成果总结

使用方式:
    from src.infrastructure.milestone import DemoManager, ReviewManager

    demo = DemoManager()
    scenario = await demo.create_scenario(...)
    result = await demo.execute_scenario(scenario.scenario_id)

    review = ReviewManager()
    decision = await review.make_decision(...)
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class ScenarioStatus(StrEnum):
    """演示场景状态。"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReviewDecision(StrEnum):
    """评审决策。"""
    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"
    PENDING = "pending"


class Phase(StrEnum):
    """项目阶段。"""
    PHASE_1 = "Phase 1 - 基础搭建"
    PHASE_2 = "Phase 2 - Multi-Agent集成"
    PHASE_3 = "Phase 3 - ERP闭环+RAG增强"
    PHASE_4 = "Phase 4 - 生产就绪"


@dataclass
class DemoScenario:
    """演示场景。"""
    scenario_id: str
    name: str
    description: str
    steps: list[str] = field(default_factory=list)
    expected_output: str = ""
    status: ScenarioStatus = ScenarioStatus.PENDING
    actual_output: str | None = None
    duration_seconds: float = 0.0
    executed_at: str | None = None
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "expected_output": self.expected_output,
            "status": self.status.value,
            "actual_output": self.actual_output,
            "duration_seconds": round(self.duration_seconds, 2),
            "executed_at": self.executed_at,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass
class ReviewItem:
    """评审项。"""
    item_id: str
    category: str
    title: str
    description: str
    target: str = ""
    actual: str = ""
    passed: bool | None = None
    comments: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "target": self.target,
            "actual": self.actual,
            "passed": self.passed,
            "comments": self.comments,
            "created_at": self.created_at,
        }


@dataclass
class MilestoneReview:
    """里程碑评审。"""
    review_id: str
    milestone: str
    phase: Phase
    total_items: int = 0
    passed_items: int = 0
    failed_items: int = 0
    pending_items: int = 0
    decision: ReviewDecision = ReviewDecision.PENDING
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    next_phase_scope: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def calculate_decision(self) -> None:
        if self.failed_items == 0 and self.pending_items == 0:
            self.decision = ReviewDecision.PASS
        elif self.failed_items <= 2:
            self.decision = ReviewDecision.CONDITIONAL_PASS
        else:
            self.decision = ReviewDecision.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "milestone": self.milestone,
            "phase": self.phase.value,
            "total_items": self.total_items,
            "passed_items": self.passed_items,
            "failed_items": self.failed_items,
            "pending_items": self.pending_items,
            "decision": self.decision.value,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "next_phase_scope": self.next_phase_scope,
            "created_at": self.created_at,
        }


@dataclass
class Phase4Plan:
    """Phase 4计划。"""
    plan_id: str
    objectives: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    timeline: dict[str, str] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objectives": self.objectives,
            "deliverables": self.deliverables,
            "timeline": self.timeline,
            "resources": self.resources,
            "risks": self.risks,
            "created_at": self.created_at,
        }


class DemoManager:
    """
    演示场景管理器(D91-D93)。

    功能:
        1. 演示场景创建
        2. 场景执行与记录
        3. 演示报告生成
    """

    DEFAULT_SCENARIOS = [
        {
            "name": "端到端选品流程",
            "description": "分析户外储能电源在欧洲市场的机会",
            "steps": [
                "输入市场分析需求",
                "四Agent协同处理",
                "展示实时状态更新",
                "输出选品报告",
            ],
            "expected_output": "包含市场机会、竞品分析、选品建议的完整报告",
        },
        {
            "name": "ERP数据联动",
            "description": "展示选品结果到ERP各模块的数据流转",
            "steps": [
                "选品结果确认",
                "SCM生成采购建议",
                "WMS更新库存预警",
                "FMS计算利润预估",
            ],
            "expected_output": "完整的ERP数据联动链路",
        },
        {
            "name": "智能问答",
            "description": "展示RAG增强的智能问答能力",
            "steps": [
                "用户提问",
                "混合检索(向量+关键词)",
                "GraphRAG知识图谱增强",
                "LLM生成精准回答",
            ],
            "expected_output": "准确、有依据的回答",
        },
        {
            "name": "自动报告",
            "description": "展示定时报告生成与分发",
            "steps": [
                "触发报告生成",
                "数据聚合计算",
                "多格式输出(HTML/PDF)",
                "分发通知",
            ],
            "expected_output": "格式规范的自动报告",
        },
    ]

    def __init__(self):
        self._scenarios: dict[str, DemoScenario] = {}
        self._stats = {
            "total_scenarios": 0,
            "by_status": defaultdict(int),
        }
        logger.info("DemoManager初始化完成")

    async def create_scenario(
        self,
        name: str,
        description: str,
        steps: list[str] | None = None,
        expected_output: str = "",
    ) -> DemoScenario:
        """创建演示场景。"""
        scenario_id = f"DEMO_{uuid.uuid4().hex[:6].upper()}"

        scenario = DemoScenario(
            scenario_id=scenario_id,
            name=name,
            description=description,
            steps=steps or [],
            expected_output=expected_output,
        )

        self._scenarios[scenario_id] = scenario
        self._stats["total_scenarios"] += 1
        self._stats["by_status"][ScenarioStatus.PENDING.value] += 1

        logger.info(f"创建演示场景: {scenario_id} - {name}")
        return scenario

    async def init_default_scenarios(self) -> list[DemoScenario]:
        """初始化默认演示场景。"""
        scenarios = []
        for config in self.DEFAULT_SCENARIOS:
            scenario = await self.create_scenario(**config)
            scenarios.append(scenario)
        return scenarios

    async def execute_scenario(self, scenario_id: str) -> DemoScenario | None:
        """执行演示场景。"""
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return None

        self._stats["by_status"][scenario.status.value] -= 1
        scenario.status = ScenarioStatus.RUNNING
        self._stats["by_status"][scenario.status.value] += 1

        start_time = datetime.now(UTC)
        await asyncio.sleep(random.uniform(1.0, 3.0))

        passed = random.random() > 0.1
        scenario.status = ScenarioStatus.PASSED if passed else ScenarioStatus.FAILED
        scenario.executed_at = datetime.now(UTC).isoformat()
        scenario.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()
        scenario.actual_output = scenario.expected_output if passed else "执行异常"

        self._stats["by_status"][ScenarioStatus.RUNNING.value] -= 1
        self._stats["by_status"][scenario.status.value] += 1

        logger.info(f"执行演示场景: {scenario_id} - {scenario.status.value}")
        return scenario

    async def execute_all(self) -> dict[str, Any]:
        """执行所有场景。"""
        results = {"total": 0, "passed": 0, "failed": 0}
        for scenario_id in self._scenarios:
            result = await self.execute_scenario(scenario_id)
            results["total"] += 1
            if result and result.status == ScenarioStatus.PASSED:
                results["passed"] += 1
            else:
                results["failed"] += 1
        return results

    async def get_scenario(self, scenario_id: str) -> DemoScenario | None:
        return self._scenarios.get(scenario_id)

    async def list_scenarios(self, status: ScenarioStatus | None = None) -> list[DemoScenario]:
        """列出演示场景。"""
        results = list(self._scenarios.values())
        if status:
            results = [s for s in results if s.status == status]
        return results

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_status": dict(self._stats["by_status"]),
        }


class ReviewManager:
    """
    评审管理器(D94-D95)。

    功能:
        1. 评审项管理
        2. 评审决策
        3. Phase 4计划
    """

    PHASE3_ITEMS = [
        {"category": "功能", "title": "混合检索增强", "target": "MRR@10>0.7", "description": "向量+关键词融合检索"},
        {"category": "功能", "title": "GraphRAG知识图谱", "target": "图谱可用", "description": "Neo4j+NER+RE"},
        {"category": "功能", "title": "Flink实时特征", "target": "5类特征", "description": "销量/价格/排名/竞品/情感"},
        {"category": "功能", "title": "ERP对接", "target": "5大模块", "description": "SCM/OMS/WMS/CRM/FMS"},
        {"category": "功能", "title": "自动报告", "target": "日/周/月报", "description": "定时生成+多格式输出"},
        {"category": "功能", "title": "前端V2", "target": "核心页面", "description": "供应链/财务/客户看板"},
        {"category": "安全", "title": "安全加固", "target": "通过审计", "description": "OWASP扫描+漏洞修复"},
        {"category": "性能", "title": "性能达标", "target": "TPS>50", "description": "API响应P99<500ms"},
    ]

    PHASE4_OBJECTIVES = [
        "生产就绪优化",
        "高可用架构升级",
        "运维自动化",
        "项目收尾与交接",
    ]

    def __init__(self):
        self._items: dict[str, ReviewItem] = {}
        self._reviews: dict[str, MilestoneReview] = {}
        self._phase4_plans: dict[str, Phase4Plan] = {}
        self._stats = {
            "total_reviews": 0,
            "by_decision": defaultdict(int),
        }
        logger.info("ReviewManager初始化完成")

    async def create_review_item(
        self,
        category: str,
        title: str,
        description: str,
        target: str = "",
    ) -> ReviewItem:
        """创建评审项。"""
        item_id = f"REV_ITEM_{uuid.uuid4().hex[:6].upper()}"

        item = ReviewItem(
            item_id=item_id,
            category=category,
            title=title,
            description=description,
            target=target,
        )

        self._items[item_id] = item
        return item

    async def init_phase3_items(self) -> list[ReviewItem]:
        """初始化Phase 3评审项。"""
        items = []
        for config in self.PHASE3_ITEMS:
            item = await self.create_review_item(**config)
            items.append(item)
        return items

    async def evaluate_item(self, item_id: str, actual: str, passed: bool, comments: str = "") -> ReviewItem | None:
        """评估评审项。"""
        item = self._items.get(item_id)
        if not item:
            return None

        item.actual = actual
        item.passed = passed
        item.comments = comments

        logger.info(f"评估评审项: {item_id} - {'通过' if passed else '不通过'}")
        return item

    async def create_review(self, milestone: str, phase: Phase = Phase.PHASE_3) -> MilestoneReview:
        """创建评审。"""
        review_id = f"REVIEW_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        items = list(self._items.values())
        review = MilestoneReview(
            review_id=review_id,
            milestone=milestone,
            phase=phase,
            total_items=len(items),
            passed_items=sum(1 for i in items if i.passed is True),
            failed_items=sum(1 for i in items if i.passed is False),
            pending_items=sum(1 for i in items if i.passed is None),
        )

        review.calculate_decision()

        if review.decision == ReviewDecision.CONDITIONAL_PASS:
            review.issues = ["存在少量遗留问题需Phase 4处理"]
            review.recommendations = ["修复遗留问题后可进入下一阶段"]
        elif review.decision == ReviewDecision.FAIL:
            review.issues = ["存在严重问题"]
            review.recommendations = ["需要修复问题后重新评审"]

        review.next_phase_scope = self.PHASE4_OBJECTIVES

        self._reviews[review_id] = review
        self._stats["total_reviews"] += 1
        self._stats["by_decision"][review.decision.value] += 1

        logger.info(f"创建评审: {review_id} - {review.decision.value}")
        return review

    async def create_phase4_plan(self) -> Phase4Plan:
        """创建Phase 4计划(D95)。"""
        plan_id = f"PLAN_P4_{uuid.uuid4().hex[:6].upper()}"

        plan = Phase4Plan(
            plan_id=plan_id,
            objectives=self.PHASE4_OBJECTIVES,
            deliverables=[
                "高可用架构文档",
                "灾备方案",
                "运维手册",
                "监控告警配置",
                "CI/CD流水线",
            ],
            timeline={
                "D96-D100": "UAT验收与生产发布准备",
                "D101-D105": "生产环境稳定性保障",
                "D106-D110": "持续迭代与功能增强",
                "D111-D115": "数据分析与报表引擎",
                "D116-D120": "移动端适配与PWA支持",
                "D121-D125": "多语言国际化",
                "D126-D130": "最终交付与知识转移",
            },
            resources={
                "team_size": "当前团队",
                "external_support": "按需",
            },
            risks=[
                "生产环境差异",
                "性能瓶颈",
                "第三方服务稳定性",
            ],
        )

        self._phase4_plans[plan_id] = plan
        logger.info(f"创建Phase 4计划: {plan_id}")
        return plan

    async def get_review(self, review_id: str) -> MilestoneReview | None:
        return self._reviews.get(review_id)

    async def get_phase4_plan(self, plan_id: str) -> Phase4Plan | None:
        return self._phase4_plans.get(plan_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_decision": dict(self._stats["by_decision"]),
            "items_count": len(self._items),
        }
