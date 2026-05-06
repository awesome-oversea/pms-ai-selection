"""D111-D115 单元测试: CI/CD自动化"""


import pytest
from src.infrastructure.cicd import (
    Deployment,
    DeploymentManager,
    DeploymentStatus,
    DeploymentStrategy,
    PipelineManager,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    QualityGate,
    QualityGateManager,
    QualityMetric,
    StageResult,
    StageStatus,
    TestManager,
)


class TestStageResult:
    """测试阶段结果"""

    def test_stage_result_creation(self):
        result = StageResult(stage=PipelineStage.LINT)
        assert result.stage == PipelineStage.LINT
        assert result.status == StageStatus.PENDING

    def test_stage_result_to_dict(self):
        result = StageResult(
            stage=PipelineStage.TEST,
            status=StageStatus.PASSED,
            duration_seconds=45.5,
        )
        d = result.to_dict()
        assert d["status"] == "passed"


class TestPipelineRun:
    """测试流水线运行"""

    def test_run_creation(self):
        run = PipelineRun(
            run_id="RUN_001",
            branch="main",
            trigger="push",
        )
        assert run.run_id == "RUN_001"
        assert run.status == PipelineStatus.PENDING

    def test_run_to_dict(self):
        run = PipelineRun(
            run_id="RUN_001",
            branch="develop",
            trigger="merge",
            status=PipelineStatus.SUCCESS,
            stages=[StageResult(stage=PipelineStage.LINT)],
        )
        d = run.to_dict()
        assert d["branch"] == "develop"
        assert len(d["stages"]) == 1


class TestDeployment:
    """测试部署"""

    def test_deployment_creation(self):
        deploy = Deployment(
            deployment_id="DEPLOY_001",
            version="v1.0.0",
            strategy=DeploymentStrategy.CANARY,
        )
        assert deploy.deployment_id == "DEPLOY_001"
        assert deploy.strategy == DeploymentStrategy.CANARY

    def test_deployment_to_dict(self):
        deploy = Deployment(
            deployment_id="DEPLOY_001",
            version="v1.2.0",
            strategy=DeploymentStrategy.ROLLING,
            status=DeploymentStatus.COMPLETED,
            traffic_percent=100,
        )
        d = deploy.to_dict()
        assert d["traffic_percent"] == 100


class TestQualityGate:
    """测试质量门禁"""

    def test_gate_creation(self):
        gate = QualityGate(
            gate_id="GATE_001",
            metric=QualityMetric.COVERAGE,
            threshold=80.0,
        )
        assert gate.gate_id == "GATE_001"
        assert gate.passed is False

    def test_gate_to_dict(self):
        gate = QualityGate(
            gate_id="GATE_001",
            metric=QualityMetric.COVERAGE,
            threshold=80.0,
            actual_value=85.5,
            passed=True,
        )
        d = gate.to_dict()
        assert d["passed"] is True


class TestPipelineManager:
    """测试流水线管理器(D111-D112)"""

    def setup_method(self):
        self.pipeline = PipelineManager()

    @pytest.mark.asyncio
    async def test_trigger_pipeline(self):
        run = await self.pipeline.trigger_pipeline(
            branch="main",
            trigger="push",
            commit_sha="abc123",
        )
        assert run.run_id.startswith("RUN_")
        assert run.branch == "main"

    @pytest.mark.asyncio
    async def test_execute_stage(self):
        run = await self.pipeline.trigger_pipeline("main", "push")
        result = await self.pipeline.execute_stage(run.run_id, PipelineStage.LINT)
        assert result.status in [StageStatus.PASSED, StageStatus.FAILED]

    @pytest.mark.asyncio
    async def test_run_pipeline(self):
        run = await self.pipeline.trigger_pipeline("main", "push")
        result = await self.pipeline.run_pipeline(run.run_id)
        assert result.status in [PipelineStatus.SUCCESS, PipelineStatus.FAILED]

    @pytest.mark.asyncio
    async def test_get_run(self):
        created = await self.pipeline.trigger_pipeline("main", "push")
        run = await self.pipeline.get_run(created.run_id)
        assert run.branch == "main"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.pipeline.trigger_pipeline("main", "push")
        stats = self.pipeline.get_stats()
        assert stats["total_runs"] == 1


class TestTestManager:
    """测试自动化测试管理器(D113)"""

    def setup_method(self):
        self.test_mgr = TestManager()

    @pytest.mark.asyncio
    async def test_run_tests(self):
        result = await self.test_mgr.run_tests("unit")
        assert "test_id" in result
        assert result["total"] > 0

    @pytest.mark.asyncio
    async def test_run_all_tests(self):
        result = await self.test_mgr.run_all_tests()
        assert "results" in result
        assert "total_coverage" in result

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.test_mgr.run_all_tests()
        stats = self.test_mgr.get_stats()
        assert stats["total_tests"] > 0


class TestDeploymentManager:
    """测试部署管理器(D114)"""

    def setup_method(self):
        self.deploy = DeploymentManager()

    @pytest.mark.asyncio
    async def test_create_deployment(self):
        deployment = await self.deploy.create_deployment(
            version="v1.0.0",
            strategy=DeploymentStrategy.ROLLING,
        )
        assert deployment.deployment_id.startswith("DEPLOY_")

    @pytest.mark.asyncio
    async def test_canary_deploy(self):
        result = await self.deploy.canary_deploy("v1.2.0", 50)
        assert result.strategy == DeploymentStrategy.CANARY
        assert result.status in [DeploymentStatus.COMPLETED, DeploymentStatus.ROLLED_BACK]

    @pytest.mark.asyncio
    async def test_rolling_deploy(self):
        result = await self.deploy.rolling_deploy("v1.3.0")
        assert result.strategy == DeploymentStrategy.ROLLING
        assert result.status in [DeploymentStatus.COMPLETED, DeploymentStatus.FAILED]

    @pytest.mark.asyncio
    async def test_get_deployment(self):
        created = await self.deploy.create_deployment("v1.0.0", DeploymentStrategy.ROLLING)
        deployment = await self.deploy.get_deployment(created.deployment_id)
        assert deployment.version == "v1.0.0"

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.deploy.rolling_deploy("v1.0.0")
        stats = self.deploy.get_stats()
        assert stats["total_deployments"] == 1


class TestQualityGateManager:
    """测试质量门禁管理器(D115)"""

    def setup_method(self):
        self.quality = QualityGateManager()

    @pytest.mark.asyncio
    async def test_check_quality(self):
        gate = await self.quality.check_quality(
            metric=QualityMetric.COVERAGE,
            threshold=80.0,
        )
        assert gate.gate_id.startswith("GATE_")
        assert gate.passed in [True, False]

    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        result = await self.quality.run_all_checks()
        assert "gates" in result
        assert len(result["gates"]) == 5

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.quality.run_all_checks()
        stats = self.quality.get_stats()
        assert stats["total_checks"] == 5


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_cicd_workflow(self):
        pipeline = PipelineManager()
        test_mgr = TestManager()
        deploy = DeploymentManager()
        quality = QualityGateManager()

        await pipeline.trigger_pipeline("main", "push")

        test_result = await test_mgr.run_all_tests()

        quality_result = await quality.run_all_checks()

        if quality_result["all_passed"]:
            await deploy.canary_deploy("v1.0.0", 100)

        assert test_result["total_coverage"] > 0
        assert len(quality_result["gates"]) == 5


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
