from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.product_planner import ProductPlannerAgent
from src.services.audio_transcription_service import (
    AudioTranscriptionService,
    build_audio_acceptance_snapshot,
    write_audio_acceptance_artifact,
)


async def _run() -> dict:
    service = AudioTranscriptionService()
    transcription = await service.transcribe_audio(
        audio_url="sample://bluetooth-earbuds-commute-office-sport",
        language="zh",
        prompt="提取产品使用场景和卖点",
        title="蓝牙耳机TikTok音频样本",
        description="重点提到通勤降噪、办公通话和运动佩戴稳定性",
        use_mock=None,
    )

    agent = ProductPlannerAgent()
    agent_result = await agent._transcribe_audio_batch(
        [
            {
                "audio_url": "sample://bluetooth-earbuds-commute-office-sport",
                "language": "zh",
                "prompt": "整理产品使用场景",
                "title": "蓝牙耳机TikTok音频样本",
                "description": "重点提到通勤降噪、办公通话和运动佩戴稳定性",
                "use_mock": None,
            }
        ]
    )

    acceptance = {
        "accepted": bool(
            transcription.get("transcript")
            and transcription.get("product_scenarios")
            and agent_result.get("audio_count") == 1
        ),
        "runtime_status": service.build_status(),
        "transcription": build_audio_acceptance_snapshot(transcription),
        "agent_integration": {
            "audio_count": agent_result.get("audio_count"),
            "top_product_scenarios": agent_result.get("top_product_scenarios"),
            "languages": agent_result.get("languages"),
        },
        "notes": [
            "当前脚本优先走真实 Whisper 运行时；若当前环境未安装 Whisper 依赖，则自动回退到 compatible mock 路径。",
            "该工件可作为 P2-04 / P12-06 的本地 API 与 ProductPlannerAgent 联调证据。",
        ],
    }

    artifact_path = Path("artifacts/llm/whisper_cpu_acceptance.json")
    write_audio_acceptance_artifact(artifact_path, acceptance)
    acceptance["artifact_path"] = str(artifact_path).replace("\\", "/")
    return acceptance


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
