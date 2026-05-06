from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.business_defaults import DEFAULT_CONFIG_DESCRIPTIONS, get_business_default_config_bundle
from src.infrastructure.database import get_async_session_factory
from src.services.config_center_service import ConfigCenterService


async def _run(tenant_id: str) -> dict:
    session = get_async_session_factory()()
    try:
        service = ConfigCenterService(session, tenant_id=tenant_id)
        bundle = get_business_default_config_bundle()
        published = []
        verified = []
        for config_key, value in bundle.items():
            current = await service.publish_config(
                config_key,
                value,
                DEFAULT_CONFIG_DESCRIPTIONS.get(config_key, "业务默认配置基线"),
            )
            read_back = await service.get_config(config_key)
            matches = bool(read_back and read_back.get("value") == value)
            published.append({"config_key": config_key, "version": current.get("version")})
            verified.append({
                "config_key": config_key,
                "exists": read_back is not None,
                "matches": matches,
                "version": read_back.get("version") if read_back else None,
            })
        await session.commit()
        ok = all(item["exists"] and item["matches"] for item in verified)
        payload = {"tenant_id": tenant_id, "ok": ok, "published": published, "verified": verified}
        artifact_path = ROOT / "artifacts" / "ops" / "business_default_config_acceptance.json"
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
