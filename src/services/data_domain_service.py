"""
主数据与业务数据域服务
======================

为 T7.5 提供统一的数据域字典：
- 主实体定义
- 关键字段
- source of truth
- 同步方向
- 业务口径说明
"""

from __future__ import annotations

from typing import Any


class DataDomainService:
    """统一主数据与业务数据域模型字典。"""

    _DOMAINS: dict[str, dict[str, Any]] = {
        "Product": {
            "domain": "master_data",
            "owner": "selection_platform",
            "source_of_truth": "products",
            "sync_direction": "inbound_from_marketplaces_and_collectors",
            "description": "平台商品主数据实体，承载跨平台商品基础属性与聚合画像。",
            "key_fields": ["id", "platform", "external_product_id", "name", "brand", "category_id", "price", "rating", "sales_rank"],
        },
        "Competitor": {
            "domain": "reference_data",
            "owner": "selection_platform",
            "source_of_truth": "competitors",
            "sync_direction": "derived_from_product_monitoring",
            "description": "竞品参考数据，服务于选品与市场分析。",
            "key_fields": ["id", "product_id", "seller_name", "price", "stock_status", "buy_box_percentage"],
        },
        "SelectionTask": {
            "domain": "business_transaction",
            "owner": "selection_workflow",
            "source_of_truth": "selection_tasks",
            "sync_direction": "created_internally",
            "description": "选品业务任务主表，是工作流调度与状态追踪的事务源。",
            "key_fields": ["id", "tenant_id", "status", "priority", "target_market", "target_category", "created_by", "completed_at"],
        },
        "SelectionResult": {
            "domain": "business_result",
            "owner": "selection_workflow",
            "source_of_truth": "selection_results",
            "sync_direction": "derived_from_selection_task",
            "description": "选品结果实体，承载推荐排序与分析分数。",
            "key_fields": ["id", "tenant_id", "task_id", "product_id", "rank", "overall_score", "reasoning"],
        },
        "AgentRun": {
            "domain": "execution_log",
            "owner": "agent_platform",
            "source_of_truth": "agent_runs",
            "sync_direction": "generated_by_agents",
            "description": "Agent 执行日志实体，用于模型调用、成本、时延、状态追踪。",
            "key_fields": ["id", "tenant_id", "task_id", "agent_type", "status", "model_used", "token_usage_input", "token_usage_output", "cost_usd"],
        },
        "KnowledgeBase": {
            "domain": "knowledge_master",
            "owner": "knowledge_platform",
            "source_of_truth": "knowledge_bases",
            "sync_direction": "created_internally",
            "description": "知识库主实体，定义 collection、embedding、chunk 策略。",
            "key_fields": ["id", "tenant_id", "name", "kb_type", "collection_name", "embedding_model", "is_active"],
        },
        "Document": {
            "domain": "knowledge_asset",
            "owner": "knowledge_platform",
            "source_of_truth": "documents",
            "sync_direction": "uploaded_internally_or_sync_from_sources",
            "description": "知识文档资产实体，支持版本、索引状态、当前版本标记。",
            "key_fields": ["id", "tenant_id", "knowledge_base_id", "title", "content_hash", "status", "chunk_count", "extra_data"],
        },
        "Report": {
            "domain": "reporting",
            "owner": "reporting_platform",
            "source_of_truth": "reports",
            "sync_direction": "generated_internally",
            "description": "报告主实体，对外提供选品、市场、商业化等报告。",
            "key_fields": ["id", "report_type", "status", "title", "created_at"],
        },
        "ErpConfig": {
            "domain": "integration_config",
            "owner": "integration_platform",
            "source_of_truth": "erp_configs",
            "sync_direction": "managed_internally",
            "description": "ERP 对接配置主实体。",
            "key_fields": ["id", "system_type", "base_url", "is_active", "tenant_id"],
        },
        "ErpSyncLog": {
            "domain": "integration_log",
            "owner": "integration_platform",
            "source_of_truth": "erp_sync_logs",
            "sync_direction": "generated_by_sync_jobs",
            "description": "ERP 同步日志实体，记录同步对象、结果、耗时与异常。",
            "key_fields": ["id", "tenant_id", "system_type", "sync_type", "status", "items_total", "items_success", "items_failed"],
        },
    }

    def list_domains(self) -> dict[str, Any]:
        return {
            "total": len(self._DOMAINS),
            "entities": [
                {"entity": name, **meta}
                for name, meta in self._DOMAINS.items()
            ],
        }

    def get_domain(self, entity: str) -> dict[str, Any] | None:
        meta = self._DOMAINS.get(entity)
        if meta is None:
            return None
        return {"entity": entity, **meta}
