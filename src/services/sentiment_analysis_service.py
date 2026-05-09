from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.enums import RecommendationCategory, RecommendationPriority
from src.models.models import SentimentAnalysis
from src.services.recommendation_pool_service import RecommendationPoolService

logger = get_logger(__name__)


class SentimentAnalysisService:
    """
    情感分析服务。

    职责:
    - 对产品评论/反馈进行情感分析
    - 生成情感趋势和关键词洞察
    - 将负面情感预警推送至ERP CRM/BI域
    - 跟踪情感变化趋势
    """

    NEGATIVE_THRESHOLD = -0.3
    CRITICAL_NEGATIVE_THRESHOLD = -0.7
    MIN_REVIEWS_FOR_TREND = 5

    def __init__(self, session: AsyncSession, tenant_id: str | None = None, actor: dict[str, Any] | None = None):
        self.session = session
        self.tenant_id = tenant_id or (actor or {}).get("tenant_id")
        self.actor = actor or {}
        self.pool_service = RecommendationPoolService(session, tenant_id=self.tenant_id, actor=self.actor)

    async def analyze_product_sentiment(
        self,
        *,
        product_id: str,
        reviews: list[dict[str, Any]],
        marketplace: str | None = None,
    ) -> dict[str, Any]:
        if not reviews:
            return {"product_id": product_id, "total_reviews": 0, "sentiment_score": 0, "status": "no_data"}

        sentiment_scores = []
        keywords: dict[str, int] = {}
        negative_reviews = []
        positive_reviews = []

        for review in reviews:
            score = self._compute_sentiment_score(review)
            sentiment_scores.append(score)

            review_keywords = review.get("keywords", [])
            for kw in review_keywords:
                keywords[kw] = keywords.get(kw, 0) + 1

            if score < self.NEGATIVE_THRESHOLD:
                negative_reviews.append({"review_id": review.get("id"), "score": score, "text_snippet": review.get("text", "")[:200]})
            elif score > 0.3:
                positive_reviews.append({"review_id": review.get("id"), "score": score})

        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        negative_ratio = len(negative_reviews) / len(reviews) if reviews else 0
        top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:20]
        sentiment_trend = self._compute_sentiment_trend(reviews)

        analysis = SentimentAnalysis(
            tenant_id=UUID(str(self.tenant_id)) if self.tenant_id else uuid4(),
            product_id=UUID(product_id) if product_id else None,
            source_type="product_review",
            total_reviews=len(reviews),
            sentiment_score=avg_sentiment,
            sentiment_distribution=self._compute_distribution(sentiment_scores),
            top_keywords=[{"keyword": k, "count": v} for k, v in top_keywords],
            negative_review_ratio=negative_ratio,
            sentiment_trend=sentiment_trend,
            marketplace=marketplace,
            analysis_metadata={
                "positive_count": len(positive_reviews),
                "negative_count": len(negative_reviews),
                "neutral_count": len(reviews) - len(positive_reviews) - len(negative_reviews),
            },
        )
        self.session.add(analysis)
        await self.session.flush()

        if avg_sentiment < self.CRITICAL_NEGATIVE_THRESHOLD or negative_ratio > 0.4:
            await self._create_negative_sentiment_alert(analysis, product_id, avg_sentiment, negative_ratio, negative_reviews, marketplace)

        return self._serialize_analysis(analysis)

    async def analyze_marketplace_sentiment(
        self,
        *,
        product_id: str,
        marketplace: str,
        reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = await self.analyze_product_sentiment(
            product_id=product_id,
            reviews=reviews,
            marketplace=marketplace,
        )

        if result.get("total_reviews", 0) > 0:
            pool_result = await self.pool_service.create_recommendation(
                category=RecommendationCategory.SENTIMENT_INSIGHT,
                target_domain="bi",
                title=f"市场情感洞察 - {marketplace} - 产品 {product_id}",
                description=f"情感评分 {result['sentiment_score']:.2f}, 负面比例 {result.get('negative_review_ratio', 0):.1%}",
                priority=RecommendationPriority.LOW,
                score=abs(result["sentiment_score"]) * 100,
                evidence_chain=result,
                data_sources=[{"type": "marketplace_review", "marketplace": marketplace}],
                payload={"analysis_id": result["id"], "marketplace": marketplace},
                source_product_id=UUID(product_id) if product_id else None,
            )
            result["recommendation_pool"] = pool_result

        return result

    async def list_analyses(
        self,
        *,
        source_type: str | None = None,
        marketplace: str | None = None,
        min_sentiment: float | None = None,
        max_sentiment: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = select(SentimentAnalysis)
        count_query = select(func.count()).select_from(SentimentAnalysis)

        if self.tenant_id:
            query = query.where(SentimentAnalysis.tenant_id == UUID(str(self.tenant_id)))
            count_query = count_query.where(SentimentAnalysis.tenant_id == UUID(str(self.tenant_id)))
        if source_type:
            query = query.where(SentimentAnalysis.source_type == source_type)
            count_query = count_query.where(SentimentAnalysis.source_type == source_type)
        if marketplace:
            query = query.where(SentimentAnalysis.marketplace == marketplace)
            count_query = count_query.where(SentimentAnalysis.marketplace == marketplace)
        if min_sentiment is not None:
            query = query.where(SentimentAnalysis.sentiment_score >= min_sentiment)
            count_query = count_query.where(SentimentAnalysis.sentiment_score >= min_sentiment)
        if max_sentiment is not None:
            query = query.where(SentimentAnalysis.sentiment_score <= max_sentiment)
            count_query = count_query.where(SentimentAnalysis.sentiment_score <= max_sentiment)

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(SentimentAnalysis.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        analyses = result.scalars().all()

        return {
            "total": total,
            "items": [self._serialize_analysis(a) for a in analyses],
            "limit": limit,
            "offset": offset,
        }

    async def _create_negative_sentiment_alert(
        self,
        analysis: SentimentAnalysis,
        product_id: str,
        avg_sentiment: float,
        negative_ratio: float,
        negative_reviews: list[dict[str, Any]],
        marketplace: str | None,
    ) -> None:
        priority = RecommendationPriority.CRITICAL if avg_sentiment < self.CRITICAL_NEGATIVE_THRESHOLD else RecommendationPriority.HIGH
        await self.pool_service.create_recommendation(
            category=RecommendationCategory.SENTIMENT_INSIGHT,
            target_domain="crm",
            title=f"负面情感预警 - 产品 {product_id}",
            description=f"情感评分 {avg_sentiment:.2f}, 负面比例 {negative_ratio:.1%}, 共 {len(negative_reviews)} 条负面评论",
            priority=priority,
            score=abs(avg_sentiment) * 100,
            evidence_chain={
                "sentiment_score": avg_sentiment,
                "negative_ratio": negative_ratio,
                "negative_reviews_sample": negative_reviews[:5],
            },
            data_sources=[{"type": "sentiment_analysis", "marketplace": marketplace}],
            risk_flags=[{"type": "negative_sentiment", "severity": "high" if avg_sentiment < self.CRITICAL_NEGATIVE_THRESHOLD else "medium"}],
            payload={"analysis_id": str(analysis.id), "product_id": product_id},
            source_product_id=UUID(product_id) if product_id else None,
        )

    @staticmethod
    def _compute_sentiment_score(review: dict[str, Any]) -> float:
        rating = review.get("rating")
        if rating is not None:
            normalized = (rating - 3) / 2
            return max(-1, min(1, normalized))
        text = review.get("text", "")
        if not text:
            return 0.0
        negative_words = {"差", "坏", "糟糕", "退货", "失望", "不好", "broken", "terrible", "awful", "bad", "worst", "defective", "return"}
        positive_words = {"好", "棒", "优秀", "满意", "推荐", "great", "excellent", "good", "love", "amazing", "perfect", "best"}
        text_lower = text.lower()
        neg_count = sum(1 for w in negative_words if w in text_lower)
        pos_count = sum(1 for w in positive_words if w in text_lower)
        total = neg_count + pos_count
        if total == 0:
            return 0.0
        return (pos_count - neg_count) / total

    @staticmethod
    def _compute_distribution(scores: list[float]) -> dict[str, int]:
        distribution = {"very_negative": 0, "negative": 0, "neutral": 0, "positive": 0, "very_positive": 0}
        for s in scores:
            if s <= -0.6:
                distribution["very_negative"] += 1
            elif s <= -0.2:
                distribution["negative"] += 1
            elif s < 0.2:
                distribution["neutral"] += 1
            elif s < 0.6:
                distribution["positive"] += 1
            else:
                distribution["very_positive"] += 1
        return distribution

    @staticmethod
    def _compute_sentiment_trend(reviews: list[dict[str, Any]]) -> str:
        if len(reviews) < SentimentAnalysisService.MIN_REVIEWS_FOR_TREND:
            return "insufficient_data"
        sorted_reviews = sorted(reviews, key=lambda r: r.get("date", ""), reverse=True)
        recent = sorted_reviews[: len(sorted_reviews) // 2]
        older = sorted_reviews[len(sorted_reviews) // 2 :]

        def avg_score(rev_list: list[dict[str, Any]]) -> float:
            scores = []
            for r in rev_list:
                rating = r.get("rating")
                if rating is not None:
                    scores.append((rating - 3) / 2)
            return sum(scores) / len(scores) if scores else 0

        recent_avg = avg_score(recent)
        older_avg = avg_score(older)
        diff = recent_avg - older_avg
        if diff > 0.1:
            return "improving"
        if diff < -0.1:
            return "declining"
        return "stable"

    @staticmethod
    def _serialize_analysis(analysis: SentimentAnalysis) -> dict[str, Any]:
        return {
            "id": str(analysis.id),
            "tenant_id": str(analysis.tenant_id),
            "recommendation_id": str(analysis.recommendation_id) if analysis.recommendation_id else None,
            "product_id": str(analysis.product_id) if analysis.product_id else None,
            "source_type": analysis.source_type,
            "total_reviews": analysis.total_reviews,
            "sentiment_score": analysis.sentiment_score,
            "sentiment_distribution": analysis.sentiment_distribution,
            "top_keywords": analysis.top_keywords,
            "negative_review_ratio": analysis.negative_review_ratio,
            "sentiment_trend": analysis.sentiment_trend,
            "marketplace": analysis.marketplace,
            "analysis_metadata": analysis.analysis_metadata,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }
