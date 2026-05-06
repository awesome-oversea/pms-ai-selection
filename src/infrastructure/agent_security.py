"""
Agent增强 + 性能测试 + 安全审计
================================

提供Agent能力增强、性能测试、安全审计能力(D81-D85):
    - 多轮对话记忆管理
    - 性能压测工具
    - 安全审计日志
    - 监控告警规则

使用方式:
    from src.infrastructure.agent_security import (
        ConversationMemory, PerformanceTester, SecurityAuditor, AlertManager
    )

    memory = ConversationMemory()
    memory.add_message("user", "查询储能电源")

    tester = PerformanceTester()
    result = await tester.run_test("api", concurrency=100)

    auditor = SecurityAuditor()
    auditor.log_event("login", user_id="U001", ip="192.168.1.1")
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class MessageRole(StrEnum):
    """消息角色。"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AlertSeverity(StrEnum):
    """告警严重程度。"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AuditEventType(StrEnum):
    """审计事件类型。"""
    LOGIN = "login"
    LOGOUT = "logout"
    API_CALL = "api_call"
    DATA_ACCESS = "data_access"
    CONFIG_CHANGE = "config_change"
    SECURITY_EVENT = "security_event"


@dataclass
class ConversationMessage:
    """对话消息。"""
    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ConversationSession:
    """对话会话。"""
    session_id: str
    user_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": [m.to_dict() for m in self.messages],
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PerformanceResult:
    """性能测试结果。"""
    test_id: str
    test_type: str
    concurrency: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    tps: float
    duration_seconds: float
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_type": self.test_type,
            "concurrency": self.concurrency,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "tps": round(self.tps, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "errors": self.errors[:10],
        }


@dataclass
class AuditEvent:
    """审计事件。"""
    event_id: str
    event_type: AuditEventType
    user_id: str | None
    ip_address: str | None
    resource: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    risk_level: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "resource": self.resource,
            "action": self.action,
            "details": self.details,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
        }


@dataclass
class Alert:
    """告警。"""
    alert_id: str
    name: str
    severity: AlertSeverity
    condition: str
    current_value: float
    threshold: float
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "severity": self.severity.value,
            "condition": self.condition,
            "current_value": round(self.current_value, 2),
            "threshold": self.threshold,
            "message": self.message,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
        }


class ConversationMemory:
    """
    对话记忆管理器(D81)。

    功能:
        1. 多轮对话历史管理
        2. 上下文记忆(Redis模拟)
        3. 用户偏好存储
        4. 长期记忆(向量存储模拟)
    """

    MAX_HISTORY = 50

    def __init__(self):
        self._sessions: dict[str, ConversationSession] = {}
        self._user_preferences: dict[str, dict[str, Any]] = defaultdict(dict)
        self._long_term_memory: dict[str, list[dict]] = defaultdict(list)
        self._stats = {
            "total_sessions": 0,
            "total_messages": 0,
            "active_sessions": 0,
        }
        logger.info("ConversationMemory初始化完成")

    async def create_session(self, user_id: str, context: dict | None = None) -> ConversationSession:
        """创建对话会话。"""
        session_id = f"SESS_{uuid.uuid4().hex[:8].upper()}"
        session = ConversationSession(
            session_id=session_id,
            user_id=user_id,
            context=context or {},
        )
        self._sessions[session_id] = session
        self._stats["total_sessions"] += 1
        self._stats["active_sessions"] = len(self._sessions)
        logger.info(f"创建会话: {session_id} for user {user_id}")
        return session

    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationMessage | None:
        """添加消息。"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        message = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        session.messages.append(message)
        session.updated_at = datetime.now(UTC).isoformat()

        if len(session.messages) > self.MAX_HISTORY:
            session.messages = session.messages[-self.MAX_HISTORY :]

        self._stats["total_messages"] += 1
        return message

    async def get_history(self, session_id: str, limit: int = 20) -> list[ConversationMessage]:
        """获取对话历史。"""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.messages[-limit:]

    async def get_context(self, session_id: str) -> dict[str, Any] | None:
        """获取上下文。"""
        session = self._sessions.get(session_id)
        return session.context if session else None

    async def update_context(self, session_id: str, context: dict[str, Any]) -> bool:
        """更新上下文。"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.context.update(context)
        session.updated_at = datetime.now(UTC).isoformat()
        return True

    async def set_user_preference(self, user_id: str, key: str, value: Any) -> None:
        """设置用户偏好。"""
        self._user_preferences[user_id][key] = value
        self._long_term_memory[user_id].append({
            "type": "preference",
            "key": key,
            "value": value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    async def get_user_preference(self, user_id: str, key: str) -> Any | None:
        """获取用户偏好。"""
        return self._user_preferences[user_id].get(key)

    async def get_long_term_memory(self, user_id: str, limit: int = 100) -> list[dict]:
        """获取长期记忆。"""
        return self._long_term_memory[user_id][-limit:]

    async def end_session(self, session_id: str) -> bool:
        """结束会话。"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._stats["active_sessions"] = len(self._sessions)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "user_preferences_count": len(self._user_preferences),
        }


class PerformanceTester:
    """
    性能测试器(D82-D83)。

    功能:
        1. 并发测试
        2. TPS/延迟统计
        3. 瓶颈分析
        4. 测试报告生成
    """

    TEST_SCENARIOS = {
        "api": {"concurrency": 100, "target_tps": 50},
        "agent": {"concurrency": 20, "target_tps": 10},
        "rag": {"concurrency": 500, "target_tps": 200},
        "report": {"concurrency": 10, "target_tps": 5},
    }

    def __init__(self):
        self._results: dict[str, PerformanceResult] = {}
        self._stats = {
            "total_tests": 0,
            "total_requests": 0,
        }
        logger.info("PerformanceTester初始化完成")

    async def run_test(
        self,
        test_type: str,
        concurrency: int | None = None,
        duration_seconds: float = 10.0,
    ) -> PerformanceResult:
        """运行性能测试。"""
        scenario = self.TEST_SCENARIOS.get(test_type, {"concurrency": 50, "target_tps": 25})
        concurrency = concurrency or scenario["concurrency"]

        test_id = f"PERF_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        latencies: list[float] = []
        errors: list[str] = []
        successful = 0
        failed = 0

        start_time = time.time()
        end_time = start_time + duration_seconds

        async def simulate_request():
            nonlocal successful, failed
            try:
                request_start = time.time()
                await asyncio.sleep(random.uniform(0.01, 0.1))
                latency = (time.time() - request_start) * 1000
                latencies.append(latency)
                if random.random() > 0.02:
                    successful += 1
                else:
                    failed += 1
                    errors.append(f"Simulated error {len(errors) + 1}")
            except Exception as e:
                failed += 1
                errors.append(str(e))

        tasks = []
        while time.time() < end_time:
            for _ in range(concurrency):
                if time.time() >= end_time:
                    break
                tasks.append(simulate_request())
            await asyncio.gather(*tasks)
            tasks = []

        actual_duration = time.time() - start_time
        total_requests = successful + failed

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
        avg = sum(latencies) / len(latencies) if latencies else 0
        tps = total_requests / actual_duration if actual_duration > 0 else 0

        result = PerformanceResult(
            test_id=test_id,
            test_type=test_type,
            concurrency=concurrency,
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=failed,
            avg_latency_ms=avg,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            tps=tps,
            duration_seconds=actual_duration,
            errors=errors[:10],
        )

        self._results[test_id] = result
        self._stats["total_tests"] += 1
        self._stats["total_requests"] += total_requests

        logger.info(f"性能测试完成: {test_id} TPS={tps:.2f}")
        return result

    async def get_result(self, test_id: str) -> PerformanceResult | None:
        return self._results.get(test_id)

    async def list_results(self, limit: int = 20) -> list[PerformanceResult]:
        return sorted(self._results.values(), key=lambda x: x.test_id, reverse=True)[:limit]

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "results_count": len(self._results),
        }


class SecurityAuditor:
    """
    安全审计器(D84)。

    功能:
        1. 操作审计日志
        2. 安全事件检测
        3. 风险评估
        4. 合规报告
    """

    RISK_INDICATORS = {
        "failed_login_threshold": 5,
        "suspicious_ip_patterns": ["192.168.0.", "10.0.0."],
        "high_risk_actions": ["config_change", "data_access"],
    }

    def __init__(self):
        self._events: dict[str, AuditEvent] = {}
        self._user_events: dict[str, list[str]] = defaultdict(list)
        self._ip_events: dict[str, list[str]] = defaultdict(list)
        self._stats = {
            "total_events": 0,
            "by_type": defaultdict(int),
            "high_risk_count": 0,
        }
        logger.info("SecurityAuditor初始化完成")

    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: str | None = None,
        ip_address: str | None = None,
        resource: str = "",
        action: str = "",
        details: dict | None = None,
    ) -> AuditEvent:
        """记录审计事件。"""
        event_id = f"AUDIT_{uuid.uuid4().hex[:8].upper()}"

        risk_level = self._assess_risk(event_type, user_id, ip_address, action)

        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            resource=resource,
            action=action,
            details=details or {},
            risk_level=risk_level,
        )

        self._events[event_id] = event
        if user_id:
            self._user_events[user_id].append(event_id)
        if ip_address:
            self._ip_events[ip_address].append(event_id)

        self._stats["total_events"] += 1
        self._stats["by_type"][event_type.value] += 1
        if risk_level == "high":
            self._stats["high_risk_count"] += 1

        logger.info(f"审计事件: {event_id} - {event_type.value} - {risk_level}")
        return event

    def _assess_risk(
        self,
        event_type: AuditEventType,
        user_id: str | None,
        ip_address: str | None,
        action: str,
    ) -> str:
        """评估风险等级。"""
        if event_type.value in self.RISK_INDICATORS["high_risk_actions"]:
            return "high"

        if user_id:
            recent_events = self._user_events.get(user_id, [])
            failed_logins = sum(
                1 for eid in recent_events[-20:]
                if self._events.get(eid, AuditEvent(
                    event_id="", event_type=AuditEventType.LOGIN, user_id="", ip_address="", resource="", action=""
                )).action == "failed_login"
            )
            if failed_logins >= self.RISK_INDICATORS["failed_login_threshold"]:
                return "high"

        if action in ["failed_login", "unauthorized_access"]:
            return "medium"

        return "low"

    async def get_event(self, event_id: str) -> AuditEvent | None:
        return self._events.get(event_id)

    async def query_events(
        self,
        user_id: str | None = None,
        event_type: AuditEventType | None = None,
        risk_level: str | None = None,
        start_time: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """查询审计事件。"""
        results = list(self._events.values())

        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if risk_level:
            results = [e for e in results if e.risk_level == risk_level]
        if start_time:
            results = [e for e in results if e.timestamp >= start_time]

        return sorted(results, key=lambda x: x.timestamp, reverse=True)[:limit]

    async def get_user_activity(self, user_id: str) -> list[AuditEvent]:
        """获取用户活动。"""
        event_ids = self._user_events.get(user_id, [])
        return [self._events[eid] for eid in event_ids if eid in self._events]

    async def detect_anomalies(self) -> list[dict[str, Any]]:
        """检测异常。"""
        anomalies = []

        for ip, events in self._ip_events.items():
            if len(events) > 100:
                anomalies.append({
                    "type": "high_frequency_ip",
                    "ip": ip,
                    "event_count": len(events),
                    "severity": "medium",
                })

        for user_id, events in self._user_events.items():
            failed_count = sum(
                1 for eid in events[-20:]
                if self._events.get(eid, AuditEvent(
                    event_id="", event_type=AuditEventType.LOGIN, user_id="", ip_address="", resource="", action=""
                )).action == "failed_login"
            )
            if failed_count >= self.RISK_INDICATORS["failed_login_threshold"]:
                anomalies.append({
                    "type": "brute_force_attempt",
                    "user_id": user_id,
                    "failed_attempts": failed_count,
                    "severity": "high",
                })

        return anomalies

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_type": dict(self._stats["by_type"]),
        }


class AlertManager:
    """
    告警管理器(D85)。

    功能:
        1. 告警规则配置
        2. 告警触发与通知
        3. 告警确认与处理
        4. 告警统计
    """

    ALERT_RULES = [
        {"name": "api_error_rate", "condition": "error_rate > 5%", "threshold": 5, "severity": AlertSeverity.CRITICAL},
        {"name": "gpu_utilization", "condition": "gpu_util < 20%", "threshold": 20, "severity": AlertSeverity.WARNING},
        {"name": "disk_usage", "condition": "usage > 80%", "threshold": 80, "severity": AlertSeverity.WARNING},
        {"name": "memory_usage", "condition": "usage > 90%", "threshold": 90, "severity": AlertSeverity.CRITICAL},
        {"name": "response_time", "condition": "p99 > 2000ms", "threshold": 2000, "severity": AlertSeverity.WARNING},
    ]

    def __init__(self):
        self._alerts: dict[str, Alert] = {}
        self._metrics: dict[str, float] = {}
        self._stats = {
            "total_alerts": 0,
            "by_severity": defaultdict(int),
            "acknowledged": 0,
        }
        logger.info("AlertManager初始化完成")

    async def update_metric(self, name: str, value: float) -> None:
        """更新指标。"""
        self._metrics[name] = value
        await self._check_rules(name, value)

    async def _check_rules(self, metric_name: str, value: float) -> None:
        """检查告警规则。"""
        for rule in self.ALERT_RULES:
            if rule["name"] == metric_name:
                should_alert = False
                if "error_rate" in metric_name and value > rule["threshold"] or "gpu_util" in metric_name and value < rule["threshold"] or "usage" in metric_name and value > rule["threshold"] or "response_time" in metric_name and value > rule["threshold"]:
                    should_alert = True

                if should_alert:
                    await self._create_alert(rule, value)

    async def _create_alert(self, rule: dict, current_value: float) -> Alert:
        """创建告警。"""
        alert_id = f"ALERT_{uuid.uuid4().hex[:8].upper()}"

        alert = Alert(
            alert_id=alert_id,
            name=rule["name"],
            severity=rule["severity"],
            condition=rule["condition"],
            current_value=current_value,
            threshold=rule["threshold"],
            message=f"{rule['name']} 触发告警: 当前值 {current_value:.2f}, 阈值 {rule['threshold']}",
        )

        self._alerts[alert_id] = alert
        self._stats["total_alerts"] += 1
        self._stats["by_severity"][rule["severity"].value] += 1

        logger.warning(f"告警触发: {alert_id} - {rule['name']}")
        return alert

    async def acknowledge_alert(self, alert_id: str) -> Alert | None:
        """确认告警。"""
        alert = self._alerts.get(alert_id)
        if alert and not alert.acknowledged:
            alert.acknowledged = True
            self._stats["acknowledged"] += 1
        return alert

    async def get_alert(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    async def list_alerts(
        self,
        severity: AlertSeverity | None = None,
        acknowledged: bool | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        """列出告警。"""
        results = list(self._alerts.values())

        if severity:
            results = [a for a in results if a.severity == severity]
        if acknowledged is not None:
            results = [a for a in results if a.acknowledged == acknowledged]

        return sorted(results, key=lambda x: x.timestamp, reverse=True)[:limit]

    async def get_active_alerts(self) -> list[Alert]:
        """获取活跃告警。"""
        return [a for a in self._alerts.values() if not a.acknowledged]

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_severity": dict(self._stats["by_severity"]),
            "active_alerts": len([a for a in self._alerts.values() if not a.acknowledged]),
        }
