from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

DEFAULT_CONFIG_DESCRIPTIONS: dict[str, str] = {
    "selection.commercial.decision_rules": "商业决策默认规则基线，用于 Go/No-Go 阈值与权重回放验证",
    "selection.scheduler.defaults": "定时选品任务默认业务参数基线",
    "selection.feedback.defaults": "反馈闭环默认调度参数基线",
    "selection.kpi.defaults": "KPI 默认调度参数基线",
    "knowledge.rag_evaluation.defaults": "RAG 默认评测基线与阈值配置",
}

DEFAULT_SCHEDULED_SELECTION_CONFIG: dict[str, Any] = {
    "task_id": "scheduled-selection-demo",
    "tenant_id": "default",
    "query": "蓝牙耳机",
    "category": "electronics",
    "market": "US",
    "budget": 50000.0,
    "priority": "normal",
}

DEFAULT_COMMERCIAL_DECISION_RULES: dict[str, Any] = {
    "thresholds": {"go": 70.0, "no_go": 40.0},
    "weights": {"margin": 0.4, "risk": 0.3, "market": 0.2, "budget": 0.1},
}

DEFAULT_RAG_EVALUATION_CONFIG: dict[str, Any] = {
    "thresholds": {
        "default_top_k": 5,
        "default_threshold": 0.1,
    },
    "baseline_cases": [
        {
            "query": "默认知识库是什么？",
            "expected_document_ids": [],
            "expected_keywords": ["默认知识库"],
            "top_k": 5,
            "threshold": 0.1,
        },
        {
            "query": "如何进行文档版本回滚？",
            "expected_document_ids": [],
            "expected_keywords": ["回滚", "版本"],
            "top_k": 5,
            "threshold": 0.1,
        },
    ],
}


def get_scheduled_selection_config() -> dict[str, Any]:
    config = deepcopy(DEFAULT_SCHEDULED_SELECTION_CONFIG)
    config["query"] = os.getenv("CELERY_SCHEDULED_SELECTION_QUERY", config["query"])
    config["category"] = os.getenv("CELERY_SCHEDULED_SELECTION_CATEGORY", config["category"])
    config["market"] = os.getenv("CELERY_SCHEDULED_SELECTION_MARKET", config["market"])
    config["tenant_id"] = os.getenv("CELERY_SCHEDULED_SELECTION_TENANT", config["tenant_id"])
    config["task_id"] = os.getenv("CELERY_SCHEDULED_SELECTION_TASK_ID", config["task_id"])
    config["budget"] = float(os.getenv("CELERY_SCHEDULED_SELECTION_BUDGET", str(config["budget"])))
    config["priority"] = os.getenv("CELERY_SCHEDULED_SELECTION_PRIORITY", config["priority"])
    return config


def get_feedback_schedule_config() -> dict[str, Any]:
    scheduled = get_scheduled_selection_config()
    return {
        "task_id": os.getenv("CELERY_SCHEDULED_FEEDBACK_TASK_ID", scheduled["task_id"]),
        "tenant_id": scheduled["tenant_id"],
    }


def get_kpi_schedule_config() -> dict[str, Any]:
    scheduled = get_scheduled_selection_config()
    return {
        "tenant_id": os.getenv("CELERY_SCHEDULED_KPI_TENANT", scheduled["tenant_id"]),
    }


def get_commercial_decision_rules() -> dict[str, Any]:
    return deepcopy(DEFAULT_COMMERCIAL_DECISION_RULES)


def get_rag_evaluation_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_RAG_EVALUATION_CONFIG)


def get_business_default_config_bundle() -> dict[str, Any]:
    return {
        "selection.commercial.decision_rules": get_commercial_decision_rules(),
        "selection.scheduler.defaults": get_scheduled_selection_config(),
        "selection.feedback.defaults": get_feedback_schedule_config(),
        "selection.kpi.defaults": get_kpi_schedule_config(),
        "knowledge.rag_evaluation.defaults": get_rag_evaluation_config(),
    }
