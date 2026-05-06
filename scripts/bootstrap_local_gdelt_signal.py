from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.kafka import close_kafka
from src.services.external_signal_service import ExternalSignalService


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_real_ready(result: dict[str, Any]) -> bool:
    degradation = result.get("degradation") or {}
    return (
        result.get("mode") == "real"
        and bool(degradation.get("businessization_ready"))
        and not bool(degradation.get("degraded"))
        and int(result.get("total_count") or 0) > 0
    )


def _build_acceptance_payload(
    *,
    query: str,
    live_result: dict[str, Any],
    auto_result: dict[str, Any],
) -> dict[str, Any]:
    real_result_source = None
    if _is_real_ready(live_result):
        real_result_source = "live"
    elif _is_real_ready(auto_result):
        real_result_source = "auto"

    real_result = live_result if real_result_source == "live" else auto_result if real_result_source == "auto" else None
    live_degraded = bool((live_result.get("degradation") or {}).get("degraded"))
    auto_degraded = bool((auto_result.get("degradation") or {}).get("degraded"))
    degradation_evidence_ready = live_degraded or auto_degraded or live_result.get("mode") == "error"
    live_endpoint_ready = real_result is not None
    businessization_ready = bool((real_result or auto_result).get("degradation", {}).get("businessization_ready"))

    return {
        "query": query,
        "accepted": bool(live_endpoint_ready and businessization_ready),
        "live_endpoint_ready": live_endpoint_ready,
        "real_result_source": real_result_source,
        "real_article_count": int(real_result.get("total_count") or 0) if real_result else 0,
        "degradation_evidence_ready": degradation_evidence_ready,
        "first_attempt": {
            "mode": live_result.get("mode"),
            "ready": _is_real_ready(live_result),
            "upstream_error": live_result.get("upstream_error"),
        },
        "live_result": live_result,
        "auto_result": auto_result,
    }


async def _run() -> dict[str, Any]:
    service = ExternalSignalService(timeout_seconds=15.0)
    query = "bluetooth speaker"
    try:
        live_result = await service.collect_gdelt_event_signals(query=query, mode="real")
        auto_result = await service.collect_gdelt_event_signals(query=query, mode="auto")
        payload = _build_acceptance_payload(query=query, live_result=live_result, auto_result=auto_result)
        artifact_path = PROJECT_ROOT / "artifacts" / "ops" / "gdelt_signal_validation.json"
        _write_json(artifact_path, payload)
        return payload
    finally:
        await close_kafka()


def main() -> None:
    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
