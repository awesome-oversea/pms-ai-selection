from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventDrivenSchedulerService:
    def __init__(self, state_path: Path | str | None = None) -> None:
        self.state_path = Path(state_path or Path("artifacts") / "data_platform" / "event_driven_scheduler_state.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"executions": [], "last_evaluation": None}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("executions", [])
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"executions": [], "last_evaluation": None}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _build_trigger_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []

        backlog = int(payload.get("kafka_backlog") or 0)
        backlog_threshold = int(payload.get("kafka_backlog_threshold") or 10000)
        if backlog > backlog_threshold:
            triggers.append(
                {
                    "trigger_type": "backlog_spike",
                    "flow_key": "scale_stream_consumers",
                    "severity": "high",
                    "reason": f"Kafka backlog {backlog} > {backlog_threshold}",
                    "inputs": {"kafka_backlog": backlog, "threshold": backlog_threshold},
                }
            )

        trends_growth = float(payload.get("google_trends_growth_percent") or 0.0)
        trends_threshold = float(payload.get("google_trends_threshold_percent") or 200.0)
        if trends_growth > trends_threshold:
            triggers.append(
                {
                    "trigger_type": "google_trends_spike",
                    "flow_key": "run_market_insight_flow",
                    "severity": "high",
                    "reason": f"搜索热度上涨 {trends_growth}% > {trends_threshold}%",
                    "inputs": {"growth_percent": trends_growth, "threshold_percent": trends_threshold},
                }
            )

        negative_rate = float(payload.get("negative_review_rate") or 0.0)
        negative_threshold = float(payload.get("negative_review_threshold") or 0.2)
        if negative_rate > negative_threshold:
            triggers.append(
                {
                    "trigger_type": "negative_review_spike",
                    "flow_key": "run_competitor_alert_flow",
                    "severity": "high",
                    "reason": f"差评率 {negative_rate:.4f} > {negative_threshold:.4f}",
                    "inputs": {"negative_review_rate": negative_rate, "threshold": negative_threshold},
                }
            )
        return triggers

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        triggers = self._build_trigger_results(payload)
        execution = {
            "executed_at": self._now_iso(),
            "trigger_count": len(triggers),
            "triggers": triggers,
            "triggered": bool(triggers),
            "source": payload.get("source") or "event_scheduler_api",
        }
        executions = list(self._state.get("executions") or [])
        executions.append(execution)
        self._state["executions"] = executions[-50:]
        self._state["last_evaluation"] = execution
        self._save_state()
        return {
            "scheduler": "prefect-compatible-local",
            "triggered": bool(triggers),
            "trigger_count": len(triggers),
            "executions": triggers,
            "last_evaluation": execution,
        }

    def build_status(self) -> dict[str, Any]:
        executions = list(self._state.get("executions") or [])
        trigger_counts: dict[str, int] = {}
        for execution in executions:
            for trigger in execution.get("triggers") or []:
                trigger_type = str(trigger.get("trigger_type") or "unknown")
                trigger_counts[trigger_type] = trigger_counts.get(trigger_type, 0) + 1
        return {
            "scheduler": "prefect-compatible-local",
            "state_path": str(self.state_path),
            "execution_count": len(executions),
            "trigger_counts": trigger_counts,
            "last_evaluation": self._state.get("last_evaluation"),
            "supported_triggers": [
                "backlog_spike",
                "google_trends_spike",
                "negative_review_spike",
            ],
            "platform_ready": True,
        }
