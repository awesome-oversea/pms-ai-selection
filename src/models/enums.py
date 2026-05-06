"""
业务枚举类型定义
================

集中定义系统中所有枚举常量，确保类型安全和一致性。
所有业务逻辑中的状态/类型/优先级等均使用此模块的枚举值。

分类:
    TaskStatus: 选品任务生命周期状态
    TaskPriority: 任务优先级
    AgentType: AI Agent类型
    AgentStatus: Agent运行状态
    ReportType: 报告类型
    ERPSystemType: ERP系统类型
"""

from enum import Enum


class TaskStatus(str, Enum):
    """
    选品任务生命周期状态。

    状态流转(V11 6态):
        PENDING → RUNNING → PAUSED → RUNNING → COMPLETED
                   RUNNING → COMPLETED
                   RUNNING → FAILED
                   RUNNING → CANCELLED
        PENDING → CANCELLED (取消)
        PAUSED  → CANCELLED (暂停后取消)

    Attributes:
        PENDING: 待执行(已创建，等待Agent调度)
        RUNNING: 执行中(Agent正在分析)
        PAUSED: 已暂停(人工干预或等待审批)
        COMPLETED: 已完成(结果已生成)
        FAILED: 执行失败(需重试或人工介入)
        CANCELLED: 已取消(用户主动终止)
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """
    任务优先级。

    用于任务队列排序和资源分配策略。
    数值越高越紧急。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentType(str, Enum):
    """
    AI Agent类型定义。

    对应设计文档中的四核心Agent架构:
    - DataCollectorAgent: 数据采集(爬虫/API/Kafka/Flink)
    - MarketInsightAgent: 市场洞察(Jaxx模式)
    - ProductPlannerAgent: 产品规划(Jobs模式)
    - CommercializationAgent: 商业化(Pony模式)
    """

    DATA_COLLECTOR = "data_collector"
    MARKET_INSIGHT = "market_insight"
    PRODUCT_PLANNER = "product_planner"
    COMMERCIALIZATION = "commercialization"


class AgentStatus(str, Enum):
    """
    Agent运行状态。

    描述Agent实例在DAG工作流中的当前状态。
    """

    IDLE = "idle"
    INITIALIZING = "initializing"
    PROCESSING = "processing"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


class ReportType(str, Enum):
    """
    报告类型枚举。

    支持自动生成的各类选品报告格式。
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ERPSystemType(str, Enum):
    """
    ERP系统集成类型。

    定义 PMS 需要对接的 ERP 14 域与平台编排域。
    """

    IAM = "iam"
    PDM = "pdm"
    SOM = "som"
    ADS = "ads"
    OMS = "oms"
    SCM = "scm"
    WMS = "wms"
    FBA = "fba"
    TMS = "tms"
    CRM = "crm"
    FMS = "fms"
    BI = "bi"
    SYS = "sys"
    DASHBOARD = "dashboard"
    PAAS = "paas"
    MS = "ms"


class RecommendationExecutionState(str, Enum):
    """
    建议执行13态状态机。

    覆盖 PMS 建议池 → ERP 审批执行全生命周期闭环。

    正向流转:
        SUGGESTED → PMS_APPROVED → ERP_SUBMITTED → SCM_REVIEWING → SCM_APPROVED
        → SCM_ORDERED → WMS_RESERVED → WMS_CONFIRMED → OMS_DRAFT_CREATED
        → OMS_PUBLISHED → OMS_ACTIVE → CLOSED

    逆向/异常流转:
        SUGGESTED → PMS_REJECTED
        SCM_REVIEWING → SCM_REJECTED
        任意执行态 → EXECUTION_FAILED
        OMS_ACTIVE → CLOSED
    """

    SUGGESTED = "suggested"
    PMS_APPROVED = "pms_approved"
    PMS_REJECTED = "pms_rejected"
    ERP_SUBMITTED = "erp_submitted"
    SCM_REVIEWING = "scm_reviewing"
    SCM_APPROVED = "scm_approved"
    SCM_REJECTED = "scm_rejected"
    SCM_ORDERED = "scm_ordered"
    WMS_RESERVED = "wms_reserved"
    WMS_CONFIRMED = "wms_confirmed"
    OMS_DRAFT_CREATED = "oms_draft_created"
    OMS_PUBLISHED = "oms_published"
    OMS_ACTIVE = "oms_active"
    EXECUTION_FAILED = "execution_failed"
    CLOSED = "closed"


class ERPDomainType(str, Enum):
    """
    ERP六域服务类型。

    对应 ERP 六域服务化拆分:
    - MS: 商品主数据服务 (Master Service)
    - SCM: 供应链管理 (Supply Chain Management)
    - WMS: 仓储管理 (Warehouse Management System)
    - OMS: 订单管理 (Order Management System)
    - CRM: 客户关系管理 (Customer Relationship Management)
    - BI: 商业智能 (Business Intelligence)
    """

    MS = "ms"
    SCM = "scm"
    WMS = "wms"
    OMS = "oms"
    CRM = "crm"
    BI = "bi"


_TRANSITIONS: dict[RecommendationExecutionState, set[RecommendationExecutionState]] = {
    RecommendationExecutionState.SUGGESTED: {
        RecommendationExecutionState.PMS_APPROVED,
        RecommendationExecutionState.PMS_REJECTED,
    },
    RecommendationExecutionState.PMS_APPROVED: {
        RecommendationExecutionState.ERP_SUBMITTED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.PMS_REJECTED: set(),
    RecommendationExecutionState.ERP_SUBMITTED: {
        RecommendationExecutionState.SCM_REVIEWING,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.SCM_REVIEWING: {
        RecommendationExecutionState.SCM_APPROVED,
        RecommendationExecutionState.SCM_REJECTED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.SCM_APPROVED: {
        RecommendationExecutionState.SCM_ORDERED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.SCM_REJECTED: set(),
    RecommendationExecutionState.SCM_ORDERED: {
        RecommendationExecutionState.WMS_RESERVED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.WMS_RESERVED: {
        RecommendationExecutionState.WMS_CONFIRMED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.WMS_CONFIRMED: {
        RecommendationExecutionState.OMS_DRAFT_CREATED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.OMS_DRAFT_CREATED: {
        RecommendationExecutionState.OMS_PUBLISHED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.OMS_PUBLISHED: {
        RecommendationExecutionState.OMS_ACTIVE,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.OMS_ACTIVE: {
        RecommendationExecutionState.CLOSED,
    },
    RecommendationExecutionState.EXECUTION_FAILED: {
        RecommendationExecutionState.ERP_SUBMITTED,
    },
    RecommendationExecutionState.CLOSED: set(),
}


def can_transition(current: RecommendationExecutionState, target: RecommendationExecutionState) -> bool:
    return target in _TRANSITIONS.get(current, set())


def get_valid_transitions(current: RecommendationExecutionState) -> set[RecommendationExecutionState]:
    return _TRANSITIONS.get(current, set()).copy()


def is_terminal_state(state: RecommendationExecutionState) -> bool:
    return state in {
        RecommendationExecutionState.PMS_REJECTED,
        RecommendationExecutionState.SCM_REJECTED,
        RecommendationExecutionState.CLOSED,
    }
