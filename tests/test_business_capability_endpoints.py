from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import pytest
from fastapi.testclient import TestClient

from src.core.auth import create_access_token
from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    async def _noop_init_db():
        return None

    async def _noop_close():
        return None

    async def _healthy_db():
        return {"status": "healthy"}

    async def _healthy_redis():
        return {"status": "healthy"}

    async def _healthy_qdrant():
        return {"status": "healthy"}

    def _noop_get_redis_connection():
        return object()

    def _noop_get_qdrant_client():
        return object()

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.close_db", _noop_close)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.get_redis_connection", _noop_get_redis_connection)
    monkeypatch.setattr("src.infrastructure.redis.close_redis", _noop_close)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.get_qdrant_client", _noop_get_qdrant_client)
    monkeypatch.setattr("src.infrastructure.qdrant.close_qdrant", _noop_close)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    token = create_access_token(
        {
            "sub": "testuser",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "is_superuser": True,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_product_planning_endpoint_uses_service_layer(client, auth_headers, monkeypatch) -> None:
    async def _fake_analyze(self, *, query, category, target_market="US", budget_range=None, extra_params=None, external_results=None):
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "service_summary": {"recommendation_count": 1},
        }

    monkeypatch.setattr("src.services.product_planning_service.ProductPlanningService.analyze", _fake_analyze)

    response = client.post(
        "/api/v1/product-planning/analyze",
        headers=auth_headers,
        json={"query": "bluetooth headset", "category": "electronics", "target_market": "US"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"] == "bluetooth headset"
    assert data["service_summary"]["recommendation_count"] == 1


def test_market_insight_endpoint_uses_service_layer(client, auth_headers, monkeypatch) -> None:
    async def _fake_predict(self, *, query, category, target_market="US"):
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "selection_signal": {"recommended_action": "create_selection_task"},
        }

    monkeypatch.setattr("src.services.market_insight_service.MarketInsightService.predict", _fake_predict)

    response = client.post(
        "/api/v1/market-insight/predict",
        headers=auth_headers,
        json={"query": "bluetooth headset", "category": "electronics", "target_market": "US"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["selection_signal"]["recommended_action"] == "create_selection_task"


def test_selection_scoring_endpoint_uses_service_layer(client, auth_headers, monkeypatch) -> None:
    def _fake_score(self, *, query, category, target_market="US", **kwargs):
        assert query == "bluetooth headset"
        assert category == "electronics"
        return {
            "query": query,
            "category": category,
            "target_market": target_market,
            "suggestion_status": "scored",
            "ai_score": 84.2,
            "scoring_summary": {"overall_score": 84.2},
            "top_recommendations": [{"rank": 1, "product_name": "bluetooth headset pro"}],
            "decision_output": {"suggestion_status": "scored"},
        }

    monkeypatch.setattr("src.services.selection_scoring_service.SelectionScoringService.score_selection", _fake_score)

    response = client.post(
        "/api/v1/selection/recommendations/score",
        headers=auth_headers,
        json={
            "query": "bluetooth headset",
            "category": "electronics",
            "target_market": "US",
            "market_analysis_result": {"opportunity_score": {"overall_score": 78}},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["suggestion_status"] == "scored"
    assert data["scoring_summary"]["overall_score"] == 84.2
    assert data["top_recommendations"][0]["product_name"] == "bluetooth headset pro"
