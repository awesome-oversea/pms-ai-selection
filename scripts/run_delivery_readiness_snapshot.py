from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_business_config_governance_runbook import _run as run_business_governance
from scripts.run_local_main_chain_exception_acceptance import _run_acceptance as run_main_chain_exception_acceptance
from scripts.run_rag_governance_runbook import _run as run_rag_governance
from src.services.operations_governance_overview_service import OperationsGovernanceOverviewService


REQUIRED_ARTIFACTS = [
    "artifacts/ops/business_config_governance_runbook.json",
    "artifacts/ops/business_default_config_acceptance.json",
    "artifacts/ops/business_default_config_rollback_acceptance.json",
    "artifacts/knowledge/rag_governance_runbook.json",
    "artifacts/knowledge/rag_evaluation_latest.json",
    "artifacts/knowledge/rag_feedback_learning_cases.json",
]


def _latest_exception_summary() -> dict[str, object]:
    root = ROOT / "artifacts" / "local_main_chain_exceptions"
    candidates = sorted(root.glob("*/summary.json"))
    if not candidates:
        return {"ok": False, "artifact_path": None, "summary": {}}
    path = candidates[-1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": bool(payload.get("accepted")),
        "artifact_path": str(path).replace('\\', '/'),
        "summary": {
            "status": payload.get("status"),
            "check_count": len(payload.get("checks") or []),
            "passed_check_count": sum(1 for item in (payload.get("checks") or []) if item.get("passed")),
        },
    }


async def _run(tenant_id: str) -> dict:
    business = await run_business_governance(tenant_id)
    rag = await run_rag_governance()
    exception_summary = await run_main_chain_exception_acceptance()
    exception_artifact_path = exception_summary.get("artifacts", {}).get("summary")
    main_chain_exceptions = {
        "ok": bool(exception_summary.get("accepted")),
        "artifact_path": exception_artifact_path,
        "summary": {
            "status": exception_summary.get("status"),
            "check_count": len(exception_summary.get("checks") or []),
            "passed_check_count": sum(1 for item in (exception_summary.get("checks") or []) if item.get("passed")),
        },
    }
    overview = OperationsGovernanceOverviewService(ROOT).build_status()
    artifact_checks = []
    for relative_path in REQUIRED_ARTIFACTS:
        path = ROOT / relative_path
        artifact_checks.append({
            "artifact": relative_path,
            "exists": path.exists(),
        })
    ok = bool(
        business.get("ok")
        and rag.get("ok")
        and main_chain_exceptions.get("ok")
        and overview.get("status") == "ready"
        and all(item["exists"] for item in artifact_checks)
    )
    result = {
        "tenant_id": tenant_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "steps": {
            "business_governance": {
                "ok": business.get("ok"),
                "artifact_path": business.get("artifact_path"),
                "summary": business.get("summary", {}),
            },
            "rag_governance": {
                "ok": rag.get("ok"),
                "artifact_path": rag.get("artifact_path"),
                "summary": rag.get("summary", {}),
            },
            "main_chain_exceptions": main_chain_exceptions,
            "operations_overview": {
                "status": overview.get("status"),
            },
            "artifacts": artifact_checks,
        },
        "ok": ok,
    }
    result["summary"] = {
        "business_governance_ok": business.get("ok"),
        "rag_governance_ok": rag.get("ok"),
        "main_chain_exceptions_ok": main_chain_exceptions.get("ok"),
        "operations_overview_status": overview.get("status"),
        "artifact_ready_count": sum(1 for item in artifact_checks if item["exists"]),
        "artifact_total_count": len(artifact_checks),
    }
    artifact_path = ROOT / "artifacts" / "ops" / "delivery_readiness_snapshot.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["artifact_path"] = str(artifact_path).replace('\\', '/')
    return result


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    result = asyncio.run(_run(tenant_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
