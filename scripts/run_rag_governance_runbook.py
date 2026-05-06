from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.rag_evaluation import RAGEvaluationService


class _RunbookKnowledgeService:
    async def query_knowledge(self, query, top_k=5, threshold=0.1):
        return {
            "results": [
                {
                    "document_id": "runbook-doc",
                    "content": f"{query} 默认知识库 回滚 版本 反馈学习",
                    "score": 0.92,
                }
            ]
        }

    async def get_stats(self):
        return {
            "total_documents": 4,
            "indexed_documents": 4,
            "total_chunks": 8,
        }


async def _run() -> dict:
    service = RAGEvaluationService(_RunbookKnowledgeService(), root=ROOT)
    feedback = await service.ingest_feedback_learning(
        {
            "query": "如何通过 runbook 验证 RAG 反馈学习？",
            "expected_document_ids": ["runbook-doc"],
            "expected_keywords": ["反馈学习", "默认知识库"],
            "top_k": 5,
            "threshold": 0.1,
        }
    )
    evaluation = await service.run_cases(service.build_default_cases())
    dashboard = await service.build_dashboard()
    result = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "steps": {
            "feedback_learning": feedback,
            "evaluation": {
                "ok": evaluation.get("total_cases", 0) >= 1,
                "artifact_path": evaluation.get("artifact_path"),
                "total_cases": evaluation.get("total_cases", 0),
            },
            "dashboard": {
                "ok": dashboard.get("feedback_learning", {}).get("feedback_case_count", 0) >= 1,
                "artifact_path": dashboard.get("feedback_learning", {}).get("artifact_path"),
                "feedback_case_count": dashboard.get("feedback_learning", {}).get("feedback_case_count", 0),
            },
        },
    }
    result["ok"] = bool(result["steps"]["evaluation"]["ok"] and result["steps"]["dashboard"]["ok"])
    result["summary"] = {
        "feedback_learning_ok": feedback.get("stored"),
        "evaluation_ok": result["steps"]["evaluation"]["ok"],
        "dashboard_ok": result["steps"]["dashboard"]["ok"],
        "evaluated_case_count": result["steps"]["evaluation"]["total_cases"],
        "feedback_case_count": result["steps"]["dashboard"]["feedback_case_count"],
    }
    artifact_path = ROOT / "artifacts" / "knowledge" / "rag_governance_runbook.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["artifact_path"] = str(artifact_path).replace('\\', '/')
    return result


def main() -> int:
    result = asyncio.run(_run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
