from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.delivery_readiness_service import DeliveryReadinessService


def _status_text(ok: bool | None) -> str:
    if ok is True:
        return "通过"
    if ok is False:
        return "未通过"
    return "未知"


def build_summary() -> dict:
    payload = DeliveryReadinessService(ROOT).build_status()
    steps = payload.get("steps", {}) if isinstance(payload, dict) else {}
    business = steps.get("business_governance", {}) if isinstance(steps, dict) else {}
    rag = steps.get("rag_governance", {}) if isinstance(steps, dict) else {}
    exceptions = steps.get("main_chain_exceptions", {}) if isinstance(steps, dict) else {}
    artifacts = steps.get("artifacts", []) if isinstance(steps, dict) else []
    artifact_ready_count = sum(1 for item in artifacts if item.get("exists")) if isinstance(artifacts, list) else 0
    artifact_total_count = len(artifacts) if isinstance(artifacts, list) else 0

    lines = [
        f"交付巡检状态：{payload.get('status', 'pending')}",
        f"巡检时间：{payload.get('executed_at', '-')}",
        f"配置治理：{_status_text(business.get('ok'))}",
        f"RAG治理：{_status_text(rag.get('ok'))}",
        f"主链异常验收：{_status_text(exceptions.get('ok'))}",
        f"工件就绪：{artifact_ready_count}/{artifact_total_count}",
    ]

    summary = {
        "status": payload.get("status"),
        "executed_at": payload.get("executed_at"),
        "delivery_ready": payload.get("status") == "ready",
        "business_governance": {
            "status": _status_text(business.get("ok")),
            "summary": business.get("summary", {}),
        },
        "rag_governance": {
            "status": _status_text(rag.get("ok")),
            "summary": rag.get("summary", {}),
        },
        "main_chain_exceptions": {
            "status": _status_text(exceptions.get("ok")),
            "summary": exceptions.get("summary", {}),
        },
        "artifacts": {
            "ready_count": artifact_ready_count,
            "total_count": artifact_total_count,
            "items": artifacts,
        },
        "acceptance_conclusion": {
            "summary_lines": lines,
            "next_action": "可进入交付/验收沟通" if payload.get("status") == "ready" else "需先处理未通过项",
        },
    }
    return summary


def main() -> int:
    summary = build_summary()
    artifact_path = ROOT / "artifacts" / "ops" / "delivery_conclusion_summary.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "artifact_path": str(artifact_path).replace('\\', '/')}, ensure_ascii=False, indent=2))
    return 0 if summary.get("delivery_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
