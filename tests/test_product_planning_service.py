from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.product_planning_service import ProductPlanningService


def test_product_planning_alias_module_exports_expected_symbols() -> None:
    from src.agents.product_planning import ProductPlanningAgent, ProductPlannerAgent

    assert ProductPlanningAgent is ProductPlannerAgent


@pytest.mark.asyncio
async def test_product_planning_service_analyze_normalizes_agent_output() -> None:
    class _FakeAgent:
        async def run(self, input_data):
            assert input_data["query"] == "bluetooth headset"
            assert input_data["category"] == "electronics"
            return SimpleNamespace(
                output={
                    "data": {
                        "recommendations": [{"product_name": "bluetooth headset pro"}],
                        "differentiation": {"overall_score": 78.0},
                        "context_sources": 3,
                    }
                }
            )

    service = ProductPlanningService(agent=_FakeAgent())
    result = await service.analyze(query="bluetooth headset", category="electronics", target_market="US")

    assert result["business_capability"] == "product_planning"
    assert result["service_summary"]["recommendation_count"] == 1
    assert result["service_summary"]["top_recommendation"]["product_name"] == "bluetooth headset pro"
    assert result["service_summary"]["differentiation_score"] == 78.0


@pytest.mark.asyncio
async def test_product_planning_service_multimodal_analysis_aggregates_agent_methods() -> None:
    class _FakeAgent:
        async def _analyze_review_images(self, review_images=None):
            return {"image_count": len(review_images or [])}

        async def _analyze_tiktok_video_batch(self, tiktok_videos=None):
            return {"video_count": len(tiktok_videos or [])}

        async def _analyze_social_image_trends(self, image_posts=None):
            return {"post_count": len(image_posts or [])}

    service = ProductPlanningService(agent=_FakeAgent())
    result = await service.analyze_multimodal_assets(
        review_images=[{"image_url": "https://example.com/1.jpg"}],
        tiktok_videos=[{"video_url": "https://example.com/v1"}],
        social_images=[{"image_url": "https://example.com/s1.jpg"}],
    )

    assert result["image_review_insights"]["image_count"] == 1
    assert result["tiktok_video_insights"]["video_count"] == 1
    assert result["social_image_trends"]["post_count"] == 1
