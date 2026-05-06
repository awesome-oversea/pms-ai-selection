from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from src.core.auth import get_current_user
from src.infrastructure.data_adapters import build_data_adapter, list_data_adapters
from src.services.competitor_site_collection_service import CompetitorSiteCollectionService
from src.services.crawl_governance_service import CrawlDataQualityService, CrawlGovernanceService
from src.services.external_signal_service import ExternalSignalService
from src.services.forum_collection_service import ForumCollectionService
from src.services.market_trend_service import MarketTrendService
from src.services.media_blog_collection_service import MediaBlogCollectionService
from src.services.patent_signal_service import PatentSignalService
from src.services.price_site_collection_service import PriceSiteCollectionService
from src.services.social_media_collection_service import SocialMediaCollectionService

router = APIRouter(prefix="/market", tags=["市场趋势"])


class MarketTrendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    target_market: str = Field(default="US")


class ExternalSignalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = Field(default="auto", pattern="^(auto|real|mock)$")


@router.post("/trends/predict", response_model=dict)
async def predict_market_trends(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.predict_trends(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"市场趋势预测失败: {e}")


@router.post("/signals/minimal-real", response_model=dict)
async def collect_minimal_real_signals(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        return await service.collect_minimal_real_signals(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"外部真实信号采集失败: {e}")


@router.post("/signals/business-real", response_model=dict)
async def collect_business_real_signals(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        return await service.collect_business_real_signals(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"业务外部真实信号采集失败: {e}")


@router.post("/signals/gdelt-real", response_model=dict)
async def collect_gdelt_real_signals(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        return await service.collect_gdelt_event_signals(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"GDELT事件信号采集失败: {e}")


@router.post("/signals/rss-real", response_model=dict)
async def collect_rss_real_signals(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        return await service.collect_rss_signals(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RSS外部真实信号采集失败: {e}")


@router.post("/signals/rss-subscriptions", response_model=dict)
async def build_rss_subscription_bundle(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        return await service.build_rss_subscription_bundle(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RSS订阅构建失败: {e}")


@router.post("/crawl/competitor-sites", response_model=dict)
async def collect_competitor_site_content(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = CompetitorSiteCollectionService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"竞品官网采集失败: {e}")


@router.post("/crawl/forums", response_model=dict)
async def collect_forum_content(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ForumCollectionService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"论坛采集失败: {e}")


@router.post("/crawl/social-media", response_model=dict)
async def collect_social_media_content(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = SocialMediaCollectionService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"社交媒体采集失败: {e}")


@router.post("/crawl/price-sites", response_model=dict)
async def collect_price_site_content(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = PriceSiteCollectionService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"比价网站采集失败: {e}")


@router.post("/crawl/media-blog-collection", response_model=dict)
async def collect_media_blog_content(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MediaBlogCollectionService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"行业媒体/博客采集失败: {e}")


@router.post("/crawl/patent-pages", response_model=dict)
async def collect_patent_public_pages(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = PatentSignalService()
        return await service.collect(query=request.query, mode=request.mode)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"专利/商标公开页面采集失败: {e}")


@router.post("/crawl/quality-check", response_model=dict)
async def crawl_quality_check(request: dict = Body(...), current_user: dict = Depends(get_current_user)):
    try:
        service = CrawlDataQualityService()
        return service.validate_records(source=str(request.get("source") or "rss"), records=list(request.get("records") or []))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"爬虫数据质量检查失败: {e}")


@router.post("/crawl/governance-check", response_model=dict)
async def crawl_governance_check(request: dict = Body(...), current_user: dict = Depends(get_current_user)):
    try:
        service = CrawlGovernanceService()
        return service.evaluate_url(
            url=str(request.get("url") or ""),
            user_agent=request.get("user_agent"),
            sample_record=request.get("sample_record"),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"爬虫合规检查失败: {e}")


@router.get("/signals/adapters", response_model=dict)
async def get_signal_adapters(current_user: dict = Depends(get_current_user)):
    return {"items": list_data_adapters()}


@router.post("/signals/adapters/rss", response_model=dict)
async def collect_rss_by_adapter(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        adapter = build_data_adapter("rss", service=service)
        return await adapter.collect(query=request.query, mode=request.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RSS适配器采集失败: {e}")


@router.post("/signals/adapters/minimal-real", response_model=dict)
async def collect_minimal_by_adapter(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        adapter = build_data_adapter("minimal-real", service=service)
        return await adapter.collect(query=request.query, mode=request.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"最小真实信号适配器采集失败: {e}")


@router.post("/signals/adapters/business-real", response_model=dict)
async def collect_business_by_adapter(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        adapter = build_data_adapter("business-real", service=service)
        return await adapter.collect(query=request.query, mode=request.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"业务真实信号适配器采集失败: {e}")


@router.post("/signals/adapters/gdelt-real", response_model=dict)
async def collect_gdelt_by_adapter(request: ExternalSignalRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = ExternalSignalService()
        adapter = build_data_adapter("gdelt-real", service=service)
        return await adapter.collect(query=request.query, mode=request.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"GDELT适配器采集失败: {e}")


@router.post("/trends/aggregate", response_model=dict)
async def get_google_trends_aggregate(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_google_trends_aggregate(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Google Trends聚合查询失败: {e}")


@router.post("/bsr-demand-ratio", response_model=dict)
async def get_bsr_demand_supply_ratio(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_bsr_demand_supply_ratio(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"BSR供需比查询失败: {e}")


@router.post("/oms-benchmark", response_model=dict)
async def get_oms_sales_benchmark(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_oms_sales_benchmark(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OMS历史销量对比失败: {e}")


@router.post("/tiktok-tag-trends", response_model=dict)
async def get_tiktok_tag_trends(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_tiktok_tag_trends(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TikTok热门标签趋势查询失败: {e}")


@router.post("/forum-topics", response_model=dict)
async def get_forum_topic_trends(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_forum_topic_trends(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"论坛热词统计失败: {e}")


@router.post("/lifecycle", response_model=dict)
async def get_supply_demand_lifecycle(request: MarketTrendRequest, current_user: dict = Depends(get_current_user)):
    try:
        service = MarketTrendService()
        return await service.get_supply_demand_lifecycle(query=request.query, category=request.category, target_market=request.target_market)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"供需比/生命周期分析失败: {e}")
