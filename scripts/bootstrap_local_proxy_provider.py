from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_proxy_runtime_service import LocalProxyRuntimeService
from src.services.proxy_provider_service import ProxyProviderService


def main() -> None:
    runtime = ProxyProviderService().build_status(include_probe=True)
    if runtime.get("configuration_ready"):
        payload = {
            "accepted": bool(runtime.get("probe", {}).get("ready")),
            "mode": "configured-provider",
            "configuration_ready": bool(runtime.get("configuration_ready")),
            "proxy_pool_source": runtime.get("proxy_pool_source"),
            "provider_runtime": runtime,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    else:
        local_runtime = LocalProxyRuntimeService().run_acceptance()
        payload = {
            "accepted": bool(local_runtime.get("accepted")),
            "mode": "local-self-hosted",
            "configuration_ready": bool(local_runtime.get("provider_runtime", {}).get("configuration_ready")),
            "proxy_pool_source": local_runtime.get("provider_runtime", {}).get("proxy_pool_source"),
            "provider_runtime": local_runtime.get("provider_runtime"),
            "local_runtime": local_runtime.get("runtime"),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    artifact_path = PROJECT_ROOT / "artifacts" / "ops" / "local_proxy_provider_acceptance.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
