from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.ollama_client import OllamaClient
from src.services.audio_transcription_service import (
    AudioTranscriptionService,
    extract_product_scenarios,
    summarize_product_scenarios,
)
from src.services.triton_status_service import TritonStatusService
import contextlib


@dataclass
class _ResolvedBinaryAsset:
    asset_ref: str
    local_path: Path | None
    cleanup_path: Path | None
    base64_payload: str | None = None


class MultimodalInferenceService:
    def __init__(self) -> None:
        settings = get_settings().llm
        self.model_name = getattr(settings, "multimodal_model", "qwen3.5:2b")
        self.endpoint = getattr(settings, "ollama_endpoint", "http://localhost:11434")
        self.timeout_seconds = min(float(getattr(settings, "request_timeout_seconds", 30.0)), 20.0)
        self.audio_service = AudioTranscriptionService()

    def build_status(self) -> dict[str, Any]:
        audio = self.audio_service.build_status()
        default_use_mock = self._should_use_mock(None)
        provider = "mock-qwen35" if default_use_mock else "ollama-compatible"
        provider_mode = "mock" if default_use_mock else "real"
        return {
            "image_model": self.model_name,
            "video_model": self.model_name,
            "audio_model": audio["audio_model"],
            "router_ready": True,
            "default_provider_mode": provider_mode,
            "supported_tasks": ["image_analysis", "video_analysis", "audio_transcription"],
            "image_route": {
                "provider": provider,
                "ready": True,
                "endpoint": self.endpoint,
            },
            "video_route": {
                "provider": provider,
                "ready": True,
                "endpoint": self.endpoint,
            },
            "audio_route": {
                "provider": audio["runtime_backend"],
                "ready": audio["ready"],
                "model_loaded": audio["model_loaded"],
                "deployment_mode": audio["deployment_mode"],
                "supported_languages": audio["supported_languages"],
                "fallback_ready": audio["fallback_ready"],
            },
            "triton_runtime": TritonStatusService().build_status(),
        }

    async def analyze_image(
        self,
        *,
        image_url: str,
        prompt: str = "",
        analysis_type: str = "features",
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        should_use_mock = self._should_use_mock(use_mock)
        image_ref = self._normalize_asset_ref(image_url)
        if should_use_mock:
            result = self._mock_image_analysis(
                image_ref=image_ref,
                analysis_type=analysis_type,
                prompt=prompt,
            )
            result["provider_mode"] = "mock"
            result["degraded"] = True
            return result

        try:
            source = await asyncio.to_thread(
                self._resolve_binary_asset,
                asset_url=image_url,
                default_suffix=".png",
                encode_base64=True,
            )
        except Exception as exc:
            fallback = self._mock_image_analysis(
                image_ref=image_ref,
                analysis_type=analysis_type,
                prompt=prompt,
            )
            fallback["provider_mode"] = "fallback"
            fallback["degraded"] = True
            fallback["load_error"] = str(exc)
            return fallback
        try:
            if source.base64_payload:
                try:
                    payload = await self._client().generate(
                        self._build_image_prompt(prompt=prompt, analysis_type=analysis_type),
                        model_name=self.model_name,
                        images=[source.base64_payload],
                    )
                    return self._format_real_image_result(
                        payload=payload,
                        analysis_type=analysis_type,
                        image_ref=source.asset_ref,
                    )
                except Exception as exc:
                    fallback = self._mock_image_analysis(
                        image_ref=source.asset_ref,
                        analysis_type=analysis_type,
                        prompt=prompt,
                    )
                    fallback["provider_mode"] = "fallback"
                    fallback["degraded"] = True
                    fallback["load_error"] = str(exc)
                    return fallback

            result = self._mock_image_analysis(
                image_ref=source.asset_ref,
                analysis_type=analysis_type,
                prompt=prompt,
            )
            result["provider_mode"] = "fallback"
            result["degraded"] = True
            return result
        finally:
            self._cleanup_path(source.cleanup_path)

    async def analyze_video(
        self,
        *,
        video_url: str,
        video_title: str = "",
        video_description: str = "",
        prompt: str = "",
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        should_use_mock = self._should_use_mock(use_mock)
        if should_use_mock:
            fallback = self._mock_video_analysis(
                video_url=video_url,
                video_title=video_title,
                video_description=video_description,
            )
            fallback["provider_mode"] = "mock"
            fallback["degraded"] = True
            fallback["frame_analyses"] = []
            fallback["frames_analyzed"] = 0
            return fallback

        try:
            source = await asyncio.to_thread(
                self._resolve_binary_asset,
                asset_url=video_url,
                default_suffix=".mp4",
                encode_base64=False,
            )
        except Exception as exc:
            fallback = self._mock_video_analysis(
                video_url=video_url,
                video_title=video_title,
                video_description=video_description,
            )
            fallback["provider_mode"] = "fallback"
            fallback["degraded"] = True
            fallback["frame_analyses"] = []
            fallback["frames_analyzed"] = 0
            fallback["load_error"] = str(exc)
            return fallback
        frame_paths: list[Path] = []
        frame_cleanup_dir: Path | None = None
        try:
            if source.local_path is not None:
                frame_paths, frame_cleanup_dir = await asyncio.to_thread(self._extract_video_frames, source.local_path)

            frame_analyses: list[dict[str, Any]] = []
            for frame_path in frame_paths[:3]:
                frame_analyses.append(
                    await self.analyze_image(
                        image_url=str(frame_path),
                        prompt=prompt or video_description or video_title,
                        analysis_type="features",
                        use_mock=False,
                    )
                )

            try:
                payload = await self._client().generate(
                    self._build_video_prompt(
                        video_title=video_title,
                        video_description=video_description,
                        prompt=prompt,
                        frame_count=len(frame_analyses),
                    ),
                    model_name=self.model_name,
                )
                return self._format_real_video_result(
                    payload=payload,
                    video_url=video_url,
                    video_title=video_title,
                    video_description=video_description,
                    frame_analyses=frame_analyses,
                )
            except Exception as exc:
                fallback = self._mock_video_analysis(
                    video_url=video_url,
                    video_title=video_title,
                    video_description=video_description,
                )
                fallback["provider_mode"] = "fallback"
                fallback["degraded"] = True
                fallback["frame_analyses"] = frame_analyses
                fallback["frames_analyzed"] = len(frame_analyses)
                fallback["load_error"] = str(exc)
                return fallback
        finally:
            self._cleanup_path(source.cleanup_path)
            if frame_cleanup_dir is not None:
                shutil.rmtree(frame_cleanup_dir, ignore_errors=True)

    def _client(self) -> OllamaClient:
        return OllamaClient(
            endpoint=self.endpoint,
            timeout_seconds=self.timeout_seconds,
            model_name=self.model_name,
        )

    def _should_use_mock(self, use_mock: bool | None) -> bool:
        if use_mock is not None:
            return bool(use_mock)
        environment = (get_settings().app.environment or "development").lower()
        local_runtime_mode = os.getenv("LOCAL_RUNTIME_SCENARIO_MODE", "").strip().lower()
        return not (environment in {"test", "staging", "preprod"} or local_runtime_mode == "local-real")

    def _resolve_binary_asset(
        self,
        *,
        asset_url: str,
        default_suffix: str,
        encode_base64: bool,
    ) -> _ResolvedBinaryAsset:
        if not asset_url:
            return _ResolvedBinaryAsset(asset_ref="unknown-asset", local_path=None, cleanup_path=None)

        if asset_url.startswith("data:"):
            payload = asset_url.split(",", 1)[-1]
            raw = base64.b64decode(payload)
            suffix = default_suffix
            if ";base64" in asset_url:
                match = re.search(r"data:([^;]+);base64", asset_url)
                if match and "/" in match.group(1):
                    suffix = "." + match.group(1).split("/", 1)[1]
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp.write(raw)
            temp.close()
            path = Path(temp.name)
            return _ResolvedBinaryAsset(
                asset_ref="inline-base64",
                local_path=path,
                cleanup_path=path,
                base64_payload=payload if encode_base64 else None,
            )

        if asset_url.startswith("file://"):
            path = Path(asset_url.removeprefix("file://"))
            return self._build_resolved_asset(asset_ref=asset_url, path=path, encode_base64=encode_base64)

        local_path = Path(asset_url)
        if local_path.exists():
            return self._build_resolved_asset(asset_ref=str(local_path), path=local_path, encode_base64=encode_base64)

        if asset_url.startswith(("http://", "https://")):
            suffix = Path(asset_url).suffix or default_suffix
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            with urllib.request.urlopen(asset_url, timeout=10) as response:
                temp.write(response.read())
            temp.close()
            path = Path(temp.name)
            return self._build_resolved_asset(
                asset_ref=asset_url,
                path=path,
                cleanup_path=path,
                encode_base64=encode_base64,
            )

        return _ResolvedBinaryAsset(asset_ref=asset_url, local_path=None, cleanup_path=None)

    def _normalize_asset_ref(self, asset_url: str) -> str:
        if not asset_url:
            return "unknown-asset"
        if asset_url.startswith("data:"):
            return "inline-base64"
        return asset_url

    def _build_resolved_asset(
        self,
        *,
        asset_ref: str,
        path: Path,
        cleanup_path: Path | None = None,
        encode_base64: bool,
    ) -> _ResolvedBinaryAsset:
        base64_payload = None
        if encode_base64 and path.exists():
            base64_payload = base64.b64encode(path.read_bytes()).decode("utf-8")
        return _ResolvedBinaryAsset(
            asset_ref=asset_ref,
            local_path=path if path.exists() else None,
            cleanup_path=cleanup_path,
            base64_payload=base64_payload,
        )

    def _extract_video_frames(self, video_path: Path) -> tuple[list[Path], Path | None]:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path or not video_path.exists():
            return [], None

        output_dir = Path(tempfile.mkdtemp(prefix="fms-video-frames-"))
        output_pattern = output_dir / "frame_%02d.jpg"
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=1,scale=640:-1",
            "-frames:v",
            "3",
            str(output_pattern),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            shutil.rmtree(output_dir, ignore_errors=True)
            return [], None
        return sorted(output_dir.glob("frame_*.jpg")), output_dir

    def _build_image_prompt(self, *, prompt: str, analysis_type: str) -> str:
        return (
            "你是跨境电商商品视觉分析助手。请只输出 JSON，不要 Markdown。"
            "字段包括：product_description(string)、visual_features(array[object])、"
            "design_score(number)、market_positioning_hint(string)、"
            "defects(array[object])、recommendations(array[string])。"
            f"当前分析类型：{analysis_type}。"
            f"补充上下文：{prompt or '无'}。"
        )

    def _build_video_prompt(
        self,
        *,
        video_title: str,
        video_description: str,
        prompt: str,
        frame_count: int,
    ) -> str:
        return (
            "你是跨境电商短视频分析助手。请只输出 JSON，不要 Markdown。"
            "字段包括：transcript(string)、selling_points(array[string])、"
            "risks(array[string])、engagement_hook(string)、"
            "scenario_summary(string)、product_scenarios(array[object])。"
            f"标题：{video_title or '无'}。描述：{video_description or '无'}。"
            f"补充提示：{prompt or '无'}。已提取关键帧数量：{frame_count}。"
        )

    def _format_real_image_result(
        self,
        *,
        payload: dict[str, Any],
        analysis_type: str,
        image_ref: str,
    ) -> dict[str, Any]:
        raw_response = str(payload.get("response") or "")
        parsed = self._extract_json_payload(raw_response)
        visual_features = self._normalize_visual_features(parsed.get("visual_features"))
        defects = self._normalize_defects(parsed.get("defects"))
        recommendations = self._normalize_string_list(parsed.get("recommendations"))
        return {
            "source": "multimodal_image_analysis",
            "analysis_type": analysis_type,
            "image_ref": image_ref,
            "provider": "ollama",
            "provider_mode": "real",
            "model_name": self.model_name,
            "visual_features": visual_features,
            "product_description": str(parsed.get("product_description") or parsed.get("summary") or raw_response[:200]),
            "design_score": self._safe_float(parsed.get("design_score"), default=8.0),
            "market_positioning_hint": str(parsed.get("market_positioning_hint") or "mid-range"),
            "defects_detected": len(defects),
            "defects": defects,
            "recommendations": recommendations or ["建议结合用户评论进一步交叉验证视觉判断"],
            "raw_response": raw_response[:800],
            "latency_ms": payload.get("latency_ms"),
            "degraded": False,
        }

    def _format_real_video_result(
        self,
        *,
        payload: dict[str, Any],
        video_url: str,
        video_title: str,
        video_description: str,
        frame_analyses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_response = str(payload.get("response") or "")
        parsed = self._extract_json_payload(raw_response)
        transcript = str(parsed.get("transcript") or raw_response[:240]).strip()
        scenarios = parsed.get("product_scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            scenarios = extract_product_scenarios(" ".join(filter(None, [transcript, video_title, video_description])))

        selling_points = self._normalize_string_list(parsed.get("selling_points"))
        if not selling_points:
            selling_points = self._derive_top_visual_tags(frame_analyses)
        if not selling_points:
            selling_points = ["场景表达清晰", "卖点表达直接"]

        risks = self._normalize_string_list(parsed.get("risks"))
        if not risks and "低价" in f"{video_title} {video_description}":
            risks = ["价格导向较强，可能削弱品牌溢价"]

        return {
            "source": "tiktok_video_analysis",
            "video_url": video_url,
            "video_title": video_title,
            "provider": "ollama",
            "provider_mode": "real",
            "model_name": self.model_name,
            "transcript": transcript,
            "key_frames": self._build_frame_summary(frame_analyses),
            "selling_points": selling_points,
            "risks": risks,
            "product_scenarios": scenarios,
            "scenario_summary": str(parsed.get("scenario_summary") or summarize_product_scenarios(scenarios)),
            "engagement_hook": str(parsed.get("engagement_hook") or "前3秒聚焦核心使用场景和差异化卖点"),
            "frame_analyses": frame_analyses,
            "frames_analyzed": len(frame_analyses),
            "raw_response": raw_response[:800],
            "latency_ms": payload.get("latency_ms"),
            "degraded": False,
        }

    def _mock_image_analysis(self, *, image_ref: str, analysis_type: str, prompt: str) -> dict[str, Any]:
        visual_features = [
            {"attribute": "color_scheme", "value": "深空灰", "confidence": 0.95},
            {"attribute": "material", "value": "铝合金", "confidence": 0.92},
            {"attribute": "form_factor", "value": "入耳式", "confidence": 0.9},
            {"attribute": "design_style", "value": "极简主义", "confidence": 0.88},
        ]
        if analysis_type == "design_defects":
            defects = [
                {
                    "issue": "接口位置不合理",
                    "severity": "low",
                    "suggestion": "建议将充电口调整至更易操作的位置",
                }
            ]
            return {
                "source": "multimodal_image_analysis",
                "analysis_type": analysis_type,
                "image_ref": image_ref,
                "provider": "mock-qwen35",
                "model_name": self.model_name,
                "visual_features": [],
                "product_description": prompt or "商品外观结构存在轻微可优化点",
                "design_score": 7.6,
                "market_positioning_hint": "mid-range",
                "defects_detected": len(defects),
                "defects": defects,
                "recommendations": ["优化接口布局", "补充实物佩戴验证"],
            }

        return {
            "source": "multimodal_image_analysis",
            "analysis_type": analysis_type,
            "image_ref": image_ref,
            "provider": "mock-qwen35",
            "model_name": self.model_name,
            "visual_features": visual_features,
            "product_description": "深空灰极简风格商品，整体质感偏中高端，适合办公与通勤场景。",
            "design_score": 8.6,
            "market_positioning_hint": "mid-range",
            "defects_detected": 0,
            "defects": [],
            "recommendations": ["突出材质质感卖点", "补充场景化主图"],
        }

    def _mock_video_analysis(
        self,
        *,
        video_url: str,
        video_title: str,
        video_description: str,
    ) -> dict[str, Any]:
        transcript_parts = [
            "开场展示产品核心外观与使用场景",
            "强调续航、舒适度和连接稳定性",
            "结合真实体验给出通勤和办公场景建议",
        ]
        seed_text = f"{video_title} {video_description}".lower()
        if "降噪" in seed_text or "anc" in seed_text:
            transcript_parts.append("视频重点演示了降噪效果")
        if "运动" in seed_text or "sport" in seed_text:
            transcript_parts.append("展示了运动佩戴稳定性")
        transcript = "，".join(transcript_parts)
        scenarios = extract_product_scenarios(transcript)
        return {
            "source": "tiktok_video_analysis",
            "video_url": video_url,
            "video_title": video_title,
            "provider": "mock-qwen35",
            "model_name": self.model_name,
            "transcript": transcript,
            "key_frames": [
                {"timestamp": "00:03", "scene": "产品近景展示", "focus": "外观与颜色"},
                {"timestamp": "00:11", "scene": "佩戴演示", "focus": "舒适度与贴合度"},
                {"timestamp": "00:19", "scene": "功能演示", "focus": "续航与连接稳定性"},
            ],
            "selling_points": ["场景表达清晰", "卖点表达直接", "佩戴演示完整"],
            "risks": ["评论区反馈需二次核验"] if "差评" in seed_text else [],
            "product_scenarios": scenarios,
            "scenario_summary": summarize_product_scenarios(scenarios),
            "engagement_hook": "前3秒以真实问题场景切入，转化效率更高",
        }

    def _extract_json_payload(self, text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?", "", candidate, flags=re.IGNORECASE).strip()
            candidate = re.sub(r"```$", "", candidate).strip()
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _normalize_visual_features(self, features: Any) -> list[dict[str, Any]]:
        if not isinstance(features, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in features[:8]:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "attribute": str(item.get("attribute") or item.get("name") or "feature"),
                        "value": str(item.get("value") or item.get("description") or ""),
                        "confidence": self._safe_float(item.get("confidence"), default=0.8),
                    }
                )
            elif item:
                normalized.append({"attribute": "feature", "value": str(item), "confidence": 0.8})
        return normalized

    def _normalize_defects(self, defects: Any) -> list[dict[str, Any]]:
        if not isinstance(defects, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in defects[:6]:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "issue": str(item.get("issue") or item.get("name") or ""),
                        "severity": str(item.get("severity") or "medium"),
                        "suggestion": str(item.get("suggestion") or item.get("advice") or ""),
                    }
                )
            elif item:
                normalized.append({"issue": str(item), "severity": "medium", "suggestion": ""})
        return normalized

    def _normalize_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[,\n;；、]", value) if item.strip()]
        return []

    def _derive_top_visual_tags(self, frame_analyses: list[dict[str, Any]]) -> list[str]:
        counter: Counter[str] = Counter()
        for item in frame_analyses:
            for feature in item.get("visual_features", []):
                value = str(feature.get("value") or "").strip()
                if value:
                    counter[value] += 1
        return [key for key, _ in counter.most_common(3)]

    def _build_frame_summary(self, frame_analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for index, item in enumerate(frame_analyses, start=1):
            top_features = [feature.get("value") for feature in item.get("visual_features", [])[:2] if feature.get("value")]
            summaries.append(
                {
                    "timestamp": f"00:0{index * 3}",
                    "scene": str(item.get("product_description") or "关键帧视觉摘要")[:48],
                    "focus": " / ".join(top_features) or "外观与使用场景",
                }
            )
        return summaries

    def _safe_float(self, value: Any, *, default: float) -> float:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return default

    def _cleanup_path(self, path: Path | None) -> None:
        if path is None:
            return
        with contextlib.suppress(Exception):
            path.unlink(missing_ok=True)
