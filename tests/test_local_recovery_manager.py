from __future__ import annotations

from pathlib import Path

import pytest
from scripts.local_recovery_manager import (
    _ensure_within_workspace,
    collect_local_status,
    reset_local_state,
    restore_baseline_artifacts,
)


def test_ensure_within_workspace_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _ensure_within_workspace(tmp_path, "..\\outside.txt")


def test_reset_local_state_removes_selected_targets(tmp_path: Path) -> None:
    feature_store = tmp_path / "data" / "local_feature_store.db"
    knowledge_store = tmp_path / "data" / "local_knowledge.db"
    report_state = tmp_path / "artifacts" / "report_center" / "state.json"
    feature_store.parent.mkdir(parents=True, exist_ok=True)
    report_state.parent.mkdir(parents=True, exist_ok=True)
    feature_store.write_text("feature", encoding="utf-8")
    knowledge_store.write_text("knowledge", encoding="utf-8")
    report_state.write_text("report", encoding="utf-8")

    payload = reset_local_state(tmp_path, include_report_state=True)

    assert payload["status"] == "passed"
    assert not feature_store.exists()
    assert not knowledge_store.exists()
    assert not report_state.exists()


def test_collect_local_status_and_restore_baseline_artifacts(tmp_path: Path) -> None:
    payload = restore_baseline_artifacts(tmp_path)

    assert payload["status"] == "passed"
    status = collect_local_status(tmp_path)

    assert status["targets"]["erp_local_root"]["exists"] is True
    assert status["targets"]["erp_orders"]["exists"] is True
    assert status["targets"]["crm_feedback"]["exists"] is True
