from __future__ import annotations

from typing import Any

from src.config.settings import get_settings
from src.services.audio_transcription_service import AudioTranscriptionService


class CPUModelStatusService:
    def build_status(self) -> dict[str, Any]:
        llm_settings = get_settings().llm
        audio_status = AudioTranscriptionService().build_status()
        return {
            "model_name": "cpu-local-models",
            "deployment_mode": "cpu-compatible",
            "use_cases": ["safety_filter", "fast_classification", "rerank", "audio_transcription"],
            "ready": True,
            "latency_target_ms": 500,
            "provider_mode": "application-side-compatible",
            "rerank_model": {
                "model_name": llm_settings.rerank_model,
                "deployment_mode": "in-process-cpu",
                "provider_mode": "sentence-transformers-cross-encoder-compatible",
            },
            "speech_model": {
                "model_name": audio_status["audio_model"],
                "runtime_backend": audio_status["runtime_backend"],
                "model_loaded": audio_status["model_loaded"],
                "supported_languages": audio_status["supported_languages"],
            },
        }
