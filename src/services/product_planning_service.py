from __future__ import annotations

from typing import Any

from src.agents.product_planning import ProductPlanningAgent


class ProductPlanningService:
    def __init__(self, agent: ProductPlanningAgent | None = None) -> None:
        self.agent = agent or ProductPlanningAgent()

    @staticmethod
    def _normalize_agent_payload(result: Any) -> dict[str, Any]:
        payload = getattr(result, "output", result)
        if not isinstance(payload, dict):
            return {"raw_output": payload}
        if "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]
        return payload

    @staticmethod
    def _build_summary(payload: dict[str, Any]) -> dict[str, Any]:
        recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
        top_recommendation = recommendations[0] if recommendations and isinstance(recommendations[0], dict) else {}
        return {
            "recommendation_count": len(recommendations),
            "top_recommendation": top_recommendation,
            "differentiation_score": (
                (payload.get("differentiation") or {}).get("overall_score")
                if isinstance(payload.get("differentiation"), dict)
                else None
            ),
            "context_sources": payload.get("context_sources", 0),
        }

    async def analyze(
        self,
        *,
        query: str,
        category: str,
        target_market: str = "US",
        budget_range: list[float] | None = None,
        extra_params: dict[str, Any] | None = None,
        external_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "query": query,
            "category": category,
            "target_market": target_market,
        }
        if budget_range:
            input_data["budget_range"] = budget_range
        if external_results:
            input_data["external_results"] = external_results
        if extra_params:
            input_data.update(extra_params)

        result = await self.agent.run(input_data)
        payload = self._normalize_agent_payload(result)
        payload.setdefault("business_capability", "product_planning")
        payload.setdefault("service_summary", self._build_summary(payload))
        return payload

    async def cluster_reviews(self, *, reviews: list[str], review_clusters: int = 4) -> dict[str, Any]:
        return await self.agent._cluster_reviews(reviews=reviews, review_clusters=review_clusters)

    async def compare_supplier_specs(
        self,
        *,
        reviews: list[str] | None = None,
        review_clusters: int = 4,
        max_suppliers: int = 10,
    ) -> dict[str, Any]:
        return await self.agent._compare_1688_specs(
            reviews=reviews,
            review_clusters=review_clusters,
            max_suppliers=max_suppliers,
        )

    async def fetch_crm_review_insights(
        self,
        *,
        crm_api_endpoint: str | None = None,
        crm_api_key: str | None = None,
        crm_inbound_path: str = "/customer-feedback",
        product_id: str | None = None,
        asin: str | None = None,
    ) -> dict[str, Any]:
        return await self.agent._fetch_crm_reviews(
            crm_api_endpoint=crm_api_endpoint,
            crm_api_key=crm_api_key,
            crm_inbound_path=crm_inbound_path,
            product_id=product_id,
            asin=asin,
        )

    async def analyze_multimodal_assets(
        self,
        *,
        review_images: list[dict[str, Any]] | None = None,
        tiktok_videos: list[dict[str, Any]] | None = None,
        social_images: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "image_review_insights": await self.agent._analyze_review_images(review_images=review_images),
            "tiktok_video_insights": await self.agent._analyze_tiktok_video_batch(tiktok_videos=tiktok_videos),
            "social_image_trends": await self.agent._analyze_social_image_trends(image_posts=social_images),
        }
