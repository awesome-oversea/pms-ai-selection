from __future__ import annotations

import asyncio
from pathlib import Path

from scripts import run_whisper_cpu_acceptance
from src.agents.product_planner import ProductPlannerAgent
from src.services.audio_transcription_service import AudioTranscriptionService


def test_audio_transcription_service_mock_path_extracts_product_scenarios():
    result = asyncio.run(
        AudioTranscriptionService().transcribe_audio(
            audio_url="sample://bluetooth-earbuds-commute-office-sport",
            language="zh",
            prompt="提取产品使用场景",
            use_mock=True,
        )
    )

    assert result["provider_mode"] == "mock"
    assert result["transcript"]
    assert len(result["product_scenarios"]) >= 2
    assert any(item["scenario"] == "通勤降噪场景" for item in result["product_scenarios"])
    assert "办公会议场景" in result["scenario_summary"]


def test_product_planner_audio_batch_aggregates_transcription_results():
    result = asyncio.run(
        ProductPlannerAgent()._transcribe_audio_batch(
            [
                {
                    "audio_url": "sample://bluetooth-earbuds-commute-office-sport",
                    "language": "zh",
                    "prompt": "整理产品使用场景",
                    "use_mock": True,
                }
            ]
        )
    )

    assert result["audio_count"] == 1
    assert result["audios"][0]["transcript"]
    assert any(item["scenario"] == "通勤降噪场景" for item in result["top_product_scenarios"])
    assert result["languages"][0]["language"] == "zh"


def test_whisper_cpu_acceptance_script_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = asyncio.run(run_whisper_cpu_acceptance._run())

    artifact_path = Path(tmp_path, "artifacts", "llm", "whisper_cpu_acceptance.json")
    assert result["accepted"] is True
    assert artifact_path.exists()
