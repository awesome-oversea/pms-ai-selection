"""
Agent管理API端点
================

提供Agent实例的管理和监控功能:
- Agent列表查询
- Agent状态监控
- Agent能力描述
- Agent健康检查

API端点:
    GET  /api/v1/agents              # 获取所有可用Agent
    GET  /api/v1/agents/types        # 获取Agent类型定义
    GET  /api/v1/agents/{name}       # 获取Agent详情
    GET  /api/v1/agents/{name}/health # Agent健康检查
    POST /api/v1/agents/{name}/invoke # 直接调用Agent
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.agents.base import AgentType, BaseAgent
from src.agents.commercial import CommercialAgent
from src.agents.data_collection import DataCollectionAgent
from src.agents.market_insight import MarketInsightAgent
from src.agents.product_planner import ProductPlannerAgent
from src.agents.report_generator import ReportGeneratorAgent
from src.agents.risk_assessor import RiskAssessorAgent
from src.core.auth import get_current_user
from src.core.security import add_audit_log
from src.services.agent_platform_service import AgentPlatformService, get_agent_platform_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agent管理"])

_agent_registry: dict[str, type[BaseAgent]] = {
    "data_collection": DataCollectionAgent,
    "market_insight": MarketInsightAgent,
    "product_planner": ProductPlannerAgent,
    "commercial": CommercialAgent,
    "risk_assessor": RiskAssessorAgent,
    "report_generator": ReportGeneratorAgent,
}

_active_agents: dict[str, BaseAgent] = {}


def get_registered_agent_classes() -> dict[str, type[BaseAgent]]:
    """返回已注册 Agent 类表的只读副本。"""
    return dict(_agent_registry)


class AgentInfo(BaseModel):
    """Agent信息响应。"""
    name: str
    agent_type: str
    version: str
    description: str
    status: str
    capabilities: list[str]
    required_inputs: list[str]
    timeout_seconds: int


class AgentInvokeRequest(BaseModel):
    """调用Agent的请求体。"""
    query: str = Field(..., min_length=2, description="输入查询")
    category: str | None = Field(None, description="产品类目")
    investment_budget: float | None = Field(None, ge=0, description="投资预算")
    extra_params: dict | None = Field(None, description="额外参数")


class AgentListResponse(BaseModel):
    """Agent列表响应。"""
    total: int
    agents: list[AgentInfo]


class AgentManualInterventionRequest(BaseModel):
    action: str = Field(..., min_length=1)
    comment: str | None = None


class AgentStrategyPublishRequest(BaseModel):
    value: dict = Field(default_factory=dict)
    description: str = ""


class AgentWorkflowInvokeRequest(BaseModel):
    framework_key: str = Field(default="langgraph-compatible")
    input_data: dict = Field(default_factory=dict)
    breakpoints: list[str] = Field(default_factory=list)
    single_step: bool = Field(default=False)


class AgentWorkflowResumeRequest(BaseModel):
    human_input: dict = Field(default_factory=dict)


class AgentWorkflowRollbackRequest(BaseModel):
    target_node: str | None = Field(default=None)


class AgentInstanceCreateRequest(BaseModel):
    agent_name: str = Field(..., min_length=1)
    config: dict = Field(default_factory=dict)


class AgentInstanceStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(pending|running|waiting|completed|failed|cancelled)$")


class AgentInstanceRestartRequest(BaseModel):
    reason: str = Field(default="manual_restart")


class AgentMessagePublishRequest(BaseModel):
    sender: str = Field(..., min_length=1)
    receiver: str = Field(..., min_length=1)
    content: dict = Field(default_factory=dict)
    message_type: str = Field(default="data_transfer")
    priority: str = Field(default="normal")
    correlation_id: str = Field(default="")
    reply_to: str = Field(default="")
    metadata: dict = Field(default_factory=dict)


class ExternalWorkflowRegisterRequest(BaseModel):
    workflow_key: str = Field(..., min_length=1)
    definition: dict = Field(default_factory=dict)


@router.get("/platform/topology", response_model=dict)
async def get_agent_platform_topology(current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.build_topology()
    finally:
        await session.close()


@router.get("/platform/operations", response_model=dict)
async def get_agent_platform_operations(current_user: dict = Depends(get_current_user)):
    try:
        service, session = await get_agent_platform_service(current_user)
        try:
            return await service.build_operations_status()
        finally:
            await session.close()
    except Exception:
        kafka_compatibility = {
            "mode": AgentPlatformService.KAFKA_COMPATIBLE_BACKEND,
            "supports": list(AgentPlatformService.KAFKA_COMPATIBLE_SUPPORTS),
            "local_acceptance_ready": False,
            "persistence_ready": False,
            "trace_summary_ready": False,
            "replay_ready": False,
            "ordered_offset_ready": False,
            "observed_offset_monotonic": False,
            "observed_offset_gap_count": 0,
            "observed_offset_integrity": False,
            "real_broker_status": "blocked",
            "blocked_reason": AgentPlatformService.KAFKA_REAL_BROKER_BLOCKED_REASON,
        }
        return {
            "lifecycle_summary": {"running": 0, "failed": 0, "waiting": 0},
            "diagnostics": {"status": "degraded", "fallback": True},
            "operations": [],
            "kafka_compatibility": kafka_compatibility,
            "message_bus": {
                "backend": AgentPlatformService.KAFKA_COMPATIBLE_BACKEND,
                "supports": list(AgentPlatformService.KAFKA_COMPATIBLE_SUPPORTS),
                "replay_ready": False,
                "ordered_offset_ready": False,
                "kafka_compatibility": kafka_compatibility,
                "fallback": True,
            },
        }


@router.get("/platform/frameworks", response_model=dict)
async def get_agent_platform_frameworks(current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        topology = await service.build_topology()
        return {
            "frameworks": topology.get("frameworks", {}),
            "workflow_registry": topology.get("workflow_registry", {}),
            "active_framework": topology.get("active_framework"),
        }
    finally:
        await session.close()


@router.get("/platform/frameworks/{framework_key}", response_model=dict)
async def get_agent_platform_framework_detail(framework_key: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        topology = await service.build_topology()
        framework = (topology.get("frameworks") or {}).get(framework_key)
        if framework is None:
            raise HTTPException(status_code=404, detail=f"框架不存在: {framework_key}")
        return {"framework_key": framework_key, "detail": framework}
    finally:
        await session.close()


@router.post("/platform/messages", response_model=dict)
async def publish_agent_message(request: AgentMessagePublishRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.publish_agent_message(
            sender=request.sender,
            receiver=request.receiver,
            content=request.content,
            message_type=request.message_type,
            priority=request.priority,
            correlation_id=request.correlation_id,
            reply_to=request.reply_to,
            metadata=request.metadata,
        )
        add_audit_log("agent.platform.message.publish", actor=current_user, target_type="agent_message", target_id=result["message"]["message_id"], result="success")
        return result
    finally:
        await session.close()


@router.get("/platform/messages", response_model=dict)
async def query_agent_messages(
    sender: str | None = Query(None),
    receiver: str | None = Query(None),
    message_type: str | None = Query(None),
    after_offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.query_agent_messages(
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            after_offset=after_offset,
            limit=limit,
        )
    finally:
        await session.close()


@router.get("/platform/messages/replay", response_model=dict)
async def replay_agent_messages(
    sender: str | None = Query(None),
    receiver: str | None = Query(None),
    message_type: str | None = Query(None),
    after_offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.replay_agent_messages(
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            after_offset=after_offset,
            limit=limit,
        )
    finally:
        await session.close()


@router.post("/platform/workflows/invoke", response_model=dict)
async def invoke_agent_workflow(request: AgentWorkflowInvokeRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.invoke_workflow(
            framework_key=request.framework_key,
            input_data=request.input_data,
            breakpoints=request.breakpoints,
            single_step=request.single_step,
        )
        add_audit_log("agent.platform.workflow.invoke", actor=current_user, target_type="agent_workflow", target_id=request.framework_key, result="success")
        return result
    finally:
        await session.close()


@router.get("/platform/workflows/snapshots", response_model=dict)
async def list_agent_workflow_snapshots(limit: int = Query(20, ge=1, le=100), current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.list_workflow_snapshots(limit=limit)
    finally:
        await session.close()


@router.post("/platform/instances/{instance_id}/restart", response_model=dict)
async def restart_agent_platform_instance(instance_id: str, request: AgentInstanceRestartRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.restart_agent_instance(instance_id, reason=request.reason)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Agent实例不存在: {instance_id}")
        add_audit_log("agent.platform.instance.restart", actor=current_user, target_type="agent_instance", target_id=instance_id, result="success", detail={"reason": request.reason})
        return result
    finally:
        await session.close()


@router.get("/platform/workflows/snapshots/{snapshot_id}", response_model=dict)
async def get_agent_workflow_snapshot(snapshot_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.get_workflow_snapshot(snapshot_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"工作流快照不存在: {snapshot_id}")
        return result
    finally:
        await session.close()


@router.post("/platform/workflows/snapshots/{snapshot_id}/step", response_model=dict)
async def step_agent_workflow_snapshot(snapshot_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.step_workflow_snapshot(snapshot_id)
        add_audit_log("agent.platform.workflow.step", actor=current_user, target_type="agent_workflow_snapshot", target_id=snapshot_id, result="success")
        return result
    finally:
        await session.close()


@router.post("/platform/workflows/snapshots/{snapshot_id}/resume", response_model=dict)
async def resume_agent_workflow_snapshot(snapshot_id: str, request: AgentWorkflowResumeRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.resume_workflow_snapshot(snapshot_id, human_input=request.human_input or None)
        add_audit_log("agent.platform.workflow.resume", actor=current_user, target_type="agent_workflow_snapshot", target_id=snapshot_id, result="success")
        return result
    finally:
        await session.close()


@router.post("/platform/workflows/snapshots/{snapshot_id}/rollback", response_model=dict)
async def rollback_agent_workflow_snapshot(snapshot_id: str, request: AgentWorkflowRollbackRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.rollback_workflow_snapshot(snapshot_id, target_node=request.target_node)
        add_audit_log("agent.platform.workflow.rollback", actor=current_user, target_type="agent_workflow_snapshot", target_id=snapshot_id, result="success", detail={"target_node": request.target_node})
        return result
    finally:
        await session.close()


@router.post("/platform/tasks/{task_id}/resume", response_model=dict)
async def resume_agent_task(task_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.resume_task(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或不可恢复: {task_id}")
        add_audit_log("agent.platform.resume", actor=current_user, target_type="selection_task", target_id=task_id, result="success")
        return result
    finally:
        await session.close()


@router.post("/platform/tasks/{task_id}/intervene", response_model=dict)
async def intervene_agent_task(task_id: str, request: AgentManualInterventionRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.manual_intervene(task_id, request.action, request.comment)
        if result is None:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        add_audit_log("agent.platform.intervene", actor=current_user, target_type="selection_task", target_id=task_id, result="success", detail={"action": request.action})
        return result
    finally:
        await session.close()


@router.get("/platform/instances", response_model=dict)
async def list_agent_instances(current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.list_agent_instances()
    finally:
        await session.close()


@router.post("/platform/instances", response_model=dict)
async def create_agent_instance(request: AgentInstanceCreateRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.create_agent_instance(agent_name=request.agent_name, config=request.config)
        add_audit_log("agent.platform.instance.create", actor=current_user, target_type="agent_instance", target_id=result["instance_id"], result="success")
        return result
    finally:
        await session.close()


@router.get("/platform/instances/{instance_id}", response_model=dict)
async def get_agent_instance(instance_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.get_agent_instance(instance_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Agent实例不存在: {instance_id}")
        return result
    finally:
        await session.close()


@router.post("/platform/instances/{instance_id}/status", response_model=dict)
async def update_agent_instance_status(instance_id: str, request: AgentInstanceStatusRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.update_agent_instance_status(instance_id, status=request.status)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Agent实例不存在: {instance_id}")
        add_audit_log("agent.platform.instance.status", actor=current_user, target_type="agent_instance", target_id=instance_id, result="success", detail={"status": request.status})
        return result
    finally:
        await session.close()


@router.delete("/platform/instances/{instance_id}", response_model=dict)
async def delete_agent_instance(instance_id: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.delete_agent_instance(instance_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Agent实例不存在: {instance_id}")
        add_audit_log("agent.platform.instance.delete", actor=current_user, target_type="agent_instance", target_id=instance_id, result="success")
        return result
    finally:
        await session.close()


@router.get("/platform/workflows", response_model=dict)
async def list_registered_workflows(current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        return await service.list_registered_workflows()
    finally:
        await session.close()


@router.post("/platform/workflows/register", response_model=dict)
async def register_external_workflow(request: ExternalWorkflowRegisterRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.register_external_workflow(request.workflow_key, request.definition)
        add_audit_log("agent.platform.workflow.register", actor=current_user, target_type="external_workflow", target_id=request.workflow_key, result="success")
        return result
    finally:
        await session.close()


@router.post("/platform/strategies/{strategy_key}/publish", response_model=dict)
async def publish_agent_strategy(strategy_key: str, request: AgentStrategyPublishRequest, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.publish_strategy(strategy_key, request.value, request.description)
        await session.commit()
        add_audit_log("agent.platform.strategy.publish", actor=current_user, target_type="agent_strategy", target_id=strategy_key, result="success", detail={"version": result.get("version")})
        return result
    finally:
        await session.close()


@router.post("/platform/strategies/{strategy_key}/rollback", response_model=dict)
async def rollback_agent_strategy(strategy_key: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.rollback_strategy(strategy_key)
        if result is None:
            raise HTTPException(status_code=404, detail=f"策略不存在或无历史版本: {strategy_key}")
        await session.commit()
        add_audit_log("agent.platform.strategy.rollback", actor=current_user, target_type="agent_strategy", target_id=strategy_key, result="success", detail={"version": result.get("version")})
        return result
    finally:
        await session.close()


@router.get("/platform/strategies/{strategy_key}", response_model=dict)
async def get_agent_strategy(strategy_key: str, current_user: dict = Depends(get_current_user)):
    service, session = await get_agent_platform_service(current_user)
    try:
        result = await service.get_strategy(strategy_key)
        if result is None:
            raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_key}")
        return result
    finally:
        await session.close()


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """
    获取所有可用的Agent列表。

    返回系统中注册的所有Agent及其基本信息，
    包括名称、类型、版本、能力和所需输入参数。

    Returns:
        AgentListResponse: Agent列表
    """
    agents = []

    for name, agent_cls in _agent_registry.items():
        try:
            instance = agent_cls()
            agents.append(
                AgentInfo(
                    name=instance.name,
                    agent_type=instance.agent_type.value,
                    version=instance.version,
                    description=instance.description,
                    status="available",
                    capabilities=[tool.name for tool in instance.get_tools()],
                    required_inputs=list(instance.REQUIRED_INPUT_KEYS),
                    timeout_seconds=instance.timeout_seconds,
                )
            )
        except Exception as e:
            logger.warning(f"获取Agent信息失败 {name}: {e}")

    return AgentListResponse(total=len(agents), agents=agents)


@router.get("/types", response_model=dict)
async def get_agent_types():
    """
    获取所有Agent类型定义。

    返回系统支持的Agent类型枚举值及其说明。

    Returns:
        dict: Agent类型定义
    """
    types_info = {}

    for agent_type in AgentType:
        types_info[agent_type.value] = {
            "value": agent_type.value,
            "name": agent_type.name,
            "description": {
                AgentType.DATA_COLLECTOR: "数据采集Agent - 负责多源数据采集与清洗",
                AgentType.MARKET_INSIGHT: "市场洞察Agent - 市场分析与机会识别",
                AgentType.PRODUCT_PLANNER: "产品规划Agent - 产品规格与供应链规划",
                AgentType.COMMERCIAL: "商业化Agent - 财务建模与Go/No-Go决策",
                AgentType.COORDINATOR: "协调器Agent - 工作流编排与任务调度",
            }.get(agent_type, "未知类型"),
        }

    return {"total": len(types_info), "types": types_info}


@router.get("/{agent_name}", response_model=AgentInfo)
async def get_agent_detail(agent_name: str):
    """
    获取指定Agent的详细信息。

    Args:
        agent_name: Agent名称(market_insight/product_planner/commercial)

    Returns:
        AgentInfo: Agent详细信息

    Raises:
        HTTPException: Agent不存在时返回404
    """
    if agent_name not in _agent_registry:
        raise HTTPException(status_code=404, detail=f"Agent不存在: {agent_name}")

    agent_cls = _agent_registry[agent_name]
    instance = agent_cls()

    return AgentInfo(
        name=instance.name,
        agent_type=instance.agent_type.value,
        version=instance.version,
        description=instance.description,
        status="available",
        capabilities=[tool.name for tool in instance.get_tools()],
        required_inputs=list(instance.REQUIRED_INPUT_KEYS),
        timeout_seconds=instance.timeout_seconds,
    )


@router.get("/{agent_name}/health", response_model=dict)
async def check_agent_health(agent_name: str):
    """
    检查指定Agent的健康状态。

    验证Agent是否可以正常初始化和运行。

    Args:
        agent_name: Agent名称

    Returns:
        dict: 健康状态

    Raises:
        HTTPException: Agent不存在时返回404
    """
    import asyncio

    if agent_name not in _agent_registry:
        raise HTTPException(status_code=404, detail=f"Agent不存在: {agent_name}")

    agent_cls = _agent_registry[agent_name]

    health_status = {
        "agent_name": agent_name,
        "status": "healthy",
        "checks": {
            "initialization": False,
            "tools_loaded": False,
            "quick_test": False,
        },
        "error": None,
    }

    try:
        instance = agent_cls()
        health_status["checks"]["initialization"] = True

        if instance.get_tools():
            health_status["checks"]["tools_loaded"] = True

        test_result = await asyncio.wait_for(
            instance.run({"query": "health_check", "category": "test"}),
            timeout=10.0,
        )

        if test_result and test_result.success:
            health_status["checks"]["quick_test"] = True

    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
        logger.error(f"Agent健康检查失败 {agent_name}: {e}")

    all_healthy = all(health_status["checks"].values())
    health_status["status"] = "healthy" if all_healthy else "degraded"

    return health_status


@router.post("/{agent_name}/invoke", response_model=dict)
async def invoke_agent(agent_name: str, request: AgentInvokeRequest):
    """
    直接调用指定的Agent执行任务。

    此接口用于单独测试或使用某个特定Agent的能力，
    不经过完整的SelectionMaster工作流。

    Args:
        agent_name: Agent名称
        request: 调用请求体

    Returns:
        dict: Agent执行结果

    Raises:
        HTTPException: Agent不存在或执行失败时返回错误
    """
    import asyncio

    if agent_name not in _agent_registry:
        raise HTTPException(status_code=404, detail=f"Agent不存在: {agent_name}")

    agent_cls = _agent_registry[agent_name]

    try:
        instance = agent_cls()

        input_data = {
            "query": request.query,
            "category": request.category or "electronics",
        }

        if request.investment_budget is not None:
            input_data["investment_budget"] = request.investment_budget

        if request.extra_params:
            input_data.update(request.extra_params)

        logger.info(f"🤖 直接调用Agent: {agent_name} | 查询: {request.query}")

        result = await asyncio.wait_for(
            instance.run(input_data),
            timeout=instance.timeout_seconds + 5,
        )

        response_data = {
            "agent_name": agent_name,
            "status": "success" if result.success else "error",
            "execution_time": result.execution_time_ms,
            "steps_count": len(result.steps),
        }

        if hasattr(result, 'output') and isinstance(result.output, dict):
            response_data["data"] = result.output.get("data") if "data" in result.output else result.output

        if result.error:
            response_data["error"] = result.error

        logger.info(f"✅ Agent执行完成: {agent_name} | 状态: {'success' if result.success else 'error'}")

        return response_data

    except Exception as e:
        logger.error(f"❌ Agent执行失败: {agent_name} | 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent执行失败: {str(e)}")
