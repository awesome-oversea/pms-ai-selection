"""
RAG 评测与质量统计服务
=======================

为 T7.4 提供最小可执行评测能力：
- 评测集执行
- hit@k / MRR / citation_match_rate / avg_score
- 最小 dashboard 汇总
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.business_defaults import get_rag_evaluation_config

DEFAULT_FEEDBACK_BASELINE_FILENAME = "rag_feedback_learning_cases.json"


@dataclass
class RAGEvalCase:
    query: str
    expected_document_ids: list[str]
    expected_keywords: list[str]
    top_k: int = 5
    threshold: float = 0.1


class RAGEvaluationService:
    def __init__(self, knowledge_service, root: Path | None = None):
        self.knowledge_service = knowledge_service
        self.root = root or Path(__file__).resolve().parents[2]
        self.artifact_dir = self.root / "artifacts" / "knowledge"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _load_feedback_learning_payload(self) -> dict[str, Any]:
        path = self.artifact_dir / DEFAULT_FEEDBACK_BASELINE_FILENAME
        if not path.exists():
            return {"cases": [], "updated_at": None, "artifact_path": str(path).replace('\\', '/')}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"cases": [], "updated_at": None, "artifact_path": str(path).replace('\\', '/')}
        if not isinstance(payload, dict):
            return {"cases": [], "updated_at": None, "artifact_path": str(path).replace('\\', '/')}
        payload.setdefault("cases", [])
        payload.setdefault("updated_at", None)
        payload["artifact_path"] = str(path).replace('\\', '/')
        return payload

    def _load_feedback_learning_cases(self) -> list[dict[str, Any]]:
        return list(self._load_feedback_learning_payload().get("cases", []))

    def build_default_cases(self) -> list[RAGEvalCase]:
        config = get_rag_evaluation_config()
        thresholds = config.get("thresholds", {}) if isinstance(config, dict) else {}
        default_top_k = int(thresholds.get("default_top_k", 5))
        default_threshold = float(thresholds.get("default_threshold", 0.1))
        merged_cases = list(config.get("baseline_cases", []) if isinstance(config, dict) else [])
        merged_cases.extend(self._load_feedback_learning_cases())
        items = []
        for case in merged_cases:
            if not isinstance(case, dict):
                continue
            items.append(
                RAGEvalCase(
                    query=str(case.get("query") or ""),
                    expected_document_ids=list(case.get("expected_document_ids") or []),
                    expected_keywords=list(case.get("expected_keywords") or []),
                    top_k=int(case.get("top_k") or default_top_k),
                    threshold=float(case.get("threshold") or default_threshold),
                )
            )
        return items

    async def run_cases(self, cases: list[RAGEvalCase]) -> dict[str, Any]:
        if not cases:
            return {
                "total_cases": 0,
                "hit_at_k": 0.0,
                "mrr": 0.0,
                "citation_match_rate": 0.0,
                "avg_score": 0.0,
                "cases": [],
            }

        results = []
        hit_count = 0
        reciprocal_ranks: list[float] = []
        citation_hits = 0
        score_sum = 0.0

        for case in cases:
            output = await self.knowledge_service.query_knowledge(case.query, top_k=case.top_k, threshold=case.threshold)
            docs = output.get("results", [])
            matched_rank: int | None = None
            citation_ok = False
            top_score = docs[0].get("score", 0.0) if docs else 0.0
            score_sum += float(top_score)

            for idx, item in enumerate(docs, 1):
                doc_id = item.get("document_id")
                content = item.get("content", "")
                if matched_rank is None and doc_id in case.expected_document_ids:
                    matched_rank = idx
                if any(keyword in content for keyword in case.expected_keywords):
                    citation_ok = True

            hit = matched_rank is not None
            if hit:
                hit_count += 1
                reciprocal_ranks.append(1.0 / matched_rank)
            else:
                reciprocal_ranks.append(0.0)
            if citation_ok:
                citation_hits += 1

            results.append(
                {
                    "query": case.query,
                    "hit": hit,
                    "matched_rank": matched_rank,
                    "citation_ok": citation_ok,
                    "top_score": round(float(top_score), 6),
                    "returned": len(docs),
                }
            )

        total = len(cases)
        payload = {
            "total_cases": total,
            "hit_at_k": round(hit_count / total, 4),
            "mrr": round(sum(reciprocal_ranks) / total, 4),
            "citation_match_rate": round(citation_hits / total, 4),
            "avg_score": round(score_sum / total, 6),
            "cases": results,
        }
        artifact_path = self.artifact_dir / "rag_evaluation_latest.json"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["artifact_path"] = str(artifact_path).replace('\\', '/')
        return payload

    async def ingest_feedback_learning(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        case = {
            "query": query,
            "expected_document_ids": list(payload.get("expected_document_ids") or []),
            "expected_keywords": list(payload.get("expected_keywords") or []),
            "top_k": int(payload.get("top_k") or 5),
            "threshold": float(payload.get("threshold") or 0.1),
        }
        path = self.artifact_dir / DEFAULT_FEEDBACK_BASELINE_FILENAME
        existing = self._load_feedback_learning_cases()
        deduped = [item for item in existing if str(item.get("query") or "").strip() != query]
        deduped.append(case)
        output = {
            "cases": deduped[-50:],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"stored": True, "artifact_path": str(path).replace('\\', '/'), "total_cases": len(output["cases"]), "updated_at": output["updated_at"], "case": case}

    def _load_latest_evaluation_artifact(self) -> dict[str, Any] | None:
        path = self.artifact_dir / "rag_evaluation_latest.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload["artifact_path"] = str(path).replace('\\', '/')
        return payload

    async def build_dashboard(self) -> dict[str, Any]:
        stats = await self.knowledge_service.get_stats()
        config = get_rag_evaluation_config()
        static_cases = list(config.get("baseline_cases", []) if isinstance(config, dict) else [])
        feedback_payload = self._load_feedback_learning_payload()
        feedback_cases = list(feedback_payload.get("cases", []))
        baseline_cases = self.build_default_cases()
        baseline_result = self._load_latest_evaluation_artifact()
        if baseline_cases and (
            not baseline_result or int(baseline_result.get("total_cases") or 0) < len(baseline_cases)
        ):
            baseline_result = await self.run_cases(baseline_cases)
        retrieval_status = "available" if baseline_result else "pending"
        return {
            "knowledge_health": {
                "total_documents": stats.get("total_documents", 0),
                "indexed_documents": stats.get("indexed_documents", 0),
                "total_chunks": stats.get("total_chunks", 0),
                "index_coverage": round(
                    (stats.get("indexed_documents", 0) / max(stats.get("total_documents", 1), 1)), 4
                ),
            },
            "retrieval_quality": {
                "status": retrieval_status,
                "metrics": ["hit_at_k", "mrr", "citation_match_rate", "avg_score"],
                "default_evaluation": baseline_result,
                "artifact_path": (baseline_result or {}).get("artifact_path"),
            },
            "feedback_learning": {
                "status": "available",
                "feedback_case_count": len(feedback_cases),
                "static_baseline_case_count": len(static_cases),
                "combined_baseline_case_count": len(baseline_cases),
                "latest_updated_at": feedback_payload.get("updated_at"),
                "artifact_path": feedback_payload.get("artifact_path"),
                "coverage_ratio": round(len(feedback_cases) / max(len(baseline_cases), 1), 4) if baseline_cases else 0.0,
            },
        }
