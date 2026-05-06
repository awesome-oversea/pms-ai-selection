"""D91-D95 单元测试: M3里程碑验收"""

import random

import pytest
from src.infrastructure.milestone import (
    DemoManager,
    DemoScenario,
    MilestoneReview,
    Phase,
    Phase4Plan,
    ReviewDecision,
    ReviewItem,
    ReviewManager,
    ScenarioStatus,
)


class TestDemoScenario:
    """测试演示场景"""

    def test_scenario_creation(self):
        scenario = DemoScenario(
            scenario_id="DEMO_001",
            name="端到端选品流程",
            description="完整选品演示",
        )
        assert scenario.scenario_id == "DEMO_001"
        assert scenario.status == ScenarioStatus.PENDING

    def test_scenario_to_dict(self):
        scenario = DemoScenario(
            scenario_id="DEMO_001",
            name="端到端选品流程",
            description="完整选品演示",
            steps=["步骤1", "步骤2"],
            status=ScenarioStatus.PASSED,
        )
        d = scenario.to_dict()
        assert d["name"] == "端到端选品流程"
        assert d["status"] == "passed"


class TestReviewItem:
    """测试评审项"""

    def test_item_creation(self):
        item = ReviewItem(
            item_id="REV_001",
            category="功能",
            title="混合检索增强",
            description="向量+关键词融合检索",
            target="MRR@10>0.7",
        )
        assert item.item_id == "REV_001"
        assert item.passed is None

    def test_item_to_dict(self):
        item = ReviewItem(
            item_id="REV_001",
            category="功能",
            title="混合检索增强",
            description="描述",
            target="MRR@10>0.7",
            actual="MRR@10=0.75",
            passed=True,
        )
        d = item.to_dict()
        assert d["passed"] is True


class TestMilestoneReview:
    """测试里程碑评审"""

    def test_review_creation(self):
        review = MilestoneReview(
            review_id="REVIEW_001",
            milestone="M3",
            phase=Phase.PHASE_3,
            total_items=8,
            passed_items=8,
            failed_items=0,
            pending_items=0,
        )
        review.calculate_decision()
        assert review.decision == ReviewDecision.PASS

    def test_review_conditional_pass(self):
        review = MilestoneReview(
            review_id="REVIEW_001",
            milestone="M3",
            phase=Phase.PHASE_3,
            total_items=8,
            passed_items=7,
            failed_items=1,
            pending_items=0,
        )
        review.calculate_decision()
        assert review.decision == ReviewDecision.CONDITIONAL_PASS

    def test_review_fail(self):
        review = MilestoneReview(
            review_id="REVIEW_001",
            milestone="M3",
            phase=Phase.PHASE_3,
            total_items=8,
            passed_items=5,
            failed_items=3,
            pending_items=0,
        )
        review.calculate_decision()
        assert review.decision == ReviewDecision.FAIL

    def test_review_to_dict(self):
        review = MilestoneReview(
            review_id="REVIEW_001",
            milestone="M3",
            phase=Phase.PHASE_3,
            total_items=8,
            passed_items=8,
        )
        review.calculate_decision()
        d = review.to_dict()
        assert d["milestone"] == "M3"


class TestPhase4Plan:
    """测试Phase 4计划"""

    def test_plan_creation(self):
        plan = Phase4Plan(
            plan_id="PLAN_001",
            objectives=["生产就绪优化", "高可用架构升级"],
            deliverables=["运维手册", "监控配置"],
        )
        assert plan.plan_id == "PLAN_001"
        assert len(plan.objectives) == 2

    def test_plan_to_dict(self):
        plan = Phase4Plan(
            plan_id="PLAN_001",
            objectives=["目标1"],
            deliverables=["交付物1"],
            timeline={"D96-D100": "UAT验收"},
        )
        d = plan.to_dict()
        assert "objectives" in d
        assert "timeline" in d


class TestDemoManager:
    """测试演示管理器(D91-D93)"""

    def setup_method(self):
        self.demo = DemoManager()

    @pytest.mark.asyncio
    async def test_create_scenario(self):
        scenario = await self.demo.create_scenario(
            name="端到端选品流程",
            description="完整选品演示",
            steps=["步骤1", "步骤2"],
            expected_output="选品报告",
        )
        assert scenario.scenario_id.startswith("DEMO_")
        assert scenario.name == "端到端选品流程"

    @pytest.mark.asyncio
    async def test_init_default_scenarios(self):
        scenarios = await self.demo.init_default_scenarios()
        assert len(scenarios) == 4

    @pytest.mark.asyncio
    async def test_execute_scenario(self):
        scenario = await self.demo.create_scenario(
            name="测试场景",
            description="描述",
        )
        result = await self.demo.execute_scenario(scenario.scenario_id)
        assert result.status in [ScenarioStatus.PASSED, ScenarioStatus.FAILED]
        assert result.executed_at is not None

    @pytest.mark.asyncio
    async def test_execute_all(self):
        await self.demo.init_default_scenarios()
        results = await self.demo.execute_all()
        assert results["total"] == 4

    @pytest.mark.asyncio
    async def test_get_scenario(self):
        created = await self.demo.create_scenario(name="场景", description="描述")
        scenario = await self.demo.get_scenario(created.scenario_id)
        assert scenario.name == "场景"

    @pytest.mark.asyncio
    async def test_list_scenarios(self):
        await self.demo.create_scenario(name="场景1", description="")
        await self.demo.create_scenario(name="场景2", description="")
        scenarios = await self.demo.list_scenarios()
        assert len(scenarios) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.demo.create_scenario(name="场景", description="")
        stats = self.demo.get_stats()
        assert stats["total_scenarios"] == 1


class TestReviewManager:
    """测试评审管理器(D94-D95)"""

    def setup_method(self):
        self.review = ReviewManager()

    @pytest.mark.asyncio
    async def test_create_review_item(self):
        item = await self.review.create_review_item(
            category="功能",
            title="混合检索增强",
            description="向量+关键词融合检索",
            target="MRR@10>0.7",
        )
        assert item.item_id.startswith("REV_ITEM_")
        assert item.category == "功能"

    @pytest.mark.asyncio
    async def test_init_phase3_items(self):
        items = await self.review.init_phase3_items()
        assert len(items) == 8

    @pytest.mark.asyncio
    async def test_evaluate_item(self):
        item = await self.review.create_review_item(
            category="功能",
            title="测试项",
            description="描述",
        )
        result = await self.review.evaluate_item(
            item.item_id,
            actual="MRR@10=0.75",
            passed=True,
            comments="达标",
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_create_review(self):
        await self.review.init_phase3_items()
        items = list(self.review._items.values())
        for item in items[:6]:
            await self.review.evaluate_item(item.item_id, "达标", True)
        for item in items[6:]:
            await self.review.evaluate_item(item.item_id, "达标", True)

        review = await self.review.create_review(milestone="M3")
        assert review.decision in [ReviewDecision.PASS, ReviewDecision.CONDITIONAL_PASS]

    @pytest.mark.asyncio
    async def test_create_phase4_plan(self):
        plan = await self.review.create_phase4_plan()
        assert plan.plan_id.startswith("PLAN_P4_")
        assert len(plan.objectives) == 4

    @pytest.mark.asyncio
    async def test_get_review(self):
        await self.review.init_phase3_items()
        created = await self.review.create_review(milestone="M3")
        review = await self.review.get_review(created.review_id)
        assert review.milestone == "M3"

    @pytest.mark.asyncio
    async def test_get_phase4_plan(self):
        created = await self.review.create_phase4_plan()
        plan = await self.review.get_phase4_plan(created.plan_id)
        assert plan is not None

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.review.create_review_item(category="功能", title="测试", description="")
        stats = self.review.get_stats()
        assert stats["items_count"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_milestone_workflow(self):
        demo = DemoManager()
        review = ReviewManager()

        await demo.init_default_scenarios()
        await demo.execute_all()

        items = await review.init_phase3_items()
        for item in items:
            passed = random.random() > 0.1
            await review.evaluate_item(
                item.item_id,
                actual="达标" if passed else "未达标",
                passed=passed,
            )

        review_result = await review.create_review(milestone="M3")
        assert review_result.decision in [ReviewDecision.PASS, ReviewDecision.CONDITIONAL_PASS]

        plan = await review.create_phase4_plan()
        assert len(plan.objectives) > 0


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
