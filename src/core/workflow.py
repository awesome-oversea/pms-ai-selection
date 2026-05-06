"""
工作流引擎(Workflow Engine)
==========================

实现选品系统的核心工作流编排(D25-T068):
- 任务调度与执行
- Agent协同与数据流转
- 状态管理与持久化
- 错误处理与重试
- 并行执行支持

工作流阶段:
    1. 数据采集(Data Collection) - MarketInsightAgent
    2. 产品规划(Product Planning) - ProductPlannerAgent
    3. 商业化评估(Commercial Evaluation) - CommercialAgent
    4. 决策汇总(Decision Summary) - SelectionMaster
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowStatus(StrEnum):
    """工作流状态枚举。"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowPhase(StrEnum):
    """工作流阶段枚举。"""
    INITIALIZED = "initialized"
    DATA_COLLECTION = "data_collection"
    PRODUCT_PLANNING = "product_planning"
    COMMERCIAL_EVALUATION = "commercial_evaluation"
    DECISION_SUMMARY = "decision_summary"


@dataclass
class WorkflowStep:
    """
    工作流步骤定义。

    每个步骤包含:
        - name: 步骤名称
        - agent: 执行的Agent实例
        - phase: 所属阶段
        - timeout: 超时时间(秒)
        - retry_count: 重试次数
        - dependencies: 依赖的前置步骤
    """
    name: str
    agent: Any
    phase: WorkflowPhase
    timeout: float = 60.0
    retry_count: int = 2
    dependencies: list[str] = field(default_factory=list)

    start_time: float | None = None
    end_time: float | None = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Any | None = None
    error: str | None = None


@dataclass
class WorkflowContext:
    """
    工作流上下文。

    在各步骤间传递共享数据:
        - input_data: 初始输入参数
        - step_results: 各步骤的输出结果
        - metadata: 元数据(时间戳/配置等)
        - errors: 错误信息收集
    """
    workflow_id: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def get_step_result(self, step_name: str) -> Any | None:
        """获取指定步骤的结果。"""
        return self.step_results.get(step_name)

    def set_step_result(self, step_name: str, result: Any) -> None:
        """设置步骤结果。"""
        self.step_results[step_name] = result

    def add_error(self, error: str) -> None:
        """添加错误信息。"""
        self.errors.append(error)


@dataclass
class WorkflowResult:
    """
    工作流执行结果。

    包含完整的执行记录和最终输出。
    """
    workflow_id: str
    status: WorkflowStatus
    current_phase: WorkflowPhase
    steps_completed: int
    total_steps: int
    execution_time_seconds: float
    final_output: dict[str, Any] | None = None
    error: str | None = None
    step_details: list[dict[str, Any]] = field(default_factory=list)


class WorkflowEngine:
    """
    工作流引擎(D25-T068)。

    核心功能:
        1. 定义和管理工作流步骤
        2. 按依赖关系调度步骤执行
        3. 支持并行执行无依赖的步骤
        4. 自动重试失败的步骤
        5. 收集和传递步骤间的数据
        6. 提供完整的执行日志

    使用示例:
        >>> engine = WorkflowEngine("wf_001")
        >>> engine.add_step("market_analysis", market_agent, WorkflowPhase.DATA_COLLECTION)
        >>> engine.add_step("product_planning", product_agent, WorkflowPhase.PRODUCT_PLANNING,
        ...                dependencies=["market_analysis"])
        >>> result = await engine.run({"query": "蓝牙耳机"})
    """

    def __init__(
        self,
        workflow_id: str = "",
        max_concurrent: int = 3,
        enable_retry: bool = True,
    ):
        self.workflow_id = workflow_id or f"wf_{int(time.time())}"
        self.max_concurrent = max_concurrent
        self.enable_retry = enable_retry

        self._steps: dict[str, WorkflowStep] = {}
        self._step_order: list[str] = []
        self._context = WorkflowContext(workflow_id=self.workflow_id)

        self._status = WorkflowStatus.PENDING
        self._current_phase = WorkflowPhase.INITIALIZED
        self._start_time: float | None = None
        self._end_time: float | None = None

        self._on_step_complete: Callable[[str, Any], None] | None = None
        _on_step_error: Callable[[str, Exception], None] | None = None

    def add_step(
        self,
        name: str,
        agent: Any,
        phase: WorkflowPhase,
        timeout: float = 60.0,
        retry_count: int = 2,
        dependencies: list[str] | None = None,
    ):
        """
        添加工作流步骤。

        Args:
            name: 步骤名称(唯一标识)
            agent: 执行该步骤的Agent实例
            phase: 所属工作流阶段
            timeout: 超时时间(秒)
            retry_count: 失败重试次数
            dependencies: 依赖的前置步骤名称列表
        """
        if name in self._steps:
            raise ValueError(f"步骤已存在: {name}")

        step = WorkflowStep(
            name=name,
            agent=agent,
            phase=phase,
            timeout=timeout,
            retry_count=retry_count,
            dependencies=dependencies or [],
        )

        self._steps[name] = step
        self._step_order.append(name)

        logger.debug(f"📋 添加工作流步骤: {name} | 阶段: {phase.value} | 依赖: {dependencies or []}")

    async def run(self, input_data: dict[str, Any]) -> WorkflowResult:
        """
        执行完整工作流。

        执行流程:
            1. 初始化上下文
            2. 按拓扑序执行各步骤
            3. 处理步骤间的数据传递
            4. 收集最终结果

        Args:
            input_data: 工作流输入参数

        Returns:
            WorkflowResult: 完整的执行结果
        """
        self._start_time = time.time()
        self._status = WorkflowStatus.RUNNING
        self._context.input_data = input_data.copy()

        logger.info(f"🚀 工作流启动: {self.workflow_id} | 步骤数: {len(self._steps)}")

        try:
            completed_steps = 0

            for step_name in self._step_order:
                step = self._steps[step_name]

                if not self._check_dependencies(step):
                    logger.warning(f"⚠️ 步骤依赖未满足，跳过: {step_name}")
                    continue

                self._current_phase = step.phase

                result = await self._execute_step(step, input_data)

                if result is not None:
                    self._context.set_step_result(step_name, result)
                    completed_steps += 1
                else:
                    if step.status == WorkflowStatus.FAILED:
                        raise RuntimeError(f"步骤执行失败且重试耗尽: {step_name}")

            execution_time = time.time() - self._start_time

            self._status = WorkflowStatus.COMPLETED
            self._current_phase = WorkflowPhase.DECISION_SUMMARY
            self._end_time = time.time()

            final_output = self._build_final_output()

            logger.info(
                f"✅ 工作流完成: {self.workflow_id} "
                f"| 耗时: {execution_time:.2f}s "
                f"| 完成步骤: {completed_steps}/{len(self._steps)}"
            )

            return WorkflowResult(
                workflow_id=self.workflow_id,
                status=self._status,
                current_phase=self._current_phase,
                steps_completed=completed_steps,
                total_steps=len(self._steps),
                execution_time_seconds=execution_time,
                final_output=final_output,
                step_details=self._build_step_details(),
            )

        except asyncio.CancelledError:
            self._status = WorkflowStatus.CANCELLED
            logger.warning(f"⛔ 工作流已取消: {self.workflow_id}")
            raise

        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._end_time = time.time()
            logger.error(f"❌ 工作流失败: {self.workflow_id} | 错误: {str(e)}")

            return WorkflowResult(
                workflow_id=self.workflow_id,
                status=self._status,
                current_phase=self._current_phase,
                steps_completed=sum(
                    1 for s in self._steps.values()
                    if s.status == WorkflowStatus.COMPLETED
                ),
                total_steps=len(self._steps),
                execution_time_seconds=time.time() - (self._start_time or 0),
                error=str(e),
                step_details=self._build_step_details(),
            )

    async def _execute_step(
        self,
        step: WorkflowStep,
        input_data: dict[str, Any],
    ) -> Any | None:
        """
        执行单个工作流步骤(带重试)。

        Args:
            step: 要执行的步骤
            input_data: 输入数据(可能包含前置步骤的结果)

        Returns:
            步骤执行结果，失败返回None
        """
        step.status = WorkflowStatus.RUNNING
        step.start_time = time.time()

        merged_input = self._merge_input_with_context(input_data, step.name)

        for attempt in range(step.retry_count + 1):
            try:
                logger.info(
                    f"🔄 执行步骤: {step.name} "
                    f"| 尝试: {attempt + 1}/{step.retry_count + 1}"
                )

                result = await asyncio.wait_for(
                    step.agent.run(merged_input),
                    timeout=step.timeout,
                )

                step.status = WorkflowStatus.COMPLETED
                step.end_time = time.time()
                step.result = result

                elapsed = (step.end_time - step.start_time) or 0
                logger.info(
                    f"✅ 步骤完成: {step.name} | 耗时: {elapsed:.2f}s"
                )

                if self._on_step_complete:
                    try:
                        self._on_step_complete(step.name, result)
                    except Exception as cb_error:
                        logger.warning(f"步骤完成回调失败: {cb_error}")

                return result

            except TimeoutError:
                logger.warning(
                    f"⏰ 步骤超时: {step.name} | 限制: {step.timeout}s"
                )
                step.error = f"超时({step.timeout}s)"

            except Exception as e:
                logger.warning(
                    f"❌ 步骤失败: {step.name} | 错误: {str(e)}"
                )
                step.error = str(e)
                self._context.add_error(f"{step.name}: {str(e)}")

                if attempt < step.retry_count and self.enable_retry:
                    await asyncio.sleep(1.0 * (attempt + 1))

        step.status = WorkflowStatus.FAILED
        step.end_time = time.time()
        return None

    def _check_dependencies(self, step: WorkflowStep) -> bool:
        """检查步骤的依赖是否都已满足。"""
        for dep_name in step.dependencies:
            dep_step = self._steps.get(dep_name)
            if not dep_step or dep_step.status != WorkflowStatus.COMPLETED:
                return False
        return True

    def _merge_input_with_context(
        self,
        base_input: dict[str, Any],
        current_step: str,
    ) -> dict[str, Any]:
        """
        合并基础输入与上下文中的前置步骤结果。

        将已完成步骤的结果注入到当前步骤的输入中，
        实现步骤间的数据流转。
        """
        merged = base_input.copy()

        for step_name, step_obj in self._steps.items():
            if step_name != current_step and step_obj.result is not None:
                if hasattr(step_obj.result, 'output') and isinstance(step_obj.result.output, dict):
                    merged[f"_{step_name}_result"] = step_obj.result.output.get("data", {})
                else:
                    merged[f"_{step_name}_result"] = step_obj.result

        return merged

    def _build_final_output(self) -> dict[str, Any]:
        """构建最终输出，整合所有步骤结果。"""
        output: dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "status": self._status.value,
            "completed_at": datetime.now(UTC).isoformat(),
            "results": {},
        }

        for step_name, step_obj in self._steps.items():
            if step_obj.result is not None:
                if hasattr(step_obj.result, 'output') and isinstance(step_obj.result.output, dict):
                    output["results"][step_name] = step_obj.result.output.get("data", {})
                else:
                    output["results"][step_name] = step_obj.result

        results = output["results"]
        if isinstance(results, dict):
            gng_data = results.get("commercial", {}).get("go_no_go")
            if gng_data:
                output["decision"] = gng_data

        return output

    def _build_step_details(self) -> list[dict]:
        """构建步骤详情列表用于响应。"""
        details = []

        for step_name in self._step_order:
            step = self._steps[step_name]
            details.append({
                "name": step.name,
                "phase": step.phase.value,
                "status": step.status.value,
                "duration_seconds": round((step.end_time or 0) - (step.start_time or 0), 2),
                "error": step.error,
            })

        return details

    @property
    def status(self) -> WorkflowStatus:
        """获取当前工作流状态。"""
        return self._status

    @property
    def context(self) -> WorkflowContext:
        """获取工作流上下文。"""
        return self._context

    def cancel(self):
        """取消正在运行的工作流。"""
        self._status = WorkflowStatus.CANCELLED
        logger.info(f"⛔ 工作流取消请求: {self.workflow_id}")


def create_workflow_engine(
    workflow_id: str = "",
    max_concurrent: int = 3,
) -> WorkflowEngine:
    """创建WorkflowEngine工厂函数。"""
    return WorkflowEngine(
        workflow_id=workflow_id,
        max_concurrent=max_concurrent,
    )
