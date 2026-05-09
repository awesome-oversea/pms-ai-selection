from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

from src.core.auth import create_access_token
from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    async def _noop_init_db():
        return None

    async def _healthy_db():
        return {"status": "healthy"}

    async def _healthy_redis():
        return {"status": "healthy"}

    async def _healthy_qdrant():
        return {"status": "healthy"}

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy_db)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy_redis)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy_qdrant)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


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


@pytest.fixture
def operator_headers():
    token = create_access_token(
        {
            "sub": "operator1",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "is_superuser": False,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["operator"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


class TestPageRoutes:
    def test_recommendations_page(self, client):
        resp = client.get("/recommendations", follow_redirects=False)
        assert resp.status_code in (200, 307)

    def test_ads_optimization_page(self, client):
        resp = client.get("/ads-optimization", follow_redirects=False)
        assert resp.status_code in (200, 307)

    def test_fba_restock_page(self, client):
        resp = client.get("/fba-restock", follow_redirects=False)
        assert resp.status_code in (200, 307)

    def test_ai_insights_page(self, client):
        resp = client.get("/ai-insights", follow_redirects=False)
        assert resp.status_code in (200, 307)


class TestErpDomainsAPIEndpoints:
    def test_list_recommendations(self, client, auth_headers):
        mock_result = {"items": [], "total": 0}
        with patch("src.services.recommendation_pool_service.RecommendationPoolService.list_recommendations", new_callable=AsyncMock, return_value=mock_result):
            resp = client.get("/api/v1/erp-domains/recommendations", headers=auth_headers)
            assert resp.status_code == 200

    def test_get_recommendation_statistics(self, client, auth_headers):
        mock_stats = {"total": 0, "by_state": {}, "by_category": {}}
        with patch("src.services.recommendation_pool_service.RecommendationPoolService.get_recommendation_statistics", new_callable=AsyncMock, return_value=mock_stats):
            resp = client.get("/api/v1/erp-domains/recommendations/statistics", headers=auth_headers)
            assert resp.status_code == 200

    def test_ads_bid_adjustment(self, client, auth_headers):
        mock_result = {"suggestion_type": "bid_adjustment", "suggested_bid": 1.25, "confidence": 0.85}
        with patch("src.services.ads_optimization_service.AdsOptimizationService.generate_bid_adjustment_suggestion", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/ads/bid-adjustment", headers=auth_headers, json={
                "product_id": "prod-001",
                "campaign_id": "camp-001",
                "current_metrics": {"acos": 0.35},
            })
            assert resp.status_code == 200

    def test_fba_restock(self, client, auth_headers):
        mock_result = {"urgency": "high", "suggested_quantity": 500, "days_of_supply": 15.0}
        with patch("src.services.fba_restock_service.FBARestockService.generate_restock_suggestion", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/fba/restock", headers=auth_headers, json={
                "product_id": "prod-001",
                "current_stock": 100,
                "daily_velocity": 10.0,
                "lead_time_days": 30,
            })
            assert resp.status_code == 200

    def test_risk_assess(self, client, auth_headers):
        mock_result = {"risk_score": 45.0, "risk_level": "medium", "risk_factors": []}
        with patch("src.services.risk_scoring_service.RiskScoringService.assess_order_risk", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/risk/assess", headers=auth_headers, json={
                "risk_type": "order_risk",
                "target_id": "order-001",
                "target_domain": "scm",
            })
            assert resp.status_code == 200

    def test_pricing_suggest(self, client, auth_headers):
        mock_result = {"suggested_price": 29.99, "min_price": 25.0, "max_price": 35.0, "estimated_margin": 0.3}
        with patch("src.services.pricing_suggestion_service.PricingSuggestionService.generate_new_product_pricing", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/pricing/suggest", headers=auth_headers, json={
                "product_id": "prod-001",
                "cost_data": {"total_cost": 15.0},
                "target_margin": 0.3,
            })
            assert resp.status_code == 200

    def test_inventory_predict(self, client, auth_headers):
        mock_result = {"predicted_demand_short": 70, "predicted_demand_medium": 300, "stockout_probability": 0.15}
        with patch("src.services.inventory_prediction_service.InventoryPredictionService.generate_prediction", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/inventory/predict", headers=auth_headers, json={
                "product_id": "prod-001",
                "current_stock": 200,
                "historical_sales": [{"date": "2024-01-01", "quantity": 10}],
                "lead_time_days": 30,
            })
            assert resp.status_code == 200

    def test_sentiment_analyze(self, client, auth_headers):
        mock_result = {"sentiment_score": 0.65, "sentiment_label": "positive", "total_reviews": 150}
        with patch("src.services.sentiment_analysis_service.SentimentAnalysisService.analyze_product_sentiment", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/sentiment/analyze", headers=auth_headers, json={
                "product_id": "prod-001",
                "reviews": [{"text": "Great product!", "rating": 5}],
            })
            assert resp.status_code == 200

    def test_ai_feature_toggle_get(self, client, auth_headers):
        mock_result = {"feature_key": "ai_selection", "is_enabled": True}
        with patch("src.services.ai_feature_toggle_service.AIFeatureToggleService.get_feature_config", new_callable=AsyncMock, return_value=mock_result):
            resp = client.get("/api/v1/erp-domains/sys/ai-feature/ai_selection", headers=auth_headers)
            assert resp.status_code == 200

    def test_ai_feature_toggle_set(self, client, auth_headers):
        mock_result = {"feature_key": "ai_selection", "is_enabled": False}
        with patch("src.services.ai_feature_toggle_service.AIFeatureToggleService.set_feature_config", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/sys/ai-feature", headers=auth_headers, json={
                "feature_key": "ai_selection",
                "is_enabled": False,
            })
            assert resp.status_code == 200

    def test_feedback_event(self, client, auth_headers):
        mock_result = {"status": "accepted", "event_id": "evt-001"}
        with patch("src.services.erp_feedback_consumer.handle_erp_feedback_event", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/feedback/event", headers=auth_headers, json={
                "event_type": "execution_result",
                "aggregate_id": "rec-001",
                "payload": {"domain": "ads", "result": {"status": "success"}},
            })
            assert resp.status_code == 200

    def test_approve_recommendation(self, client, auth_headers):
        mock_result = {"id": "rec-001", "execution_state": "pms_approved"}
        with patch("src.services.recommendation_pool_service.RecommendationPoolService.approve_recommendation", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/recommendations/rec-001/approve", headers=auth_headers, json={
                "detail": "通过联调测试批准",
            })
            assert resp.status_code == 200

    def test_reject_recommendation(self, client, auth_headers):
        mock_result = {"id": "rec-001", "execution_state": "pms_rejected"}
        with patch("src.services.recommendation_pool_service.RecommendationPoolService.reject_recommendation", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/api/v1/erp-domains/recommendations/rec-001/reject", headers=auth_headers, json={
                "reason": "联调测试拒绝",
            })
            assert resp.status_code == 200

    def test_unauthorized_access_returns_401(self, client):
        resp = client.get("/api/v1/erp-domains/recommendations")
        assert resp.status_code == 401

    def test_operator_can_list_recommendations(self, client, operator_headers):
        mock_result = {"items": [], "total": 0}
        with patch("src.services.recommendation_pool_service.RecommendationPoolService.list_recommendations", new_callable=AsyncMock, return_value=mock_result):
            resp = client.get("/api/v1/erp-domains/recommendations", headers=operator_headers)
            assert resp.status_code == 200


class TestFrontendStaticAssets:
    def test_erp_domains_api_js_accessible(self, client):
        resp = client.get("/static/js/erp_domains_api.js")
        assert resp.status_code == 200
        assert "ErpDomainsAPI" in resp.text

    def test_recommendations_html_template_exists(self):
        assert Path("web/templates/recommendations.html").exists()

    def test_ads_optimization_html_template_exists(self):
        assert Path("web/templates/ads_optimization.html").exists()

    def test_fba_restock_html_template_exists(self):
        assert Path("web/templates/fba_restock.html").exists()

    def test_ai_insights_html_template_exists(self):
        assert Path("web/templates/ai_insights.html").exists()
