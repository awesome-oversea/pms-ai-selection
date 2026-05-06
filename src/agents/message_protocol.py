"""
多Agent消息协议
===============

定义Agent间通信的消息格式(D26-T064):
    - 消息类型与结构
    - 消息队列(内存实现)
    - 协议验证
    - 消息路由

使用方式:
    from src.agents.message_protocol import AgentMessage, MessageBus, MessageType

    bus = MessageBus()
    msg = AgentMessage.from_agent("DataCollector", "MarketAnalyst", {"data": {...}})
    await bus.send(msg)
    messages = await bus.receive("MarketAnalyst")
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class MessageType(StrEnum):
    """消息类型枚举。"""

    DATA_TRANSFER = "data_transfer"
    ANALYSIS_RESULT = "analysis_result"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"
    STATUS_UPDATE = "status_update"
    ERROR_REPORT = "error_report"
    CONTROL_COMMAND = "control_command"
    HEARTBEAT = "heartbeat"


class MessagePriority(StrEnum):
    """消息优先级。"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentMessage:
    """
    Agent间通信消息(D26-T064)。

    标准消息格式:
        {
            "type": "agent_message",
            "message_id": "msg_001",
            "from": "DataCollector",
            "to": "MarketAnalyst",
            "content": { ... },
            "message_type": "data_transfer",
            "priority": "normal",
            "timestamp": "2024-01-01T10:00:00Z",
            "correlation_id": "",
            "reply_to": "",
            "metadata": {}
        }

    Attributes:
        message_id: 消息唯一标识
        sender: 发送方Agent名称
        receiver: 接收方Agent名称("*"=广播)
        content: 消息载荷(任意JSON可序列化数据)
        message_type: 消息类型
        priority: 优先级
        timestamp: 发送时间戳
        correlation_id: 关联ID(用于请求-响应匹配)
        reply_to: 回复目标消息ID
        metadata: 扩展元数据
    """

    message_id: str = ""
    sender: str = ""
    receiver: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    message_type: MessageType = MessageType.DATA_TRANSFER
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: str = ""
    correlation_id: str = ""
    reply_to: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"msg_{uuid.uuid4().hex[:10]}"
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata or {})

    @classmethod
    def from_agent(
        cls,
        sender: str,
        receiver: str,
        content: dict[str, Any],
        message_type: MessageType = MessageType.DATA_TRANSFER,
        priority: MessagePriority = MessagePriority.NORMAL,
        correlation_id: str = "",
        reply_to: str = "",
        **metadata: Any,
    ) -> AgentMessage:
        """便捷方法: 从Agent创建消息。"""
        return cls(
            sender=sender,
            receiver=receiver,
            content=content,
            message_type=message_type,
            priority=priority,
            correlation_id=correlation_id,
            reply_to=reply_to,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "type": "agent_message",
            "message_id": self.message_id,
            "from": self.sender,
            "to": self.receiver,
            "content": self.content,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """序列化为JSON字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> AgentMessage:
        """从JSON字符串反序列化。"""
        data = json.loads(json_str)

        return cls(
            message_id=data.get("message_id", ""),
            sender=data.get("from", ""),
            receiver=data.get("to", ""),
            content=data.get("content", {}),
            message_type=MessageType(data.get("message_type", "data_transfer")),
            priority=MessagePriority(data.get("priority", "normal")),
            timestamp=data.get("timestamp", ""),
            correlation_id=data.get("correlation_id", ""),
            reply_to=data.get("reply_to", ""),
            metadata=data.get("metadata", {}),
        )

    def is_broadcast(self) -> bool:
        """是否为广播消息。"""
        return self.receiver == "*"

    def is_reply(self) -> bool:
        """是否为回复消息。"""
        return self.reply_to != ""

    def validate(self) -> tuple[bool, list[str]]:
        """
        验证消息格式合规性。

        Returns:
            (is_valid, errors): 是否有效 + 错误列表
        """
        errors = []

        if not self.sender:
            errors.append("sender不能为空")
        if not self.receiver:
            errors.append("receiver不能为空")
        if not isinstance(self.content, dict):
            errors.append("content必须是dict类型")

        try:
            json.dumps(self.content, default=str)
        except (TypeError, ValueError):
            errors.append("content无法JSON序列化")

        return len(errors) == 0, errors


@dataclass
class MessageBus:
    """
    消息总线(D26-T064)。

    提供Agent间消息传递的本地持久化实现:
        - send(): 发送消息到指定接收者或广播
        - receive(): 接收发送给指定Agent的消息
        - query(): 按条件查询历史消息
        - replay(): 按offset回放历史消息

    Attributes:
        _inbox: 各Agent收件箱 {receiver_name: [messages]}
        _history: 全部消息历史
        max_history: 最大保留历史条数
    """

    def __init__(self, max_history: int = 10000, persistence_path: str | Path | None = None):
        self._inbox: dict[str, list[AgentMessage]] = {}
        self._history: list[AgentMessage] = []
        self.max_history = max_history
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self._last_offset = 0
        self._load_persisted_history()

    def _load_persisted_history(self) -> None:
        if self.persistence_path is None or not self.persistence_path.exists():
            return
        try:
            loaded: list[AgentMessage] = []
            for raw in self.persistence_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    continue
                message = AgentMessage.from_json(line)
                offset = int((message.metadata or {}).get("bus_offset") or 0)
                if offset > self._last_offset:
                    self._last_offset = offset
                loaded.append(message)
            self._history = loaded[-self.max_history :]
        except Exception as exc:
            logger.warning("加载消息持久化日志失败: %s", exc)

    def _next_offset(self) -> int:
        self._last_offset += 1
        return self._last_offset

    def _append_persistence(self, message: AgentMessage) -> None:
        if self.persistence_path is None:
            return
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with self.persistence_path.open("a", encoding="utf-8") as fh:
                fh.write(message.to_json())
                fh.write("\n")
        except Exception as exc:
            logger.warning("写入消息持久化日志失败: %s", exc)

    @staticmethod
    def _sort_messages(messages: list[AgentMessage]) -> list[AgentMessage]:
        return sorted(
            messages,
            key=lambda m: (
                int((m.metadata or {}).get("bus_offset") or 0),
                m.timestamp,
                m.message_id,
            ),
        )

    @staticmethod
    def _offset_of(message: AgentMessage) -> int:
        return int((message.metadata or {}).get("bus_offset") or 0)

    @staticmethod
    def _extract_task_key(message: AgentMessage) -> str | None:
        metadata = message.metadata or {}
        content = message.content or {}
        for key in ("task_id", "selection_task_id", "workflow_task_id"):
            value = metadata.get(key)
            if value:
                return str(value)
            if isinstance(content, dict) and content.get(key):
                return str(content.get(key))
        if message.correlation_id:
            return str(message.correlation_id)
        return None

    def build_trace_summary(self, messages: list[AgentMessage] | None = None, *, limit: int = 10) -> dict[str, Any]:
        ordered = self._sort_messages(list(messages if messages is not None else self._history))
        offsets = [self._offset_of(message) for message in ordered]
        offset_monotonic = all(current < nxt for current, nxt in zip(offsets, offsets[1:], strict=False))
        offset_gaps = [
            {"expected": current + 1, "actual": nxt}
            for current, nxt in zip(offsets, offsets[1:], strict=False)
            if nxt > current + 1
        ]

        route_counts: dict[str, dict[str, Any]] = {}
        correlation_groups: dict[str, dict[str, Any]] = {}
        task_associations: dict[str, dict[str, Any]] = {}

        for message in ordered:
            offset = self._offset_of(message)
            route_key = f"{message.sender}->{message.receiver}"
            route_entry = route_counts.setdefault(
                route_key,
                {
                    "route": route_key,
                    "sender": message.sender,
                    "receiver": message.receiver,
                    "message_count": 0,
                    "last_offset": 0,
                },
            )
            route_entry["message_count"] += 1
            route_entry["last_offset"] = max(route_entry["last_offset"], offset)

            if message.correlation_id:
                correlation_entry = correlation_groups.setdefault(
                    message.correlation_id,
                    {
                        "correlation_id": message.correlation_id,
                        "message_count": 0,
                        "participants": set(),
                        "last_offset": 0,
                    },
                )
                correlation_entry["message_count"] += 1
                correlation_entry["participants"].update([message.sender, message.receiver])
                correlation_entry["last_offset"] = max(correlation_entry["last_offset"], offset)

            task_key = self._extract_task_key(message)
            if task_key:
                task_entry = task_associations.setdefault(
                    task_key,
                    {
                        "task_key": task_key,
                        "message_count": 0,
                        "participants": set(),
                        "last_offset": 0,
                    },
                )
                task_entry["message_count"] += 1
                task_entry["participants"].update([message.sender, message.receiver])
                task_entry["last_offset"] = max(task_entry["last_offset"], offset)

        def _serialize_group(entry: dict[str, Any], participant_key: str = "participants") -> dict[str, Any]:
            return {
                **entry,
                participant_key: sorted(entry.get(participant_key, set())),
            }

        recent_routes = sorted(
            route_counts.values(),
            key=lambda item: (-int(item["message_count"]), -int(item["last_offset"]), item["route"]),
        )[:limit]
        serialized_correlations = [
            _serialize_group(item)
            for item in sorted(
                correlation_groups.values(),
                key=lambda entry: (-int(entry["message_count"]), -int(entry["last_offset"]), entry["correlation_id"]),
            )[:limit]
        ]
        serialized_tasks = [
            _serialize_group(item)
            for item in sorted(
                task_associations.values(),
                key=lambda entry: (-int(entry["message_count"]), -int(entry["last_offset"]), entry["task_key"]),
            )[:limit]
        ]

        return {
            "trace_ready": True,
            "message_count": len(ordered),
            "offset_monotonic": offset_monotonic,
            "offset_gap_count": len(offset_gaps),
            "offset_gaps": offset_gaps[:limit],
            "first_offset": offsets[0] if offsets else 0,
            "last_offset": offsets[-1] if offsets else 0,
            "recent_routes": recent_routes,
            "correlation_groups": serialized_correlations,
            "task_associations": serialized_tasks,
        }

    async def send(self, message: AgentMessage) -> bool:
        """
        发送消息。

        如果是广播消息(receiver="*"), 则投递给所有已注册接收者。
        否则仅投递给指定接收者。
        """
        is_valid, errors = message.validate()
        if not is_valid:
            logger.error(f"❌ 消息验证失败: {errors}")
            return False

        message.metadata = dict(message.metadata or {})
        message.metadata.setdefault("bus_offset", self._next_offset())
        message.metadata.setdefault("persisted", self.persistence_path is not None)
        message.metadata.setdefault("persisted_at", datetime.now(UTC).isoformat())

        self._history.append(message)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history :]

        self._append_persistence(message)

        if message.is_broadcast():
            for inbox in self._inbox.values():
                inbox.append(message)
            logger.debug(f"📢 广播消息: {message.message_id} from {message.sender}")
        else:
            if message.receiver not in self._inbox:
                self._inbox[message.receiver] = []
            self._inbox[message.receiver].append(message)
            logger.debug(
                f"📩 投递消息: {message.message_id} "
                f"{message.sender} → {message.receiver} "
                f"[{message.message_type.value}]"
            )

        return True

    async def receive(
        self,
        receiver_name: str,
        message_type: MessageType | None = None,
        limit: int = 50,
    ) -> list[AgentMessage]:
        """
        接收消息。

        Args:
            receiver_name: 接收者Agent名称
            message_type: 可选过滤消息类型
            limit: 最大返回数量

        Returns:
            消息列表(按offset和时间正序)
        """
        messages = list(self._inbox.get(receiver_name, []))
        if message_type:
            messages = [m for m in messages if m.message_type == message_type]

        result = self._sort_messages(messages)[:limit]
        delivered_ids = {m.message_id for m in result}
        self._inbox[receiver_name] = [
            m for m in self._inbox.get(receiver_name, []) if m.message_id not in delivered_ids
        ]
        return result

    def register_receiver(self, name: str):
        """注册接收者(创建空收件箱)。"""
        if name not in self._inbox:
            self._inbox[name] = []

    def unregister_receiver(self, name: str):
        """注销接收者。"""
        self._inbox.pop(name, None)

    def query(
        self,
        sender: str | None = None,
        receiver: str | None = None,
        message_type: MessageType | None = None,
        since: str | None = None,
        after_offset: int = 0,
        limit: int = 100,
    ) -> list[AgentMessage]:
        """
        查询历史消息。

        支持按发送者/接收者/类型/时间范围/offset过滤。
        """
        result = list(self._history)

        if sender:
            result = [m for m in result if m.sender == sender]
        if receiver:
            result = [m for m in result if m.receiver == receiver or m.is_broadcast()]
        if message_type:
            result = [m for m in result if m.message_type == message_type]
        if since:
            result = [m for m in result if m.timestamp >= since]
        if after_offset > 0:
            result = [m for m in result if int((m.metadata or {}).get("bus_offset") or 0) > after_offset]

        return list(reversed(self._sort_messages(result)[-limit:]))

    def replay(
        self,
        *,
        receiver: str | None = None,
        sender: str | None = None,
        message_type: MessageType | None = None,
        after_offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        items = self.query(
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            after_offset=after_offset,
            limit=limit,
        )
        ordered = list(reversed(items))
        next_offset = max([after_offset] + [int((item.metadata or {}).get("bus_offset") or 0) for item in ordered])
        return {
            "items": ordered,
            "after_offset": after_offset,
            "next_offset": next_offset,
            "has_more": any(int((msg.metadata or {}).get("bus_offset") or 0) > next_offset for msg in self._history),
        }

    @property
    def stats(self) -> dict[str, Any]:
        """返回消息总线统计信息。"""
        type_counts: dict[str, int] = {}
        for msg in self._history:
            t = msg.message_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_messages": len(self._history),
            "registered_receivers": list(self._inbox.keys()),
            "pending_messages": sum(len(v) for v in self._inbox.values()),
            "by_type": type_counts,
            "persistence_enabled": self.persistence_path is not None,
            "persistence_path": str(self.persistence_path) if self.persistence_path is not None else None,
            "last_offset": self._last_offset,
            "trace_summary": self.build_trace_summary(),
        }


def create_message_bus(max_history: int = 10000, persistence_path: str | Path | None = None) -> MessageBus:
    """创建MessageBus工厂函数。"""
    return MessageBus(max_history=max_history, persistence_path=persistence_path)
