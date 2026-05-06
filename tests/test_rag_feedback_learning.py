import asyncio
from pathlib import Path


class _DummyKnowledgeService:
    async def query_knowledge(self, query, top_k=5, threshold=0.1):
        return {
            "results": [
                {
                    "document_id": "feedback-doc",
                    "content": f"{query} 反馈学习 基线样本",
                    "score": 0.95,
                }
            ]
        }

    async def get_stats(self):
        return {
            "total_documents": 3,
            "indexed_documents": 3,
            "total_chunks": 6,
        }


def test_feedback_learning_case_is_reused(tmp_path: Path):
    from src.services.rag_evaluation import RAGEvaluationService

    service = RAGEvaluationService(_DummyKnowledgeService(), root=tmp_path)
    result = asyncio.run(service.ingest_feedback_learning({
        "query": "如何验证反馈学习样本？",
        "expected_document_ids": ["feedback-doc"],
        "expected_keywords": ["反馈学习"],
        "top_k": 3,
        "threshold": 0.2,
    }))

    assert result["stored"] is True

    cases = service.build_default_cases()
    assert any(case.query == "如何验证反馈学习样本？" for case in cases)

    dashboard = asyncio.run(service.build_dashboard())
    assert dashboard["retrieval_quality"]["default_evaluation"]["total_cases"] >= 1
    assert dashboard["retrieval_quality"]["artifact_path"].endswith("rag_evaluation_latest.json")
    assert dashboard["feedback_learning"]["feedback_case_count"] >= 1
    assert dashboard["feedback_learning"]["combined_baseline_case_count"] >= dashboard["feedback_learning"]["feedback_case_count"]
    assert dashboard["feedback_learning"]["artifact_path"].endswith("rag_feedback_learning_cases.json")
    assert dashboard["feedback_learning"]["latest_updated_at"] is not None
