"""
Agent基础框架
==============

提供Multi-Agent系统的基础能力(D16-T053):
    - Agent基类(生命周期/状态管理)
    - 工具注册与调用机制
    - 步骤追踪(Chain-of-Thought)
    - 结果序列化

使用方式:
    from src.agents.base import BaseAgent, AgentTool

    class MyAgent(BaseAgent):
        name = "my_agent"

        async def execute(self, input_data: dict) -> dict:
            context = await self.retrieve(input_data["query"])
            return await self.reason(context, input_data)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class AgentStatus(StrEnum):
    """Agent运行状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentType(StrEnum):
    """Agent类型枚举。"""

    DATA_COLLECTOR = "data_collector"
    MARKET_INSIGHT = "market_insight"
    PRODUCT_PLANNER = "product_planner"
    COMMERCIAL = "commercial"
    COORDINATOR = "coordinator"


@dataclass
class AgentStep:
    """
    Agent执行步骤记录。

    用于Chain-of-Thought追踪，
    支持调试和审计。

    Attributes:
        step_id: 步骤唯一标识
        step_name: 步骤名称
        step_type: 步骤类型(retrieve/reason/tool/format)
        input_data: 输入数据摘要
        output_data: 输出数据摘要
        duration_ms: 执行耗时(毫秒)
        status: 执行状态(success/error)
        error_message: 错误信息(如有)
        timestamp: 执行时间戳
    """

    step_id: str = ""
    step_name: str = ""
    step_type: str = ""
    input_data: str = ""
    output_data: str = ""
    duration_ms: float = 0.0
    status: str = "success"
    error_message: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "step_type": self.step_type,
            "input_summary": self.input_data[:200] if len(self.input_data) > 200 else self.input_data,
            "output_summary": self.output_data[:500] if len(self.output_data) > 500 else self.output_data,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error_message if self.error_message else None,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentResult:
    """
    Agent执行结果。

    Attributes:
        agent_id: Agent实例ID
        agent_type: Agent类型
        success: 是否成功
        output: 输出数据
        steps: 执行步骤列表
        metadata: 额外元数据
        execution_time_ms: 总执行时间
        error: 错误信息(如有)
    """

    agent_id: str = ""
    agent_type: str = ""
    success: bool = False
    output: Any = None
    steps: list[AgentStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "success": self.success,
            "output": self.output,
            "steps": [s.to_dict() for s in self.steps],
            "metadata": self.metadata,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
        }


class AgentTool:
    """
    Agent工具定义。

    封装可被Agent调用的外部功能:
        - 数据库查询
        - API调用
        - 计算函数

    Attributes:
        name: 工具名称(唯一标识)
        description: 功能描述(用于LLM选择)
        func: 实际执行函数
        parameters: 参数Schema(JSON Schema格式)
    """

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or {}

    async def execute(self, **kwargs: Any) -> Any:
        """执行工具调用。"""
        result = self.func(**kwargs)

        if asyncio.iscoroutine(result):
            result = await result

        return result


class BaseAgent:
    """
    Agent基类(D16-T053)。

    定义所有Agent的通用生命周期:
        1. initialize(): 初始化配置和依赖
        2. validate_input(): 校验输入数据
        3. execute(): 核心执行逻辑(子类实现)
        4. format_output(): 格式化输出结果

    内置能力:
        - 步骤追踪(AgentStep)
        - 工具注册与管理
        - 状态转换
        - 超时控制

    Attributes:
        name: Agent名称
        agent_type: Agent类型
        version: 版本号
        timeout_seconds: 单次执行超时
    """

    name: str = "base_agent"
    agent_type: AgentType = AgentType.COORDINATOR
    version: str = "1.0.0"
    timeout_seconds: int = 300
    description: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.agent_id = str(uuid.uuid4())
        self.status = AgentStatus.PENDING
        self._tools: dict[str, AgentTool] = {}
        self._steps: list[AgentStep] = []
        self._start_time: float | None = None

    def register_tool(self, tool: AgentTool):
        """
        注册工具到Agent。

        Args:
            tool: AgentTool实例
        """
        self._tools[tool.name] = tool
        logger.debug(f"🔧 Agent '{self.name}' 注册工具: {tool.name}")

    def get_tools(self) -> list[AgentTool]:
        """获取已注册的工具列表。"""
        return list(self._tools.values())

    def get_tool_names(self) -> list[str]:
        """获取已注册的工具名称列表。"""
        return list(self._tools.keys())

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """
        调用指定工具。

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            KeyError: 工具不存在时抛出
        """
        if tool_name not in self._tools:
            raise KeyError(f"工具 '{tool_name}' 未注册")

        tool = self._tools[tool_name]
        step = self._create_step(
            f"call_tool:{tool_name}",
            "tool",
            input_data=json.dumps(kwargs, ensure_ascii=False)[:500],
        )

        try:
            start = time.time()
            result = await tool.execute(**kwargs)
            elapsed = (time.time() - start) * 1000

            step.output_data = json.dumps(result, ensure_ascii=False, default=str)[:500]
            step.duration_ms = elapsed
            step.status = "success"

            return result
        except Exception as e:
            step.status = "error"
            step.error_message = str(e)
            raise

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """
        运行Agent完整流程。

        Args:
            input_data: 输入数据字典

        Returns:
            AgentResult: 包含输出、步骤、元数据的完整结果
        """
        self._start_time = time.time()
        self.status = AgentStatus.RUNNING
        self._steps.clear()

        try:
            await self.validate_input(input_data)

            init_step = self._create_step("initialize", "system")
            await self.initialize()
            init_step.duration_ms = (time.time() - self._start_time) * 1000

            exec_step = self._create_step("execute", "core", input_data=str(type(input_data)))
            output = await self.execute(input_data)
            exec_step.output_data = str(output)[:500]
            exec_step.status = "success"

            fmt_step = self._create_step("format_output", "post_process")
            formatted = await self.format_output(output)
            fmt_step.duration_ms = (time.time() - self._start_time) - (
                init_step.duration_ms / 1000 + getattr(exec_step, 'duration_ms', 0) / 1000
            ) * 1000

            total_elapsed = (time.time() - self._start_time) * 1000
            self.status = AgentStatus.COMPLETED

            return AgentResult(
                agent_id=self.agent_id,
                agent_type=self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type),
                success=True,
                output=formatted,
                steps=list(self._steps),
                metadata={
                    "version": self.version,
                    "config_keys": list(self.config.keys()),
                    "tools_registered": len(self._tools),
                },
                execution_time_ms=total_elapsed,
            )

        except Exception as e:
            self.status = AgentStatus.FAILED
            total_elapsed = (time.time() - self._start_time) * 1000

            logger.error(f"❌ Agent '{self.name}' 执行失败: {e}")

            return AgentResult(
                agent_id=self.agent_id,
                agent_type=self.agent_type.value if hasattr(self.agent_type, 'value') else str(self.agent_type),
                success=False,
                steps=list(self._steps),
                execution_time_ms=total_elapsed,
                error=str(e),
            )

    async def initialize(self):
        """初始化Agent(子类可选重写)。"""
        pass

    async def validate_input(self, input_data: dict[str, Any]):
        """校验输入数据(子类可重写)。"""
        if not isinstance(input_data, dict):
            raise ValueError("input_data必须是dict类型")

    async def execute(self, input_data: dict[str, Any]) -> Any:
        """
        核心执行逻辑(子类必须实现)。

        Args:
            input_data: 经过校验的输入数据

        Returns:
            原始输出数据(将被format_output处理)
        """
        raise NotImplementedError("子类必须实现execute方法")

    async def format_output(self, raw_output: Any) -> Any:
        """格式化输出(子类可重写)。"""
        return raw_output

    def _create_step(
        self,
        step_name: str,
        step_type: str = "general",
        input_data: str = "",
    ) -> AgentStep:
        """创建并记录一个执行步骤。"""
        step = AgentStep(
            step_id=str(uuid.uuid4())[:8],
            step_name=step_name,
            step_type=step_type,
            input_data=input_data,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._steps.append(step)
        return step

    def _parse_llm_json_response(self, raw_response: Any) -> dict[str, Any]:
        """尽量从LLM文本响应中提取JSON对象。"""
        if not isinstance(raw_response, str):
            return {}

        text = raw_response.strip()
        if not text:
            return {}

        candidates: list[str] = [text]
        if "```" in text:
            for chunk in text.split("```"):
                normalized = chunk.strip()
                if not normalized:
                    continue
                if normalized.lower().startswith("json"):
                    normalized = normalized[4:].strip()
                if normalized:
                    candidates.append(normalized)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    @property
    def info(self) -> dict[str, Any]:
        """返回Agent描述信息。"""
        return {
            "name": self.name,
            "type": self.agent_type.value,
            "version": self.version,
            "description": self.description or f"{self.name} Agent",
            "tools": [t.name for t in self._tools.values()],
            "status": self.status.value,
        }
