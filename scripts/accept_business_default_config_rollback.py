from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.business_defaults import get_commercial_decision_rules
from src.infrastructure.database import get_async_session_factory
from src.services.config_center_service import ConfigCenterService


async def _run(tenant_id: str) -> dict:
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=tenant_id)
        config_key = "selection.commercial.decision_rules"
        base_rules = get_commercial_decision_rules()
        patched_rules = {
            "thresholds": {"go": 75.0, "no_go": 45.0},
            "weights": {"margin": 0.5, "risk": 0.2, "market": 0.2, "budget": 0.1},
        }

        v1 = await service.publish_config(config_key, base_rules, "商业决策默认规则 v1")
        v2 = await service.publish_config(config_key, patched_rules, "商业决策默认规则 v2")
        rolled_back = await service.rollback_config(config_key)
        await session.commit()

        ok = bool(rolled_back and rolled_back.get("value") == base_rules)
        payload = {
            "tenant_id": tenant_id,
            "config_key": config_key,
            "published_versions": [v1.get("version"), v2.get("version")],
            "rolled_back_version": rolled_back.get("version") if rolled_back else None,
            "ok": ok,
            "current": rolled_back,
        }
        artifact_path = ROOT / "artifacts" / "ops" / "business_default_config_rollback_acceptance.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**payload, "artifact_path": str(artifact_path).replace('\\', '/')}
    finally:
        await session.close()


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = asyncio.run(_run(tenant_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
