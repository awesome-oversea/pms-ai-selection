from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.kettle_etl_service import KettleETLService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local kettle-compatible ETL job")
    parser.add_argument(
        "--runner",
        default="python-local",
        choices=["python-local", "ray-compatible"],
        help="Execution runner to use for the local ETL pipeline.",
    )
    args = parser.parse_args()
    payload = KettleETLService(root=ROOT).run(runner=args.runner)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
