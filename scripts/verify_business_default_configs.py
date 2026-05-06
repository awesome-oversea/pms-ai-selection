from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.business_defaults import get_business_default_config_bundle
from src.infrastructure.database import get_async_session_factory
from src.services.config_center_service import ConfigCenterService


# 注意：当前本地 ConfigCenter 可能走内存兜底，跨进程验证不能作为强保证。
# 若需要本地强验收，请优先使用 accept_business_default_configs.py。


async def _run(tenant_id: str) -> dict:
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=tenant_id)
        expected = get_business_default_config_bundle()
        checks = {}
        for config_key, expected_value in expected.items():
            current = await service.get_config(config_key)
            checks[config_key] = {
                "exists": current is not None,
                "matches": bool(current and current.get("value") == expected_value),
                "version": current.get("version") if current else None,
            }
        ok = all(item["exists"] and item["matches"] for item in checks.values())
        return {"tenant_id": tenant_id, "ok": ok, "checks": checks}
    finally:
        await session.close()


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = asyncio.run(_run(tenant_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
