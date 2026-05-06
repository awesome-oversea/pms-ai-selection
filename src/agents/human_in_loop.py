"""
人机协作(Human-in-the-Loop)模块
=============================

提供人工审批与介入能力(D25-T060):
    - 审批节点定义
    - WebSocket通知机制
    - 审批记录存储
    - 状态可视化

使用方式:
    from src.agents.human_in_loop import ApprovalNode, HumanInLoopManager

    manager = HumanInLoopManager()
    approval = await manager.request_approval(
        session_id="sess_001",
        agent_name="MarketInsight",
        action="proceed_to_product_planning",
        context={"score": 78.5, "recommendation": "strong_recommend"},
    )
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class ApprovalStatus(StrEnum):
    """审批状态枚举。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalType(StrEnum):
    """审批类型枚举。"""

    PHASE_TRANSITION = "phase_transition"
    DATA_REVIEW = "data_review"
    GO_NO_GO = "go_no_go"
    BUDGET_EXCEED = "budget_exceed"
    RISK_THRESHOLD = "risk_threshold"


@dataclass
class ApprovalRequest:
    """
    审批请求(D25-T060)。

    Attributes:
        request_id: 请求唯一标识
        session_id: 关联的选品会话ID
        agent_name: 发起审批的Agent名称
        approval_type: 审批类型
        action: 待审批的操作描述
        context: 审批上下文数据
        status: 当前状态
        created_at: 创建时间
        expires_at: 过期时间(默认30分钟)
        reviewed_by: 审批人
        reviewed_at: 审批时间
        comment: 审批意见
    """

    request_id: str = ""
    session_id: str = ""
    agent_name: str = ""
    approval_type: ApprovalType = ApprovalType.PHASE_TRANSITION
    action: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = ""
    expires_at: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    comment: str = ""

    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"apr_{uuid.uuid4().hex[:10]}"
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if not self.expires_at:
            from datetime import timedelta
            self.expires_at = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "approval_type": self.approval_type.value,
            "action": self.action,
            "context": self.context,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "comment": self.comment,
        }

    def approve(self, reviewer: str = "system", comment: str = ""):
        """批准该请求。"""
        self.status = ApprovalStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = datetime.now(UTC).isoformat()
        self.comment = comment

    def reject(self, reviewer: str = "system", comment: str = ""):
        """拒绝该请求。"""
        self.status = ApprovalStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = datetime.now(UTC).isoformat()
        self.comment = comment


@dataclass
class ApprovalConfig:
    """
    审批配置。

    定义哪些操作需要人工介入:
        - auto_approve_threshold: 自动批准阈值(低于此分数自动通过)
        - require_approval_types: 需要人工审批的类型列表
        - timeout_minutes: 审批超时时间
        - default_reviewer: 默认审批人
        - on_auto_approve: 自动批准回调
        - on_auto_reject: 自动拒绝回调
    """

    auto_approve_threshold: float = 85.0
    require_approval_types: list[ApprovalType] = field(default_factory=lambda: [
        ApprovalType.GO_NO_GO,
        ApprovalType.BUDGET_EXCEED,
        ApprovalType.RISK_THRESHOLD,
    ])
    timeout_minutes: int = 30
    default_reviewer: str = "product_manager"
    on_auto_approve: Callable | None = None
    on_auto_reject: Callable | None = None


class HumanInLoopManager:
    """
    人机协作管理器(D25-T060)。

    功能:
        1. 审批请求创建与管理
        2. 自动批准/拒绝(基于阈值)
        3. 超时处理
        4. 审批记录查询
        5. WebSocket通知模拟

    Attributes:
        config: 审批配置
        _pending_requests: 待处理请求字典
        _history: 历史记录列表
    """

    def __init__(self, config: ApprovalConfig | None = None):
        self.config = config or ApprovalConfig()
        self._pending_requests: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []

    async def request_approval(
        self,
        session_id: str,
        agent_name: str,
        action: str,
        approval_type: ApprovalType = ApprovalType.PHASE_TRANSITION,
        context: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """
        发起审批请求。

        如果满足自动批准条件，则直接返回已批准的请求。
        否则进入待审批队列等待人工处理。
        """
        request = ApprovalRequest(
            session_id=session_id,
            agent_name=agent_name,
            approval_type=approval_type,
            action=action,
            context=context or {},
        )

        score = context.get("score", 0) if context else 0

        should_auto_approve = (
            approval_type not in self.config.require_approval_types
            and score >= self.config.auto_approve_threshold
        )

        should_auto_reject = (
            approval_type in [ApprovalType.RISK_THRESHOLD]
            and score < 20
        )

        if should_auto_approve:
            request.approve(reviewer="auto_system", comment=f"自动批准(评分{score}>=阈值{self.config.auto_approve_threshold})")

            if self.config.on_auto_approve:
                try:
                    self.config.on_auto_approve(request)
                except Exception as e:
                    logger.warning(f"自动批准回调失败: {e}")

        elif should_auto_reject:
            request.reject(reviewer="auto_system", comment=f"自动拒绝(风险评分{score}<20)")

            if self.config.on_auto_reject:
                try:
                    self.config.on_auto_reject(request)
                except Exception as e:
                    logger.warning(f"自动拒绝回调失败: {e}")

        else:
            self._pending_requests[request.request_id] = request
            logger.info(f"📋 审批请求已提交: {request.request_id} ({agent_name}: {action})")

        self._history.append(request)

        return request

    async def approve_request(self, request_id: str, reviewer: str = "", comment: str = "") -> bool:
        """人工批准请求。"""
        request = self._pending_requests.get(request_id)
        if not request or request.status != ApprovalStatus.PENDING:
            return False

        request.approve(reviewer or self.config.default_reviewer, comment)
        del self._pending_requests[request_id]

        logger.info(f"✅ 审批通过: {request_id} by {reviewer}")
        return True

    async def reject_request(self, request_id: str, reviewer: str = "", comment: str = "") -> bool:
        """人工拒绝请求。"""
        request = self._pending_requests.get(request_id)
        if not request or request.status != ApprovalStatus.PENDING:
            return False

        request.reject(reviewer or self.config.default_reviewer, comment)
        del self._pending_requests[request_id]

        logger.info(f"❌ 审批拒绝: {request_id} by {reviewer}")
        return True

    def get_pending_requests(self) -> list[ApprovalRequest]:
        """获取所有待审批请求。"""
        return list(self._pending_requests.values())

    def get_request_history(self, session_id: str | None = None) -> list[dict]:
        """获取审批历史记录。"""
        history = self._history

        if session_id:
            history = [r for r in history if r.session_id == session_id]

        return [r.to_dict() for r in history]

    async def check_expired(self) -> list[ApprovalRequest]:
        """检查并处理过期请求。"""
        now = datetime.now(UTC)
        expired = []

        for req_id, req in list(self._pending_requests.items()):
            try:
                exp_time = datetime.fromisoformat(req.expires_at.replace("Z", "+00:00"))
                if now > exp_time:
                    req.status = ApprovalStatus.EXPIRED
                    expired.append(req)
                    del self._pending_requests[req_id]
                    logger.warning(f"⏰ 审批请求过期: {req_id}")
            except (ValueError, TypeError):
                continue

        return expired

    @property
    def stats(self) -> dict[str, Any]:
        """返回审批统计信息。"""
        total = len(self._history)
        approved = sum(1 for r in self._history if r.status == ApprovalStatus.APPROVED)
        rejected = sum(1 for r in self._history if r.status == ApprovalStatus.REJECTED)
        pending = len(self._pending_requests)

        return {
            "total_requests": total,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "approval_rate": f"{(approved / max(total, 1)) * 100:.1f}%" if total > 0 else "N/A",
        }


def create_human_in_loop_manager(config: ApprovalConfig | None = None) -> HumanInLoopManager:
    """创建HumanInLoopManager工厂函数。"""
    return HumanInLoopManager(config=config)
