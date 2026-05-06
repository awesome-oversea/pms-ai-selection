"""
SQLAlchemy ORM数据模型
======================

定义系统中所有数据库持久化表结构(D7-T015/T016)。
所有模型继承自Base(DeclarativeBase)，支持:
    - 自动时间戳(created_at/updated_at)
    - 软删除(is_deleted)
    - UUID主键(id)
    - to_dict()序列化方法

核心表清单(50+表中的核心部分):
    用户与权限: User, Role, Permission, UserRole
    选品业务: Product, Competitor, SelectionTask, SelectionResult
    Agent系统: AgentRun, AgentStep, AgentMessage
    知识库: KnowledgeBase, Document, Chunk
    报告: Report, ReportSection
    ERP集成: ErpSyncLog, ErpConfig
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from src.models.base import Base
from src.models.enums import (
    AgentStatus,
    AgentType,
    ERPSystemType,
    ReportType,
    TaskPriority,
    TaskStatus,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_UUID_BIND_PROCESSOR = UUID.bind_processor
_UUID_RESULT_PROCESSOR = UUID.result_processor


def _uuid_bind_processor_sqlite(self, dialect):
    if dialect.name != "sqlite":
        return _UUID_BIND_PROCESSOR(self, dialect)

    def process(value):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    return process


def _uuid_result_processor_sqlite(self, dialect, coltype):
    if dialect.name != "sqlite":
        return _UUID_RESULT_PROCESSOR(self, dialect, coltype)

    def process(value):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))

    return process


UUID.bind_processor = _uuid_bind_processor_sqlite
UUID.result_processor = _uuid_result_processor_sqlite


class TimestampMixin:
    """
    时间戳混入类。

    为所有业务表提供created_at/updated_at自动管理，
    配合server_default和onupdate实现数据库级自动更新。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间",
    )


class SoftDeleteMixin:
    """
    软删除混入类。

    提供is_deleted标记，配合查询过滤器
    实现逻辑删除而非物理删除。
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="是否已软删除",
    )


class UUIDPrimaryKeyMixin:
    """
    UUID主键混入类。

    使用UUID作为主键，避免自增ID的分布式冲突问题，
    同时提升安全性(不可枚举)。
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="唯一标识(UUID)",
    )


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """租户表（Phase 5 最小基线）。"""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="租户名称"
    )
    tenant_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, comment="租户唯一键"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, comment="租户状态"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict, comment="租户配置"
    )


class TenantConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """租户配置表（Phase 5 最小基线）。"""

    __tablename__ = "tenant_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True, comment="租户ID"
    )
    config_key: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="配置键"
    )
    config_value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False, comment="配置值"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "config_key", name="uq_tenant_config_key"),
        Index("ix_tenant_config_tenant_active", "tenant_id", "is_active"),
    )


class TenantQuota(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """租户配额表（Phase 5 最小基线）。"""

    __tablename__ = "tenant_quotas"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True, comment="租户ID"
    )
    quota_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="配额类型"
    )
    limit_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="额度上限"
    )
    used_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已用额度"
    )
    reset_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly", comment="重置周期"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "quota_type", name="uq_tenant_quota_type"),
        Index("ix_tenant_quota_tenant_active", "tenant_id", "is_active"),
    )


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """用户表。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="登录用户名"
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True, comment="邮箱"
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="bcrypt哈希密码"
    )
    full_name: Mapped[str | None] = mapped_column(
        String(100), comment="真实姓名"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否激活"
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否超级管理员"
    )

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """角色表(RBAC)。"""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="角色名称"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="角色描述")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles"
    )
    users: Mapped[list["UserRole"]] = relationship(back_populates="role")


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """权限表。"""

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="权限标识"
    )
    description: Mapped[str | None] = mapped_column(String(255))
    resource: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="资源类型"
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="操作类型"
    )
    roles: Mapped[list["Role"]] = relationship(
        secondary="role_permissions", back_populates="permissions"
    )


class UserRole(Base):
    """用户-角色关联表(多对多)。"""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship(back_populates="users")


class RolePermission(Base):
    """角色-权限关联表(多对多)。"""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )

    role: Mapped["Role"] = relationship(overlaps="permissions,roles")
    permission: Mapped["Permission"] = relationship(overlaps="permissions,roles")


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """产品分类表。"""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="分类名称"
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), comment="父分类ID"
    )
    level: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="层级深度"
    )
    platform: Mapped[str | None] = mapped_column(
        String(20), comment="所属平台"
    )
    external_id: Mapped[str | None] = mapped_column(
        String(100), comment="平台原始分类ID"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序权重")

    parent: Mapped[Optional["Category"]] = relationship(
        remote_side="Category.id", backref="children"
    )
    products: Mapped[list["Product"]] = relationship(back_populates="category")

    __table_args__ = (
        Index("ix_category_platform_external", "platform", "external_id"),
    )


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """产品表(核心业务表)。"""

    __tablename__ = "products"

    name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="产品标题"
    )
    brand: Mapped[str | None] = mapped_column(
        String(200), index=True, comment="品牌名"
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), index=True
    )
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="来源平台"
    )
    external_product_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="平台产品ID"
    )
    asin: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True, comment="Amazon ASIN"
    )
    price: Mapped[float | None] = mapped_column(Float, comment="当前价格(USD)")
    original_price: Mapped[float | None] = mapped_column(
        Float, comment="原价(USD)"
    )
    currency: Mapped[str] = mapped_column(
        String(10), default="USD", comment="货币单位"
    )
    rating: Mapped[float | None] = mapped_column(
        Float, comment="评分(0-5)"
    )
    review_count: Mapped[int | None] = mapped_column(
        Integer, default=0, comment="评论数"
    )
    sales_rank: Mapped[int | None] = mapped_column(
        Integer, comment="销售排名(BSR)"
    )
    image_url: Mapped[str | None] = mapped_column(String(500))
    product_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(
        JSONB, comment="产品属性JSON"
    )
    specs: Mapped[dict | None] = mapped_column(
        JSONB, comment="技术规格JSON"
    )
    is_fba: Mapped[bool | None] = mapped_column(Boolean, comment="是否FBA")
    is_prime: Mapped[bool | None] = mapped_column(Boolean)

    category: Mapped[Optional["Category"]] = relationship(back_populates="products")
    competitors: Mapped[list["Competitor"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    selection_results: Mapped[list["SelectionResult"]] = relationship(
        back_populates="product"
    )

    __table_args__ = (
        UniqueConstraint("platform", "external_product_id", name="uq_platform_product"),
        Index("ix_product_price_range", "price"),
        Index("ix_product_rating_review", "rating", "review_count"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "brand": self.brand,
            "platform": self.platform,
            "asin": self.asin,
            "price": self.price,
            "rating": self.rating,
            "review_count": self.review_count,
            "sales_rank": self.sales_rank,
        }


class Competitor(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """竞品表。"""

    __tablename__ = "competitors"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    seller_name: Mapped[str] = mapped_column(String(200), comment="卖家名称")
    seller_id: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Float, comment="竞品价格")
    stock_status: Mapped[str | None] = mapped_column(
        String(20), comment="库存状态"
    )
    delivery_info: Mapped[str | None] = mapped_column(String(200))
    buy_box_percentage: Mapped[float | None] = mapped_column(
        Float, comment="购物车占有率(%)"
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB)

    product: Mapped["Product"] = relationship(back_populates="competitors")


class SelectionTask(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """选品任务表(核心业务流程表)。"""

    __tablename__ = "selection_tasks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    title: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="任务标题"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="任务描述")
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority), default=TaskPriority.MEDIUM, index=True
    )
    target_market: Mapped[str] = mapped_column(
        String(50), default="US", comment="目标市场"
    )
    target_category: Mapped[str | None] = mapped_column(
        String(200), comment="目标品类关键词"
    )
    budget_min: Mapped[float | None] = mapped_column(Float, comment="预算下限(USD)")
    budget_max: Mapped[float | None] = mapped_column(Float, comment="预算上限(USD)")
    expected_margin: Mapped[float | None] = mapped_column(
        Float, comment="期望利润率(%)"
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, comment="任务配置参数JSON"
    )
    result_summary: Mapped[str | None] = mapped_column(Text, comment="结果摘要")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), comment="创建者"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="selection_task", cascade="all, delete-orphan"
    )
    results: Mapped[list["SelectionResult"]] = relationship(
        back_populates="selection_task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_task_status_priority", "status", "priority"),
        Index("ix_task_status_created", "status", "created_at"),
        Index("ix_task_created_by", "created_by"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "status": self.status.value if self.status else None,
            "priority": self.priority.value if self.priority else None,
            "target_market": self.target_market,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SelectionResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """选品结果表。"""

    __tablename__ = "selection_results"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("selection_tasks.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, default=0, comment="推荐排名")
    overall_score: Mapped[float] = mapped_column(
        Float, comment="综合评分(0-100)"
    )
    market_score: Mapped[float | None] = mapped_column(Float, comment="市场潜力分")
    profit_score: Mapped[float | None] = mapped_column(Float, comment="利润空间分")
    competition_score: Mapped[float | None] = mapped_column(Float, comment="竞争程度分")
    trend_score: Mapped[float | None] = mapped_column(Float, comment="趋势热度分")
    reasoning: Mapped[str | None] = mapped_column(Text, comment="AI推荐理由")
    analysis_data: Mapped[dict | None] = mapped_column(
        JSONB, comment="详细分析数据JSON"
    )

    selection_task: Mapped["SelectionTask"] = relationship(back_populates="results")
    product: Mapped["Product"] = relationship(back_populates="selection_results")

    __table_args__ = (
        UniqueConstraint("task_id", "product_id", name="uq_task_product_result"),
        Index("ix_result_score", "overall_score"),
    )


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Agent运行记录表。"""

    __tablename__ = "agent_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("selection_tasks.id"), index=True
    )
    agent_type: Mapped[AgentType] = mapped_column(
        SAEnum(AgentType), nullable=False, index=True, comment="Agent类型"
    )
    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus), default=AgentStatus.IDLE, index=True
    )
    input_data: Mapped[dict | None] = mapped_column(
        JSONB, comment="Agent输入参数"
    )
    output_data: Mapped[dict | None] = mapped_column(
        JSONB, comment="Agent输出结果"
    )
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    model_used: Mapped[str | None] = mapped_column(
        String(100), comment="使用的LLM模型"
    )
    token_usage_input: Mapped[int | None] = mapped_column(Integer, default=0)
    token_usage_output: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float, comment="耗时(秒)")
    cost_usd: Mapped[float | None] = mapped_column(Float, comment="API调用成本(USD)")

    selection_task: Mapped[Optional["SelectionTask"]] = relationship(
        back_populates="agent_runs"
    )
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_agent_run_task_type", "task_id", "agent_type"),
        Index("ix_agent_run_status_time", "status", "created_at"),
    )


class AgentStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Agent步骤记录表。"""

    __tablename__ = "agent_steps"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    step_type: Mapped[str] = mapped_column(
        String(50), index=True, comment="步骤类型"
    )
    step_name: Mapped[str] = mapped_column(String(200), comment="步骤名称")
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="步骤状态"
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer, comment="耗时(毫秒)")

    agent_run: Mapped["AgentRun"] = relationship(back_populates="steps")


class AgentMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Agent消息记录表。"""

    __tablename__ = "agent_messages"

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), index=True
    )
    sender_type: Mapped[str] = mapped_column(String(50), comment="发送者类型(agent/human/system)")
    sender_id: Mapped[str] = mapped_column(String(100), comment="发送者ID")
    receiver_type: Mapped[str | None] = mapped_column(String(50), comment="接收者类型")
    receiver_id: Mapped[str | None] = mapped_column(String(100), comment="接收者ID")
    message_type: Mapped[str] = mapped_column(
        String(30), index=True, comment="消息类型(request/response/event)"
    )
    content: Mapped[dict] = mapped_column(JSONB, comment="消息内容JSON")
    extra_data: Mapped[dict | None] = mapped_column(JSONB, comment="元数据")

    run: Mapped[Optional["AgentRun"]] = relationship(back_populates="messages")


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """知识库表。"""

    __tablename__ = "knowledge_bases"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="知识库名称"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="描述")
    kb_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="product", comment="知识库类型(product/market/competitor)"
    )
    collection_name: Mapped[str | None] = mapped_column(
        String(200), comment="向量库集合名称"
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100), comment="Embedding模型名称"
    )
    chunk_size: Mapped[int | None] = mapped_column(
        Integer, default=512, comment="分块大小"
    )
    chunk_overlap: Mapped[int | None] = mapped_column(
        Integer, default=50, comment="分块重叠"
    )
    config: Mapped[dict | None] = mapped_column(JSONB, comment="配置参数")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_base_tenant_name", "tenant_id", "name"),
    )


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """文档表。"""

    __tablename__ = "documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="文档标题"
    )
    doc_type: Mapped[str] = mapped_column(
        String(50), comment="文档类型(pdf/docx/txt/html)"
    )
    file_path: Mapped[str | None] = mapped_column(String(500), comment="文件路径")
    file_size: Mapped[int | None] = mapped_column(Integer, comment="文件大小(字节)")
    content_hash: Mapped[str | None] = mapped_column(
        String(64), comment="内容SHA256哈希"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="处理状态"
    )
    chunk_count: Mapped[int | None] = mapped_column(
        Integer, default=0, comment="分段数量"
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB, comment="元数据")

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_document_tenant_status_created", "tenant_id", "status", "created_at"),
    )


class Chunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """文档分段表。"""

    __tablename__ = "document_chunks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="分段内容")
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="分段索引"
    )
    vector_id: Mapped[str | None] = mapped_column(
        String(100), comment="向量数据库ID"
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB, comment="元数据")

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_tenant_document_index", "tenant_id", "document_id", "chunk_index"),
    )


# 向后兼容别名 — 部分测试/文档使用 DocumentChunk 指代 Chunk
DocumentChunk = Chunk


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """报告表。"""

    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="报告标题"
    )
    report_type: Mapped[ReportType] = mapped_column(
        SAEnum(ReportType), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("selection_tasks.id"), index=True
    )
    content: Mapped[dict | None] = mapped_column(JSONB, comment="报告内容JSON")
    file_path: Mapped[str | None] = mapped_column(String(500), comment="文件路径")
    status: Mapped[str] = mapped_column(
        String(20), default="draft", comment="状态(draft/published)"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    sections: Mapped[list["ReportSection"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class ReportSection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """报告章节表。"""

    __tablename__ = "report_sections"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), comment="章节标题")
    content: Mapped[str] = mapped_column(Text, comment="章节内容")
    section_order: Mapped[int] = mapped_column(
        Integer, default=0, comment="章节顺序"
    )
    section_type: Mapped[str] = mapped_column(
        String(50), comment="章节类型(text/table/chart/image)"
    )
    extra_data: Mapped[dict | None] = mapped_column(JSONB, comment="元数据")

    report: Mapped["Report"] = relationship(back_populates="sections")


class ErpConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ERP配置表。"""

    __tablename__ = "erp_configs"

    system_type: Mapped[ERPSystemType] = mapped_column(
        SAEnum(ERPSystemType), nullable=False, comment="ERP系统类型"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="配置名称"
    )
    api_endpoint: Mapped[str | None] = mapped_column(
        String(500), comment="API端点"
    )
    api_key: Mapped[str | None] = mapped_column(String(255), comment="API密钥")
    secret_key: Mapped[str | None] = mapped_column(String(255), comment="密钥")
    extra_config: Mapped[dict | None] = mapped_column(JSONB, comment="额外配置")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最后同步时间"
    )


class ErpSyncLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """ERP同步日志表。"""

    __tablename__ = "erp_sync_logs"

    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_configs.id"), nullable=False, index=True
    )
    sync_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="同步类型(import/export)"
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), comment="实体类型(product/order/inventory)"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="状态"
    )
    items_total: Mapped[int] = mapped_column(
        Integer, default=0, comment="总条目数"
    )
    items_success: Mapped[int] = mapped_column(
        Integer, default=0, comment="成功条目数"
    )
    items_failed: Mapped[int] = mapped_column(
        Integer, default=0, comment="失败条目数"
    )
    error_detail: Mapped[str | None] = mapped_column(Text, comment="错误详情")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float, comment="耗时(秒)")


class DataSyncEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """数据同步事件/outbox 样板表。"""

    __tablename__ = "data_sync_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="实体类型")
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="事件类型")
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="聚合ID")
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="Kafka Topic")
    event_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, comment="事件幂等键")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="事件载荷")
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True, comment="pending/sent/failed/dead_letter")
    source: Mapped[str] = mapped_column(String(30), default="outbox", nullable=False, comment="来源")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="重试次数")
    last_error: Mapped[str | None] = mapped_column(Text, comment="最近一次错误")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="成功发布时间")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近尝试时间")

    __table_args__ = (
        Index("ix_sync_event_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_sync_event_tenant_topic_created", "tenant_id", "topic", "created_at"),
    )


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """审计日志表。"""

    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="租户ID"
    )
    user_id: Mapped[str | None] = mapped_column(String(100), index=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="用户名")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否超级管理员")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="操作标识")
    target_type: Mapped[str | None] = mapped_column(String(100), index=True, comment="目标资源类型")
    target_id: Mapped[str | None] = mapped_column(String(100), index=True, comment="目标资源ID")
    result: Mapped[str] = mapped_column(String(30), nullable=False, index=True, comment="操作结果")
    detail: Mapped[dict | None] = mapped_column(JSONB, comment="附加详情")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True, comment="事件发生时间"
    )

    __table_args__ = (
        Index("ix_audit_tenant_action_time", "tenant_id", "action", "occurred_at"),
        Index("ix_audit_tenant_user_time", "tenant_id", "username", "occurred_at"),
        Index("ix_audit_tenant_target_time", "tenant_id", "target_type", "target_id", "occurred_at"),
    )
