from __future__ import annotations

import json
from types import SimpleNamespace

from src.workers.celery_schedule_monitor import build_schedule_monitor_status, record_schedule_run


def test_build_schedule_monitor_status_collects_recent_runs(tmp_path, monkeypatch):
    state_path = tmp_path / "celery_schedule_monitor.json"
    monkeypatch.setenv("CELERY_SCHEDULE_MONITOR_PATH", str(state_path))

    record_schedule_run(
        entry_name="scheduled-selection-hourly",
        task_name="src.workers.celery_tasks.execute_selection_task",
        queue_name="selection",
        status="success",
        detail={"task_id": "task-001"},
    )
    record_schedule_run(
        entry_name="bi-kpi-daily",
        task_name="src.workers.celery_tasks.compute_bi_kpi_task",
        queue_name="feedback",
        status="success",
        detail={"tenant_id": "tenant-001"},
    )

    app = SimpleNamespace(
        conf=SimpleNamespace(
            beat_schedule={
                "scheduled-selection-hourly": {
                    "task": "src.workers.celery_tasks.execute_selection_task",
                    "schedule": 3600.0,
                    "args": ["task-001", "tenant-001"],
                },
                "bi-kpi-daily": {
                    "task": "src.workers.celery_tasks.compute_bi_kpi_task",
                    "schedule": 86400.0,
                    "args": ["tenant-001"],
                },
            },
            task_routes={
                "src.workers.celery_tasks.execute_selection_task": {"queue": "selection"},
                "src.workers.celery_tasks.compute_bi_kpi_task": {"queue": "feedback"},
            },
        )
    )

    payload = build_schedule_monitor_status(app)

    assert payload["monitor_type"] == "local-file-monitor"
    assert payload["equivalent_to_flower"] is True
    assert payload["total_recorded_runs"] == 2
    assert len(payload["recent_runs"]) == 2
    assert payload["scheduled_entry_count"] == 2
    assert payload["scheduled_entries"][0]["last_status"] == "success"
    assert payload["scheduled_entries"][1]["last_status"] == "success"


def test_compute_bi_kpi_task_records_monitor_run(tmp_path, monkeypatch):
    from src.workers.celery_tasks import compute_bi_kpi_task

    state_path = tmp_path / "celery_schedule_monitor.json"
    monkeypatch.setenv("CELERY_SCHEDULE_MONITOR_PATH", str(state_path))

    class _FakeWorker:
        def __init__(self, interval_seconds=0.0, bootstrap_delay_seconds=0.0):
            self.interval_seconds = interval_seconds
            self.bootstrap_delay_seconds = bootstrap_delay_seconds

        async def run_once(self, day=None):
            return {"kpi_date": day or "2026-04-19", "log_id": "log-001"}

    monkeypatch.setattr("src.workers.bi_kpi_worker.BIDailyKpiWorker", _FakeWorker)

    result = compute_bi_kpi_task("tenant-demo", "2026-04-19")
    monitor_data = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["kpi_date"] == "2026-04-19"
    assert monitor_data["runs"][-1]["entry_name"] == "bi-kpi-daily"
    assert monitor_data["runs"][-1]["status"] == "success"
    assert monitor_data["tasks"]["src.workers.celery_tasks.compute_bi_kpi_task"]["success_count"] >= 1
