from __future__ import annotations

from pathlib import Path

from scripts.run_local_pilot_acceptance import (
    run_runtime_baseline,
    run_scenario_catalog_smoke,
    validate_local_pilot_package,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "data" / "local_pilot"


def test_validate_local_pilot_package_passes_for_repo_package() -> None:
    result = validate_local_pilot_package(PACKAGE_ROOT)

    assert result["status"] == "passed"


def test_run_scenario_catalog_smoke_matches_expected_scenarios() -> None:
    result = run_scenario_catalog_smoke(PACKAGE_ROOT)

    assert result["status"] == "passed"
    assert len(result["cases"]) >= 4
    assert all(item["matched"] for item in result["cases"])


def test_run_runtime_baseline_returns_summary_and_plan() -> None:
    result = run_runtime_baseline()

    assert "summary" in result
    assert "plan" in result
    assert "validation_checks" in result
