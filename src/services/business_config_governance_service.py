from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BusinessConfigGovernanceService:
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
        acceptance = self._read_json("artifacts/ops/business_default_config_acceptance.json") or {}
        rollback = self._read_json("artifacts/ops/business_default_config_rollback_acceptance.json") or {}
        runbook = self._read_json("artifacts/ops/business_config_governance_runbook.json") or {}
        return {
            "default_config_acceptance": acceptance,
            "rollback_acceptance": rollback,
            "runbook": runbook,
            "artifacts": {
                "default_config_acceptance": "artifacts/ops/business_default_config_acceptance.json",
                "rollback_acceptance": "artifacts/ops/business_default_config_rollback_acceptance.json",
                "runbook": "artifacts/ops/business_config_governance_runbook.json",
            },
            "status": "ready" if acceptance.get("ok") and rollback.get("ok") else "partial",
        }
