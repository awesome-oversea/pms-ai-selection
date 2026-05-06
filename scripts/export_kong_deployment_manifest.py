from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "ops" / "kong_deployment_manifest.json"


def main() -> int:
    payload = {
        "runtime": "kong-cluster",
        "deploy_mode": "docker-or-k8s",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": ["local", "test", "preprod", "prod"],
        "dependencies": ["postgresql", "dns", "ingress-controller"],
        "entrypoints": ["docker compose up kong", "kubectl apply -f k8s/gateway/kong.yml"],
        "health_checks": ["/status", "/routes", "/services"],
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
