from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.config.settings import get_settings


def _normalize_whisper_model(model_name: str) -> str:
    normalized = str(model_name or "").strip().lower()
    if normalized.startswith("whisper-"):
        return normalized.split("whisper-", 1)[1]
    return normalized or "tiny"


def bootstrap_local_model_assets() -> dict[str, Any]:
    settings = get_settings().llm
    started_at = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "started_at": started_at,
        "rerank_model": settings.rerank_model,
        "speech_model": settings.speech_model,
        "speech_device": settings.speech_device,
        "accepted": False,
    }
    try:
        from faster_whisper import WhisperModel
        from sentence_transformers import CrossEncoder

        rerank = CrossEncoder(settings.rerank_model, device="cpu")
        whisper_model = WhisperModel(
            _normalize_whisper_model(settings.speech_model),
            device=settings.speech_device,
            compute_type="int8",
        )
        payload.update(
            {
                "accepted": True,
                "provider_mode": "real",
                "runtime_backend": {
                    "rerank": "sentence-transformers-cross-encoder",
                    "speech": "faster-whisper",
                },
                "model_cache_ready": {
                    "rerank_loaded": rerank is not None,
                    "speech_loaded": whisper_model is not None,
                },
            }
        )
    except Exception as exc:  # pragma: no cover - environment-dependent runtime branch
        payload.update(
            {
                "accepted": False,
                "provider_mode": "blocked",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    payload["finished_at"] = datetime.now(UTC).isoformat()
    return payload


def main() -> None:
    print(json.dumps(bootstrap_local_model_assets(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
