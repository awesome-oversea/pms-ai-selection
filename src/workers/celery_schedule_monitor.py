from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_STATE_PATH = Path("artifacts") / "ops" / "celery_schedule_monitor.json"


def get_state_path() -> Path:
    raw_path = os.getenv("CELERY_SCHEDULE_MONITOR_PATH")
    path = Path(raw_path) if raw_path else _DEFAULT_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or get_state_path()
    if not state_path.exists():
        return {"runs": [], "tasks": {}}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"runs": [], "tasks": {}}
    if not isinstance(payload, dict):
        return {"runs": [], "tasks": {}}
    payload.setdefault("runs", [])
    payload.setdefault("tasks", {})
    return payload


def _save_state(state: dict[str, Any], path: Path | None = None) -> None:
    state_path = path or get_state_path()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_schedule_run(
    *,
    entry_name: str,
    task_name: str,
    queue_name: str,
    status: str,
    detail: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    state = _load_state(path)
    event = {
        "entry_name": entry_name,
        "task_name": task_name,
        "queue_name": queue_name,
        "status": status,
        "recorded_at": _now_iso(),
        "detail": detail or {},
    }
    runs = list(state.get("runs") or [])
    runs.append(event)
    state["runs"] = runs[-50:]

    task_state = dict((state.get("tasks") or {}).get(task_name) or {})
    task_state["entry_name"] = entry_name
    task_state["queue_name"] = queue_name
    task_state["last_status"] = status
    task_state["last_run_at"] = event["recorded_at"]
    task_state["last_detail"] = event["detail"]
    task_state["success_count"] = int(task_state.get("success_count") or 0) + (1 if status == "success" else 0)
    task_state["failure_count"] = int(task_state.get("failure_count") or 0) + (1 if status != "success" else 0)
    tasks = dict(state.get("tasks") or {})
    tasks[task_name] = task_state
    state["tasks"] = tasks
    _save_state(state, path)
    return event


def _normalize_schedule_value(raw_value: Any) -> Any:
    if isinstance(raw_value, (int, float, str)):
        return raw_value
    return str(raw_value)


def build_schedule_monitor_status(celery_app: Any, *, path: Path | None = None) -> dict[str, Any]:
    state_path = path or get_state_path()
    state = _load_state(state_path)
    beat_schedule = getattr(getattr(celery_app, "conf", None), "beat_schedule", {}) or {}
    task_routes = getattr(getattr(celery_app, "conf", None), "task_routes", {}) or {}
    entries: list[dict[str, Any]] = []
    tasks = dict(state.get("tasks") or {})

    for entry_name, config in beat_schedule.items():
        task_name = str(config.get("task") or "")
        task_state = dict(tasks.get(task_name) or {})
        route = task_routes.get(task_name, {}) if isinstance(task_routes, dict) else {}
        entries.append(
            {
                "entry_name": entry_name,
                "task_name": task_name,
                "queue_name": route.get("queue") or task_state.get("queue_name"),
                "schedule": _normalize_schedule_value(config.get("schedule")),
                "args_preview": list(config.get("args") or [])[:3],
                "last_status": task_state.get("last_status", "never-run"),
                "last_run_at": task_state.get("last_run_at"),
                "success_count": int(task_state.get("success_count") or 0),
                "failure_count": int(task_state.get("failure_count") or 0),
            }
        )

    recent_runs = list(reversed(list(state.get("runs") or [])[-10:]))
    return {
        "monitor_type": "local-file-monitor",
        "equivalent_to_flower": True,
        "monitor_ready": True,
        "state_path": str(state_path),
        "scheduled_entry_count": len(entries),
        "scheduled_entries": entries,
        "total_recorded_runs": len(state.get("runs") or []),
        "recent_runs": recent_runs,
    }
