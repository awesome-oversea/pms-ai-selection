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

from enum import StrEnum


class TaskStatus(StrEnum):
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


class TaskPriority(StrEnum):
    """
    任务优先级。

    用于任务队列排序和资源分配策略。
    数值越高越紧急。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AgentType(StrEnum):
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


class AgentStatus(StrEnum):
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


class ReportType(StrEnum):
    """
    报告类型枚举。

    支持自动生成的各类选品报告格式。
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ERPSystemType(StrEnum):
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


class RecommendationExecutionState(StrEnum):
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
    ERP_APPROVED = "erp_approved"
    ERP_REJECTED = "erp_rejected"
    ERP_DRAFT_CREATED = "erp_draft_created"
    ERP_PENDING_REVIEW = "erp_pending_review"
    SCM_REVIEWING = "scm_reviewing"
    SCM_APPROVED = "scm_approved"
    SCM_REJECTED = "scm_rejected"
    SCM_ORDERED = "scm_ordered"
    WMS_RESERVED = "wms_reserved"
    WMS_CONFIRMED = "wms_confirmed"
    OMS_DRAFT_CREATED = "oms_draft_created"
    OMS_PUBLISHED = "oms_published"
    OMS_ACTIVE = "oms_active"
    EXECUTED = "executed"
    PARTIALLY_EXECUTED = "partially_executed"
    EXECUTION_FAILED = "execution_failed"
    CLOSED = "closed"


class RecommendationCategory(StrEnum):
    """
    PMS建议类别。

    对应ERP 14域中PMS可输出的建议类型。
    """

    SELECTION = "selection"
    PRICING = "pricing"
    RESTOCK = "restock"
    AD_OPTIMIZATION = "ad_optimization"
    RISK_ALERT = "risk_alert"
    LISTING_DRAFT = "listing_draft"
    PURCHASE_DRAFT = "purchase_draft"
    INVENTORY_PREDICTION = "inventory_prediction"
    SENTIMENT_INSIGHT = "sentiment_insight"
    LOGISTICS_RISK = "logistics_risk"
    PROFIT_INSIGHT = "profit_insight"


class RecommendationPriority(StrEnum):
    """
    建议优先级。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DataCredibilityLevel(StrEnum):
    """
    数据可信等级。

    V9交叉验证新增：为每类数据源定义可信等级。
    """

    A = "a"
    B = "b"
    C = "c"
    D = "d"


class AIFeatureToggle(StrEnum):
    """
    AI功能开关枚举。

    按ERP域控制AI增强功能的启用/禁用。
    """

    AI_SELECTION = "ai_selection"
    AI_PRICING = "ai_pricing"
    AI_RESTOCK = "ai_restock"
    AI_AD_OPTIMIZATION = "ai_ad_optimization"
    AI_RISK_SCORING = "ai_risk_scoring"
    AI_SENTIMENT = "ai_sentiment"
    AI_INVENTORY_PREDICTION = "ai_inventory_prediction"
    AI_LOGISTICS_RISK = "ai_logistics_risk"
    AI_PROFIT_INSIGHT = "ai_profit_insight"


class ERPDomainType(StrEnum):
    """
    ERP 14域服务类型。

    对应 ERP 14域服务化拆分:
    - DASHBOARD: 工作台域 (AI看板)
    - IAM: 组织权限域
    - PDM: 产品开发域 (AI选品)
    - SOM: 销售运营域
    - ADS: 广告管理域 (AI优化)
    - OMS: 订单域 (AI风控)
    - SCM: 供应链域 (AI补货)
    - WMS: 仓储域 (AI预测)
    - FBA: FBA/海外仓域
    - TMS: 物流域
    - CRM: 客服售后域 (AI情感)
    - FMS: 财务域
    - BI: 商业智能域 (KPI)
    - SYS: 系统设置域
    """

    DASHBOARD = "dashboard"
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
    MS = "ms"


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
        RecommendationExecutionState.ERP_APPROVED,
        RecommendationExecutionState.ERP_REJECTED,
        RecommendationExecutionState.ERP_DRAFT_CREATED,
        RecommendationExecutionState.ERP_PENDING_REVIEW,
        RecommendationExecutionState.SCM_REVIEWING,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.ERP_APPROVED: {
        RecommendationExecutionState.SCM_REVIEWING,
        RecommendationExecutionState.EXECUTED,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.ERP_REJECTED: set(),
    RecommendationExecutionState.ERP_DRAFT_CREATED: {
        RecommendationExecutionState.ERP_PENDING_REVIEW,
        RecommendationExecutionState.EXECUTION_FAILED,
    },
    RecommendationExecutionState.ERP_PENDING_REVIEW: {
        RecommendationExecutionState.ERP_APPROVED,
        RecommendationExecutionState.ERP_REJECTED,
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
    RecommendationExecutionState.EXECUTED: {
        RecommendationExecutionState.CLOSED,
    },
    RecommendationExecutionState.PARTIALLY_EXECUTED: {
        RecommendationExecutionState.EXECUTED,
        RecommendationExecutionState.EXECUTION_FAILED,
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
