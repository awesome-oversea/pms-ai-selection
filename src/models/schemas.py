"""
Pydantic API Schema定义
=======================

定义所有API请求/响应的数据验证模型。
与ORM模型分离，负责:
    - 请求参数校验(输入)
    - 响应序列化(输出)
    - OpenAPI文档自动生成

Schema命名规范:
    - XxxCreate: 创建请求体
    - XxxUpdate: 更新请求体
    - XxxResponse: 完整响应
    - XxxList: 列表项(精简版)
"""

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class HealthCheckResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(description="健康状态: healthy/unhealthy")
    service: str = Field(default="pms-ai-selection")
    version: str = Field(default="0.1.0")
    timestamp: str | None = None


class ReadinessResponse(BaseModel):
    """就绪探针响应。"""

    status: str = Field(description="ready/not_ready")
    timestamp: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)


# ============================================================
# 用户相关 Schema
# ============================================================


class UserBase(BaseModel):
    """用户基础字段。"""

    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    full_name: str | None = Field(None, max_length=100)


class UserCreate(UserBase):
    """创建用户请求。"""

    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含至少一个数字")
        if not any(c.isalpha() for c in v):
            raise ValueError("密码必须包含至少一个字母")
        return v


class UserUpdate(BaseModel):
    """更新用户请求(全部可选)。"""

    email: str | None = Field(None, max_length=255)
    full_name: str | None = Field(None, max_length=100)
    is_active: bool | None = None


class UserResponse(UserBase):
    """用户信息响应。"""

    id: UUID
    tenant_id: UUID | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT Token响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str | None = None
    tenant_key: str | None = None
    tenant_name: str | None = None
    expires_in: int = Field(default=900, description="Access Token过期时间(秒)")


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str
    password: str


# ============================================================
# 选品任务 Schema
# ============================================================


class SelectionTaskBase(BaseModel):
    """选品任务基础字段。"""

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    target_market: str = Field(default="US", max_length=50)
    target_category: str | None = Field(None, max_length=200)
    budget_min: float | None = Field(None, ge=0)
    budget_max: float | None = Field(None, ge=0)
    expected_margin: float | None = Field(None, ge=0, le=100)


class SelectionTaskCreate(SelectionTaskBase):
    """创建选品任务请求。"""

    priority: str = Field(default="medium", description="low/medium/high/urgent")
    config: dict[str, Any] | None = None


class SelectionTaskUpdate(BaseModel):
    """更新选品任务请求。"""

    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    config: dict[str, Any] | None = None


class SelectionTaskResponse(SelectionTaskBase):
    """选品任务详情响应。"""

    id: UUID
    status: str = "pending"
    priority: str = "medium"
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class SelectionTaskList(BaseModel):
    """选品任务列表项(精简)。"""

    id: UUID
    title: str
    status: str
    priority: str
    target_market: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SelectionTaskRunCreate(BaseModel):
    """创建选品运行任务请求。"""

    query: str = Field(min_length=2, max_length=500, description="选品查询关键词")
    category: str | None = Field(None, description="产品类目")
    investment_budget: float | None = Field(50000.0, ge=0, description="投资预算(USD)")
    target_market: str | None = Field("US", description="目标市场")
    auto_approve: bool = Field(False, description="是否自动审批")
    priority: str = Field("normal", description="任务优先级: low/normal/high")


class SelectionTaskRunResponse(BaseModel):
    """创建选品运行任务响应。"""

    task_id: str
    query: str
    status: str
    phase: str
    created_at: str
    message: str


class SelectionTaskRunDetail(BaseModel):
    """选品运行任务详情。"""

    task_id: str
    session_id: str
    tenant_id: str | None = None
    query: str
    category: str | None = None
    target_market: str | None = None
    investment_budget: float | None = None
    status: str
    phase: str
    priority: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    result_summary: str | None = None
    error: str | None = None
    status_reason: str | None = None
    status_history: list[dict[str, Any]] = Field(default_factory=list)
    approval: dict[str, Any] | None = None
    approval_history: list[dict[str, Any]] = Field(default_factory=list)
    adoption: dict[str, Any] | None = None
    retry_count: int = 0
    max_retries: int | None = None
    timed_out: bool = False
    dead_letter: bool = False
    dead_letter_reason: str | None = None
    go_no_go: Any | None = None
    go_no_go_decision: str | None = None
    decision_output: dict[str, Any] | None = None
    signal_governance_status: str | None = None
    signal_governance_summary: dict[str, Any] | None = None
    data_source_governance: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class SelectionTaskRunListResponse(BaseModel):
    """选品运行任务列表响应。"""

    total: int
    tasks: list[SelectionTaskRunDetail]


class SelectionTaskRunResultResponse(BaseModel):
    """选品运行任务结果响应。"""

    task_id: str
    query: str
    status: str
    result: dict[str, Any] | None = None
    result_summary: str | None = None
    go_no_go: Any | None = None
    go_no_go_decision: str | None = None
    decision_output: dict[str, Any] | None = None
    signal_governance_status: str | None = None
    signal_governance_summary: dict[str, Any] | None = None
    data_source_governance: dict[str, Any] | None = None
    similar_history_cases: dict[str, Any] | None = None
    review_cases: dict[str, Any] | None = None
    historical_performance: dict[str, Any] | None = None
    completed_at: str | None = None


class SelectionTaskApprovalAction(BaseModel):
    """选品运行任务审批动作。"""

    action: str = Field(..., description="审批动作: submit/approve/reject")
    comment: str | None = Field(None, description="审批意见")
    reviewer: str | None = Field(None, description="审批人")
    stage: str | None = Field(None, description="审批阶段，如 operator_review/procurement_review/manager_review")
    stage_order: int | None = Field(None, ge=1, le=20, description="审批阶段序号")
    notify_channels: list[str] = Field(default_factory=list, description="通知渠道，如 dingtalk/wechat/email")
    webhook_url: str | None = Field(None, description="审批通知 Webhook 地址")


class SelectionTaskFeedbackCreate(BaseModel):
    """选品任务反馈录入。"""

    source: str = Field(..., min_length=1, description="反馈来源，如 crm/review/after_sale")
    rating: float | None = Field(None, ge=0, le=5, description="反馈评分")
    sentiment: str | None = Field(None, description="情感倾向: positive/neutral/negative")
    tags: list[str] = Field(default_factory=list, description="反馈标签")
    comment: str | None = Field(None, description="反馈内容")


class SelectionTaskRescoreRequest(BaseModel):
    """选品任务执行后回流再评分请求。"""

    sales_7d: int = Field(default=0, ge=0, description="近 7 天销量")
    review_rating: float | None = Field(default=None, ge=0, le=5, description="执行后评价均分")
    review_count: int = Field(default=0, ge=0, description="执行后评价数")
    gross_profit: float = Field(default=0.0, description="执行后毛利润")
    margin_rate: float | None = Field(default=None, ge=0, le=1, description="执行后毛利率，0-1")
    available_inventory: int = Field(default=0, ge=0, description="当前可用库存")
    stockout_risk: bool = Field(default=False, description="是否存在缺货风险")
    source: str = Field(default="close_loop", min_length=1, description="回流来源")
    notes: str | None = Field(default=None, description="补充说明")


class SelectionTaskAdoptionRequest(BaseModel):
    """选品任务采纳推荐并生成采购建议请求。"""

    scm_name: str = Field(default="default", min_length=1, description="SCM 配置名称")
    quantity: int = Field(default=200, ge=1, le=100000, description="建议采购数量")
    supplier_code: str | None = Field(default=None, description="指定供应商编码；为空则自动选择")
    notes: str | None = Field(default=None, description="采纳说明")


class SelectionTaskRejectionRequest(BaseModel):
    """选品任务拒绝推荐并记录模型反馈请求。"""

    reason: str = Field(..., min_length=2, max_length=500, description="拒绝原因")
    feedback_tags: list[str] = Field(default_factory=list, description="用于模型反馈的标签")
    notes: str | None = Field(default=None, description="补充说明")


# ============================================================
# 产品 Schema
# ============================================================


class ProductBase(BaseModel):
    """产品基础字段。"""

    name: str = Field(max_length=500)
    brand: str | None = Field(None, max_length=200)
    platform: str = Field(max_length=20)
    external_product_id: str = Field(max_length=100)
    asin: str | None = Field(None, max_length=20)
    price: float | None = Field(None, ge=0)
    rating: float | None = Field(None, ge=0, le=5)
    review_count: int | None = Field(None, ge=0)
    sales_rank: int | None = Field(None, ge=0)
    image_url: str | None = Field(None, max_length=500)
    product_url: str | None = Field(None, max_length=500)
    attributes: dict[str, Any] | None = None


class ProductCreate(ProductBase):
    """创建产品请求(批量导入)。"""

    pass


class ProductResponse(ProductBase):
    """产品详情响应。"""

    id: UUID
    category_id: UUID | None = None
    currency: str = "USD"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductList(BaseModel):
    """产品列表项(精简)。"""

    id: UUID
    name: str
    platform: str
    price: float | None
    rating: float | None
    review_count: int | None

    model_config = {"from_attributes": True}


# ============================================================
# 选品结果 Schema
# ============================================================


class SelectionResultBase(BaseModel):
    """选品结果基础字段。"""

    rank: int = Field(ge=0)
    overall_score: float = Field(ge=0, le=100)
    market_score: float | None = Field(None, ge=0, le=100)
    profit_score: float | None = Field(None, ge=0, le=100)
    competition_score: float | None = Field(None, ge=0, le=100)
    trend_score: float | None = Field(None, ge=0, le=100)
    reasoning: str | None = None


class SelectionResultResponse(SelectionResultBase):
    """选品结果详情响应。"""

    id: UUID
    task_id: UUID
    product_id: UUID
    product: ProductList | None = None
    analysis_data: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ============================================================
# Agent运行 Schema
# ============================================================


class AgentRunBase(BaseModel):
    """Agent运行记录基础字段。"""

    agent_type: str = Field(description="data_collector/market_insight/product_planner/commercialization")
    status: str = Field(default="idle")
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    duration_seconds: float | None = Field(None, ge=0)
    cost_usd: float | None = Field(None, ge=0)


class AgentRunResponse(AgentRunBase):
    """Agent运行详情响应。"""

    id: UUID
    task_id: UUID | None = None
    model_used: str | None = None
    token_usage_input: int | None = None
    token_usage_output: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ============================================================
# 知识库 Schema (RAG)
# ============================================================


class KnowledgeBaseBase(BaseModel):
    """知识库基础字段。"""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    collection_name: str = Field(max_length=100)
    embedding_model: str = Field(default="bge-large-zh")
    chunk_size: int = Field(default=512, ge=100, le=4096)
    chunk_overlap: int = Field(default=50, ge=0, le=500)


class KnowledgeBaseCreate(KnowledgeBaseBase):
    """创建知识库请求。"""

    pass


class KnowledgeBaseResponse(KnowledgeBaseBase):
    """知识库详情响应。"""

    id: UUID
    document_count: int = 0
    vector_count: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """文档上传响应。"""

    document_id: UUID
    filename: str
    file_size: int
    status: str = "pending"
    chunk_count: int = 0


# ============================================================
# 报告 Schema
# ============================================================


class ReportBase(BaseModel):
    """报告基础字段。"""

    title: str = Field(min_length=1, max_length=300)
    report_type: str = Field(default="custom", description="daily/weekly/monthly/custom")
    content: str | None = None
    task_id: UUID | None = None


class ReportCreate(ReportBase):
    """创建报告请求。"""

    pass


class ReportResponse(ReportBase):
    """报告详情响应。"""

    id: UUID
    generated_by: UUID | None = None
    status: str = "draft"
    view_count: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ============================================================
# 通用分页 Schema
# ============================================================


class PaginationParams(BaseModel):
    """分页查询参数。"""

    page: int = Field(default=1, ge=1, description="页码(从1开始)")
    page_size: int = Field(
        default=20, ge=1, le=100, description="每页数量"
    )
    sort_by: str | None = Field(None, description="排序字段")
    sort_order: str | None = Field(
        default="desc", pattern="^(asc|desc)$", description="排序方向"
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    通用分页响应模板。

    使用泛型支持任意数据类型的分页返回。

    Type Parameters:
        T: 列表项类型(如ProductList/SelectionTaskList)
    """

    items: list[T] = Field(description="当前页数据列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
    total_pages: int = Field(description="总页数")

    @classmethod
    def create(cls, items: list, total: int, page: int, page_size: int) -> "PaginatedResponse":
        from math import ceil

        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if total > 0 else 0,
        )


# ============================================================
# 错误响应 Schema
# ============================================================


class ErrorResponse(BaseModel):
    """统一错误响应格式。"""

    error_code: str = Field(description="错误码(E001/AUTH_001等)")
    message: str = Field(description="人类可读的错误描述")
    detail: dict[str, Any] = Field(default_factory=dict, description="额外详细信息")


class ValidationErrorDetail(BaseModel):
    """字段级校验错误详情。"""

    field: str
    message: str
    value: Any = None
