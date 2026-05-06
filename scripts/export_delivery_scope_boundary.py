from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.delivery_conclusion_service import DeliveryConclusionService
from src.services.delivery_readiness_service import DeliveryReadinessService


def build_boundary() -> dict:
    readiness = DeliveryReadinessService(ROOT).build_status()
    conclusion = DeliveryConclusionService(ROOT).build_status()
    boundary = {
        "delivery_status": readiness.get("status"),
        "executed_at": readiness.get("executed_at") or conclusion.get("executed_at"),
        "original_business_scope": {
            "local_closed_loop_validated": [
                "selection_main_chain",
                "selection_close_loop",
                "approval_flow",
                "recommendation_adoption",
                "execution_feedback_sync",
                "rescore_and_profit_trace",
            ],
            "exception_paths_validated": [
                "approval_reject_closed",
                "non_go_adoption_blocked",
                "missing_execution_result_safe_exit",
                "partial_feedback_loop_exposes_gap",
            ],
            "governance_validated": [
                "business_config_governance",
                "rag_governance",
                "operations_governance_overview",
                "delivery_readiness_snapshot",
            ],
        },
        "current_delivery_boundary": {
            "ready_for_delivery_communication": bool(conclusion.get("delivery_ready")),
            "validated_scope": "local closed-loop and governance acceptance",
            "not_claimed_as_completed": [
                "external staging integration",
                "real external API full production联调",
                "production-grade multi-env deployment beyond current local acceptance boundary",
                "all externally blocked capabilities listed in task plan",
            ],
        },
        "acceptance_summary": conclusion.get("acceptance_conclusion", {}),
        "next_action": "按当前边界进入交付/验收沟通，并对外明确本地闭环已通过、外部阻塞项未纳入本次完成口径",
    }
    return boundary


def main() -> int:
    payload = build_boundary()
    artifact_path = ROOT / "artifacts" / "ops" / "delivery_scope_boundary.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**payload, "artifact_path": str(artifact_path).replace('\\', '/')}, ensure_ascii=False, indent=2))
    return 0 if payload.get("delivery_status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
