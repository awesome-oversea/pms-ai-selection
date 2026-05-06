"""D101-D105 单元测试: 性能调优与容量规划"""


import pytest
from src.infrastructure.performance_tuning import (
    BaselineManager,
    Bottleneck,
    CapacityPlanner,
    CapacityResource,
    Layer,
    MetricType,
    OptimizationExecutor,
    PerformanceAnalyzer,
    PerformanceBaseline,
    PerformanceMetric,
    Severity,
    StressTester,
    StressTestResult,
)


class TestPerformanceMetric:
    """测试性能指标"""

    def test_metric_creation(self):
        metric = PerformanceMetric(
            metric_id="METRIC_001",
            layer=Layer.API,
            metric_type=MetricType.LATENCY,
            value=150.5,
            unit="ms",
        )
        assert metric.metric_id == "METRIC_001"
        assert metric.is_bottleneck is False

    def test_metric_to_dict(self):
        metric = PerformanceMetric(
            metric_id="METRIC_001",
            layer=Layer.DATABASE,
            metric_type=MetricType.LATENCY,
            value=200.0,
            unit="ms",
            threshold=100.0,
            is_bottleneck=True,
        )
        d = metric.to_dict()
        assert d["is_bottleneck"] is True


class TestBottleneck:
    """测试性能瓶颈"""

    def test_bottleneck_creation(self):
        bn = Bottleneck(
            bottleneck_id="BN_001",
            layer=Layer.DATABASE,
            description="数据库查询过慢",
            severity=Severity.HIGH,
            current_value=200.0,
            target_value=100.0,
        )
        assert bn.bottleneck_id == "BN_001"
        assert bn.severity == Severity.HIGH

    def test_bottleneck_to_dict(self):
        bn = Bottleneck(
            bottleneck_id="BN_001",
            layer=Layer.API,
            description="API延迟过高",
            severity=Severity.CRITICAL,
            current_value=500.0,
            target_value=100.0,
            recommendations=["优化查询", "增加缓存"],
        )
        d = bn.to_dict()
        assert len(d["recommendations"]) == 2


class TestCapacityResource:
    """测试容量资源"""

    def test_resource_creation(self):
        res = CapacityResource(
            resource_id="RES_001",
            name="K8s Node",
            current_config="10台",
            current_usage=0.6,
            estimated_peak=0.9,
            recommended_config="15台",
        )
        assert res.resource_id == "RES_001"
        assert res.estimated_peak == 0.9

    def test_resource_to_dict(self):
        res = CapacityResource(
            resource_id="RES_001",
            name="GPU卡",
            current_config="16张",
            current_usage=0.7,
            estimated_peak=0.95,
            recommended_config="24张",
        )
        d = res.to_dict()
        assert d["name"] == "GPU卡"


class TestStressTestResult:
    """测试压测结果"""

    def test_result_creation(self):
        result = StressTestResult(
            result_id="STRESS_001",
            scenario="正常负载",
            duration_minutes=480,
            total_requests=100000,
            successful_requests=99900,
            failed_requests=100,
            avg_latency_ms=120.5,
            p99_latency_ms=180.2,
            error_rate=0.001,
            throughput_rps=347.2,
            passed=True,
        )
        assert result.result_id == "STRESS_001"
        assert result.passed is True

    def test_result_to_dict(self):
        result = StressTestResult(
            result_id="STRESS_001",
            scenario="峰值负载",
            duration_minutes=120,
            total_requests=50000,
            successful_requests=49500,
            failed_requests=500,
            avg_latency_ms=150.0,
            p99_latency_ms=250.0,
            error_rate=0.01,
            throughput_rps=416.67,
        )
        d = result.to_dict()
        assert "error_rate" in d


class TestPerformanceBaseline:
    """测试性能基线"""

    def test_baseline_creation(self):
        baseline = PerformanceBaseline(
            baseline_id="BASE_001",
            name="生产环境基线",
            metrics={"api_latency": 150.0, "error_rate": 0.001},
        )
        assert baseline.baseline_id == "BASE_001"
        assert len(baseline.metrics) == 2

    def test_baseline_to_dict(self):
        baseline = PerformanceBaseline(
            baseline_id="BASE_001",
            name="基线",
            metrics={"latency": 100.0},
        )
        d = baseline.to_dict()
        assert d["name"] == "基线"


class TestPerformanceAnalyzer:
    """测试性能分析器(D101)"""

    def setup_method(self):
        self.analyzer = PerformanceAnalyzer()

    @pytest.mark.asyncio
    async def test_collect_metric(self):
        metric = await self.analyzer.collect_metric(
            layer=Layer.API,
            metric_type=MetricType.LATENCY,
            value=150.0,
            unit="ms",
        )
        assert metric.metric_id.startswith("METRIC_")

    @pytest.mark.asyncio
    async def test_collect_all_metrics(self):
        results = await self.analyzer.collect_all_metrics()
        assert len(results) == 6

    @pytest.mark.asyncio
    async def test_identify_bottlenecks(self):
        await self.analyzer.collect_metric(Layer.DATABASE, MetricType.LATENCY, 500.0, "ms")
        bottlenecks = await self.analyzer.identify_bottlenecks()
        assert len(bottlenecks) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.analyzer.collect_metric(Layer.API, MetricType.LATENCY, 100.0, "ms")
        stats = self.analyzer.get_stats()
        assert stats["total_metrics"] == 1


class TestOptimizationExecutor:
    """测试优化执行器(D102)"""

    def setup_method(self):
        self.executor = OptimizationExecutor()

    @pytest.mark.asyncio
    async def test_execute_optimization(self):
        result = await self.executor.execute_optimization(
            optimization_type="sql_index",
            target="products",
            config={"column": "category_id"},
        )
        assert result["opt_id"].startswith("OPT_")
        assert "success" in result

    @pytest.mark.asyncio
    async def test_batch_optimize(self):
        results = await self.executor.batch_optimize()
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.executor.execute_optimization("sql_index", "test", {})
        stats = self.executor.get_stats()
        assert stats["total_optimizations"] == 1


class TestCapacityPlanner:
    """测试容量规划器(D103)"""

    def setup_method(self):
        self.planner = CapacityPlanner()

    @pytest.mark.asyncio
    async def test_add_resource(self):
        resource = await self.planner.add_resource(
            name="K8s Node",
            current_config="10台",
            current_usage=0.6,
            estimated_peak=0.9,
            recommended_config="15台",
        )
        assert resource.resource_id.startswith("RES_")

    @pytest.mark.asyncio
    async def test_init_default_resources(self):
        resources = await self.planner.init_default_resources()
        assert len(resources) == 5

    @pytest.mark.asyncio
    async def test_generate_plan(self):
        await self.planner.init_default_resources()
        plan = await self.planner.generate_plan()
        assert "total_resources" in plan
        assert "need_expansion" in plan

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.planner.add_resource("测试资源", "10", 0.5, 0.7, "15")
        stats = self.planner.get_stats()
        assert stats["total_resources"] == 1


class TestStressTester:
    """测试压测器(D104)"""

    def setup_method(self):
        self.tester = StressTester()

    @pytest.mark.asyncio
    async def test_run_test(self):
        result = await self.tester.run_test(
            scenario="正常负载",
            duration_minutes=60,
            multiplier=1,
        )
        assert result.result_id.startswith("STRESS_")
        assert result.total_requests > 0

    @pytest.mark.asyncio
    async def test_run_all_scenarios(self):
        results = await self.tester.run_all_scenarios()
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.tester.run_test("测试场景", 10, 1)
        stats = self.tester.get_stats()
        assert stats["total_tests"] == 1


class TestBaselineManager:
    """测试基线管理器(D105)"""

    def setup_method(self):
        self.manager = BaselineManager()

    @pytest.mark.asyncio
    async def test_create_baseline(self):
        baseline = await self.manager.create_baseline(
            name="生产环境基线",
            metrics={"api_latency": 150.0},
        )
        assert baseline.baseline_id.startswith("BASE_")

    @pytest.mark.asyncio
    async def test_compare_with_baseline(self):
        baseline = await self.manager.create_baseline("测试基线")
        comparison = await self.manager.compare_with_baseline(
            baseline.baseline_id,
            {"api_p99_latency_ms": 100.0},
        )
        assert "comparison" in comparison
        assert "all_passed" in comparison

    @pytest.mark.asyncio
    async def test_generate_report(self):
        baseline = await self.manager.create_baseline("报告基线")
        report = await self.manager.generate_report(baseline.baseline_id)
        assert "report_id" in report
        assert "sections" in report

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.manager.create_baseline("基线")
        stats = self.manager.get_stats()
        assert stats["total_baselines"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_performance_workflow(self):
        analyzer = PerformanceAnalyzer()
        executor = OptimizationExecutor()
        planner = CapacityPlanner()
        tester = StressTester()
        baseline_mgr = BaselineManager()

        await analyzer.collect_all_metrics()
        bottlenecks = await analyzer.identify_bottlenecks()

        if bottlenecks:
            await executor.batch_optimize()

        await planner.init_default_resources()
        await planner.generate_plan()

        results = await tester.run_all_scenarios()

        baseline = await baseline_mgr.create_baseline("最终基线")
        report = await baseline_mgr.generate_report(baseline.baseline_id)

        assert len(results) == 4
        assert "report_id" in report


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
