"""
工作流引擎测试
==============

覆盖:
1. 步骤添加与依赖验证
2. 顺序执行（有依赖的步骤按序执行）
3. 步骤超时处理（asyncio.wait_for 超时 → 自动重试）
4. 步骤失败重试（失败 → 重试 → 成功 / 失败 → 重试耗尽 → 工作流失败）
5. 工作流取消（CancelledError 处理）
6. 上下文数据传递与最终输出构建

不依赖外部服务 (DB / Redis / LLM)。
"""

import asyncio

import pytest
from src.core.workflow import (
    WorkflowContext,
    WorkflowEngine,
    WorkflowPhase,
    WorkflowStatus,
    create_workflow_engine,
)

# ---------------------------------------------------------------------------
# 辅助 Mock Agent
# ---------------------------------------------------------------------------

class MockAgent:
    """成功执行的 Mock Agent。"""

    def __init__(self, output=None):
        self._output = output or {"data": {"score": 85}}

    async def run(self, input_data: dict):
        return self._output


class FailingMockAgent:
    """始终失败的 Mock Agent。"""

    def __init__(self, error_msg="模拟错误"):
        self._error_msg = error_msg

    async def run(self, input_data: dict):
        raise RuntimeError(self._error_msg)


class SlowMockAgent:
    """执行很慢的 Mock Agent，用于测试超时。"""

    def __init__(self, delay: float = 10.0):
        self._delay = delay

    async def run(self, input_data: dict):
        await asyncio.sleep(self._delay)
        return {"data": {"slow": True}}


class EventuallySucceedAgent:
    """前 N 次失败，之后成功的 Mock Agent，用于测试重试。"""

    def __init__(self, fail_times: int = 1, output=None):
        self._fail_times = fail_times
        self._attempt = 0
        self._output = output or {"data": {"recovered": True}}

    async def run(self, input_data: dict):
        self._attempt += 1
        if self._attempt <= self._fail_times:
            raise RuntimeError(f"第 {self._attempt} 次失败")
        return self._output


# ---------------------------------------------------------------------------
# 1. 步骤添加与依赖验证
# ---------------------------------------------------------------------------

def test_add_step_basic():
    """添加步骤应注册到引擎中。"""
    engine = WorkflowEngine("test_wf")
    engine.add_step("step1", MockAgent(), WorkflowPhase.DATA_COLLECTION)

    assert "step1" in engine._steps
    assert len(engine._step_order) == 1


def test_add_duplicate_step_raises():
    """重复添加同名步骤应抛 ValueError。"""
    engine = WorkflowEngine("test_wf")
    engine.add_step("step1", MockAgent(), WorkflowPhase.DATA_COLLECTION)

    with pytest.raises(ValueError, match="步骤已存在"):
        engine.add_step("step1", MockAgent(), WorkflowPhase.DATA_COLLECTION)


def test_add_step_with_dependencies():
    """添加带依赖的步骤应正确记录依赖关系。"""
    engine = WorkflowEngine("test_wf")
    engine.add_step("step1", MockAgent(), WorkflowPhase.DATA_COLLECTION)
    engine.add_step(
        "step2", MockAgent(), WorkflowPhase.PRODUCT_PLANNING,
        dependencies=["step1"],
    )

    assert engine._steps["step2"].dependencies == ["step1"]


# ---------------------------------------------------------------------------
# 2. 正常顺序执行
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_execution():
    """有依赖的步骤应按序执行，结果正确。"""
    engine = WorkflowEngine("seq_wf")
    engine.add_step("market", MockAgent({"data": {"trend": "up"}}), WorkflowPhase.DATA_COLLECTION)
    engine.add_step(
        "product", MockAgent({"data": {"plan": "A"}}), WorkflowPhase.PRODUCT_PLANNING,
        dependencies=["market"],
    )
    engine.add_step(
        "commercial", MockAgent({"data": {"go_no_go": "GO"}}), WorkflowPhase.COMMERCIAL_EVALUATION,
        dependencies=["product"],
    )

    result = await engine.run({"query": "蓝牙耳机"})

    assert result.status == WorkflowStatus.COMPLETED
    assert result.steps_completed == 3
    assert result.total_steps == 3
    assert result.execution_time_seconds >= 0
    assert result.error is None
    # step_details 应有 3 条
    assert len(result.step_details) == 3


# ---------------------------------------------------------------------------
# 3. 步骤超时处理
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_timeout_triggers_retry():
    """步骤超时应触发重试，重试耗尽后工作流失败。"""
    engine = WorkflowEngine("timeout_wf", enable_retry=True)
    engine.add_step(
        "slow_step",
        SlowMockAgent(delay=10.0),
        WorkflowPhase.DATA_COLLECTION,
        timeout=0.1,     # 100ms 超时
        retry_count=1,   # 重试 1 次
    )

    result = await engine.run({"query": "test"})

    assert result.status == WorkflowStatus.FAILED
    assert "重试耗尽" in (result.error or "")
    # slow_step 应标记为 FAILED
    step_detail = result.step_details[0]
    assert step_detail["status"] == "failed"
    assert "超时" in (step_detail["error"] or "")


# ---------------------------------------------------------------------------
# 4. 步骤失败重试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_then_succeed():
    """步骤首次失败后重试成功，工作流应完成。"""
    engine = WorkflowEngine("retry_ok_wf", enable_retry=True)
    engine.add_step(
        "flaky_step",
        EventuallySucceedAgent(fail_times=1, output={"data": {"ok": True}}),
        WorkflowPhase.DATA_COLLECTION,
        retry_count=2,
    )

    result = await engine.run({"query": "test"})

    assert result.status == WorkflowStatus.COMPLETED
    assert result.steps_completed == 1


@pytest.mark.asyncio
async def test_retry_exhausted_fails():
    """重试耗尽后工作流应失败。"""
    engine = WorkflowEngine("retry_fail_wf", enable_retry=True)
    engine.add_step(
        "bad_step",
        FailingMockAgent("持续失败"),
        WorkflowPhase.DATA_COLLECTION,
        retry_count=2,
    )

    result = await engine.run({"query": "test"})

    assert result.status == WorkflowStatus.FAILED
    assert "重试耗尽" in (result.error or "")


# ---------------------------------------------------------------------------
# 5. 工作流取消
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_cancel():
    """取消正在运行的工作流应触发 CancelledError。"""
    engine = WorkflowEngine("cancel_wf")
    engine.add_step("slow", SlowMockAgent(delay=30.0), WorkflowPhase.DATA_COLLECTION, timeout=30.0)

    async def cancel_after_delay():
        await asyncio.sleep(0.05)
        task.cancel()

    task = asyncio.create_task(engine.run({"query": "test"}))
    asyncio.create_task(cancel_after_delay())

    with pytest.raises(asyncio.CancelledError):
        await task

    assert engine.status == WorkflowStatus.CANCELLED


# ---------------------------------------------------------------------------
# 6. 上下文与工厂函数
# ---------------------------------------------------------------------------

def test_workflow_context_operations():
    """WorkflowContext 应正确存取步骤结果和错误。"""
    ctx = WorkflowContext(workflow_id="ctx_test")
    ctx.set_step_result("step1", {"score": 90})
    ctx.add_error("step2: 连接超时")

    assert ctx.get_step_result("step1") == {"score": 90}
    assert ctx.get_step_result("nonexistent") is None
    assert len(ctx.errors) == 1
    assert "连接超时" in ctx.errors[0]


def test_create_workflow_engine_factory():
    """工厂函数应创建配置正确的引擎实例。"""
    engine = create_workflow_engine("factory_wf", max_concurrent=5)

    assert engine.workflow_id == "factory_wf"
    assert engine.max_concurrent == 5
    assert engine.status == WorkflowStatus.PENDING


@pytest.mark.asyncio
async def test_dependency_skip_unmet():
    """依赖未满足的步骤应被跳过。"""
    engine = WorkflowEngine("dep_skip_wf")
    # step2 依赖 step1，但 step1 失败了
    engine.add_step("step1", FailingMockAgent(), WorkflowPhase.DATA_COLLECTION, retry_count=0)
    engine.add_step("step2", MockAgent(), WorkflowPhase.PRODUCT_PLANNING, dependencies=["step1"])

    result = await engine.run({"query": "test"})

    assert result.status == WorkflowStatus.FAILED
    # step2 应该不会执行（被跳过或因 step1 失败导致整体失败）
    step2_detail = next((d for d in result.step_details if d["name"] == "step2"), None)
    if step2_detail:
        assert step2_detail["status"] in ("pending", "failed")
