from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from src.agents.product_planner import ProductPlannerAgent
from src.agents.selection_master import SelectionMaster
from src.api.v1.endpoints.agents import get_registered_agent_classes
from src.api.v1.endpoints.llm import _build_gateway_config
from src.core.rbac import (
    ACTION_MANAGE,
    ACTION_READ,
    CORE_PERMISSIONS,
    DEFAULT_PLATFORM_ADMIN_ROLE,
    DEFAULT_VIEWER_ROLE,
    PLATFORM_ROLES,
    RESOURCE_SELECTION,
    ROLE_MATRIX,
    ROLE_PERMISSIONS,
    TENANT_ROLES,
    build_permission,
    derive_roles,
)
from src.infrastructure.database import close_db, get_async_session_factory, init_db
from src.infrastructure.llm_gateway import GatewayConfig, LLMGateway
from src.infrastructure.qdrant import _QDRANT_AVAILABLE, QdrantService, close_qdrant, get_qdrant_client
from src.infrastructure.qdrant import models as qdrant_models
from src.models.enums import TaskStatus
from src.models.models import Chunk, Document, TenantConfig, TenantQuota
from src.repositories.base import TenantScopedRepository
from src.repositories.knowledge_repository import KnowledgeRepository
from src.repositories.tenant_repository import TenantRepository
from src.services.embedding import EmbeddingProvider
from src.services.knowledge_service import KnowledgeService
from src.services.market_trend_service import MarketTrendService
from src.services.profit_optimization_service import ProfitOptimizationService
from src.services.report_center_service import ReportCenterService
from src.services.selection_service import SelectionTaskExecutionContext, SelectionTaskService
from src.workers.bi_kpi_worker import BIDailyKpiWorker
from src.workers.celery_selection_tasks import execute_selection_task
from src.workers.selection_worker import SelectionTaskWorker, run_worker
from src.workers.selection_worker import main as worker_module_main


def _run(coro):
    return asyncio.run(coro)


def test_selection_master_preserves_session_id():
    session_id = "phase2-session-001"
    master = SelectionMaster(config={"session_id": session_id})

    result = _run(
        master.run(
            {
                "session_id": session_id,
                "query": "蓝牙耳机",
                "category": "electronics",
                "target_market": "US",
            }
        )
    )

    assert result["session_id"] == session_id
    assert result["state_summary"]["session_id"] == session_id
    assert result["framework"] == "langgraph-compatible"
    assert result["langgraph_execution"]["risk_assessor_integrated"] is True
    assert result["langgraph_execution"]["report_generator_integrated"] is True
    assert "risk_assessment" in result["results"]
    assert "report_generation" in result["results"]
    assert "go_no_go_decision" in result


def test_product_planner_compare_1688_specs_outputs_differences(monkeypatch):
    async def _fake_execute(self, **kwargs):
        return {
            "suppliers": [
                {
                    "supplier_id": "SUP-1688-001",
                    "company_name": "深圳优选工厂",
                    "location": "Shenzhen, Guangdong",
                    "is_verified": True,
                    "trade_assurance": True,
                    "oem_odm_supported": True,
                    "sample_available": True,
                    "lead_time_days": 9,
                    "moq_tiers": [{"min_qty": 120, "unit_price_usd": 18.6}],
                }
            ]
        }

    monkeypatch.setattr("src.agents.data_collection.Tool1688._collect_supply_chain", _fake_execute)
    agent = ProductPlannerAgent()
    result = _run(
        agent._compare_1688_specs(
            product_keyword="蓝牙耳机",
            product_spec={
                "core_features": ["主动降噪", "无线充电", "蓝牙5.3"],
                "key_parameters": {"battery_hours": 36},
            },
            max_suppliers=5,
        )
    )
    assert result["source"] == "ali1688_spec_comparison"
    assert result["supplier_count"] == 1
    assert isinstance(result["difference_items"], list)
    assert isinstance(result["recommended_alignment"], list)


def test_product_planner_fetch_crm_reviews_matches_feedback(monkeypatch):
    async def _fake_fetch(self):
        return [
            {"product_id": "prod-001", "asin": "B0ERP0001", "product_name": "蓝牙耳机企业联调样本", "feedback": "客户评价良好，但出现少量退货投诉，需要优化包装。", "customer_score": 4.6, "review_count": 13},
            {"product_id": "prod-002", "asin": "B0ERP9999", "product_name": "其他产品", "feedback": "无关评论", "customer_score": 3.8, "review_count": 5},
        ]

    monkeypatch.setattr("src.infrastructure.crm_client.CRMClient.fetch_customer_feedbacks", _fake_fetch)
    agent = ProductPlannerAgent()
    result = _run(
        agent._fetch_crm_reviews(
            crm_api_endpoint="file://artifacts/erp_local/crm",
            crm_inbound_path="/feedback",
            product_id="prod-001",
            asin="B0ERP0001",
        )
    )
    assert result["source"] == "crm_review_insights"
    assert result["matched_review_count"] == 1
    assert result["summary"]["complaint_count"] == 1
    assert result["avg_rating"] == 4.6


def test_product_planner_review_clustering_extracts_pain_points():
    agent = ProductPlannerAgent()
    result = _run(
        agent._cluster_reviews(
            reviews=[
                "音质不错，但是蓝牙连接不稳定，经常断连",
                "佩戴半小时耳朵就疼，舒适度一般",
                "电池衰减太快，用了三个月续航明显下降",
                "外观可以，但塑料感很强，做工一般",
            ],
            n_clusters=4,
        )
    )
    assert result["cluster_count"] >= 3
    assert any("连接" in item["point"] or "佩戴" in item["point"] or "续航" in item["point"] for item in result["pain_points"])
    assert isinstance(result["function_pain_points"], list)
    assert isinstance(result["quality_defects"], list)
    assert isinstance(result["design_improvements"], list)


def test_product_planner_multimodal_image_and_video_analysis_outputs(monkeypatch):
    agent = ProductPlannerAgent()

    async def _fake_llava(self, image_url="", analysis_type="features"):
        if analysis_type == "design_defects":
            return {
                "source": "llava_analysis",
                "analysis_type": "design_defects",
                "image_ref": image_url,
                "defects_detected": 1,
                "defects": [{"issue": "接口位置不合理", "severity": "low", "suggestion": "调整接口布局"}],
                "recommendations": ["调整接口布局"],
            }
        return {
            "source": "llava_analysis",
            "analysis_type": analysis_type,
            "image_ref": image_url,
            "visual_features": [{"attribute": "color_scheme", "value": "深空灰", "confidence": 0.95}],
            "product_description": "深空灰极简风耳机",
            "design_score": 8.8,
            "market_positioning_hint": "mid-range",
        }

    monkeypatch.setattr("src.agents.product_planner.ProductPlannerAgent._llava_analyze_image", _fake_llava)

    image_result = _run(
        agent._analyze_review_images(
            [
                {"image_url": "https://example.com/review1.jpg", "analysis_type": "features"},
                {"image_url": "data:image/png;base64,AAA", "analysis_type": "design_defects"},
            ]
        )
    )
    video_result = _run(
        agent._analyze_tiktok_video_batch(
            [
                {"video_url": "https://tiktok.example/video/1", "title": "蓝牙耳机降噪测试", "description": "展示续航与佩戴"},
            ]
        )
    )
    social_result = _run(
        agent._analyze_social_image_trends(
            [
                {"platform": "instagram", "image_url": "https://example.com/ig1.jpg", "tags": ["minimal", "premium"], "caption": "desk setup for daily work", "engagement": 1200},
                {"platform": "pinterest", "image_url": "https://example.com/pin1.jpg", "tags": ["sport", "outdoor"], "caption": "travel and commute style", "engagement": 860},
            ]
        )
    )

    assert image_result["source"] == "review_image_multimodal"
    assert image_result["image_count"] == 2
    assert "url" in image_result["supports"]
    assert "base64" in image_result["supports"]
    assert isinstance(image_result["top_visual_tags"], list)
    assert isinstance(image_result["top_defects"], list)
    assert video_result["source"] == "tiktok_video_batch_analysis"
    assert video_result["video_count"] == 1
    assert video_result["videos"][0]["transcript"]
    assert len(video_result["videos"][0]["key_frames"]) >= 1
    assert social_result["source"] == "social_image_trends"
    assert social_result["image_count"] == 2
    assert social_result["top_tags"]
    assert social_result["top_visual_directions"]


def test_embedding_provider_exposes_provider_mode():
    provider = EmbeddingProvider.get_instance()
    mode = provider.provider_mode
    assert mode in {"local-real", "local-mock"}


def test_proxy_pool_rotates_and_blocks_failed_proxies():
    from src.crawlers.amazon import ProxyPool

    pool = ProxyPool(["http://proxy-1:8080", "http://proxy-2:8080"], max_failures=1, cooldown_seconds=60)
    first = pool.acquire()
    second = pool.acquire()
    pool.report_failure(first)
    third = pool.acquire()
    status = pool.build_status()

    assert first == "http://proxy-1:8080"
    assert second == "http://proxy-2:8080"
    assert third == "http://proxy-2:8080"
    assert status["total_proxy_count"] == 2
    assert status["blocked_proxy_count"] == 1


def test_amazon_crawler_exposes_anti_crawl_status():
    from src.crawlers.amazon import AmazonBSRCrawler

    crawler = AmazonBSRCrawler(proxy_list=["http://proxy-1:8080", "http://proxy-2:8080"])
    status = crawler.build_anti_crawl_status()

    assert status["user_agent_pool_size"] >= 5
    assert status["proxy_pool"]["total_proxy_count"] == 2
    assert status["captcha_ocr_endpoint"] == "/api/v1/security/captcha-ocr"
    assert status["captcha_ocr_ready"] is True


def test_crawl_governance_and_quality_services():
    from src.services.crawl_governance_service import (
        BloomFilterDeduper,
        CrawlDataQualityService,
        CrawlGovernanceService,
    )

    deduper = BloomFilterDeduper(size=128)
    assert deduper.contains("https://example.com/a") is False
    deduper.add("https://example.com/a")
    assert deduper.contains("https://example.com/a") is True

    quality = CrawlDataQualityService().validate_records(
        source="rss",
        records=[
            {"title": "A", "url": "https://example.com/a"},
            {"title": "A", "url": "https://example.com/a"},
            {"title": "", "url": "https://example.com/b"},
        ],
    )
    assert quality["duplicate_count"] == 1
    assert quality["invalid_count"] == 1
    assert quality["valid_records"] == 1

    governance = CrawlGovernanceService().evaluate_url(
        url="https://example.com/products/123",
        sample_record={"email": "demo@example.com", "title": "demo"},
    )
    assert governance["robots_url"] == "https://example.com/robots.txt"
    assert governance["privacy_redacted"] is True


def test_amazon_crawlers_parse_and_validate_basic_records():
    from src.crawlers.amazon import AmazonBSRCrawler, AmazonReviewCrawler, normalize_price, validate_product_data

    bsr_html = '<a href="/B012345678">p1</a><span>$29.99</span><a href="/B087654321">p2</a><span>$49.50</span>'
    review_html = 'data-review-id="R12345"<i data-icon="a-star-5"></i><a class="review-title"><span>Excellent Product</span></a>'

    bsr = AmazonBSRCrawler()
    review = AmazonReviewCrawler()
    products = bsr._parse_bsr_page(bsr_html, page=1)
    reviews = review._parse_reviews(review_html, asin="B012345678")

    assert len(products) >= 2
    assert products[0]["asin"] == "B012345678"
    assert validate_product_data({"asin": "B012345678", "name": "Demo", "price": 29.99}) is True
    assert normalize_price("$29.99") == 29.99
    assert len(reviews) == 1
    assert reviews[0]["asin"] == "B012345678"
    assert reviews[0]["rating"] == 5


def test_captcha_ocr_service_normalizes_hint_and_rejects_invalid_base64():
    from src.services.captcha_ocr_service import CaptchaOCRService

    service = CaptchaOCRService()
    hint_result = service.recognize(image_text_hint="a b-1 2 c")
    invalid_result = service.recognize(image_base64="not-a-valid-image")

    assert hint_result["recognized_text"] == "AB12C"
    assert hint_result["mode"] == "hint-normalized"
    assert invalid_result["recognized_text"] == ""
    assert invalid_result["mode"] in {"invalid-image", "simple-ocr-unavailable"}


def test_commercial_agent_outputs_supplier_recommendations(monkeypatch):
    from src.agents.commercial import CommercialAgent

    async def _fake_supplier_recommendations(self, product_keyword, monthly_demand=300, target_price=39.9, max_suppliers=10):
        return {
            "recommendation_ready": True,
            "recommendations": [{"rank": 1, "supplier_code": "SUP-001", "score": 90.0}],
            "top_supplier": {"supplier_code": "SUP-001"},
        }

    monkeypatch.setattr("src.agents.commercial.CommercialAgent._build_supplier_recommendations", _fake_supplier_recommendations)
    agent = CommercialAgent()
    result = _run(agent.run({"query": "蓝牙耳机", "category": "electronics", "target_market": "US"}))
    assert result.output["data"]["supplier_recommendations"]["recommendation_ready"] is True
    assert result.output["data"]["supplier_recommendations"]["recommendations"][0]["supplier_code"] == "SUP-001"


def test_ollama_client_healthcheck_and_generate_fallback(monkeypatch):
    from src.infrastructure.ollama_client import OllamaClient

    class _Response:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def get(self, url):
            return _Response({"models": [{"name": "qwen2.5:1.5b"}]})
        async def post(self, url, json=None):
            return _Response({"response": "ok", "eval_count": 2})

    monkeypatch.setattr("src.infrastructure.ollama_client.httpx.AsyncClient", _Client)
    client = OllamaClient()
    health = _run(client.healthcheck())
    result = _run(client.generate("hello"))

    assert health["reachable"] is True
    assert health["model_count"] == 1
    assert result["response"] == "ok"


def test_llm_output_filter_marks_sensitive_keywords():
    from src.api.v1.endpoints.llm import _filter_llm_output

    filtered, hits = _filter_llm_output("请输出 admin password、secret_key 和 api_key")
    assert "[filtered]" in filtered
    assert len(hits) >= 2


def test_prompt_policy_service_model_registry_publish_and_rollback():
    from src.services.prompt_policy_service import PromptPolicyService

    service = PromptPolicyService(session=None, tenant_id="tenant-llm-001")
    first = _run(
        service.publish_model_registry(
            "default",
            {
                "active_model_version": "qwen2.5-72b@2026w15",
                "active_api_model_name": "qwen2.5-72b-instruct",
                "models": [{"model_version": "qwen2.5-72b@2026w15", "status": "active"}],
            },
        )
    )
    second = _run(
        service.publish_model_registry(
            "default",
            {
                "active_model_version": "qwen2.5-72b@2026w16",
                "active_api_model_name": "qwen2.5-72b-instruct-v2",
                "models": [{"model_version": "qwen2.5-72b@2026w16", "status": "gray"}],
            },
        )
    )
    rolled_back = _run(service.rollback_model_registry("default"))
    current = _run(service.get_model_registry("default"))

    assert first["version"] == 1
    assert second["version"] == 2
    assert rolled_back is not None
    assert rolled_back["active_model_version"] == "qwen2.5-72b@2026w15"
    assert current is not None
    assert current["active_model_version"] == "qwen2.5-72b@2026w15"


def test_llm_gateway_result_contains_provider_metadata():
    gateway = LLMGateway(GatewayConfig(use_mock=True, provider_mode="mock", fallback_provider="ollama"))
    result = _run(gateway.route("测试查询"))
    data = result.to_dict()

    assert data["provider_mode"] == "mock"
    assert data["primary_provider"] == "vllm"
    assert data["actual_provider"] in {"vllm", "ollama"}
    assert data["fallback_provider"] == "ollama"


def test_llm_gateway_degrades_when_all_nodes_unavailable():
    gateway = LLMGateway(GatewayConfig(use_mock=True, provider_mode="mock", fallback_provider="ollama"))
    for cb in gateway._circuit_breakers.values():
        cb.state = cb.state.OPEN

    result = _run(gateway.route("测试降级"))
    assert result.degraded is True
    assert result.circuit_broken is True
    assert result.actual_provider == "ollama"


def test_registered_agent_classes_public_function():
    registry = get_registered_agent_classes()
    assert isinstance(registry, dict)
    assert "market_insight" in registry
    assert "product_planner" in registry
    assert "commercial" in registry


class _FakeRepo:
    def __init__(self):
        self.kb = SimpleNamespace(id=uuid4(), collection_name="product_knowledge")
        self.existing_doc = None
        self.indexed_chunks = []

    async def get_or_create_default_knowledge_base(self):
        return self.kb

    async def get_document_by_hash(self, knowledge_base_id, content_hash, title=None):
        return self.existing_doc

    async def list_indexed_chunks(self):
        return self.indexed_chunks


class _FakeTaskRepo:
    def __init__(self):
        self.claimed = []

    async def create_task(self, **kwargs):
        now = datetime.now(UTC)
        return SimpleNamespace(
            id=uuid4(),
            title=kwargs["title"],
            target_category=kwargs["category"],
            target_market=kwargs["target_market"],
            budget_max=kwargs.get("budget_max"),
            status=SimpleNamespace(value="pending"),
            priority=SimpleNamespace(value="medium"),
            created_at=now,
            updated_at=now,
            completed_at=None,
            result_summary="任务已创建",
            config=kwargs.get("config") or {},
        )

    async def update_task_status(self, task_id, status, result_summary=None, phase=None, reason=None):
        return True

    async def count_running_tasks_by_tenant(self, tenant_id=None):
        return 0

    async def count_backlog_tasks_by_tenant(self, tenant_id=None):
        return 1

    async def claim_pending_tasks(self, limit=1, tenant_id=None):
        now = datetime.now(UTC)
        task = SimpleNamespace(
            id=uuid4(),
            tenant_id=uuid.UUID("00000000-0000-0000-0000-00000000c101"),
            title="蓝牙耳机",
            target_category="electronics",
            target_market="US",
            budget_max=1000.0,
            priority=SimpleNamespace(value="medium"),
            config={"auto_approve": False},
            status=SimpleNamespace(value="running"),
            created_at=now,
        )
        self.claimed.append(task)
        return [task]


def test_selection_task_service_persists_tenant_id_in_config():
    service = SelectionTaskService(
        session=SimpleNamespace(commit=lambda: None, refresh=lambda obj: None),
        actor={"roles": ["operator"], "tenant_id": "tenant-actor-001"},
    )
    service.repo = _FakeTaskRepo()

    async def _commit():
        return None

    async def _refresh(obj):
        return None

    service.session.commit = _commit
    service.session.refresh = _refresh

    result = _run(
        service.create_task(
            payload={"query": "蓝牙耳机", "category": "electronics", "priority": "normal"},
            created_by=None,
        )
    )
    assert result["tenant_id"] == "tenant-actor-001"


def test_report_center_service_builds_valid_xlsx_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(tmp_path / "report_state.json"))
    service = ReportCenterService()
    report = _run(service.generate(report_type="daily", format="xlsx", task_id="task-xlsx-001", params={"gmv": 333.3, "completion_rate": 0.95}))
    downloaded = _run(service.build_download(report["report_id"]))
    assert downloaded is not None
    content, media_type, filename = downloaded
    assert media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert filename.endswith(".xlsx")
    assert content.startswith(b"PK")


def test_report_center_service_builds_valid_pptx_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(tmp_path / "report_state.json"))
    service = ReportCenterService()
    report = _run(service.generate(report_type="daily", format="pptx", task_id="task-pptx-001", params={"gmv": 222.2, "completion_rate": 0.93}))
    downloaded = _run(service.build_download(report["report_id"]))
    assert downloaded is not None
    content, media_type, filename = downloaded
    assert media_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    assert filename.endswith(".pptx")
    assert content.startswith(b"PK")


def test_report_center_service_archive_and_compare_include_archive_context(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(tmp_path / "report_state.json"))
    service = ReportCenterService()
    report_a = _run(service.generate(report_type="daily", format="html", task_id="task-archive-a", params={"gmv": 100, "completion_rate": 0.8}))
    report_b = _run(service.generate(report_type="daily", format="html", task_id="task-archive-b", params={"gmv": 120, "completion_rate": 0.9}))
    archive_result = _run(service.archive_report(report_a["report_id"]))
    archived_list = _run(service.list_archived_reports(limit=10, offset=0))
    compare_result = _run(service.compare_reports(report_a["report_id"], report_b["report_id"]))

    assert archive_result is not None
    assert archive_result["archived"] is True
    assert archive_result["archive_record"]["report_id"] == report_a["report_id"]
    assert archived_list["total"] >= 1
    assert archived_list["items"][0]["report_id"] == report_a["report_id"]
    assert compare_result is not None
    assert compare_result["baseline"]["archived"] is True
    assert compare_result["archive_context"]["baseline_archived"] is True
    assert compare_result["archive_context"]["archived_report_total"] >= 1


def test_report_center_service_share_report_to_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(tmp_path / "report_state.json"))

    async def _fake_share_report_link(self, *, channel, webhook_url, report_title, report_summary, share_url):
        return {
            "channel": channel,
            "delivered": True,
            "message_type": "report_delivery",
            "result": {"webhook_url": webhook_url, "share_url": share_url, "title": report_title, "summary": report_summary},
        }

    monkeypatch.setattr("src.services.channel_delivery_service.ChannelDeliveryService.share_report_link", _fake_share_report_link)
    service = ReportCenterService()
    report = _run(service.generate(report_type="daily", format="html", task_id="task-share-001", params={"gmv": 180.5, "completion_rate": 0.92}))
    result = _run(
        service.share_report_to_channel(
            report["report_id"],
            channel="wechat",
            webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
            created_by="tester",
            expires_in_hours=12,
        )
    )

    assert result is not None
    assert result["report_id"] == report["report_id"]
    assert result["share"]["share_token"]
    assert result["share"]["share_url"].startswith("/api/v1/reports/share/")
    assert result["delivery"]["channel"] == "wechat"
    assert result["delivery"]["delivered"] is True


def test_data_adapter_catalog_and_builders():
    from src.infrastructure.data_adapters import (
        BaseDataAdapter,
        BusinessRealSignalAdapter,
        MinimalRealSignalAdapter,
        RSSNewsAdapter,
        build_data_adapter,
        list_data_adapters,
    )

    items = list_data_adapters()
    assert any(item["adapter_key"] == "rss" for item in items)
    assert isinstance(build_data_adapter("rss"), RSSNewsAdapter)
    assert isinstance(build_data_adapter("minimal-real"), MinimalRealSignalAdapter)
    assert isinstance(build_data_adapter("business-real"), BusinessRealSignalAdapter)
    assert issubclass(RSSNewsAdapter, BaseDataAdapter)


def test_market_trend_service_builds_tiktok_tag_trends(monkeypatch):
    async def _fake_collect(self, *, query, category, target_market):
        return (
            {
                "summary": {
                    "local_business_ready": True,
                    "enterprise_ready": False,
                    "readiness_tier": "local_business_ready",
                    "real_count": 2,
                }
            },
            {
                "tiktok_data": {
                    "products": [
                        {"title": "蓝牙耳机 Viral Product Trending", "engagement_rate": 8.6, "total_views": 120000, "creator_count": 16, "trend_status": "rising"},
                        {"title": "蓝牙耳机 Trending Gadget", "engagement_rate": 7.2, "total_views": 98000, "creator_count": 12, "trend_status": "hot"},
                    ]
                }
            },
            {},
        )

    service = MarketTrendService()
    service._collect_base_bundle = _fake_collect.__get__(service, MarketTrendService)
    result = _run(service.get_tiktok_tag_trends(query="蓝牙耳机", category="electronics", target_market="US"))
    assert result["dataset"] == "tiktok_tag_trends"
    assert result["tag_count"] >= 1
    assert result["tags"][0]["tag"].startswith("#")
    assert "avg_engagement_rate" in result["tags"][0]
    assert result["source_bundle"]["local_business_ready"] is True
    assert result["source_bundle"]["enterprise_ready"] is False


def test_report_center_service_builds_valid_pdf_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CENTER_STATE_PATH", str(tmp_path / "report_state.json"))
    service = ReportCenterService()
    report = _run(service.generate(report_type="daily", format="pdf", task_id="task-pdf-001", params={"gmv": 123.4, "completion_rate": 0.88}))
    downloaded = _run(service.build_download(report["report_id"]))
    assert downloaded is not None
    content, media_type, filename = downloaded
    assert media_type == "application/pdf"
    assert filename.endswith(".pdf")
    assert content.startswith(b"%PDF-")
    assert b"/Type /Catalog" in content


def test_profit_optimization_service_quote_cache_and_restock_plan(monkeypatch):
    async def _fake_execute(self, **kwargs):
        return {
            "source": "ali1688",
            "suppliers": [
                {
                    "supplier_id": "SUP-1688-001",
                    "company_name": "深圳优选工厂",
                    "is_verified": True,
                    "trade_assurance": True,
                    "response_rate": 0.96,
                    "rating": 4.8,
                    "lead_time_days": 9,
                    "monthly_capacity": 50000,
                    "defect_rate_pct": 0.6,
                    "moq_tiers": [{"min_qty": 120, "unit_price_usd": 18.6}],
                },
                {
                    "supplier_id": "SUP-1688-002",
                    "company_name": "宁波稳供工厂",
                    "is_verified": True,
                    "trade_assurance": False,
                    "response_rate": 0.88,
                    "rating": 4.5,
                    "lead_time_days": 12,
                    "monthly_capacity": 40000,
                    "defect_rate_pct": 1.1,
                    "moq_tiers": [{"min_qty": 80, "unit_price_usd": 17.9}],
                },
            ],
        }

    async def _fake_fetch_orders(self):
        return [
            {"product_id": "prod-001", "quantity": 8, "revenue": 319.2},
            {"product_id": "prod-001", "quantity": 5, "revenue": 204.5},
        ]

    async def _fake_fetch_finance_metrics(self):
        return [
            {
                "product_id": "prod-001",
                "currency": "USD",
                "procurement_cost_per_unit": 18.4,
                "logistics_cost_per_unit": 2.3,
                "marketing_cost_per_unit": 1.6,
                "tax_cost_per_unit": 0.8,
                "platform_fee_rate": 0.15,
                "platform_fee_amount": 5.99,
                "gross_profit": 12.81,
            }
        ]

    async def _fake_fetch_supplier_quotes(self):
        return [
            {
                "supplier_code": "SCM-SUP-001",
                "supplier_name": "深圳稳供供应商",
                "product_keyword": "蓝牙耳机",
                "quality_score": 4.7,
                "on_time_delivery_rate": 0.95,
                "price_stability_score": 0.9,
                "response_rate": 0.93,
                "lead_time_days": 11,
                "price_trend": "stable",
            },
            {
                "supplier_code": "SCM-SUP-002",
                "supplier_name": "宁波供应商",
                "product_keyword": "蓝牙耳机",
                "quality_score": 4.3,
                "on_time_delivery_rate": 0.89,
                "price_stability_score": 0.82,
                "response_rate": 0.88,
                "lead_time_days": 14,
                "price_trend": "rising",
            },
        ]

    monkeypatch.setattr("src.services.profit_optimization_service.Tool1688.execute", _fake_execute)
    monkeypatch.setattr("src.services.profit_optimization_service.OMSClient.fetch_orders", _fake_fetch_orders)
    monkeypatch.setattr("src.services.profit_optimization_service.FMSClient.fetch_finance_metrics", _fake_fetch_finance_metrics)
    monkeypatch.setattr("src.services.profit_optimization_service.SCMClient.fetch_supplier_quotes", _fake_fetch_supplier_quotes)
    monkeypatch.setattr("src.services.profit_optimization_service.get_redis_connection", lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")))

    service = ProfitOptimizationService()
    quote_cache = _run(service.build_quote_cache(product_keyword="蓝牙耳机", max_suppliers=10))
    restock_plan = _run(
        service.build_restock_plan(
            product_keyword="蓝牙耳机",
            monthly_demand=300,
            current_inventory_units=20,
            target_price=39.9,
            max_suppliers=10,
            preferred_supplier_code="SUP-1688-001",
            oms_api_endpoint="file://dummy/oms",
            product_id="prod-001",
        )
    )
    fms_snapshot = _run(
        service.build_fms_cost_snapshot(
            product_id="prod-001",
            fms_api_endpoint="file://dummy/fms",
            currency="USD",
            exchange_rate=1.0,
        )
    )
    supplier_reliability = _run(
        service.build_supplier_reliability(
            product_keyword="蓝牙耳机",
            scm_api_endpoint="file://dummy/scm",
            preferred_supplier_code="SCM-SUP-001",
        )
    )

    assert quote_cache["summary"]["supplier_count"] == 2
    assert quote_cache["cache_backend"] == "memory"
    assert quote_cache["quotes"][0]["supplier_code"] == "SUP-1688-002"
    assert restock_plan["restock_recommended"] is True
    assert restock_plan["supplier"]["supplier_code"] == "SUP-1688-001"
    assert restock_plan["optimal_purchase_batch"]["recommended_batch"] >= 120
    assert restock_plan["price_elasticity_snapshot"]["found"] is True
    assert fms_snapshot["found"] is True
    assert fms_snapshot["procurement_cost_per_unit"] == 18.4
    assert fms_snapshot["source"] == "fms_cost_snapshot"
    assert supplier_reliability["selected_supplier"]["found"] is True
    assert supplier_reliability["selected_supplier"]["supplier_code"] == "SCM-SUP-001"
    assert supplier_reliability["selected_supplier"]["reliability_score"] > 80


def test_selection_service_get_accuracy_trend_uses_execution_feedback():
    service = SelectionTaskService(session=None, tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca", actor={"tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca", "roles": ["tenant_admin"]})

    completed_task = SimpleNamespace(
        id="task-acc-001",
        title="蓝牙耳机",
        target_category="electronics",
        target_market="US",
        budget_max=50000,
        status=SimpleNamespace(value="completed"),
        priority=SimpleNamespace(value="high"),
        created_at=datetime.fromisoformat("2026-04-10T00:00:00+00:00"),
        updated_at=datetime.fromisoformat("2026-04-14T00:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-04-14T00:00:00+00:00"),
        result_summary="done",
        created_by=None,
        config={
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "adoption": {"status": "executed", "total_amount": 240.0, "executed_at": "2026-04-14T00:00:00+00:00"},
            "execution_result": {"decision_output": {"decision": {"decision": "GO"}}},
            "execution_feedback_snapshot": {
                "sales": {"orders": {"units": 32}},
                "reviews": {"avg_rating": 4.6},
                "profit": {"gross_profit_total": 139.0},
            },
        },
    )

    class _Repo:
        async def list_tasks(self, limit=100, offset=0, status=None):
            return [completed_task], 1

    service.repo = _Repo()
    result = _run(service.get_accuracy_trend(limit=100))
    assert result["total_tasks"] == 1
    assert result["correct_tasks"] == 1
    assert result["accuracy"] == 1.0
    assert result["trend"][0]["date"] == "2026-04-14"


def test_selection_master_build_decision_output_contains_top50_recommendations():
    from src.agents.selection_master import SelectionMaster, SelectionState

    state = SelectionState(session_id="sess-top50-001", query="蓝牙耳机", category="electronics", target_market="US")
    state.product_planning_result = {
        "product_spec": {"name": "蓝牙耳机 Pro", "positioning": "mid-range", "core_features": ["降噪", "长续航"], "selling_points": ["舒适佩戴"]},
        "supply_chain": {"lead_time_days": 21, "risk_level": "low", "recommendations": ["优先联系头部供应商"]},
        "recommendations": [
            {"rank": 1, "product_name": f"蓝牙耳机 候选{i}", "confidence": 95 - i, "expected_roi": 40 - i * 0.2, "time_to_market_weeks": 4, "risk_rating": "low", "pros": ["卖点清晰"], "cons": [], "action_items": ["验证样品"]}
            for i in range(1, 51)
        ],
    }
    state.market_analysis_result = {"opportunity_score": {"overall_score": 82, "recommendation": "值得进入"}, "trends": {"direction": "up", "strength": 0.8, "confidence": 0.9}}
    state.commercial_evaluation_result = {"go_no_go": {"decision": "GO", "confidence": 0.88, "score": 87, "recommendation": "建议推进"}, "financial_projection": {"gross_margin": 0.32, "net_margin": 0.18, "ltv_cac_ratio": 2.4}, "pricing_suggestion": {"recommended_price": 39.9, "pricing_strategy": "penetration"}, "risk_assessment": {"top_risks": []}}
    output = SelectionMaster._build_decision_output(state, execution_log=[])

    assert len(output["top_recommendations"]) == 50
    assert output["top_recommendations"][0]["rank"] == 1
    assert output["top_recommendations"][0]["product_name"].startswith("蓝牙耳机 候选")


def test_selection_service_get_task_result_includes_similar_history_cases():
    service = SelectionTaskService(session=None, actor={"roles": ["operator"], "tenant_id": "tenant-actor-002"})

    async def _fake_get_task(task_id):
        return {
            "task_id": task_id,
            "query": "蓝牙耳机",
            "category": "electronics",
            "target_market": "US",
            "status": "completed",
            "result": {"decision_output": {"decision": {"decision": "GO"}}},
            "result_summary": "执行完成",
            "go_no_go": {"decision": "GO"},
            "go_no_go_decision": "GO",
            "decision_output": {
                "decision": {"decision": "GO"},
                "product": {"name": "蓝牙耳机 Pro", "asin": "B0SIM001"},
                "pricing": {"recommended_price": 39.99},
                "recommendation_reasons": ["续航强", "降噪稳定"],
            },
            "completed_at": "2026-04-14T10:00:00+00:00",
        }

    async def _fake_load_similar_history_cases(task_payload, top_k=3):
        return {
            "query": "蓝牙耳机 electronics US GO 39.99",
            "case_type": "selection_history_case",
            "total_found": 1,
            "processing_time_ms": 6.0,
            "results": [{"document_id": "case-doc-001", "source": "selection_case_task-001.md", "score": 0.93}],
        }

    async def _fake_load_similar_review_cases(task_payload, top_k=3):
        return {
            "query": "蓝牙耳机 electronics US GO 39.99 评价 投诉 差评 好评",
            "case_type": "crm_review_case",
            "total_found": 1,
            "processing_time_ms": 5.0,
            "results": [{"document_id": "review-doc-001", "source": "crm_review_case_crm-001.md", "score": 0.91}],
        }

    async def _fake_load_historical_performance(task_payload, top_k=5):
        return {
            "query": "蓝牙耳机 electronics US GO 39.99",
            "case_type": "historical_performance",
            "total_found": 1,
            "results": [{"task_id": "task-history-001", "performance": {"oms": {"units": 32}, "crm": {"avg_rating": 4.6}, "scm": {"status": "completed"}, "wms": {"available_quantity_total": 120}}}],
        }

    service.get_task = _fake_get_task
    service._load_similar_history_cases = _fake_load_similar_history_cases
    service._load_similar_review_cases = _fake_load_similar_review_cases
    service._load_historical_performance = _fake_load_historical_performance

    result = _run(service.get_task_result("task-similar-case-001"))
    assert result is not None
    assert result["similar_history_cases"]["case_type"] == "selection_history_case"
    assert result["similar_history_cases"]["total_found"] == 1
    assert result["similar_history_cases"]["results"][0]["source"] == "selection_case_task-001.md"
    assert result["review_cases"]["case_type"] == "crm_review_case"
    assert result["review_cases"]["results"][0]["source"] == "crm_review_case_crm-001.md"
    assert result["historical_performance"]["case_type"] == "historical_performance"
    assert result["historical_performance"]["results"][0]["performance"]["oms"]["units"] == 32


def test_local_knowledge_review_case_ingest_and_query(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.local_knowledge_service._DB_PATH", tmp_path / "local_review_knowledge.db")
    monkeypatch.setattr("src.services.local_knowledge_service.get_redis_connection", lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")))
    from src.services.local_knowledge_service import LocalKnowledgeService

    service = LocalKnowledgeService()
    ingest_result = _run(
        service.ingest_review_case(
            {
                "id": "crm-001",
                "task_id": "selection-task-erp-real-001",
                "product_id": "selection-task-erp-real-001",
                "product_name": "蓝牙耳机企业联调样本",
                "asin": "B0ERP0001",
                "feedback": "客户评价良好，但出现少量退货投诉，需要优化包装。",
                "customer_score": 4.6,
                "review_count": 13,
            }
        )
    )
    assert ingest_result["case_type"] == "crm_review_case"
    assert ingest_result["vector_sync"]["is_incremental"] is True
    assert ingest_result["vector_sync"]["chunk_count"] >= 1
    assert ingest_result["vector_sync"]["collection_name"] == "product_knowledge_local"
    query_result = _run(service.query_review_cases("蓝牙耳机 退货 投诉 包装", top_k=3, threshold=0.1))
    cached_result = _run(service.query_review_cases("蓝牙耳机退货投诉包装", top_k=3, threshold=0.1))
    assert query_result["case_type"] == "crm_review_case"
    assert query_result["total_found"] >= 1
    assert query_result["cache_hit"] is False
    assert query_result["cache_backend"] == "memory"
    assert any(str(item.get("source") or "").startswith("crm_review_case_") or "case_type: crm_review_case" in str(item.get("content") or "") for item in query_result["results"])
    assert cached_result["cache_hit"] is True
    assert cached_result["cache_backend"] == "memory"
    assert (cached_result["cache_similarity"] or 0) >= 0.95


def test_knowledge_service_uses_actor_tenant_by_default():
    service = KnowledgeService(session=None, actor={"roles": ["operator"], "tenant_id": "tenant-kb-001"})
    assert service.tenant_id == "tenant-kb-001"


def test_default_tenant_context_values():
    from src.core.tenant import get_default_tenant_context

    tenant = get_default_tenant_context()
    assert tenant.tenant_key == "default"
    assert tenant.tenant_name == "默认租户"
    assert tenant.tenant_id


def test_tenant_scoped_repository_enforces_and_defaults_tenant():
    session = SimpleNamespace()

    required_repo = TenantScopedRepository(session, require_tenant=True)
    assert required_repo.require_tenant_id()
    assert required_repo.tenant_uuid()

    optional_repo = TenantScopedRepository(session, require_tenant=False)
    try:
        optional_repo.require_tenant_id()
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_tenant_config_and_quota_models_exist():
    assert TenantConfig.__tablename__ == "tenant_configs"
    assert TenantQuota.__tablename__ == "tenant_quotas"
    assert any(col.name == "tenant_id" for col in TenantConfig.__table__.columns)
    assert any(col.name == "config_key" for col in TenantConfig.__table__.columns)
    assert any(col.name == "tenant_id" for col in TenantQuota.__table__.columns)
    assert any(col.name == "quota_type" for col in TenantQuota.__table__.columns)


def test_worker_poll_once_executes_claimed_tasks(monkeypatch):
    repo = _FakeTaskRepo()

    class _Result:
        def fetchall(self):
            return [(uuid.UUID("00000000-0000-0000-0000-00000000c101"),)]

    class _FakeSession:
        async def execute(self, stmt):
            return _Result()

        async def commit(self):
            return None

    class _FakeService:
        def __init__(self, session=None, actor=None, tenant_id=None, executor=None):
            self.repo = repo
            self.executed = []

        async def execute_task(self, context):
            _FakeService._executed_context = context

    class _SessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.workers.selection_worker.get_async_session_factory", lambda: (lambda: _SessionContext()))
    monkeypatch.setattr("src.workers.selection_worker.SelectionTaskService", _FakeService)

    worker = SelectionTaskWorker(poll_interval_seconds=0.1, batch_size=1)
    processed = _run(worker.poll_and_run_once())

    assert processed == 1
    assert repo.claimed
    assert _FakeService._executed_context.query == "蓝牙耳机"


def test_celery_selection_task_wrapper_executes_service(monkeypatch):
    captured = {}

    class _FakeService:
        def __init__(self, session=None, tenant_id=None, actor=None, executor=None):
            self.session = session

        async def execute_task(self, context):
            captured["task_id"] = context.task_id
            captured["tenant_id"] = context.tenant_id
            captured["query"] = context.query

    monkeypatch.setattr("src.workers.celery_selection_tasks.SelectionTaskService", _FakeService)
    result = execute_selection_task({
        "task_id": "task-celery-001",
        "tenant_id": "tenant-celery-001",
        "query": "蓝牙耳机",
        "category": "electronics",
        "investment_budget": 50000.0,
        "target_market": "US",
        "auto_approve": False,
        "priority": "normal",
    })
    assert result["status"] == "submitted_to_execution"
    assert captured["task_id"] == "task-celery-001"
    assert captured["tenant_id"] == "tenant-celery-001"


def test_worker_stop_and_entrypoint_exist():
    worker = SelectionTaskWorker(poll_interval_seconds=0.1, batch_size=1)
    worker.stop()
    assert worker._running is False
    assert callable(run_worker)
    assert callable(worker_module_main)


def test_bi_daily_kpi_worker_run_once(monkeypatch):
    captured = {}

    class _FakeSession:
        async def commit(self):
            return None

    class _SessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeService:
        def __init__(self, session=None, tenant_id=None, actor=None):
            self.session = session

        async def sync_daily_bi_kpis(self, name="default", day=None, limit=200):
            captured["name"] = name
            captured["day"] = day
            return {"log_id": "log-bi-kpi-001", "kpi_date": day or "2026-04-14"}

    monkeypatch.setattr("src.workers.bi_kpi_worker.get_async_session_factory", lambda: (lambda: _SessionContext()))
    monkeypatch.setattr("src.workers.bi_kpi_worker.ErpIntegrationService", _FakeService)

    worker = BIDailyKpiWorker(interval_seconds=60, bootstrap_delay_seconds=0)
    result = _run(worker.run_once(day="2026-04-14"))
    assert result["kpi_date"] == "2026-04-14"
    assert captured["name"] == "default"
    assert captured["day"] == "2026-04-14"


def test_worker_skips_tenant_when_parallelism_exceeded(monkeypatch):
    tenant_id = "00000000-0000-0000-0000-00000000c101"

    class _Metric:
        def labels(self, **kwargs):
            return self

        def set(self, value):
            return None

        def inc(self):
            return None

    class _Repo:
        def __init__(self):
            self.claim_calls = 0

        async def count_running_tasks_by_tenant(self, tenant_id=None):
            return 2

        async def count_backlog_tasks_by_tenant(self, tenant_id=None):
            return 5

        async def claim_pending_tasks(self, limit=1, tenant_id=None):
            self.claim_calls += 1
            return []

    repo = _Repo()

    class _FakeService:
        def __init__(self, session=None, actor=None, tenant_id=None, executor=None):
            self.repo = repo

        async def execute_task(self, context):
            raise AssertionError("should not execute when throttled")

    class _Result:
        def fetchall(self):
            return [(uuid.UUID(tenant_id),)]

    class _Session:
        async def execute(self, stmt):
            return _Result()

        async def commit(self):
            return None

    class _SessionContext:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.workers.selection_worker.get_async_session_factory", lambda: (lambda: _SessionContext()))
    monkeypatch.setattr("src.workers.selection_worker.SelectionTaskService", _FakeService)
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_RUNNING_GAUGE", _Metric())
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_BACKLOG_GAUGE", _Metric())
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_THROTTLED_TOTAL", _Metric())

    worker = SelectionTaskWorker(poll_interval_seconds=0.1, batch_size=1)
    processed = _run(worker.poll_and_run_once())
    assert processed == 0
    assert repo.claim_calls == 0



def test_worker_updates_backlog_and_running_metrics(monkeypatch):
    tenant_id = "00000000-0000-0000-0000-00000000c102"
    metrics = {"running": [], "backlog": []}

    class _Gauge:
        def __init__(self, key):
            self.key = key

        def labels(self, **kwargs):
            return self

        def set(self, value):
            metrics[self.key].append(value)

    class _Counter:
        def labels(self, **kwargs):
            return self

        def inc(self):
            return None

    class _Repo:
        def __init__(self):
            self.claimed = []

        async def count_running_tasks_by_tenant(self, tenant_id=None):
            return 1

        async def count_backlog_tasks_by_tenant(self, tenant_id=None):
            return 3

        async def claim_pending_tasks(self, limit=1, tenant_id=None):
            now = datetime.now(UTC)
            task = SimpleNamespace(
                id=uuid4(),
                tenant_id=uuid.UUID(tenant_id),
                title="蓝牙耳机",
                target_category="electronics",
                target_market="US",
                budget_max=1000.0,
                priority=SimpleNamespace(value="medium"),
                config={"auto_approve": False},
                status=SimpleNamespace(value="running"),
                created_at=now,
            )
            self.claimed.append(task)
            return [task]

    repo = _Repo()

    class _FakeService:
        def __init__(self, session=None, actor=None, tenant_id=None, executor=None):
            self.repo = repo

        async def execute_task(self, context):
            _FakeService.executed = context

    class _Result:
        def fetchall(self):
            return [(uuid.UUID(tenant_id),)]

    class _Session:
        async def execute(self, stmt):
            return _Result()

        async def commit(self):
            return None

    class _SessionContext:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.workers.selection_worker.get_async_session_factory", lambda: (lambda: _SessionContext()))
    monkeypatch.setattr("src.workers.selection_worker.SelectionTaskService", _FakeService)
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_RUNNING_GAUGE", _Gauge("running"))
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_BACKLOG_GAUGE", _Gauge("backlog"))
    monkeypatch.setattr("src.workers.selection_worker.SELECTION_TASK_THROTTLED_TOTAL", _Counter())

    worker = SelectionTaskWorker(poll_interval_seconds=0.1, batch_size=1)
    processed = _run(worker.poll_and_run_once())
    assert processed == 1
    assert metrics["running"] == [1]
    assert metrics["backlog"] == [3]



def test_selection_service_requeues_on_retryable_failure(monkeypatch):
    service = SelectionTaskService(session=None, actor={"tenant_id": "00000000-0000-0000-0000-00000000c101"})

    class _Repo:
        def __init__(self):
            self.task = SimpleNamespace(
                id=uuid.UUID("00000000-0000-0000-0000-00000000c111"),
                status=TaskStatus.PENDING,
                config={"retry_count": 0, "max_retries": 2},
            )
            self.requeued = None
            self.updated = None

        async def get_task(self, task_id, tenant_id=None):
            return self.task

        async def update_task_status(self, *args, **kwargs):
            self.updated = (args, kwargs)
            return True

        async def requeue_task(self, task_id, reason, reset_dead_letter=False):
            self.requeued = {"task_id": str(task_id), "reason": reason, "reset_dead_letter": reset_dead_letter}
            return True

    repo = _Repo()
    service.repo = repo

    class _Session:
        async def commit(self):
            return None

        async def close(self):
            return None

    class _FailingMaster:
        def __init__(self, config=None):
            self.config = config or {}

        async def run(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr("src.services.selection_service.get_async_session_factory", lambda: (lambda: _Session()))
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService", lambda session, executor=None, tenant_id=None, actor=None: SimpleNamespace(repo=repo, _extract_payload=service._extract_payload, _extract_go_no_go=service._extract_go_no_go))
    monkeypatch.setattr("src.services.selection_service.SelectionMaster", _FailingMaster)

    context = SelectionTaskExecutionContext(
        task_id="00000000-0000-0000-0000-00000000c111",
        tenant_id="00000000-0000-0000-0000-00000000c101",
        query="蓝牙耳机",
        category="electronics",
        investment_budget=1000.0,
        target_market="US",
        auto_approve=False,
        priority="normal",
    )
    _run(service.execute_task(context))
    assert repo.requeued is not None
    assert "自动重试 1/2" in repo.requeued["reason"]



def test_selection_service_marks_dead_letter_after_max_retries(monkeypatch):
    service = SelectionTaskService(session=None, actor={"tenant_id": "00000000-0000-0000-0000-00000000c101"})

    class _Repo:
        def __init__(self):
            self.task = SimpleNamespace(
                id=uuid.UUID("00000000-0000-0000-0000-00000000c112"),
                status=TaskStatus.PENDING,
                config={"retry_count": 2, "max_retries": 2},
            )
            self.requeued = None
            self.updated = None

        async def get_task(self, task_id, tenant_id=None):
            return self.task

        async def update_task_status(self, *args, **kwargs):
            self.updated = (args, kwargs)
            return True

        async def requeue_task(self, task_id, reason, reset_dead_letter=False):
            self.requeued = {"task_id": str(task_id), "reason": reason, "reset_dead_letter": reset_dead_letter}
            return True

    repo = _Repo()
    service.repo = repo

    class _Session:
        async def commit(self):
            return None

        async def close(self):
            return None

    class _FailingMaster:
        def __init__(self, config=None):
            self.config = config or {}

        async def run(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr("src.services.selection_service.get_async_session_factory", lambda: (lambda: _Session()))
    monkeypatch.setattr("src.services.selection_service.SelectionTaskService", lambda session, executor=None, tenant_id=None, actor=None: SimpleNamespace(repo=repo, _extract_payload=service._extract_payload, _extract_go_no_go=service._extract_go_no_go))
    monkeypatch.setattr("src.services.selection_service.SelectionMaster", _FailingMaster)

    context = SelectionTaskExecutionContext(
        task_id="00000000-0000-0000-0000-00000000c112",
        tenant_id="00000000-0000-0000-0000-00000000c101",
        query="蓝牙耳机",
        category="electronics",
        investment_budget=1000.0,
        target_market="US",
        auto_approve=False,
        priority="normal",
    )
    _run(service.execute_task(context))
    assert repo.requeued is None
    assert repo.task.config["dead_letter"] is True
    assert repo.task.config["dead_letter_reason"] == "max_retries_exceeded"



def test_rbac_role_matrix_defaults_and_scopes():
    assert DEFAULT_PLATFORM_ADMIN_ROLE in PLATFORM_ROLES
    assert DEFAULT_VIEWER_ROLE in TENANT_ROLES
    assert ROLE_MATRIX["platform_admin"]["scope"] == "platform"
    assert ROLE_MATRIX["tenant_admin"]["scope"] == "tenant"
    assert derive_roles({"is_superuser": True}) == [DEFAULT_PLATFORM_ADMIN_ROLE]
    assert derive_roles({"is_superuser": False}) == [DEFAULT_VIEWER_ROLE]


def test_rbac_permission_model_and_role_mapping():
    perm = build_permission(RESOURCE_SELECTION, ACTION_READ)
    assert perm == "selection.read"
    assert perm in CORE_PERMISSIONS
    assert build_permission(RESOURCE_SELECTION, ACTION_MANAGE) in ROLE_PERMISSIONS["tenant_admin"]
    assert build_permission(RESOURCE_SELECTION, ACTION_READ) in ROLE_PERMISSIONS["viewer"]


def test_selection_service_create_task_denied_without_permission():
    service = SelectionTaskService(
        session=SimpleNamespace(commit=lambda: None, refresh=lambda obj: None),
        actor={"roles": ["viewer"]},
    )
    service.repo = _FakeTaskRepo()

    async def _commit():
        return None

    async def _refresh(obj):
        return None

    service.session.commit = _commit
    service.session.refresh = _refresh

    with pytest.raises(Exception):
        _run(
            service.create_task(
                payload={"query": "蓝牙耳机", "category": "electronics", "priority": "normal"},
                tenant_id="tenant-001",
            )
        )


def test_tenant_repository_get_or_create_default_tenant_real_postgres():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                repo = TenantRepository(session)
                tenant1 = await repo.get_or_create_default_tenant()
                await session.commit()
                tenant2 = await repo.get_or_create_default_tenant()
                return tenant1, tenant2
        finally:
            await close_db()

    tenant1, tenant2 = _run(_scenario())
    assert str(tenant1.id) == str(tenant2.id)
    assert tenant1.tenant_key == "default"
    assert tenant1.name == "默认租户"


def test_selection_task_repository_enforces_tenant_filter_real_postgres():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        tenant_a = "00000000-0000-0000-0000-00000000a001"
        tenant_b = "00000000-0000-0000-0000-00000000b001"
        try:
            async with factory() as session:
                from src.repositories.selection_repository import SelectionTaskRepository

                repo_a = SelectionTaskRepository(session, tenant_id=tenant_a)
                created = await repo_a.create_task(
                    title="tenant-a-task",
                    category="electronics",
                    target_market="US",
                    config={"tenant_id": tenant_a},
                    tenant_id=tenant_a,
                )
                await session.commit()
                task_id = created.id

            async with factory() as session:
                from src.repositories.selection_repository import SelectionTaskRepository

                repo_a = SelectionTaskRepository(session, tenant_id=tenant_a)
                repo_b = SelectionTaskRepository(session, tenant_id=tenant_b)
                visible = await repo_a.get_task(task_id)
                invisible = await repo_b.get_task(task_id)
                return visible, invisible
        finally:
            await close_db()

    visible, invisible = _run(_scenario())
    assert visible is not None
    assert invisible is None


def test_knowledge_service_upload_is_idempotent_when_hash_exists():
    service = KnowledgeService(session=None, actor={"roles": ["operator"]})
    repo = _FakeRepo()
    repo.existing_doc = SimpleNamespace(
        id=uuid4(),
        title="demo.txt",
        file_size=12,
        chunk_count=2,
        status="indexed",
        created_at=datetime.now(UTC),
        extra_data={
            "vector_status": "indexed",
            "provider_mode": "local-mock",
            "status_history": [],
        },
    )
    service.repo = repo
    service.embedding_provider = SimpleNamespace(provider_mode="local-mock")

    result = _run(service.upload_document("demo.txt", b"hello world"))
    assert result["status"] == "indexed"
    assert "文档已存在" in result["message"]
    assert result["vector_status"] == "indexed"


def test_knowledge_service_prefers_qdrant_results(monkeypatch):
    service = KnowledgeService(session=None, actor={"roles": ["analyst"]})
    service.repo = _FakeRepo()
    service.embedding_provider = SimpleNamespace(provider_mode="local-mock")

    async def _fake_qdrant(*args, **kwargs):
        return [{"content": "from qdrant", "score": 0.91, "provider_mode": "local-mock"}]

    monkeypatch.setattr(service, "_search_qdrant", _fake_qdrant)
    result = _run(service.query_knowledge("hello", top_k=3, threshold=0.5))
    assert result["total_found"] == 1
    assert result["results"][0]["content"] == "from qdrant"


def test_knowledge_service_falls_back_to_db_bm25(monkeypatch):
    service = KnowledgeService(session=None)
    repo = _FakeRepo()
    repo.indexed_chunks = [
        SimpleNamespace(
            id=uuid4(),
            document_id=uuid4(),
            chunk_index=0,
            content="fallback content",
            extra_data={"source": "demo.txt", "provider_mode": "local-mock"},
        )
    ]
    service.repo = repo
    service.embedding_provider = SimpleNamespace(provider_mode="local-mock")

    async def _fake_qdrant(*args, **kwargs):
        return []

    class _FakeResult:
        def __init__(self):
            self.content = "fallback content"
            self.score = 0.88
            self.source = "demo.txt"
            self.metadata = {"document_id": "doc-1", "chunk_index": 0, "provider_mode": "local-mock"}

    class _FakeRetriever:
        def __init__(self, *args, **kwargs):
            self.docs = []

        def add_documents(self, docs):
            self.docs.extend(docs)

        async def retrieve(self, query, top_k=5, filters=None):
            return [_FakeResult()]

    monkeypatch.setattr(service, "_search_qdrant", _fake_qdrant)
    monkeypatch.setattr("src.rag.retriever.HybridRetriever", _FakeRetriever)

    result = _run(service.query_knowledge("hello", top_k=3, threshold=0.5))
    assert result["total_found"] == 1
    assert result["results"][0]["content"] == "fallback content"
    assert result["results"][0]["provider_mode"] == "local-mock"


def test_knowledge_service_real_postgres_persistence_and_query():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                service = KnowledgeService(session)
                result = await service.upload_document(
                    "phase3_real_test.txt",
                    "蓝牙耳机适合跨境电商，重点关注续航、轻量化和评论数。".encode(),
                )
                doc_id = result["doc_id"]
                doc_count = (
                    await session.execute(
                        select(func.count()).select_from(Document).where(Document.id == doc_id)
                    )
                ).scalar()
                chunk_count = (
                    await session.execute(
                        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id)
                    )
                ).scalar()
                query_result = await service.query_knowledge("蓝牙耳机", top_k=3, threshold=0.1)
                return result, doc_count, chunk_count, query_result
        finally:
            await close_db()

    result, doc_count, chunk_count, query_result = _run(_scenario())
    assert result["status"] == "indexed"
    assert doc_count == 1
    assert chunk_count >= 1
    assert query_result["total_found"] >= 1
    assert any("蓝牙耳机" in item["content"] for item in query_result["results"])


def test_qdrant_service_real_crud():
    if not _QDRANT_AVAILABLE or qdrant_models is None:
        return

    async def _scenario():
        client = get_qdrant_client()
        service = QdrantService(client)
        collection_name = f"phase3_qdrant_{uuid4().hex[:8]}"
        try:
            await service.ensure_collection(collection_name=collection_name, vector_size=4)
            await service.upsert_points(
                collection_name=collection_name,
                points=[
                    qdrant_models.PointStruct(
                        id=str(uuid4()),
                        vector=[0.1, 0.2, 0.3, 0.4],
                        payload={"kind": "phase3", "text": "bluetooth earbud"},
                    )
                ],
            )
            results = await service.search(
                collection_name=collection_name,
                query_vector=[0.1, 0.2, 0.3, 0.4],
                limit=3,
                score_threshold=0.1,
            )
            await service.delete_by_filter(
                collection_name=collection_name,
                filter_=qdrant_models.Filter(
                    must=[qdrant_models.FieldCondition(key="kind", match=qdrant_models.MatchValue(value="phase3"))]
                ),
            )
            after_delete = await service.search(
                collection_name=collection_name,
                query_vector=[0.1, 0.2, 0.3, 0.4],
                limit=3,
                score_threshold=0.1,
            )
            return results, after_delete
        finally:
            try:
                await client.delete_collection(collection_name)
            except Exception:
                pass
            await close_qdrant()

    results, after_delete = _run(_scenario())
    assert len(results) >= 1
    assert results[0]["payload"]["text"] == "bluetooth earbud"
    assert after_delete == []


def test_knowledge_service_real_qdrant_vector_write():
    if not _QDRANT_AVAILABLE or qdrant_models is None:
        return
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                tenant_id = "00000000-0000-0000-0000-00000000c101"
                service = KnowledgeService(session, actor={"roles": ["tenant_admin"], "tenant_id": tenant_id})
                filename = f"phase3_qdrant_doc_{uuid4().hex[:8]}.txt"
                result = await service.upload_document(
                    filename,
                    "Qdrant 写入验证文本，包含蓝牙耳机与续航关键词。".encode(),
                )
                doc_id = result["doc_id"]
                vector_ids = (
                    await session.execute(
                        select(Chunk.vector_id).where(Chunk.document_id == doc_id)
                    )
                ).scalars().all()
                doc_tenant = (
                    await session.execute(select(Document.tenant_id).where(Document.id == doc_id))
                ).scalar_one()
                chunk_tenants = (
                    await session.execute(select(Chunk.tenant_id).where(Chunk.document_id == doc_id))
                ).scalars().all()
                query_result = await service.query_knowledge("续航", top_k=3, threshold=0.1)
                await service.delete_document(doc_id)
                return result, vector_ids, query_result, tenant_id, doc_tenant, chunk_tenants
        finally:
            await close_db()

    result, vector_ids, query_result, tenant_id, doc_tenant, chunk_tenants = _run(_scenario())
    assert result["qdrant_indexed"] is True
    assert result["vector_status"] == "indexed"
    assert any(vector_id for vector_id in vector_ids)
    assert str(doc_tenant) == tenant_id
    assert all(str(tid) == tenant_id for tid in chunk_tenants)
    assert query_result["total_found"] >= 1


def test_knowledge_service_document_versioning_and_rollback_real_postgres():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        tenant_id = "00000000-0000-0000-0000-00000000e101"
        actor = {"roles": ["platform_admin", "tenant_admin"], "tenant_id": tenant_id, "is_superuser": True}

        try:
            async with factory() as session:
                service = KnowledgeService(session, tenant_id=tenant_id, actor=actor)
                filename = f"spec-version-{uuid.uuid4().hex[:8]}.txt"
                first = await service.upload_document(filename, "版本一内容".encode())
                second = await service.upload_document(filename, "版本二内容".encode())
                versions_before = await service.list_document_versions(second["doc_id"])
                rollback = await service.rollback_document_version(first["doc_id"])
                await session.commit()

            async with factory() as session:
                service = KnowledgeService(session, tenant_id=tenant_id, actor=actor)
                versions_after = await service.list_document_versions(first["doc_id"])
                return first, second, versions_before, rollback, versions_after
        finally:
            await close_db()

    first, second, versions_before, rollback, versions_after = _run(_scenario())
    assert first["version"] == 1
    assert second["version"] == 2
    assert versions_before["total"] >= 2
    assert any(v["version"] == 1 for v in versions_before["versions"])
    assert any(v["version"] == 2 for v in versions_before["versions"])
    assert rollback["version"] == 1
    current_versions = [v for v in versions_after["versions"] if v["is_current_version"] is True]
    assert len(current_versions) == 1
    assert current_versions[0]["version"] == 1



def test_knowledge_service_compare_document_versions_returns_diff_summary():
    from types import SimpleNamespace

    async def _scenario():
        service = KnowledgeService(
            session=None,
            tenant_id="00000000-0000-0000-0000-00000000e101",
            actor={"roles": ["platform_admin", "tenant_admin"], "tenant_id": "00000000-0000-0000-0000-00000000e101", "is_superuser": True},
        )
        baseline_id = str(uuid.uuid4())
        target_id = str(uuid.uuid4())
        baseline_doc = SimpleNamespace(id=uuid.UUID(baseline_id), knowledge_base_id=uuid.uuid4(), title="spec.txt")
        target_doc = SimpleNamespace(id=uuid.UUID(target_id), knowledge_base_id=baseline_doc.knowledge_base_id, title="spec.txt")

        async def _fake_get_document(doc_uuid):
            if str(doc_uuid) == baseline_id:
                return baseline_doc
            if str(doc_uuid) == target_id:
                return target_doc
            return None

        async def _fake_get_document_detail(doc_id):
            if doc_id == baseline_id:
                return {
                    "doc_id": baseline_id,
                    "document_key": "spec.txt",
                    "version": 1,
                    "chunk_count": 2,
                    "is_current_version": False,
                    "chunks": [{"content": "版本一内容"}, {"content": "稳定能力"}],
                }
            return {
                "doc_id": target_id,
                "document_key": "spec.txt",
                "version": 2,
                "chunk_count": 3,
                "is_current_version": True,
                "chunks": [{"content": "版本一内容"}, {"content": "稳定能力"}, {"content": "新增能力"}],
            }

        service.repo.get_document = _fake_get_document
        service.get_document_detail = _fake_get_document_detail
        return await service.compare_document_versions(baseline_id, target_id)

    result = _run(_scenario())
    assert result is not None
    assert result["summary"]["similarity"] < 1
    assert result["summary"]["added_line_count"] == 1
    assert result["difference_items"][0]["type"] == "added"


def test_local_knowledge_service_can_ingest_and_query_selection_case(tmp_path):
    from src.services.local_knowledge_service import LocalKnowledgeRepository, LocalKnowledgeService

    repo = LocalKnowledgeRepository(tmp_path / "selection_case.db")
    service = LocalKnowledgeService(repo=repo)

    task = {
        "task_id": "selection-case-001",
        "query": "蓝牙耳机",
        "category": "electronics",
        "target_market": "US",
        "status": "completed",
        "completed_at": "2026-04-14T10:00:00+00:00",
        "adoption": {
            "status": "executed",
            "supplier_code": "SUP-001",
            "quantity": 200,
        },
        "decision_output": {
            "decision": {"decision": "GO"},
            "product": {"name": "蓝牙耳机 Pro", "asin": "B0CASE001"},
            "pricing": {"recommended_price": 39.99},
            "profitability": {"expected_margin": 28.5},
            "supply_chain": {"primary_supplier": "SUP-001"},
            "recommendation_reasons": ["近30天销量增长显著", "评论反馈集中在续航与降噪"],
            "risks": [{"name": "库存补货节奏", "category": "inventory", "score": 42}],
            "execution_feedback": {
                "sales": {"sales_7d": 12},
                "reviews": {"rating": 4.6, "count": 13},
                "profit": {"gross_profit": 139.0},
                "inventory": {"available_inventory": 18},
            },
            "rescore_summary": {"decision": "GO", "score": 88.0},
        },
        "result": {
            "execution_feedback_snapshot": {
                "sales": {"orders": {"orders": 2, "units": 12}},
                "reviews": {"avg_rating": 4.6, "review_count": 13},
                "profit": {"gross_profit_total": 139.0},
                "inventory": {"summary": {"available_quantity_total": 18}},
            }
        },
    }

    ingest_result = _run(service.ingest_selection_case(task))
    query_result = _run(service.query_selection_cases("蓝牙耳机 续航 降噪 销量", top_k=3, threshold=0.0))

    assert ingest_result["status"] == "indexed"
    assert ingest_result["case_type"] == "selection_history_case"
    assert query_result["case_type"] == "selection_history_case"
    assert query_result["total_found"] >= 1
    assert any("历史选品案例" in str(item.get("content") or "") for item in query_result["results"])


def test_knowledge_service_hybrid_fuses_vector_and_keyword_results(monkeypatch):
    service = KnowledgeService(session=None, actor={"roles": ["operator"], "tenant_id": "00000000-0000-0000-0000-00000000f101"})

    async def _fake_qdrant(*args, **kwargs):
        return [
            {
                "content": "蓝牙耳机支持 ANC 降噪",
                "score": 0.91,
                "source": "doc-a.txt",
                "document_id": "doc-a",
                "chunk_index": 0,
                "provider_mode": "local-mock",
                "metadata": {"tenant_id": service.tenant_id, "document_id": "doc-a", "chunk_index": 0},
            }
        ]

    async def _fake_db(*args, **kwargs):
        return [
            {
                "content": "蓝牙耳机支持 ANC 降噪",
                "score": 0.77,
                "vector_score": None,
                "keyword_score": 0.77,
                "source": "doc-a.txt",
                "document_id": "doc-a",
                "chunk_index": 0,
                "provider_mode": "local-mock",
                "metadata": {"tenant_id": service.tenant_id, "document_id": "doc-a", "chunk_index": 0},
            },
            {
                "content": "续航可达 30 小时",
                "score": 0.66,
                "vector_score": None,
                "keyword_score": 0.66,
                "source": "doc-b.txt",
                "document_id": "doc-b",
                "chunk_index": 1,
                "provider_mode": "local-mock",
                "metadata": {"tenant_id": service.tenant_id, "document_id": "doc-b", "chunk_index": 1},
            },
        ]

    async def _fake_kb():
        return SimpleNamespace(collection_name="product_knowledge")

    service.repo = SimpleNamespace(get_or_create_default_knowledge_base=_fake_kb)
    monkeypatch.setattr(service, "_search_qdrant", _fake_qdrant)
    monkeypatch.setattr(service, "_search_db_keyword", _fake_db)

    result = _run(service.query_knowledge("蓝牙耳机 ANC", top_k=3, threshold=0.1))
    assert result["total_found"] == 2
    assert result["results"][0]["document_id"] == "doc-a"
    assert result["results"][0]["vector_score"] == 0.91
    assert result["results"][0]["keyword_score"] == 0.77



def test_knowledge_service_prefers_search_backend_keyword_results(monkeypatch):
    service = KnowledgeService(session=None, actor={"roles": ["operator"], "tenant_id": "tenant-search"})

    class _Chunk:
        def __init__(self, chunk_id, document_id, chunk_index, content, extra_data=None):
            self.id = chunk_id
            self.document_id = document_id
            self.chunk_index = chunk_index
            self.content = content
            self.extra_data = extra_data or {}

    chunks = [
        _Chunk("c1", "doc-a", 0, "蓝牙耳机 ANC 降噪"),
        _Chunk("c2", "doc-b", 1, "30小时续航"),
    ]

    async def _fake_list_indexed_chunks():
        return chunks

    service.repo = SimpleNamespace(list_indexed_chunks=_fake_list_indexed_chunks)

    class _Backend:
        settings = SimpleNamespace(index_prefix="pms_knowledge_")

        async def index_documents(self, index_name, documents):
            return None

        async def keyword_search(self, index_name, query, top_k, filters=None):
            assert filters == {"tenant_id": "tenant-search"}
            return [
                {
                    "content": "蓝牙耳机 ANC 降噪",
                    "score": 3.0,
                    "source": "doc-a.txt",
                    "document_id": "doc-a",
                    "chunk_index": 0,
                    "metadata": {"tenant_id": "tenant-search", "document_id": "doc-a", "chunk_index": 0},
                }
            ]

    monkeypatch.setattr("src.services.knowledge_service.get_search_backend", lambda: _Backend())
    result = _run(service._search_db_keyword("蓝牙耳机", top_k=3, threshold=0.1, provider_mode="local-mock"))
    assert len(result) == 1
    assert result[0]["document_id"] == "doc-a"
    assert result[0]["keyword_score"] == 3.0



def test_data_domain_service_has_master_and_business_entities():
    from src.services.data_domain_service import DataDomainService

    service = DataDomainService()
    domains = service.list_domains()
    assert domains["total"] >= 5
    product = service.get_domain("Product")
    task = service.get_domain("SelectionTask")
    assert product is not None and product["domain"] == "master_data"
    assert task is not None and task["domain"] == "business_transaction"
    assert "source_of_truth" in product
    assert "sync_direction" in task



def test_config_center_service_resolves_feature_flag():
    from src.services.config_center_service import ConfigCenterService

    class _Repo:
        async def get_config(self, tenant_id, config_key):
            return SimpleNamespace(config_value={"current": {"version": 2, "value": {"enabled": True, "rollout_percent": 100, "tenant_whitelist": []}}})

    service = ConfigCenterService(SimpleNamespace(), tenant_id="tenant-test")
    service.repo = _Repo()
    result = _run(service.resolve_feature_flag("demo-flag"))
    assert result["version"] == 2
    assert result["enabled"] is True



def test_tenant_quota_repository_preserves_llm_cost_precision():
    from src.infrastructure.database import get_async_session_factory
    from src.repositories.tenant_quota_repository import TenantQuotaRepository
    from src.repositories.tenant_repository import TenantRepository

    async def _scenario():
        session = get_async_session_factory()()
        try:
            tenant_repo = TenantRepository(session)
            await tenant_repo.get_or_create_default_tenant()
            repo = TenantQuotaRepository(session)
            await repo.consume_quota(
                tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca",
                quota_type="llm_cost_usd",
                amount=0.0004,
                default_limit=100,
            )
            await session.commit()
            items = await repo.list_quota_status(tenant_id="86d1f796-7c55-57a1-ac77-2e952a2111ca")
            quota = next(item for item in items if item["quota_type"] == "llm_cost_usd")
            assert quota["used_value"] >= 0.0004
            assert quota["remaining"] < quota["limit_value"]
        finally:
            await session.close()

    _run(_scenario())



def test_config_center_service_build_operations_uses_list_configs():
    from src.services.config_center_service import ConfigCenterService

    class _Repo:
        async def list_configs(self, tenant_id, limit=200):
            assert tenant_id == "tenant-test"
            return [
                SimpleNamespace(config_key="config:selection.worker", config_value={"current": {"version": 2, "description": "worker"}}),
                SimpleNamespace(config_key="config:feature_flag:demo", config_value={"current": {"version": 1, "description": "flag"}}),
            ]

    service = ConfigCenterService(SimpleNamespace(), tenant_id="tenant-test")
    service.repo = _Repo()
    result = _run(service.build_operations_status())
    assert result["config_total"] >= 1
    assert result["feature_flag_total"] >= 1
    assert result["recent_versions"][0]["config_key"].startswith("config:")



def test_rag_evaluation_service_computes_metrics():
    from src.services.rag_evaluation import RAGEvalCase, RAGEvaluationService

    class _FakeKnowledgeService:
        async def query_knowledge(self, query, top_k, threshold):
            return {
                "query": query,
                "results": [
                    {
                        "document_id": "doc-1",
                        "content": "蓝牙耳机续航 30 小时",
                        "score": 0.9,
                        "citation": {"document_id": "doc-1", "chunk_index": 0, "source": "doc.txt", "snippet": "蓝牙耳机续航 30 小时"},
                    }
                ],
            }

        async def get_stats(self):
            return {"total_documents": 1, "indexed_documents": 1, "total_chunks": 2}

    evaluator = RAGEvaluationService(_FakeKnowledgeService())
    result = _run(
        evaluator.run_cases(
            [RAGEvalCase(query="蓝牙耳机", expected_document_ids=["doc-1"], expected_keywords=["续航"], top_k=3, threshold=0.1)]
        )
    )
    assert result["total_cases"] == 1
    assert result["hit_at_k"] == 1.0
    assert result["mrr"] == 1.0
    assert result["citation_match_rate"] == 1.0



def test_knowledge_service_rerank_and_citation_metadata(monkeypatch):
    service = KnowledgeService(session=None, actor={"roles": ["operator"], "tenant_id": "tenant-kb-004"})

    async def _fake_qdrant(*args, **kwargs):
        return [
            {
                "content": "普通蓝牙耳机",
                "score": 0.80,
                "source": "doc-a.txt",
                "document_id": "doc-a",
                "chunk_index": 0,
                "provider_mode": "local-mock",
                "metadata": {"tenant_id": service.tenant_id, "document_id": "doc-a", "chunk_index": 0},
            }
        ]

    async def _fake_db(*args, **kwargs):
        return [
            {
                "content": "ANC 降噪蓝牙耳机，支持 30 小时续航",
                "score": 0.70,
                "vector_score": None,
                "keyword_score": 0.70,
                "source": "doc-b.txt",
                "document_id": "doc-b",
                "chunk_index": 1,
                "provider_mode": "local-mock",
                "metadata": {"tenant_id": service.tenant_id, "document_id": "doc-b", "chunk_index": 1},
            }
        ]

    class _FakeRerank:
        def __init__(self, top_k=10):
            self.top_k = top_k

        def rerank(self, query, documents, top_k=None, return_scores=True):
            return [
                {"index": 1, "score": 0.95, "document": documents[1]},
                {"index": 0, "score": 0.61, "document": documents[0]},
            ]

    async def _fake_kb():
        return SimpleNamespace(collection_name="product_knowledge")

    service.repo = SimpleNamespace(get_or_create_default_knowledge_base=_fake_kb)
    monkeypatch.setattr(service, "_search_qdrant", _fake_qdrant)
    monkeypatch.setattr(service, "_search_db_keyword", _fake_db)
    monkeypatch.setattr("src.services.rerank.RerankService", _FakeRerank)

    result = _run(service.query_knowledge("蓝牙耳机 ANC", top_k=2, threshold=0.1))
    assert result["total_found"] == 2
    top = result["results"][0]
    assert top["document_id"] == "doc-b"
    assert top["ranking_stage"] == "rerank"
    assert top["rerank_score"] == 0.95
    assert top["citation"]["document_id"] == "doc-b"
    assert top["citation"]["chunk_index"] == 1
    assert top["citation"]["snippet"]
    assert top["ranking_meta"]["rerank_score"] == 0.95
    assert top["ranking_meta"]["final_rank"] == 1



def test_knowledge_repository_enforces_tenant_filter_real_postgres():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        tenant_a = "00000000-0000-0000-0000-00000000a101"
        tenant_b = "00000000-0000-0000-0000-00000000b101"

        try:
            async with factory() as session:
                repo_a = KnowledgeRepository(session, tenant_id=tenant_a)
                kb_a = await repo_a.get_or_create_default_knowledge_base()
                doc_a = await repo_a.create_document(
                    knowledge_base_id=kb_a.id,
                    title="tenant-a-doc",
                    doc_type="txt",
                    file_size=12,
                    content_hash="hash-a",
                    status="indexed",
                    extra_data={"tenant_id": tenant_a},
                )
                await session.commit()
                doc_a_id = doc_a.id

            async with factory() as session:
                repo_a = KnowledgeRepository(session, tenant_id=tenant_a)
                repo_b = KnowledgeRepository(session, tenant_id=tenant_b)
                doc_visible = await repo_a.get_document(doc_a_id)
                doc_hidden = await repo_b.get_document(doc_a_id)
                return doc_visible is not None, doc_hidden is None
        finally:
            await close_db()

    visible, hidden = _run(_scenario())
    assert visible is True
    assert hidden is True


def test_audit_log_persistent_store_real_postgres():
    if "postgresql+asyncpg" not in os.environ.get("DB_URL", "postgresql+asyncpg://pms:pms_dev_2024@localhost:5432/pms_db"):
        return

    async def _scenario():
        await init_db()
        factory = get_async_session_factory()
        tenant_id = "00000000-0000-0000-0000-00000000d101"

        try:
            async with factory() as session:
                from src.repositories.audit_repository import AuditLogRepository

                repo = AuditLogRepository(session, tenant_id=tenant_id)
                await repo.create_log(
                    action="selection.task.create",
                    actor={"username": "tenant-admin", "tenant_id": tenant_id, "is_superuser": False},
                    target_type="selection_task",
                    target_id="task-001",
                    result="success",
                    detail={"request_id": "req-audit-001", "trace_id": "tr-audit-001"},
                )
                await session.commit()

            async with factory() as session:
                from src.core.security import list_audit_logs_persistent

                logs = await list_audit_logs_persistent(
                    tenant_id=tenant_id,
                    username="tenant-admin",
                    action="selection.task.create",
                    target_id="task-001",
                    request_id="req-audit-001",
                    trace_id="tr-audit-001",
                    limit=10,
                )
                return logs
        finally:
            await close_db()

    logs = _run(_scenario())
    assert len(logs) >= 1
    assert logs[0]["action"] == "selection.task.create"
    assert logs[0]["actor"]["tenant_id"] == "00000000-0000-0000-0000-00000000d101"
    assert logs[0]["request_id"] == "req-audit-001"
    assert logs[0]["trace_id"] == "tr-audit-001"



def test_build_gateway_config_reads_real_settings():
    os.environ["LLM_VLLM_ENDPOINT"] = "https://api.routin.ai/v1"
    os.environ["LLM_OLLAMA_ENDPOINT"] = "http://localhost:11434"
    os.environ["LLM_API_KEY"] = "demo-key"
    os.environ["LLM_API_AUTH_HEADER"] = "Authorization"
    os.environ["LLM_API_AUTH_SCHEME"] = "Bearer"
    os.environ["LLM_API_MODEL_NAME"] = "gpt-5.4"
    os.environ["LLM_REQUEST_RETRY_COUNT"] = "2"

    from src.config.settings import get_settings

    get_settings.cache_clear()
    cfg = _build_gateway_config(use_mock=False)

    assert cfg.use_mock is False
    assert cfg.provider_mode == "real"
    assert cfg.vllm_endpoint == "https://api.routin.ai/v1"
    assert cfg.api_key == "demo-key"
    assert cfg.api_model_name == "gpt-5.4"
    assert cfg.retry_count == 2

    get_settings.cache_clear()


def test_build_gateway_config_accepts_primary_and_fallback_provider_override():
    from src.config.settings import get_settings

    get_settings.cache_clear()
    cfg = _build_gateway_config(use_mock=False, primary_provider="ollama", fallback_provider="vllm")

    assert cfg.use_mock is False
    assert cfg.provider_mode == "real"
    assert cfg.primary_provider == "ollama"
    assert cfg.fallback_provider == "vllm"
    assert cfg.fallback_timeout_budget_seconds <= 5.0

    get_settings.cache_clear()


def test_build_gateway_config_defaults_to_real_first_in_test_environment(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("LLM_VLLM_ENDPOINT", "https://real-llm.example/v1")
    monkeypatch.setenv("LLM_OLLAMA_ENDPOINT", "http://localhost:11434")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    cfg = _build_gateway_config()

    assert cfg.use_mock is False
    assert cfg.provider_mode == "real"
    assert cfg.vllm_endpoint == "https://real-llm.example/v1"

    get_settings.cache_clear()


def test_build_gateway_config_status_uses_effective_environment(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("LLM_VLLM_ENDPOINT", "https://real-llm.example/v1")
    monkeypatch.setenv("LLM_OLLAMA_ENDPOINT", "http://localhost:11434")

    from src.config.settings import get_settings

    get_settings.cache_clear()
    cfg = _build_gateway_config(use_mock=None)
    assert cfg.use_mock is False
    assert cfg.provider_mode == "real"
    get_settings.cache_clear()
