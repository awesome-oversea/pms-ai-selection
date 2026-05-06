from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DeliveryReadinessService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]

    def build_status(self) -> dict[str, Any]:
        path = self.root / "artifacts" / "ops" / "delivery_readiness_snapshot.json"
        if not path.exists():
            return {
                "status": "pending",
                "artifact_path": "artifacts/ops/delivery_readiness_snapshot.json",
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "partial",
                "artifact_path": "artifacts/ops/delivery_readiness_snapshot.json",
            }
        payload["status"] = "ready" if payload.get("ok") else "partial"
        payload["artifact_path"] = "artifacts/ops/delivery_readiness_snapshot.json"
        return payload
