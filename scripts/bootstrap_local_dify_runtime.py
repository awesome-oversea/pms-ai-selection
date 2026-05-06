from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_dify_runtime_manager import LocalDifyRuntimeManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap official Dify self-host runtime for local PMS acceptance.")
    parser.add_argument(
        "action",
        nargs="?",
        default="prepare",
        choices=["prepare", "up", "down", "ps"],
        help="Lifecycle action to run against the local Dify runtime.",
    )
    parser.add_argument(
        "--version",
        default=LocalDifyRuntimeManager.DEFAULT_RELEASE_VERSION,
        help="Official Dify release tag to download and prepare.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Redownload the official runtime and recreate the local runtime directory.",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull only missing container images before bringing the runtime up.",
    )
    args = parser.parse_args()

    manager = LocalDifyRuntimeManager(PROJECT_ROOT, version=args.version)
    summary = manager.prepare_runtime(force_refresh=args.force_refresh)

    if args.action == "up":
        if args.pull:
            summary["pull"] = manager.pull()
        summary["up"] = manager.up()
        up_payload = summary["up"]
        if int((up_payload or {}).get("returncode") or 0) == 0:
            summary["readiness"] = manager.wait_until_ready()
        else:
            summary["readiness"] = {
                "ready": False,
                "status_code": None,
                "payload": None,
                "url": f"{manager.base_url}/console/api/setup",
                "error": str((up_payload or {}).get("stderr") or (up_payload or {}).get("stdout") or "docker compose up failed"),
            }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if bool((summary.get("readiness") or {}).get("ready")) else 1

    if args.action == "down":
        summary["down"] = manager.down()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if int((summary.get("down") or {}).get("returncode") or 0) == 0 else 1

    if args.action == "ps":
        summary["ps"] = manager.ps()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if int((summary.get("ps") or {}).get("returncode") or 0) == 0 else 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
