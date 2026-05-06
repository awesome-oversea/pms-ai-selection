from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.services.model_finetune_service import ModelFinetuneService

_DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def _run() -> dict:
    service = ModelFinetuneService(session=None, tenant_id=_DEFAULT_TENANT_ID)
    result = await service.run_weekly_finetune(registry_key="default", train_days=7)
    artifact_path = Path("artifacts/llm/local_model_finetune_acceptance.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    acceptance = {
        "accepted": bool(
            result.get("status") == "completed"
            and result.get("evaluation", {}).get("not_regressed") is True
            and Path(result.get("artifact_path") or "").exists()
        ),
        "training_mode": result.get("training_mode"),
        "training_backend": result.get("training_backend"),
        "new_model_version": result.get("new_model_version"),
        "artifact_path": result.get("artifact_path"),
        "latest_artifact_path": result.get("latest_artifact_path"),
        "training_snapshot": result.get("training_snapshot"),
        "evaluation": result.get("evaluation"),
    }
    artifact_path.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    return acceptance


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
