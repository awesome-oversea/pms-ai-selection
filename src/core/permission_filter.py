from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.core.pms_governance import AuditContext, PermissionContext

PERMISSION_FILTER_FIELDS: tuple[str, ...] = (
    "tenant_id",
    "org_id",
    "department_id",
    "store_id",
    "marketplace",
    "channel",
    "warehouse_id",
    "supplier_id",
    "category_id",
    "data_level",
    "source_system",
)


def _context_filter(permission_context: AuditContext | PermissionContext | dict[str, Any] | None) -> dict[str, Any]:
    if permission_context is None:
        return {}
    raw = asdict(permission_context) if isinstance(permission_context, (AuditContext, PermissionContext)) else dict(permission_context)
    return {field: raw.get(field) for field in PERMISSION_FILTER_FIELDS if raw.get(field) not in {None, ""}}


def item_matches_permission(item: dict[str, Any], permission_context: AuditContext | PermissionContext | dict[str, Any] | None) -> bool:
    filters = _context_filter(permission_context)
    for field, expected in filters.items():
        actual = item.get(field)
        if field == "tenant_id" and actual is not None and str(actual) != str(expected):
            return False
        if field != "tenant_id" and actual not in {None, ""} and str(actual) != str(expected):
            return False
    return True


def filter_items_by_permission(items: list[dict[str, Any]], permission_context: PermissionContext | dict[str, Any] | None) -> list[dict[str, Any]]:
    return [item for item in items if isinstance(item, dict) and item_matches_permission(item, permission_context)]


def filter_dataset_by_permission(payload: dict[str, Any], permission_context: PermissionContext | dict[str, Any] | None) -> dict[str, Any]:
    datasets_raw = payload.get("datasets")
    datasets: list[dict[str, Any]] = datasets_raw if isinstance(datasets_raw, list) else []
    filtered_datasets: list[dict[str, Any]] = []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        rows = dataset.get("rows")
        filtered_rows = filter_items_by_permission(rows, permission_context) if isinstance(rows, list) else []
        filtered_datasets.append({**dataset, "rows": filtered_rows})
    return {**payload, "datasets": filtered_datasets}
