from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.database import get_async_session_factory
from src.services.config_center_service import ConfigCenterService


async def _run(tenant_id: str, config_key: str) -> dict:
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=tenant_id)
        rolled_back = await service.rollback_config(config_key)
        await session.commit()
        return {
            "tenant_id": tenant_id,
            "config_key": config_key,
            "rolled_back": rolled_back is not None,
            "current": rolled_back,
        }
    finally:
        await session.close()


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    config_key = sys.argv[2] if len(sys.argv) > 2 else "selection.commercial.decision_rules"
    result = asyncio.run(_run(tenant_id, config_key))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["rolled_back"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
