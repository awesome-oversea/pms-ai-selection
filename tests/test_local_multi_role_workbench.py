from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_local_multi_role_workbench_script_generates_accepted_artifact(tmp_path):
    env = os.environ.copy()
    env.setdefault("SEC_SECRET_KEY", "test-local-multi-role-workbench-32chars")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_multi_role_workbench_acceptance.py",
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

    manifest_path = Path(summary_payload["artifacts"]["scenario_manifest"])
    assert manifest_path.exists()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest_payload["roles"]) == 5
    assert manifest_payload["roles"][0]["role"] == "selection"
    assert manifest_payload["roles"][-1]["role"] == "operations"

    for key in (
        "selection_workbench",
        "manager_overview",
        "procurement_workbench",
        "finance_workbench",
        "operations_workbench",
    ):
        assert Path(summary_payload["artifacts"][key]).exists(), key
