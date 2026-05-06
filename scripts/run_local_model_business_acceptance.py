import asyncio
import base64
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.product_planner import ProductPlannerAgent
from src.infrastructure.ollama_client import OllamaClient
from src.services.multimodal_inference_service import MultimodalInferenceService


_SAMPLE_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+bY9sAAAAASUVORK5CYII="
)


async def _capture_step(awaitable) -> dict:
    try:
        return {"ok": True, "payload": await awaitable, "error": None}
    except Exception as exc:
        return {"ok": False, "payload": None, "error": f"{type(exc).__name__}: {exc}"}


async def _run() -> dict:
    artifact_dir = Path("artifacts/llm")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sample_image_path = artifact_dir / "multimodal_smoke_sample.png"
    sample_image_path.write_bytes(base64.b64decode(_SAMPLE_PNG_BASE64))

    client = OllamaClient()
    multimodal = MultimodalInferenceService()
    planner = ProductPlannerAgent()

    text_step = await _capture_step(client.generate("2+2 equals what? Reply with one number only."))
    image_step = await _capture_step(
        multimodal.analyze_image(
            image_url=str(sample_image_path),
            prompt="Analyze the product hero image and extract positioning hints.",
            analysis_type="features",
            use_mock=False,
        )
    )
    video_step = await _capture_step(
        multimodal.analyze_video(
            video_url="sample://bluetooth-earbuds-video",
            video_title="Bluetooth earbuds office call demo",
            video_description="Focus on commute noise reduction, office meetings, and wearing comfort.",
            prompt="Extract selling points and risks.",
            use_mock=False,
        )
    )
    agent_step = await _capture_step(
        planner.run(
            {
                "query": "Plan a bluetooth earbuds product line.",
                "category": "electronics",
                "use_mock": False,
                "review_images": [{"image_url": str(sample_image_path), "analysis_type": "features"}],
                "tiktok_videos": [
                    {
                        "video_url": "sample://bluetooth-earbuds-video",
                        "title": "Bluetooth earbuds office call demo",
                        "description": "Focus on commute noise reduction, office meetings, and wearing comfort.",
                    }
                ],
                "audio_assets": [{"audio_url": "sample://bluetooth-earbuds-commute-office-sport", "language": "zh"}],
            }
        )
    )

    text_payload = text_step["payload"] or {}
    image_payload = image_step["payload"] or {}
    video_payload = video_step["payload"] or {}
    agent_payload = agent_step["payload"]
    agent_output = (agent_payload.output or {}) if agent_step["ok"] and agent_payload is not None else {}
    agent_data = agent_output.get("data") or {}

    text_passed = text_step["ok"] and bool(str(text_payload.get("response") or "").strip())
    image_passed = image_step["ok"] and bool(image_payload.get("model_name")) and bool(
        image_payload.get("product_description") or image_payload.get("visual_features")
    )
    video_passed = video_step["ok"] and bool(video_payload.get("model_name")) and bool(
        video_payload.get("scenario_summary") or video_payload.get("selling_points")
    )
    agent_passed = bool(
        agent_step["ok"]
        and agent_payload is not None
        and agent_payload.success
        and isinstance(agent_data, dict)
        and agent_data
    )

    passed_checks = sum([text_passed, image_passed, video_passed, agent_passed])
    acceptance = {
        "status": "passed" if passed_checks == 4 else ("partial" if passed_checks else "failed"),
        "accepted": passed_checks == 4,
        "statistics": {
            "total_checks": 4,
            "passed_checks": passed_checks,
            "failed_checks": 4 - passed_checks,
            "real_provider_checks": sum(
                [
                    str(image_payload.get("provider_mode") or "") == "real",
                    str(video_payload.get("provider_mode") or "") == "real",
                    str((((agent_data.get("llm_plan") or {}).get("provider_mode")) or "")) == "real",
                ]
            ),
            "degraded_checks": sum(
                [
                    bool(image_payload.get("degraded")),
                    bool(video_payload.get("degraded")),
                ]
            ),
        },
        "text_chat": {
            "passed": text_passed,
            "model": text_payload.get("model"),
            "response": str(text_payload.get("response") or "").strip(),
            "latency_ms": text_payload.get("latency_ms"),
            "error": text_step["error"],
        },
        "image_analysis": {
            "passed": image_passed,
            "provider_mode": image_payload.get("provider_mode"),
            "model_name": image_payload.get("model_name"),
            "design_score": image_payload.get("design_score"),
            "degraded": image_payload.get("degraded"),
            "error": image_step["error"],
        },
        "video_analysis": {
            "passed": video_passed,
            "provider_mode": video_payload.get("provider_mode"),
            "model_name": video_payload.get("model_name"),
            "scenario_summary": video_payload.get("scenario_summary"),
            "frames_analyzed": video_payload.get("frames_analyzed"),
            "degraded": video_payload.get("degraded"),
            "error": video_step["error"],
        },
        "agent_integration": {
            "passed": agent_passed,
            "success": bool(agent_payload.success) if agent_payload is not None else False,
            "image_count": (agent_data.get("image_review_insights") or {}).get("image_count"),
            "video_count": (agent_data.get("tiktok_video_insights") or {}).get("video_count"),
            "audio_count": (agent_data.get("audio_transcription_insights") or {}).get("audio_count"),
            "error": agent_step["error"],
        },
        "notes": [
            "Text chat first tries the local Ollama generate API and falls back to OpenAI-compatible chat completions when available.",
            "Image and video checks force the real-first multimodal chain so degraded fallback remains visible in the artifact.",
            "Video smoke uses sample metadata input; if ffmpeg and a local video file are present, key-frame extraction is used automatically.",
        ],
    }

    artifact_path = artifact_dir / "local_model_business_acceptance.json"
    artifact_path.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
    acceptance["artifact_path"] = str(artifact_path).replace("\\", "/")
    return acceptance


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
