from __future__ import annotations

from typing import Any

from src.core.security import list_audit_logs_persistent


async def query_persistent_audit_logs(**kwargs: Any) -> list[dict[str, Any]]:
    return await list_audit_logs_persistent(**kwargs)
