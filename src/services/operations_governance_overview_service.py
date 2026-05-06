from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.services.business_config_governance_service import BusinessConfigGovernanceService


class OperationsGovernanceOverviewService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]

    def _read_json(self, relative_path: str) -> dict[str, Any] | None:
        path = self.root / relative_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def build_status(self) -> dict[str, Any]:
        business = BusinessConfigGovernanceService(self.root).build_status()
        rag = self._read_json("artifacts/knowledge/rag_governance_runbook.json") or {}
        rag_eval = self._read_json("artifacts/knowledge/rag_evaluation_latest.json") or {}
        rag_feedback = self._read_json("artifacts/knowledge/rag_feedback_learning_cases.json") or {}
        business_summary = {
            "last_executed_at": (business.get("runbook") or {}).get("executed_at"),
            "last_result_ok": (business.get("runbook") or {}).get("ok"),
            "summary": (business.get("runbook") or {}).get("summary", {}),
        }
        rag_summary = {
            "last_executed_at": rag.get("executed_at"),
            "last_result_ok": rag.get("ok"),
            "summary": rag.get("summary", {}),
        }
        return {
            "business_config_governance": {
                **business,
                "latest_execution": business_summary,
            },
            "rag_governance": {
                "runbook": rag,
                "latest_execution": rag_summary,
                "latest_evaluation": rag_eval,
                "feedback_learning": rag_feedback,
                "artifacts": {
                    "runbook": "artifacts/knowledge/rag_governance_runbook.json",
                    "latest_evaluation": "artifacts/knowledge/rag_evaluation_latest.json",
                    "feedback_learning": "artifacts/knowledge/rag_feedback_learning_cases.json",
                },
                "status": "ready" if rag.get("ok") else "partial",
            },
            "status": "ready" if business.get("status") == "ready" and rag.get("ok") else "partial",
        }
