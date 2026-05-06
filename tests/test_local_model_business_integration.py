from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.config.settings import get_settings
from src.core.auth import create_access_token
from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    async def _noop_init_db():
        return None

    async def _healthy():
        return {"status": "healthy"}

    monkeypatch.setattr("src.infrastructure.database.init_db", _noop_init_db)
    monkeypatch.setattr("src.infrastructure.database.check_db_health", _healthy)
    monkeypatch.setattr("src.infrastructure.redis.check_redis_health", _healthy)
    monkeypatch.setattr("src.infrastructure.qdrant.check_qdrant_health", _healthy)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers():
    token = create_access_token(
        {
            "sub": "integration-user",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "is_superuser": True,
            "tenant_id": "86d1f796-7c55-57a1-ac77-2e952a2111ca",
            "tenant_key": "default",
            "tenant_name": "Default Tenant",
            "roles": ["tenant_admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_llm_multimodal_route_uses_real_service_chain(client, auth_headers, monkeypatch):
    class _FakeMultimodalService:
        model_name = "qwen3.5:2b"

        async def analyze_image(self, *, image_url, prompt="", analysis_type="features", use_mock=None):
            return {
                "source": "multimodal_image_analysis",
                "analysis_type": analysis_type,
                "image_ref": image_url,
                "provider": "ollama",
                "provider_mode": "real",
                "model_name": self.model_name,
                "visual_features": [{"attribute": "design_style", "value": "极简主义", "confidence": 0.94}],
                "product_description": "真实多模态图片分析已接入",
                "design_score": 8.9,
                "market_positioning_hint": "mid-range",
                "defects_detected": 0,
                "defects": [],
                "recommendations": ["保留极简商务风格"],
                "degraded": False,
            }

        async def analyze_video(self, *, video_url, video_title="", video_description="", prompt="", use_mock=None):
            return {
                "source": "tiktok_video_analysis",
                "video_url": video_url,
                "video_title": video_title,
                "provider": "ollama",
                "provider_mode": "real",
                "model_name": self.model_name,
                "transcript": "视频重点展示通勤降噪和办公通话场景。",
                "key_frames": [{"timestamp": "00:03", "scene": "佩戴展示", "focus": "通勤场景"}],
                "selling_points": ["降噪场景直观", "办公通话表达清晰"],
                "risks": [],
                "product_scenarios": [{"scenario": "通勤降噪场景", "confidence": 0.91}],
                "scenario_summary": "通勤降噪场景",
                "engagement_hook": "前3秒展示场景问题",
                "frames_analyzed": 1,
                "frame_analyses": [],
                "degraded": False,
            }

    async def _fake_transcribe(self, **kwargs):
        return {
            "source": "audio_transcription",
            "provider": "whisper-cpu",
            "provider_mode": "real",
            "model_name": "whisper-tiny",
            "audio_ref": kwargs.get("audio_url") or "sample://audio",
            "transcript": "音频提到通勤降噪、办公通话和运动佩戴稳定性。",
            "segments": [{"start": 0.0, "end": 5.0, "text": "音频提到通勤降噪、办公通话和运动佩戴稳定性。"}],
            "language": kwargs.get("language"),
            "detected_language": kwargs.get("language") or "zh",
            "product_scenarios": [{"scenario": "通勤降噪场景", "confidence": 0.93}],
            "scenario_summary": "通勤降噪场景",
            "model_loaded": True,
            "degraded": False,
            "load_error": None,
        }

    monkeypatch.setattr("src.api.v1.endpoints.llm.MultimodalInferenceService", lambda: _FakeMultimodalService())
    monkeypatch.setattr("src.api.v1.endpoints.llm.AudioTranscriptionService.transcribe_audio", _fake_transcribe)

    image_resp = client.post(
        "/api/v1/llm/multimodal/route",
        headers=auth_headers,
        json={"task_type": "image_analysis", "image_url": "https://example.com/product.png", "prompt": "分析主图", "use_mock": False},
    )
    assert image_resp.status_code == 200
    image_data = image_resp.json()["data"]
    assert image_data["provider_mode"] == "real"
    assert image_data["model_name"] == "qwen3.5:2b"
    assert image_data["degraded"] is False

    video_resp = client.post(
        "/api/v1/llm/multimodal/route",
        headers=auth_headers,
        json={"task_type": "video_analysis", "video_url": "https://example.com/video.mp4", "title": "蓝牙耳机场景测评", "description": "重点看通勤和办公", "use_mock": False},
    )
    assert video_resp.status_code == 200
    video_data = video_resp.json()["data"]
    assert video_data["provider_mode"] == "real"
    assert video_data["result"]["frames_analyzed"] == 1
    assert "通勤降噪场景" in video_data["result"]["scenario_summary"]

    audio_resp = client.post(
        "/api/v1/llm/multimodal/route",
        headers=auth_headers,
        json={"task_type": "audio_transcription", "audio_url": "sample://bluetooth-earbuds", "language": "zh", "use_mock": False},
    )
    assert audio_resp.status_code == 200
    audio_data = audio_resp.json()["data"]
    assert audio_data["provider_mode"] == "real"
    assert audio_data["degraded"] is False
    assert audio_data["result"]["model_loaded"] is True


def test_product_planner_agent_invokes_real_model_capability_chain(client, auth_headers, monkeypatch):
    class _FakeMultimodalService:
        async def analyze_image(self, *, image_url, prompt="", analysis_type="features", use_mock=None):
            return {
                "source": "multimodal_image_analysis",
                "analysis_type": analysis_type,
                "image_ref": image_url,
                "provider": "ollama",
                "provider_mode": "real",
                "model_name": "qwen3.5:2b",
                "visual_features": [{"attribute": "material", "value": "铝合金", "confidence": 0.91}],
                "product_description": "真实图片分析链路",
                "design_score": 8.7,
                "market_positioning_hint": "mid-range",
                "defects_detected": 0,
                "defects": [],
                "recommendations": ["强化材质质感表达"],
                "degraded": False,
            }

        async def analyze_video(self, *, video_url, video_title="", video_description="", prompt="", use_mock=None):
            return {
                "source": "tiktok_video_analysis",
                "video_url": video_url,
                "video_title": video_title,
                "provider": "ollama",
                "provider_mode": "real",
                "model_name": "qwen3.5:2b",
                "transcript": "视频展示办公通话和通勤降噪。",
                "key_frames": [{"timestamp": "00:03", "scene": "办公桌面", "focus": "会议通话"}],
                "selling_points": ["办公通话清晰", "降噪表达直观"],
                "risks": ["评论区差评需跟进"],
                "product_scenarios": [{"scenario": "办公会议场景", "confidence": 0.9}],
                "scenario_summary": "办公会议场景",
                "engagement_hook": "开场直接进入会议场景",
                "frames_analyzed": 1,
                "frame_analyses": [],
                "degraded": False,
            }

    async def _fake_transcribe(self, **kwargs):
        return {
            "source": "audio_transcription",
            "provider": "whisper-cpu",
            "provider_mode": "real",
            "model_name": "whisper-tiny",
            "audio_ref": kwargs.get("audio_url"),
            "transcript": "音频强调办公通话和通勤降噪。",
            "segments": [{"start": 0.0, "end": 4.0, "text": "音频强调办公通话和通勤降噪。"}],
            "language": kwargs.get("language"),
            "detected_language": "zh",
            "product_scenarios": [{"scenario": "办公会议场景", "confidence": 0.88}],
            "scenario_summary": "办公会议场景",
            "model_loaded": True,
            "degraded": False,
            "load_error": None,
        }

    async def _fake_fetch_reviews(self):
        return [
            {
                "product_id": "selection-task-erp-real-001",
                "asin": "B0ERP0001",
                "product_name": "蓝牙耳机企业联调样本",
                "feedback": "客户评价良好，但包装仍需优化。",
                "customer_score": 4.6,
                "review_count": 13,
            }
        ]

    async def _fake_supply_chain(self, **kwargs):
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

    monkeypatch.setattr("src.agents.product_planner.MultimodalInferenceService", lambda: _FakeMultimodalService())
    monkeypatch.setattr("src.agents.product_planner.AudioTranscriptionService", lambda: type("AudioSvc", (), {"transcribe_audio": _fake_transcribe})())
    monkeypatch.setattr("src.infrastructure.crm_client.CRMClient.fetch_customer_feedbacks", _fake_fetch_reviews)
    monkeypatch.setattr("src.agents.data_collection.Tool1688._collect_supply_chain", _fake_supply_chain)

    resp = client.post(
        "/api/v1/agents/product_planner/invoke",
        headers=auth_headers,
        json={
            "query": "规划蓝牙耳机产品",
            "category": "electronics",
            "extra_params": {
                "use_mock": False,
                "review_images": [{"image_url": "https://example.com/review1.jpg", "analysis_type": "features"}],
                "tiktok_videos": [{"video_url": "https://example.com/video.mp4", "title": "蓝牙耳机场景测评", "description": "办公和通勤场景"}],
                "audio_assets": [{"audio_url": "sample://bluetooth-earbuds", "language": "zh"}],
                "crm_api_endpoint": "file://artifacts/erp_local/crm",
                "crm_inbound_path": "/feedback",
                "product_id": "selection-task-erp-real-001",
                "asin": "B0ERP0001",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]["data"]
    assert data["image_review_insights"]["analyses"][0]["provider_mode"] == "real"
    assert data["tiktok_video_insights"]["videos"][0]["provider_mode"] == "real"
    assert data["audio_transcription_insights"]["audios"][0]["provider_mode"] == "real"
    assert data["audio_transcription_insights"]["audio_count"] == 1


def test_llm_route_defaults_to_real_in_local_real_mode(client, auth_headers, monkeypatch):
    monkeypatch.setenv("LOCAL_RUNTIME_SCENARIO_MODE", "local-real")
    get_settings.cache_clear()

    async def _fake_resolve_route_policy(self, prompt: str):
        return {
            "version": 1,
            "force_tier": None,
            "use_mock": True,
            "api_model_name": None,
            "gray_hit": False,
            "model_registry_version": 0,
            "active_model_version": None,
            "registered_models": [],
        }

    class _RealFirstResult:
        def __init__(self, use_mock: bool, model_name: str) -> None:
            self.use_mock = use_mock
            self.model_name = model_name

        def to_dict(self):
            return {
                "selected_node": "ollama-local-real",
                "model_name": self.model_name,
                "tier": "light",
                "response": "local real ok",
                "tokens_used": 18,
                "latency_ms": 12.0,
                "cost_usd": 0.0002,
                "degraded": False,
                "provider_mode": "mock" if self.use_mock else "real",
                "primary_provider": "vllm",
                "actual_provider": "ollama",
                "fallback_provider": "ollama",
            }

    class _Gateway:
        def __init__(self, config) -> None:
            self.config = config

        async def route(self, prompt: str, force_tier=None):
            return _RealFirstResult(self.config.use_mock, self.config.ollama_model_name)

    monkeypatch.setattr("src.api.v1.endpoints.llm.PromptPolicyService.resolve_route_policy", _fake_resolve_route_policy)
    monkeypatch.setattr("src.api.v1.endpoints.llm.LLMGateway", _Gateway)

    try:
        resp = client.post(
            "/api/v1/llm/route",
            headers=auth_headers,
            json={"prompt": "请总结蓝牙耳机卖点"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_mode"] == "real"
        assert data["actual_provider"] == "ollama"
        assert data["model_name"] == "qwen2.5:1.5b-instruct"
    finally:
        monkeypatch.delenv("LOCAL_RUNTIME_SCENARIO_MODE", raising=False)
        get_settings.cache_clear()
