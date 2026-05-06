"""
RBAC 角色矩阵基线
=================

提供 Phase 5 正式角色矩阵与权限资源/动作模型的最小代码基线：
- 平台级角色
- 租户级角色
- 资源与动作常量
- 权限标识构造器
- 角色到权限映射
- 从当前用户上下文推导默认角色
"""

from __future__ import annotations

from typing import Any

RESOURCE_TENANT = "tenant"
RESOURCE_USER = "user"
RESOURCE_SELECTION = "selection"
RESOURCE_KNOWLEDGE = "knowledge"
RESOURCE_REPORT = "report"
RESOURCE_AUDIT = "audit"
RESOURCE_PLATFORM_CONFIG = "platform.config"
RESOURCE_RBAC = "rbac"

ACTION_READ = "read"
ACTION_WRITE = "write"
ACTION_MANAGE = "manage"
ACTION_EXECUTE = "execute"
ACTION_EXPORT = "export"
ACTION_APPROVE = "approve"

PLATFORM_ROLES = (
    "platform_admin",
)

TENANT_ROLES = (
    "tenant_admin",
    "operator",
    "analyst",
    "viewer",
    "auditor",
)

DEFAULT_VIEWER_ROLE = "viewer"
DEFAULT_PLATFORM_ADMIN_ROLE = "platform_admin"


def build_permission(resource: str, action: str) -> str:
    return f"{resource}.{action}"


CORE_PERMISSIONS = {
    build_permission(RESOURCE_TENANT, ACTION_MANAGE),
    build_permission(RESOURCE_USER, ACTION_MANAGE),
    build_permission(RESOURCE_SELECTION, ACTION_READ),
    build_permission(RESOURCE_SELECTION, ACTION_EXECUTE),
    build_permission(RESOURCE_SELECTION, ACTION_MANAGE),
    build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
    build_permission(RESOURCE_KNOWLEDGE, ACTION_READ),
    build_permission(RESOURCE_KNOWLEDGE, ACTION_WRITE),
    build_permission(RESOURCE_KNOWLEDGE, ACTION_MANAGE),
    build_permission(RESOURCE_REPORT, ACTION_READ),
    build_permission(RESOURCE_REPORT, ACTION_EXPORT),
    build_permission(RESOURCE_REPORT, ACTION_MANAGE),
    build_permission(RESOURCE_AUDIT, ACTION_READ),
    build_permission(RESOURCE_AUDIT, "read_all"),
    build_permission(RESOURCE_PLATFORM_CONFIG, ACTION_MANAGE),
    build_permission(RESOURCE_RBAC, ACTION_MANAGE),
}

ROLE_MATRIX: dict[str, dict[str, Any]] = {
    "platform_admin": {
        "scope": "platform",
        "description": "平台级管理员，负责平台配置、租户管理与全局治理",
        "responsibilities": [
            build_permission(RESOURCE_TENANT, ACTION_MANAGE),
            build_permission(RESOURCE_PLATFORM_CONFIG, ACTION_MANAGE),
            build_permission(RESOURCE_AUDIT, "read_all"),
            build_permission(RESOURCE_RBAC, ACTION_MANAGE),
        ],
    },
    "tenant_admin": {
        "scope": "tenant",
        "description": "租户管理员，负责租户内用户、任务、知识库与报表管理",
        "responsibilities": [
            build_permission(RESOURCE_USER, ACTION_MANAGE),
            build_permission(RESOURCE_SELECTION, ACTION_MANAGE),
            build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
            build_permission(RESOURCE_KNOWLEDGE, ACTION_MANAGE),
            build_permission(RESOURCE_REPORT, ACTION_MANAGE),
        ],
    },
    "operator": {
        "scope": "tenant",
        "description": "运营角色，负责执行日常任务与处理知识库文档",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_EXECUTE),
            build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
            build_permission(RESOURCE_KNOWLEDGE, ACTION_WRITE),
            build_permission(RESOURCE_REPORT, ACTION_EXPORT),
        ],
    },
    "analyst": {
        "scope": "tenant",
        "description": "分析角色，负责分析任务结果、查看报告与辅助决策",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_KNOWLEDGE, ACTION_READ),
            build_permission(RESOURCE_REPORT, ACTION_READ),
        ],
    },
    "viewer": {
        "scope": "tenant",
        "description": "只读角色，负责浏览任务、报告与知识检索结果",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_KNOWLEDGE, ACTION_READ),
            build_permission(RESOURCE_REPORT, ACTION_READ),
        ],
    },
    "auditor": {
        "scope": "tenant",
        "description": "审计角色，负责查看审计与关键操作记录",
        "responsibilities": [
            build_permission(RESOURCE_AUDIT, ACTION_READ),
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_KNOWLEDGE, ACTION_READ),
        ],
    },
    "procurement": {
        "scope": "tenant",
        "description": "采购角色，负责审批采纳结果、跟进供应商与执行采购",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
            build_permission(RESOURCE_REPORT, ACTION_READ),
        ],
    },
    "manager": {
        "scope": "tenant",
        "description": "管理者角色，负责业务审批、看板查看与决策监督",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_SELECTION, ACTION_APPROVE),
            build_permission(RESOURCE_REPORT, ACTION_READ),
            build_permission(RESOURCE_AUDIT, ACTION_READ),
        ],
    },
    "finance": {
        "scope": "tenant",
        "description": "财务角色，负责成本、利润与报表审阅",
        "responsibilities": [
            build_permission(RESOURCE_SELECTION, ACTION_READ),
            build_permission(RESOURCE_REPORT, ACTION_READ),
            build_permission(RESOURCE_REPORT, ACTION_EXPORT),
        ],
    },
}

ROLE_PERMISSIONS = {
    role: set(meta["responsibilities"])
    for role, meta in ROLE_MATRIX.items()
}


def normalize_roles(raw_roles: Any) -> list[str]:
    if raw_roles is None:
        return []
    if isinstance(raw_roles, str):
        return [raw_roles]
    if isinstance(raw_roles, (list, tuple, set)):
        return [str(role) for role in raw_roles if role]
    return []


def derive_roles(current_user: dict[str, Any] | None) -> list[str]:
    payload = current_user or {}
    roles = normalize_roles(payload.get("roles"))
    if roles:
        return roles
    if payload.get("is_superuser"):
        return [DEFAULT_PLATFORM_ADMIN_ROLE]
    return [DEFAULT_VIEWER_ROLE]
