"""
性能调优与容量规划
==================

当前状态: 本地可运行实现。
- 已支持仓内性能指标、瓶颈分析、容量规划、压测结果与基线管理的本地模拟与回归验证。
- 仍未接入真实 APM、生产监控与外部压测平台，因此属于“本地真实链路”，
  不等同于生产级性能治理集成。

提供性能调优与容量规划能力(D101-D105):
    - 全链路性能分析
    - 核心优化实施
    - 容量规划
    - 生产级压测
    - 性能基线

使用方式:
    from src.infrastructure.performance_tuning import PerformanceAnalyzer, CapacityPlanner

    analyzer = PerformanceAnalyzer()
    metrics = await analyzer.collect_metrics()
    bottlenecks = await analyzer.identify_bottlenecks()

    planner = CapacityPlanner()
    plan = await planner.generate_plan()
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


class Layer(StrEnum):
    """系统层。"""
    GATEWAY = "gateway"
    API = "api"
    AGENT = "agent"
    DATABASE = "database"
    CACHE = "cache"
    VECTOR = "vector"


class MetricType(StrEnum):
    """指标类型。"""
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"


class Severity(StrEnum):
    """严重程度。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class PerformanceMetric:
    """性能指标。"""
    metric_id: str
    layer: Layer
    metric_type: MetricType
    value: float
    unit: str = ""
    threshold: float = 0.0
    is_bottleneck: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "layer": self.layer.value,
            "metric_type": self.metric_type.value,
            "value": round(self.value, 4),
            "unit": self.unit,
            "threshold": self.threshold,
            "is_bottleneck": self.is_bottleneck,
            "timestamp": self.timestamp,
        }


@dataclass
class Bottleneck:
    """性能瓶颈。"""
    bottleneck_id: str
    layer: Layer
    description: str
    severity: Severity
    current_value: float
    target_value: float
    recommendations: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "bottleneck_id": self.bottleneck_id,
            "layer": self.layer.value,
            "description": self.description,
            "severity": self.severity.value,
            "current_value": round(self.current_value, 4),
            "target_value": round(self.target_value, 4),
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }


@dataclass
class CapacityResource:
    """容量资源。"""
    resource_id: str
    name: str
    current_config: str
    current_usage: float
    estimated_peak: float
    recommended_config: str
    cost_impact: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "current_config": self.current_config,
            "current_usage": round(self.current_usage, 4),
            "estimated_peak": round(self.estimated_peak, 4),
            "recommended_config": self.recommended_config,
            "cost_impact": self.cost_impact,
            "created_at": self.created_at,
        }


@dataclass
class StressTestResult:
    """压测结果。"""
    result_id: str
    scenario: str
    duration_minutes: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    throughput_rps: float
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "scenario": self.scenario,
            "duration_minutes": round(self.duration_minutes, 2),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "throughput_rps": round(self.throughput_rps, 2),
            "passed": self.passed,
            "created_at": self.created_at,
        }


@dataclass
class PerformanceBaseline:
    """性能基线。"""
    baseline_id: str
    name: str
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "name": self.name,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "created_at": self.created_at,
        }


class PerformanceAnalyzer:
    """
    全链路性能分析器(D101)。

    功能:
        1. 各层性能数据采集
        2. 瓶颈点识别
        3. 优化建议生成
    """

    LAYER_THRESHOLDS = {
        (Layer.GATEWAY, MetricType.LATENCY): 50,
        (Layer.API, MetricType.LATENCY): 100,
        (Layer.AGENT, MetricType.LATENCY): 2000,
        (Layer.DATABASE, MetricType.LATENCY): 100,
        (Layer.CACHE, MetricType.LATENCY): 10,
        (Layer.VECTOR, MetricType.LATENCY): 500,
        (Layer.GATEWAY, MetricType.ERROR_RATE): 0.01,
        (Layer.API, MetricType.ERROR_RATE): 0.001,
        (Layer.CACHE, MetricType.THROUGHPUT): 10000,
    }

    def __init__(self):
        self._metrics: dict[str, PerformanceMetric] = {}
        self._bottlenecks: dict[str, Bottleneck] = {}
        self._stats = {
            "total_metrics": 0,
            "bottleneck_count": 0,
        }
        logger.info("PerformanceAnalyzer初始化完成")

    async def collect_metric(
        self,
        layer: Layer,
        metric_type: MetricType,
        value: float,
        unit: str = "",
    ) -> PerformanceMetric:
        """采集性能指标。"""
        metric_id = f"METRIC_{uuid.uuid4().hex[:6].upper()}"
        threshold = self.LAYER_THRESHOLDS.get((layer, metric_type), 0)
        is_bottleneck = threshold > 0 and value > threshold

        metric = PerformanceMetric(
            metric_id=metric_id,
            layer=layer,
            metric_type=metric_type,
            value=value,
            unit=unit,
            threshold=threshold,
            is_bottleneck=is_bottleneck,
        )

        self._metrics[metric_id] = metric
        self._stats["total_metrics"] += 1

        if is_bottleneck:
            self._stats["bottleneck_count"] += 1

        return metric

    async def collect_all_metrics(self) -> dict[str, list[PerformanceMetric]]:
        """采集所有层指标。"""
        results = defaultdict(list)

        for layer in Layer:
            latency = random.uniform(10, 500)
            metric = await self.collect_metric(layer, MetricType.LATENCY, latency, "ms")
            results[layer.value].append(metric)

            if layer in [Layer.GATEWAY, Layer.API, Layer.CACHE]:
                throughput = random.uniform(100, 10000)
                metric = await self.collect_metric(layer, MetricType.THROUGHPUT, throughput, "rps")
                results[layer.value].append(metric)

        return dict(results)

    async def identify_bottlenecks(self) -> list[Bottleneck]:
        """识别瓶颈。"""
        bottlenecks = []

        for metric in self._metrics.values():
            if metric.is_bottleneck:
                bottleneck_id = f"BN_{uuid.uuid4().hex[:6].upper()}"

                severity = Severity.HIGH
                if metric.value > metric.threshold * 2:
                    severity = Severity.CRITICAL
                elif metric.value > metric.threshold * 1.5:
                    severity = Severity.HIGH
                else:
                    severity = Severity.MEDIUM

                recommendations = self._generate_recommendations(metric)

                bottleneck = Bottleneck(
                    bottleneck_id=bottleneck_id,
                    layer=metric.layer,
                    description=f"{metric.layer.value}层{metric.metric_type.value}过高",
                    severity=severity,
                    current_value=metric.value,
                    target_value=metric.threshold,
                    recommendations=recommendations,
                )

                self._bottlenecks[bottleneck_id] = bottleneck
                bottlenecks.append(bottleneck)

        return bottlenecks

    def _generate_recommendations(self, metric: PerformanceMetric) -> list[str]:
        """生成优化建议。"""
        recommendations = []

        if metric.layer == Layer.DATABASE and metric.metric_type == MetricType.LATENCY:
            recommendations = ["添加索引", "优化SQL查询", "增加连接池大小"]
        elif metric.layer == Layer.CACHE and metric.metric_type == MetricType.LATENCY:
            recommendations = ["增加Redis节点", "优化缓存策略", "使用本地缓存"]
        elif metric.layer == Layer.API and metric.metric_type == MetricType.LATENCY:
            recommendations = ["启用连接复用", "优化序列化", "增加实例数"]
        elif metric.layer == Layer.VECTOR and metric.metric_type == MetricType.LATENCY:
            recommendations = ["优化向量索引", "减少检索维度", "增加Qdrant节点"]

        return recommendations

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "metrics_by_layer": {layer.value: len([m for m in self._metrics.values() if m.layer == layer]) for layer in Layer},
        }


class OptimizationExecutor:
    """
    优化执行器(D102)。

    功能:
        1. SQL优化
        2. 缓存策略调整
        3. 连接池优化
    """

    OPTIMIZATION_TYPES = [
        "sql_index",
        "sql_rewrite",
        "cache_strategy",
        "connection_pool",
        "jvm_gc",
        "http_connection",
    ]

    def __init__(self):
        self._optimizations: dict[str, dict[str, Any]] = {}
        self._stats = {
            "total_optimizations": 0,
            "successful": 0,
        }
        logger.info("OptimizationExecutor初始化完成")

    async def execute_optimization(
        self,
        optimization_type: str,
        target: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """执行优化。"""
        opt_id = f"OPT_{uuid.uuid4().hex[:6].upper()}"

        await asyncio.sleep(random.uniform(0.1, 0.5))

        success = random.random() > 0.1
        improvement = random.uniform(10, 50) if success else 0

        optimization = {
            "opt_id": opt_id,
            "type": optimization_type,
            "target": target,
            "config": config,
            "success": success,
            "improvement_percent": round(improvement, 2),
            "executed_at": datetime.now(UTC).isoformat(),
        }

        self._optimizations[opt_id] = optimization
        self._stats["total_optimizations"] += 1
        if success:
            self._stats["successful"] += 1

        logger.info(f"执行优化: {opt_id} - {optimization_type} - {'成功' if success else '失败'}")
        return optimization

    async def batch_optimize(self) -> list[dict[str, Any]]:
        """批量优化。"""
        results = []

        results.append(await self.execute_optimization("sql_index", "products", {"column": "category_id"}))
        results.append(await self.execute_optimization("cache_strategy", "redis", {"ttl": 3600}))
        results.append(await self.execute_optimization("connection_pool", "postgresql", {"max_connections": 100}))
        results.append(await self.execute_optimization("jvm_gc", "api-service", {"gc_type": "G1GC"}))

        return results

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "success_rate": round(self._stats["successful"] / max(self._stats["total_optimizations"], 1), 4),
        }


class CapacityPlanner:
    """
    容量规划器(D103)。

    功能:
        1. 资源评估
        2. 扩容建议
        3. 成本估算
    """

    DEFAULT_RESOURCES = [
        {"name": "K8s Node", "current_config": "10台", "current_usage": 0.6, "estimated_peak": 0.9, "recommended_config": "15台"},
        {"name": "GPU卡", "current_config": "16张", "current_usage": 0.7, "estimated_peak": 0.95, "recommended_config": "24张"},
        {"name": "PG存储", "current_config": "500GB", "current_usage": 0.5, "estimated_peak": 0.8, "recommended_config": "2TB SSD"},
        {"name": "Redis内存", "current_config": "32GB", "current_usage": 0.65, "estimated_peak": 0.85, "recommended_config": "64GB"},
        {"name": "Kafka分区", "current_config": "18", "current_usage": 0.5, "estimated_peak": 0.7, "recommended_config": "36"},
    ]

    def __init__(self):
        self._resources: dict[str, CapacityResource] = {}
        self._stats = {
            "total_resources": 0,
            "need_expansion": 0,
        }
        logger.info("CapacityPlanner初始化完成")

    async def add_resource(
        self,
        name: str,
        current_config: str,
        current_usage: float,
        estimated_peak: float,
        recommended_config: str,
        cost_impact: str = "",
    ) -> CapacityResource:
        """添加资源。"""
        resource_id = f"RES_{uuid.uuid4().hex[:6].upper()}"

        resource = CapacityResource(
            resource_id=resource_id,
            name=name,
            current_config=current_config,
            current_usage=current_usage,
            estimated_peak=estimated_peak,
            recommended_config=recommended_config,
            cost_impact=cost_impact,
        )

        self._resources[resource_id] = resource
        self._stats["total_resources"] += 1

        if estimated_peak > 0.8:
            self._stats["need_expansion"] += 1

        return resource

    async def init_default_resources(self) -> list[CapacityResource]:
        """初始化默认资源。"""
        resources = []
        for config in self.DEFAULT_RESOURCES:
            resource = await self.add_resource(**config)
            resources.append(resource)
        return resources

    async def generate_plan(self) -> dict[str, Any]:
        """生成扩容计划。"""
        expansion_needed = [r for r in self._resources.values() if r.estimated_peak > 0.8]

        return {
            "total_resources": len(self._resources),
            "need_expansion": len(expansion_needed),
            "expansion_list": [r.to_dict() for r in expansion_needed],
            "estimated_cost": f"${len(expansion_needed) * 5000}/月",
            "timeline": "2周内完成扩容",
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "resources": [r.to_dict() for r in self._resources.values()],
        }


class StressTester:
    """
    生产级压测器(D104)。

    功能:
        1. 多场景压测
        2. 性能验证
        3. 结果报告
    """

    SCENARIOS = [
        {"name": "正常负载", "multiplier": 1, "duration_minutes": 480},
        {"name": "峰值负载", "multiplier": 3, "duration_minutes": 120},
        {"name": "极端压力", "multiplier": 5, "duration_minutes": 30},
        {"name": "突发流量", "multiplier": 10, "duration_minutes": 5},
    ]

    TARGETS = {
        "p99_latency_ms": 200,
        "error_rate": 0.001,
        "availability": 0.999,
    }

    def __init__(self):
        self._results: dict[str, StressTestResult] = {}
        self._stats = {
            "total_tests": 0,
            "passed_tests": 0,
        }
        logger.info("StressTester初始化完成")

    async def run_test(self, scenario: str, duration_minutes: float, multiplier: int) -> StressTestResult:
        """运行压测。"""
        result_id = f"STRESS_{uuid.uuid4().hex[:6].upper()}"

        base_requests = 10000
        total_requests = int(base_requests * multiplier * duration_minutes / 60)

        await asyncio.sleep(random.uniform(0.5, 2.0))

        error_rate = random.uniform(0.0001, 0.01) * multiplier
        successful_requests = int(total_requests * (1 - error_rate))
        failed_requests = total_requests - successful_requests

        avg_latency = random.uniform(50, 150) * (1 + multiplier * 0.1)
        p99_latency = avg_latency * random.uniform(1.5, 2.5)
        throughput = total_requests / (duration_minutes * 60)

        passed = p99_latency <= self.TARGETS["p99_latency_ms"] and error_rate <= self.TARGETS["error_rate"]

        result = StressTestResult(
            result_id=result_id,
            scenario=scenario,
            duration_minutes=duration_minutes,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            error_rate=error_rate,
            throughput_rps=throughput,
            passed=passed,
        )

        self._results[result_id] = result
        self._stats["total_tests"] += 1
        if passed:
            self._stats["passed_tests"] += 1

        logger.info(f"压测完成: {scenario} - {'通过' if passed else '不通过'}")
        return result

    async def run_all_scenarios(self) -> list[StressTestResult]:
        """运行所有场景。"""
        results = []
        for scenario in self.SCENARIOS:
            result = await self.run_test(
                scenario["name"],
                scenario["duration_minutes"],
                scenario["multiplier"],
            )
            results.append(result)
        return results

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "pass_rate": round(self._stats["passed_tests"] / max(self._stats["total_tests"], 1), 4),
        }


class BaselineManager:
    """
    性能基线管理器(D105)。

    功能:
        1. 基线建立
        2. 基线对比
        3. 报告生成
    """

    DEFAULT_BASELINE = {
        "api_p99_latency_ms": 150,
        "agent_avg_latency_ms": 1500,
        "db_query_latency_ms": 50,
        "cache_hit_rate": 0.95,
        "vector_search_latency_ms": 200,
        "throughput_rps": 500,
        "error_rate": 0.0005,
        "availability": 0.9999,
    }

    def __init__(self):
        self._baselines: dict[str, PerformanceBaseline] = {}
        self._stats = {
            "total_baselines": 0,
        }
        logger.info("BaselineManager初始化完成")

    async def create_baseline(self, name: str, metrics: dict[str, float] | None = None) -> PerformanceBaseline:
        """创建基线。"""
        baseline_id = f"BASE_{uuid.uuid4().hex[:6].upper()}"

        baseline = PerformanceBaseline(
            baseline_id=baseline_id,
            name=name,
            metrics=metrics or self.DEFAULT_BASELINE.copy(),
        )

        self._baselines[baseline_id] = baseline
        self._stats["total_baselines"] += 1

        logger.info(f"创建性能基线: {baseline_id} - {name}")
        return baseline

    async def compare_with_baseline(
        self,
        baseline_id: str,
        current_metrics: dict[str, float],
    ) -> dict[str, Any]:
        """与基线对比。"""
        baseline = self._baselines.get(baseline_id)
        if not baseline:
            return {"error": "Baseline not found"}

        comparison = {}
        for key, target in baseline.metrics.items():
            current = current_metrics.get(key, 0)
            if key in ["cache_hit_rate", "throughput_rps", "availability"]:
                passed = current >= target
                diff_percent = (current - target) / target * 100
            else:
                passed = current <= target
                diff_percent = (target - current) / target * 100

            comparison[key] = {
                "target": target,
                "current": current,
                "passed": passed,
                "diff_percent": round(diff_percent, 2),
            }

        all_passed = all(c["passed"] for c in comparison.values())

        return {
            "baseline_id": baseline_id,
            "baseline_name": baseline.name,
            "comparison": comparison,
            "all_passed": all_passed,
        }

    async def generate_report(self, baseline_id: str) -> dict[str, Any]:
        """生成报告。"""
        baseline = self._baselines.get(baseline_id)
        if not baseline:
            return {"error": "Baseline not found"}

        return {
            "report_id": f"RPT_{uuid.uuid4().hex[:6].upper()}",
            "baseline": baseline.to_dict(),
            "generated_at": datetime.now(UTC).isoformat(),
            "sections": [
                "性能测试报告",
                "容量规划文档",
                "性能基线标准",
                "扩容操作手册",
            ],
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "baselines": [b.to_dict() for b in self._baselines.values()],
        }
