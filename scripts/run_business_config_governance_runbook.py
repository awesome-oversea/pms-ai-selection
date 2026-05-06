from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.accept_business_default_config_rollback import _run as run_rollback_acceptance
from scripts.accept_business_default_configs import _run as run_acceptance
from scripts.export_business_default_configs import build_payload


async def _run(tenant_id: str) -> dict:
    export_payload = build_payload()
    acceptance = await run_acceptance(tenant_id)
    rollback = await run_rollback_acceptance(tenant_id)
    result = {
        "tenant_id": tenant_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "steps": {
            "export": {
                "ok": True,
                "config_count": len((export_payload.get("configs") or {})),
            },
            "acceptance": acceptance,
            "rollback": rollback,
        },
        "ok": bool(acceptance.get("ok") and rollback.get("ok")),
    }
    result["summary"] = {
        "exported_config_count": result["steps"]["export"]["config_count"],
        "acceptance_ok": acceptance.get("ok"),
        "rollback_ok": rollback.get("ok"),
        "verified_config_count": len(acceptance.get("verified") or []),
    }
    artifact_path = ROOT / "artifacts" / "ops" / "business_config_governance_runbook.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["artifact_path"] = str(artifact_path).replace('\\', '/')
    return result


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = asyncio.run(_run(tenant_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
