from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["test", "staging", "preprod", "prod"], required=True)
    parser.add_argument("--reason", default="manual rollback")
    args = parser.parse_args()

    artifact_dir = Path("artifacts/release")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "target": args.target,
        "status": "rolled_back",
        "reason": args.reason,
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
    }
    (artifact_dir / "latest_release.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
