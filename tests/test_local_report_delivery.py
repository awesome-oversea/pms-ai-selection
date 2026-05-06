from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_local_report_delivery_script_generates_accepted_artifact(tmp_path):
    env = os.environ.copy()
    env.setdefault("SEC_SECRET_KEY", "test-local-report-delivery-32chars")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_report_delivery_acceptance.py",
            "--output-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    summary_candidates = sorted(tmp_path.glob("*/summary.json"))
    assert summary_candidates, result.stdout
    summary_path = summary_candidates[-1]
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["accepted"] is True
    assert summary_payload["status"] == "passed"
    assert summary_payload["task_id"]
    assert "finance_pdf" in summary_payload["report_ids"]
