from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_flink_checkpoint_acceptance_service import LocalFlinkCheckpointAcceptanceService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Flink + Kafka checkpoint acceptance.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "local_flink_checkpoint",
        help="Directory used to store the acceptance artifacts.",
    )
    args = parser.parse_args()

    summary = LocalFlinkCheckpointAcceptanceService(PROJECT_ROOT).run(output_root=args.output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary.get("accepted")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
