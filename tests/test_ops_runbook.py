from pathlib import Path


def test_ops_runbook_exists_and_contains_core_sections():
    path = Path("docs/runbook_oncall_sla_change.md")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "SLA / SLO" in content
    assert "Oncall Rules" in content
    assert "Change Process" in content
    assert "Rollback Rules" in content
    assert "release_quality_gates.py all" in content
    assert "/api/v1/migrations/status" in content
