from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "ops" / "kong_canary_manifest.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "gateway": "kong",
        "strategy": "canary",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routes": [
            {
                "route_name": "pms-bff-route",
                "stable_upstream": "pms-api-stable",
                "canary_upstream": "pms-api-canary",
                "traffic_split": {"stable": 90, "canary": 10},
                "match_headers": ["X-Gray-Release", "X-Tenant-ID"],
            }
        ],
        "rollback": {
            "action": "set canary traffic to 0 and re-apply declarative config",
            "target_file": "k8s/gateway/kong-plugins.yml",
        },
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
