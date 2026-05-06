from __future__ import annotations

import pytest
from src.services.selection_service import SelectionTaskService


class _DummySession:
    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None


@pytest.mark.asyncio
async def test_similar_case_queries_use_local_knowledge_when_session_has_no_execute(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _UnexpectedKnowledgeService:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("database knowledge service should not be used for dummy sessions")

    class _FakeLocalKnowledgeService:
        async def query_selection_cases(self, *, query: str, top_k: int, threshold: float):
            calls["selection"] = {
                "query": query,
                "top_k": top_k,
                "threshold": threshold,
            }
            return {
                "query": query,
                "case_type": "selection_history_case",
                "total_found": 1,
                "processing_time_ms": 12.5,
                "results": [{"id": "case-1"}],
            }

        async def query_review_cases(self, *, query: str, top_k: int, threshold: float):
            calls["review"] = {
                "query": query,
                "top_k": top_k,
                "threshold": threshold,
            }
            return {
                "query": query,
                "case_type": "crm_review_case",
                "total_found": 1,
                "processing_time_ms": 8.0,
                "results": [{"id": "review-1"}],
            }

    monkeypatch.setattr("src.services.knowledge_service.KnowledgeService", _UnexpectedKnowledgeService)
    monkeypatch.setattr("src.services.local_knowledge_service.LocalKnowledgeService", _FakeLocalKnowledgeService)

    service = SelectionTaskService(_DummySession(), tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
    task_payload = {
        "query": "wireless earbuds",
        "category": "electronics",
        "target_market": "US",
    }

    history_result = await service._load_similar_history_cases(task_payload, top_k=2)
    review_result = await service._load_similar_review_cases(task_payload, top_k=2)

    assert history_result["total_found"] == 1
    assert review_result["total_found"] == 1
    assert calls["selection"]["query"] == "wireless earbuds electronics US"
    assert "review" in calls
    assert "评价 投诉 差评 好评" in calls["review"]["query"]
