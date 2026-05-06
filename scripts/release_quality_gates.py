"""
企业发布质量门禁脚本（T8.2 最小基线）
=====================================

用法：
  python scripts/release_quality_gates.py smoke
  python scripts/release_quality_gates.py migration-smoke
  python scripts/release_quality_gates.py perf-smoke
  python scripts/release_quality_gates.py security-smoke
  python scripts/release_quality_gates.py all
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
GATE_ARTIFACT = Path("artifacts") / "release" / "latest_gate_check.json"


def _run(command: list[str]) -> int:
    print(f"[gate] {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode


def _write_gate_record(mode: str, steps: list[dict[str, object]], exit_code: int) -> None:
    GATE_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "mode": mode,
        "status": "passed" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "steps": steps,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    GATE_ARTIFACT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def smoke() -> int:
    code = _run([sys.executable, "-m", "py_compile", "src/main.py"])
    if code != 0:
        return code
    return _run([
        sys.executable,
        "-m",
        "pytest",
        "tests/test_api_integration.py",
        "-k",
        "selection_execution_status or local_feedback_loop or model_finetune or graph or ollama or agent_platform_message_bus or agent_platform_operations or embedding_benchmark or gateway or service_split_status",
        "-q",
    ])


def migration_smoke() -> int:
    script = (
        "import asyncio; "
        "from src.infrastructure.database import init_db, close_db; "
        "async def _m():\n"
        "    await init_db()\n"
        "    await close_db()\n"
        "asyncio.run(_m())"
    )
    return _run([sys.executable, "-c", script])


def perf_smoke() -> int:
    code = _run([sys.executable, "scripts/perf_run_sample.py", "--smoke"])
    if code != 0:
        return code
    return _run([sys.executable, "scripts/perf_baseline.py"])


def security_smoke() -> int:
    return _run([sys.executable, "-m", "pytest", "tests/test_d106_d110.py", "tests/test_security_config.py", "tests/test_rate_limit.py", "-q"])


def _run_mode(mode: str) -> tuple[int, list[dict[str, object]]]:
    single_modes: dict[str, Callable[[], int]] = {
        "smoke": smoke,
        "migration-smoke": migration_smoke,
        "perf-smoke": perf_smoke,
        "security-smoke": security_smoke,
    }
    if mode in single_modes:
        code = single_modes[mode]()
        return code, [{"name": mode, "exit_code": code, "passed": code == 0}]
    if mode == "all":
        steps: list[dict[str, object]] = []
        for name, fn in single_modes.items():
            code = fn()
            steps.append({"name": name, "exit_code": code, "passed": code == 0})
            if code != 0:
                return code, steps
        return 0, steps
    return 2, []


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/release_quality_gates.py <smoke|migration-smoke|perf-smoke|security-smoke|all>")
        return 2

    mode = sys.argv[1]
    if mode not in {"smoke", "migration-smoke", "perf-smoke", "security-smoke", "all"}:
        print(f"unknown gate: {mode}")
        return 2

    exit_code, steps = _run_mode(mode)
    _write_gate_record(mode, steps, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
