from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config.settings import get_settings
import contextlib

_SCENARIO_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("通勤降噪场景", ("commute", "subway", "bus", "train", "通勤", "地铁", "公交", "降噪", "anc")),
    ("办公会议场景", ("office", "meeting", "call", "zoom", "teams", "办公", "会议", "通话")),
    ("运动佩戴场景", ("sport", "run", "running", "gym", "fitness", "运动", "跑步", "健身")),
    ("居家娱乐场景", ("home", "movie", "gaming", "game", "居家", "游戏", "追剧")),
    ("出行续航场景", ("travel", "flight", "trip", "battery", "续航", "出行", "旅行", "长途")),
    ("户外便携场景", ("outdoor", "camping", "hiking", "waterproof", "户外", "露营", "便携", "防水")),
)


@dataclass
class _ResolvedAudioSource:
    audio_ref: str
    local_path: Path | None
    cleanup_path: Path | None


def extract_product_scenarios(transcript: str) -> list[dict[str, Any]]:
    normalized = str(transcript or "").lower()
    scenarios: list[dict[str, Any]] = []

    for scenario_name, keywords in _SCENARIO_KEYWORDS:
        matched = [keyword for keyword in keywords if keyword.lower() in normalized]
        if not matched:
            continue
        scenarios.append(
            {
                "scenario": scenario_name,
                "confidence": round(min(0.99, 0.58 + 0.08 * len(matched)), 2),
                "evidence_keywords": matched[:4],
            }
        )

    if scenarios:
        return scenarios

    if normalized.strip():
        return [
            {
                "scenario": "日常泛用场景",
                "confidence": 0.52,
                "evidence_keywords": ["日常使用"],
            }
        ]
    return []


def summarize_product_scenarios(scenarios: list[dict[str, Any]]) -> str:
    if not scenarios:
        return "未识别出明确的产品使用场景"
    return "、".join(str(item.get("scenario") or "") for item in scenarios if item.get("scenario"))


def detect_transcript_language(transcript: str, fallback: str | None = None) -> str:
    text = str(transcript or "")
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return fallback or "unknown"


class AudioTranscriptionService:
    def __init__(self, model_name: str | None = None):
        llm_settings = get_settings().llm
        self.model_name = model_name or getattr(llm_settings, "speech_model", "whisper-tiny")
        self.device = getattr(llm_settings, "speech_device", "cpu")
        self._runtime_backend = self._detect_runtime_backend()
        self._model: Any | None = None
        self._load_error: str | None = None

    def build_status(self) -> dict[str, Any]:
        runtime_ready = self._runtime_backend is not None
        return {
            "audio_model": self.model_name,
            "deployment_mode": "cpu-compatible",
            "ready": True,
            "runtime_backend": self._runtime_backend or "mock-whisper",
            "model_loaded": runtime_ready and self._load_error is None,
            "provider_mode": "real" if runtime_ready else "mock",
            "supported_languages": ["zh", "en", "ja"],
            "accepted_inputs": ["file_path", "file_url", "base64", "sample_scheme"],
            "fallback_ready": True,
            "load_error": self._load_error,
        }

    async def transcribe_audio(
        self,
        *,
        audio_url: str = "",
        audio_base64: str | None = None,
        language: str | None = None,
        prompt: str = "",
        title: str | None = None,
        description: str | None = None,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        needs_local_source = audio_base64 is not None or use_mock is False or (use_mock is None and self._runtime_backend is not None)
        if needs_local_source:
            source = await asyncio.to_thread(self._resolve_audio_source, audio_url=audio_url, audio_base64=audio_base64)
        else:
            source = _ResolvedAudioSource(audio_ref=audio_url or "unknown-audio", local_path=None, cleanup_path=None)
        provider = "whisper-cpu"
        provider_mode = "mock"
        transcript = ""
        segments: list[dict[str, Any]] = []
        detected_language = language
        degraded = True
        error_message: str | None = None

        try:
            should_try_real = use_mock is False or (use_mock is None and self._runtime_backend is not None and source.local_path is not None)
            if should_try_real and self._runtime_backend is not None and source.local_path is not None:
                try:
                    transcript, segments, detected_language = await asyncio.to_thread(
                        self._transcribe_with_runtime,
                        audio_path=source.local_path,
                        language=language,
                        prompt=prompt,
                    )
                    provider_mode = "real"
                    degraded = False
                except Exception as exc:  # pragma: no cover - real runtime branch is environment dependent
                    error_message = str(exc)
                    self._load_error = error_message

            if not transcript:
                transcript = self._build_mock_transcript(
                    audio_ref=source.audio_ref,
                    prompt=prompt,
                    language=language,
                    title=title,
                    description=description,
                )
                segments = [
                    {
                        "start": 0.0,
                        "end": 12.0,
                        "text": transcript,
                    }
                ]
                detected_language = detect_transcript_language(transcript, fallback=language)
                provider = "mock-whisper"
                provider_mode = "mock"
                degraded = True

            scenarios = extract_product_scenarios(transcript)
            return {
                "source": "audio_transcription",
                "provider": provider,
                "provider_mode": provider_mode,
                "model_name": self.model_name,
                "audio_ref": source.audio_ref,
                "transcript": transcript,
                "segments": segments,
                "language": language,
                "detected_language": detected_language or detect_transcript_language(transcript, fallback=language),
                "product_scenarios": scenarios,
                "scenario_summary": summarize_product_scenarios(scenarios),
                "model_loaded": self._runtime_backend is not None and self._load_error is None,
                "degraded": degraded,
                "load_error": error_message or self._load_error,
            }
        finally:
            if source.cleanup_path is not None:
                with contextlib.suppress(Exception):
                    source.cleanup_path.unlink(missing_ok=True)

    def _detect_runtime_backend(self) -> str | None:
        if importlib.util.find_spec("faster_whisper") is not None:
            return "faster-whisper"
        if importlib.util.find_spec("whisper") is not None:
            return "openai-whisper"
        return None

    def _resolve_audio_source(self, *, audio_url: str, audio_base64: str | None) -> _ResolvedAudioSource:
        if audio_base64:
            suffix = ".wav"
            payload = audio_base64.split(",", 1)[-1]
            decoded = base64.b64decode(payload)
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp.write(decoded)
            temp.close()
            path = Path(temp.name)
            return _ResolvedAudioSource(audio_ref="base64-audio", local_path=path, cleanup_path=path)

        if not audio_url:
            return _ResolvedAudioSource(audio_ref="unknown-audio", local_path=None, cleanup_path=None)

        if audio_url.startswith("sample://"):
            return _ResolvedAudioSource(audio_ref=audio_url, local_path=None, cleanup_path=None)

        if audio_url.startswith("file://"):
            path = Path(audio_url.removeprefix("file://"))
            return _ResolvedAudioSource(audio_ref=audio_url, local_path=path if path.exists() else None, cleanup_path=None)

        candidate_path = Path(audio_url)
        if candidate_path.exists():
            return _ResolvedAudioSource(audio_ref=str(candidate_path), local_path=candidate_path, cleanup_path=None)

        if audio_url.startswith(("http://", "https://")):
            suffix = Path(audio_url).suffix or ".bin"
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            with urllib.request.urlopen(audio_url, timeout=10) as response:
                temp.write(response.read())
            temp.close()
            path = Path(temp.name)
            return _ResolvedAudioSource(audio_ref=audio_url, local_path=path, cleanup_path=path)

        return _ResolvedAudioSource(audio_ref=audio_url, local_path=None, cleanup_path=None)

    def _normalize_model_size(self) -> str:
        model_name = self.model_name.lower()
        if model_name.startswith("whisper-"):
            return model_name.split("whisper-", 1)[1]
        return model_name

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._runtime_backend is None:
            raise RuntimeError("Whisper runtime backend is unavailable")
        model_size = self._normalize_model_size()
        if self._runtime_backend == "openai-whisper":  # pragma: no cover - depends on optional dependency
            import whisper

            self._model = whisper.load_model(model_size, device=self.device)
            return self._model
        if self._runtime_backend == "faster-whisper":  # pragma: no cover - depends on optional dependency
            from faster_whisper import WhisperModel

            self._model = WhisperModel(model_size, device=self.device, compute_type="int8")
            return self._model
        raise RuntimeError(f"Unsupported runtime backend: {self._runtime_backend}")

    def _transcribe_with_runtime(
        self,
        *,
        audio_path: Path,
        language: str | None,
        prompt: str,
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        model = self._ensure_model()
        if self._runtime_backend == "openai-whisper":  # pragma: no cover - depends on optional dependency
            result = model.transcribe(str(audio_path), language=language, fp16=False, initial_prompt=prompt or None)
            segments = [
                {
                    "start": float(item.get("start") or 0.0),
                    "end": float(item.get("end") or 0.0),
                    "text": str(item.get("text") or "").strip(),
                }
                for item in result.get("segments") or []
            ]
            return str(result.get("text") or "").strip(), segments, result.get("language")

        if self._runtime_backend == "faster-whisper":  # pragma: no cover - depends on optional dependency
            segment_iter, info = model.transcribe(str(audio_path), language=language, initial_prompt=prompt or None, beam_size=1)
            segments = [
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": str(segment.text).strip(),
                }
                for segment in segment_iter
            ]
            transcript = " ".join(item["text"] for item in segments).strip()
            return transcript, segments, getattr(info, "language", None)

        raise RuntimeError("Whisper runtime backend is unavailable")

    def _build_mock_transcript(
        self,
        *,
        audio_ref: str,
        prompt: str,
        language: str | None,
        title: str | None,
        description: str | None,
    ) -> str:
        seed = " ".join(filter(None, [audio_ref, prompt, title, description])).lower()
        scenario_names = [item["scenario"] for item in extract_product_scenarios(seed)]

        if not scenario_names:
            if any(token in seed for token in ("headset", "earbud", "audio", "speaker", "耳机", "音箱")):
                scenario_names = ["通勤降噪场景", "办公会议场景"]
            else:
                scenario_names = ["日常泛用场景"]

        if language == "en":
            joined = ", ".join(scenario_names)
            return f"The audio highlights {joined} and emphasizes battery life, comfort, and connection stability."

        if language == "ja":
            joined = "、".join(scenario_names)
            return f"音声では{joined}を中心に、バッテリー持続時間と装着感、接続の安定性が強調されています。"

        return (
            f"音频内容重点提到{summarize_product_scenarios([{'scenario': name} for name in scenario_names])}，"
            "并强调续航、佩戴舒适度和连接稳定性，适合产品规划阶段提炼卖点与使用场景。"
        )


def build_audio_acceptance_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": bool(result.get("transcript") and result.get("product_scenarios")),
        "provider": result.get("provider"),
        "provider_mode": result.get("provider_mode"),
        "model_name": result.get("model_name"),
        "detected_language": result.get("detected_language"),
        "scenario_summary": result.get("scenario_summary"),
        "scenario_count": len(result.get("product_scenarios") or []),
        "transcript_preview": str(result.get("transcript") or "")[:200],
    }


def write_audio_acceptance_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
