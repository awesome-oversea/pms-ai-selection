from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.services.local_crawl_runtime_service import LocalCrawlRuntimeService


async def _run() -> dict:
    runtime_service = LocalCrawlRuntimeService()
    runtime_acceptance = await runtime_service.run_acceptance(query="bluetooth speaker")

    scheduler_command = [
        sys.executable,
        "-m",
        "src.workers.crawl_scheduler_worker",
        "--run-once",
        "--query",
        "bluetooth speaker",
        "--mode",
        "real",
    ]
    scheduler = subprocess.run(
        scheduler_command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    scheduler_payload = json.loads(scheduler.stdout) if scheduler.stdout.strip() else {}
    artifact_path = PROJECT_ROOT / "artifacts" / "ops" / "local_crawl_platform_acceptance.json"
    payload = {
        "accepted": bool(runtime_acceptance.get("accepted")) and bool(scheduler_payload.get("accepted")),
        "runtime_acceptance": runtime_acceptance,
        "scheduler": scheduler_payload,
        "scheduler_command": scheduler_command,
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
