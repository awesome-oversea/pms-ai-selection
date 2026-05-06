from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.services.kettle_etl_service import KettleETLService


def test_kettle_etl_service_runs_supplier_and_finance_etl() -> None:
    payload = KettleETLService().run()

    assert payload["job_type"] == "kettle_etl"
    assert payload["etl_engine"] == "pandas-dask-compatible"
    assert payload["runner"] == "python-local"
    assert payload["quality_summary"]["all_required_fields_ready"] is True
    assert payload["quality_summary"]["supplier_rows"] == 2
    assert payload["quality_summary"]["finance_rows"] == 1
    assert payload["quality_summary"]["quality_score"] >= 0.8
    assert payload["quality_summary"]["business_consumable"] is True
    assert payload["business_consumable"] is True
    assert payload["latest_run_quality_score"] >= 0.8
    assert payload["summary"]["supplier_count"] == 2
    assert payload["summary"]["finance_count"] == 1
    assert payload["pipelines"]["supplier_quote_etl"][0]["supplier_code"] == "SUP-ERP-001"
    assert payload["pipelines"]["finance_profit_etl"][0]["target_profit"] == 99.9


def test_kettle_etl_service_supports_ray_compatible_runner() -> None:
    payload = KettleETLService().run(runner="ray-compatible")

    assert payload["runner"] == "ray-compatible"
    assert payload["execution_mode"] == "actor_parallel"
    assert len(payload["actors"]) == 2
    assert payload["actors"][0]["actor"] == "ray-compatible.supplier_etl_actor"
    assert payload["actors"][1]["actor"] == "ray-compatible.finance_etl_actor"


def test_run_kettle_etl_job_script_supports_runner_switch() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_kettle_etl_job.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--runner", "ray-compatible"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["runner"] == "ray-compatible"
    assert payload["execution_mode"] == "actor_parallel"
