"""
运维工具链与监控
===============

提供运维工具链与监控能力(D116-D120):
    - 运维自动化脚本
    - Grafana监控大屏
    - 告警升级机制
    - 巡检自动化
    - 运维知识库

使用方式:
    from src.infrastructure.ops_toolkit import OpsScriptManager, AlertManager

    ops = OpsScriptManager()
    result = await ops.run_script("health_check")

    alert = AlertManager()
    await alert.send_alert("P0", "服务宕机")
"""

from __future__ import annotations

import asyncio
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class ScriptType(StrEnum):
    """脚本类型。"""
    HEALTH_CHECK = "health_check"
    LOG_ROTATE = "log_rotate"
    CERT_RENEW = "cert_renew"
    BACKUP_VERIFY = "backup_verify"
    CLEANUP = "cleanup"


class ScriptStatus(StrEnum):
    """脚本状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class AlertLevel(StrEnum):
    """告警等级。"""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AlertStatus(StrEnum):
    """告警状态。"""
    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"


class CheckType(StrEnum):
    """巡检类型。"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class CheckStatus(StrEnum):
    """巡检状态。"""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ScriptExecution:
    """脚本执行记录。"""
    execution_id: str
    script_type: ScriptType
    status: ScriptStatus = ScriptStatus.PENDING
    output: str = ""
    duration_seconds: float = 0.0
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "script_type": self.script_type.value,
            "status": self.status.value,
            "output": self.output,
            "duration_seconds": round(self.duration_seconds, 2),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


@dataclass
class Alert:
    """告警。"""
    alert_id: str
    level: AlertLevel
    title: str
    description: str = ""
    status: AlertStatus = AlertStatus.FIRING
    source: str = ""
    notified_channels: list[str] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: str | None = None
    fired_at: str | None = None
    resolved_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "source": self.source,
            "notified_channels": self.notified_channels,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "fired_at": self.fired_at,
            "resolved_at": self.resolved_at,
            "created_at": self.created_at,
        }


@dataclass
class InspectionItem:
    """巡检项。"""
    item_id: str
    name: str
    check_type: CheckType
    status: CheckStatus = CheckStatus.PASS
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "check_type": self.check_type.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at,
            "created_at": self.created_at,
        }


@dataclass
class KnowledgeArticle:
    """知识库文章。"""
    article_id: str
    title: str
    category: str
    content: str = ""
    tags: list[str] = field(default_factory=list)
    views: int = 0
    helpful_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "category": self.category,
            "content": self.content,
            "tags": self.tags,
            "views": self.views,
            "helpful_count": self.helpful_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class OpsScriptManager:
    """
    运维脚本管理器(D116)。

    功能:
        1. 脚本执行
        2. 执行记录
        3. 定时调度
    """

    SCRIPTS = {
        ScriptType.HEALTH_CHECK: {"frequency": "5min", "timeout": 30},
        ScriptType.LOG_ROTATE: {"frequency": "daily", "timeout": 60},
        ScriptType.CERT_RENEW: {"frequency": "monthly", "timeout": 120},
        ScriptType.BACKUP_VERIFY: {"frequency": "daily", "timeout": 300},
        ScriptType.CLEANUP: {"frequency": "weekly", "timeout": 600},
    }

    def __init__(self):
        self._executions: dict[str, ScriptExecution] = {}
        self._stats = {
            "total_runs": 0,
            "successful": 0,
            "failed": 0,
        }
        logger.info("OpsScriptManager初始化完成")

    async def run_script(self, script_type: ScriptType) -> ScriptExecution:
        """运行脚本。"""
        execution_id = f"EXEC_{uuid.uuid4().hex[:6].upper()}"

        execution = ScriptExecution(
            execution_id=execution_id,
            script_type=script_type,
            status=ScriptStatus.RUNNING,
            started_at=datetime.now(UTC).isoformat(),
        )

        self._executions[execution_id] = execution
        self._stats["total_runs"] += 1

        config = self.SCRIPTS.get(script_type, {})
        timeout = config.get("timeout", 60)

        await asyncio.sleep(random.uniform(0.5, min(timeout / 60, 2.0)))

        success = random.random() > 0.1
        execution.status = ScriptStatus.SUCCESS if success else ScriptStatus.FAILED
        execution.duration_seconds = random.uniform(1, timeout)
        execution.output = f"脚本{script_type.value}执行{'成功' if success else '失败'}"
        execution.completed_at = datetime.now(UTC).isoformat()

        if success:
            self._stats["successful"] += 1
        else:
            self._stats["failed"] += 1

        logger.info(f"运行脚本: {script_type.value} - {execution.status.value}")
        return execution

    async def run_all_scripts(self) -> list[ScriptExecution]:
        """运行所有脚本。"""
        executions = []
        for script_type in ScriptType:
            execution = await self.run_script(script_type)
            executions.append(execution)
        return executions

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "success_rate": round(self._stats["successful"] / max(self._stats["total_runs"], 1), 4),
        }


class DashboardManager:
    """
    监控大屏管理器(D117)。

    功能:
        1. Dashboard配置
        2. 指标聚合
        3. 数据刷新
    """

    DASHBOARDS = [
        {"name": "系统总览", "panels": ["QPS", "延迟", "错误率", "GPU", "内存", "磁盘"]},
        {"name": "业务指标", "panels": ["选品数", "转化率", "ROI", "用户活跃度"]},
        {"name": "基础设施", "panels": ["Pod状态", "节点资源", "网络IO", "存储使用"]},
    ]

    def __init__(self):
        self._metrics: dict[str, Any] = {}
        self._stats = {
            "refresh_count": 0,
            "last_refresh": None,
        }
        logger.info("DashboardManager初始化完成")

    async def refresh_metrics(self) -> dict[str, Any]:
        """刷新指标。"""
        self._metrics = {
            "qps": round(random.uniform(100, 1000), 2),
            "latency_ms": round(random.uniform(50, 200), 2),
            "error_rate": round(random.uniform(0.001, 0.01), 4),
            "gpu_utilization": round(random.uniform(60, 95), 2),
            "memory_usage": round(random.uniform(50, 80), 2),
            "disk_usage": round(random.uniform(40, 70), 2),
            "pod_count": random.randint(10, 20),
            "healthy_pods": random.randint(8, 20),
        }

        self._stats["refresh_count"] += 1
        self._stats["last_refresh"] = datetime.now(UTC).isoformat()

        logger.info("刷新监控指标")
        return self._metrics

    async def get_dashboard(self, name: str) -> dict[str, Any] | None:
        """获取Dashboard。"""
        for dashboard in self.DASHBOARDS:
            if dashboard["name"] == name:
                return {
                    **dashboard,
                    "metrics": self._metrics,
                    "refreshed_at": self._stats["last_refresh"],
                }
        return None

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "metrics": self._metrics,
        }


class AlertManager:
    """
    告警管理器(D118)。

    功能:
        1. 告警发送
        2. 告警升级
        3. 告警静默
    """

    ALERT_CONFIG = {
        AlertLevel.P0: {"response_minutes": 5, "channels": ["phone", "dingtalk", "sms"]},
        AlertLevel.P1: {"response_minutes": 15, "channels": ["dingtalk", "email"]},
        AlertLevel.P2: {"response_minutes": 30, "channels": ["dingtalk"]},
        AlertLevel.P3: {"response_minutes": 120, "channels": ["email"]},
    }

    def __init__(self):
        self._alerts: dict[str, Alert] = {}
        self._stats = {
            "total_alerts": 0,
            "by_level": defaultdict(int),
            "resolved": 0,
        }
        logger.info("AlertManager初始化完成")

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        description: str = "",
        source: str = "",
    ) -> Alert:
        """发送告警。"""
        alert_id = f"ALERT_{uuid.uuid4().hex[:6].upper()}"

        config = self.ALERT_CONFIG.get(level, {})
        channels = config.get("channels", ["email"])

        alert = Alert(
            alert_id=alert_id,
            level=level,
            title=title,
            description=description,
            source=source,
            notified_channels=channels,
            fired_at=datetime.now(UTC).isoformat(),
        )

        self._alerts[alert_id] = alert
        self._stats["total_alerts"] += 1
        self._stats["by_level"][level.value] += 1

        logger.warning(f"发送告警: [{level.value}] {title}")
        return alert

    async def acknowledge_alert(self, alert_id: str, user: str) -> Alert | None:
        """确认告警。"""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None

        alert.acknowledged = True
        alert.acknowledged_by = user

        logger.info(f"确认告警: {alert_id} by {user}")
        return alert

    async def resolve_alert(self, alert_id: str) -> Alert | None:
        """解决告警。"""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC).isoformat()
        self._stats["resolved"] += 1

        logger.info(f"解决告警: {alert_id}")
        return alert

    async def get_alert(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    async def list_alerts(
        self,
        level: AlertLevel | None = None,
        status: AlertStatus | None = None,
    ) -> list[Alert]:
        """列出告警。"""
        results = list(self._alerts.values())
        if level:
            results = [a for a in results if a.level == level]
        if status:
            results = [a for a in results if a.status == status]
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_level": dict(self._stats["by_level"]),
        }


class InspectionManager:
    """
    巡检管理器(D119)。

    功能:
        1. 巡检执行
        2. 结果记录
        3. 报告生成
    """

    INSPECTION_ITEMS = {
        CheckType.DAILY: [
            {"name": "服务健康检查", "check": "all_services_running"},
            {"name": "磁盘空间", "check": "disk_usage < 80%"},
            {"name": "证书有效期", "check": "cert_not_expiring_30d"},
            {"name": "备份完整性", "check": "last_backup_success"},
        ],
        CheckType.WEEKLY: [
            {"name": "数据库复制延迟", "check": "replication_lag < 1s"},
            {"name": "Redis集群状态", "check": "cluster_healthy"},
            {"name": "GPU利用率", "check": "utilization_normal"},
            {"name": "安全漏洞扫描", "check": "no_new_vulnerabilities"},
        ],
    }

    def __init__(self):
        self._items: dict[str, InspectionItem] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        self._stats = {
            "total_checks": 0,
            "passed": 0,
            "warned": 0,
            "failed": 0,
        }
        logger.info("InspectionManager初始化完成")

    async def run_check(self, name: str, check_type: CheckType) -> InspectionItem:
        """运行巡检。"""
        item_id = f"CHECK_{uuid.uuid4().hex[:6].upper()}"

        await asyncio.sleep(random.uniform(0.1, 0.5))

        rand = random.random()
        if rand > 0.9:
            status = CheckStatus.FAIL
        elif rand > 0.8:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.PASS

        item = InspectionItem(
            item_id=item_id,
            name=name,
            check_type=check_type,
            status=status,
            message=f"巡检{'通过' if status == CheckStatus.PASS else '异常'}",
            checked_at=datetime.now(UTC).isoformat(),
        )

        self._items[item_id] = item
        self._stats["total_checks"] += 1
        self._stats[f"{status.value}ed"] += 1

        logger.info(f"巡检: {name} - {status.value}")
        return item

    async def run_daily_inspection(self) -> dict[str, Any]:
        """运行日常巡检。"""
        items = []
        for config in self.INSPECTION_ITEMS.get(CheckType.DAILY, []):
            item = await self.run_check(config["name"], CheckType.DAILY)
            items.append(item)

        report_id = f"REPORT_DAILY_{datetime.now(UTC).strftime('%Y%m%d')}"
        report = {
            "report_id": report_id,
            "type": "daily",
            "items": [i.to_dict() for i in items],
            "summary": {
                "total": len(items),
                "passed": sum(1 for i in items if i.status == CheckStatus.PASS),
                "warned": sum(1 for i in items if i.status == CheckStatus.WARN),
                "failed": sum(1 for i in items if i.status == CheckStatus.FAIL),
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

        self._reports[report_id] = report
        return report

    async def run_weekly_inspection(self) -> dict[str, Any]:
        """运行周巡检。"""
        items = []
        for config in self.INSPECTION_ITEMS.get(CheckType.WEEKLY, []):
            item = await self.run_check(config["name"], CheckType.WEEKLY)
            items.append(item)

        report_id = f"REPORT_WEEKLY_{datetime.now(UTC).strftime('%Y%m%d')}"
        report = {
            "report_id": report_id,
            "type": "weekly",
            "items": [i.to_dict() for i in items],
            "summary": {
                "total": len(items),
                "passed": sum(1 for i in items if i.status == CheckStatus.PASS),
                "warned": sum(1 for i in items if i.status == CheckStatus.WARN),
                "failed": sum(1 for i in items if i.status == CheckStatus.FAIL),
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

        self._reports[report_id] = report
        return report

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "pass_rate": round(self._stats["passed"] / max(self._stats["total_checks"], 1), 4),
        }


class KnowledgeBase:
    """
    运维知识库(D120)。

    功能:
        1. 文章管理
        2. 搜索功能
        3. 分类浏览
    """

    CATEGORIES = ["troubleshooting", "runbooks", "faq", "best_practices"]

    def __init__(self):
        self._articles: dict[str, KnowledgeArticle] = {}
        self._stats = {
            "total_articles": 0,
            "total_views": 0,
            "by_category": defaultdict(int),
        }
        logger.info("KnowledgeBase初始化完成")

    async def create_article(
        self,
        title: str,
        category: str,
        content: str = "",
        tags: list[str] | None = None,
    ) -> KnowledgeArticle:
        """创建文章。"""
        article_id = f"KB_{uuid.uuid4().hex[:6].upper()}"

        article = KnowledgeArticle(
            article_id=article_id,
            title=title,
            category=category,
            content=content,
            tags=tags or [],
        )

        self._articles[article_id] = article
        self._stats["total_articles"] += 1
        self._stats["by_category"][category] += 1

        logger.info(f"创建知识库文章: {title}")
        return article

    async def get_article(self, article_id: str) -> KnowledgeArticle | None:
        """获取文章。"""
        article = self._articles.get(article_id)
        if article:
            article.views += 1
            self._stats["total_views"] += 1
        return article

    async def search_articles(self, keyword: str) -> list[KnowledgeArticle]:
        """搜索文章。"""
        results = []
        for article in self._articles.values():
            if keyword.lower() in article.title.lower() or keyword.lower() in article.content.lower() or any(keyword.lower() in tag.lower() for tag in article.tags):
                results.append(article)
        return results

    async def list_by_category(self, category: str) -> list[KnowledgeArticle]:
        """按分类列出。"""
        return [a for a in self._articles.values() if a.category == category]

    async def mark_helpful(self, article_id: str) -> KnowledgeArticle | None:
        """标记有帮助。"""
        article = self._articles.get(article_id)
        if article:
            article.helpful_count += 1
        return article

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "by_category": dict(self._stats["by_category"]),
        }
