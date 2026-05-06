from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "ops" / "efk_stack.json"
ARTIFACT = ROOT / "artifacts" / "ops" / "efk_stack_manifest.json"


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    components = payload.get("components", {}) if isinstance(payload, dict) else {}
    manifest = {
        "logging_stack": payload.get("stack", "efk"),
        "status": payload.get("status", "ready"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": "artifacts/ops/efk_stack.json",
        "component_count": len(components),
        "components": components,
        "queries": payload.get("queries", {}),
        "artifacts": payload.get("artifacts", {}),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
