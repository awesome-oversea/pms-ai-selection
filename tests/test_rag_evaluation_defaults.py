import asyncio


class _DummyKnowledgeService:
    async def query_knowledge(self, query, top_k=5, threshold=0.1):
        return {
            "results": [
                {
                    "document_id": "doc-1",
                    "content": f"{query} 默认知识库 回滚 版本",
                    "score": 0.9,
                }
            ]
        }

    async def get_stats(self):
        return {
            "total_documents": 2,
            "indexed_documents": 2,
            "total_chunks": 4,
        }


def test_rag_default_baseline_cases():
    from src.services.rag_evaluation import RAGEvaluationService

    service = RAGEvaluationService(_DummyKnowledgeService())
    cases = service.build_default_cases()

    assert len(cases) >= 2
    assert all(case.top_k >= 1 for case in cases)


def test_rag_dashboard_contains_default_evaluation():
    from src.services.rag_evaluation import RAGEvaluationService

    service = RAGEvaluationService(_DummyKnowledgeService())
    dashboard = asyncio.run(service.build_dashboard())

    retrieval_quality = dashboard["retrieval_quality"]
    assert retrieval_quality["status"] == "available"
    assert retrieval_quality["default_evaluation"]["total_cases"] >= 2
    assert retrieval_quality["artifact_path"].endswith("rag_evaluation_latest.json")
