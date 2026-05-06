from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.ha_topology_service import HATopologyService


def main() -> int:
    status = HATopologyService().build_status()
    checks = {
        "release_workflow": Path(".github/workflows/release.yml").exists(),
        "test_overlay": status["environments"]["test"]["configured"],
        "preprod_overlay": status["environments"]["preprod"]["configured"],
        "prod_overlay": status["environments"]["prod"]["configured"],
        "postgres_ha_manifest": status["postgres_ha"]["primary_count"] >= 1 and status["postgres_ha"]["replica_count"] >= 2,
        "redis_ha_manifest": status["redis_ha"]["master_count"] >= 1 and status["redis_ha"]["replica_count"] >= 2,
        "redis_sentinel": status["redis_ha"]["sentinel_count"] >= 3,
        "rag_service_manifest": status["ai_services"]["rag"]["replica_count"] >= 2,
        "llm_service_manifest": status["ai_services"]["llm"]["replica_count"] >= 2,
        "gateway_split_config": status["gateway_ha"]["split_config"],
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "status": status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
