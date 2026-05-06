from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.security_backup import BackupManager, RecoveryTester


async def _run() -> dict:
    backup_manager = BackupManager(root=ROOT, persist_state=True)
    recovery_tester = RecoveryTester(root=ROOT, persist_state=True)

    backup_jobs = await backup_manager.run_scheduled_backups()
    recovery_tests = await recovery_tester.run_all_tests()

    backup_stats = backup_manager.get_stats()
    recovery_stats = recovery_tester.get_stats()

    checks = {
        "backup_jobs_completed": len(backup_jobs) >= 3 and all(job.status.value == "completed" for job in backup_jobs),
        "recovery_tests_passed": len(recovery_tests) >= 4 and all(test.passed for test in recovery_tests),
        "backup_snapshot_written": Path(backup_stats["latest_snapshot"]).exists(),
        "recovery_snapshot_written": Path(recovery_stats["latest_snapshot"]).exists(),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "backup": backup_stats,
        "recovery": recovery_stats,
    }


def main() -> int:
    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
