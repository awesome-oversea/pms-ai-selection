from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_dify_runtime_acceptance_service import LocalDifyRuntimeAcceptanceService


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Dify self-host runtime acceptance for PMS.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "local_dify_runtime",
        help="Directory used to store the acceptance artifacts.",
    )
    parser.add_argument("--admin-email", default="admin@pms.local", help="Local Dify admin email used for setup/login.")
    parser.add_argument("--admin-name", default="PMS Admin", help="Local Dify admin display name.")
    parser.add_argument(
        "--admin-password",
        default="PmsDify!2026",
        help="Local Dify admin password used for setup/login.",
    )
    args = parser.parse_args()

    summary = LocalDifyRuntimeAcceptanceService(PROJECT_ROOT).run(
        output_root=args.output_root,
        admin_email=args.admin_email,
        admin_name=args.admin_name,
        admin_password=args.admin_password,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary.get("accepted")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
