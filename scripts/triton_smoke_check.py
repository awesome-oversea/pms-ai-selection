from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.config.settings import get_settings
except Exception:  # pragma: no cover
    get_settings = None


def _get_endpoint() -> str:
    env_value = os.getenv("LLM_TRITON_ENDPOINT")
    if env_value:
        return env_value.rstrip("/")
    if get_settings is not None:
        return get_settings().llm.triton_endpoint.rstrip("/")
    return "http://localhost:8000"


def _probe_url(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[bool, int | None, str | None, dict | None]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8") if resp.length != 0 else ""
            parsed = json.loads(body) if body else None
            return 200 <= resp.status < 300, status_code, None, parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp is not None else ""
        parsed = None
        if body:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = None
        return False, exc.code, None, parsed
    except Exception as exc:  # pragma: no cover - network dependent
        return False, None, str(exc), None


def build_payload() -> dict:
    endpoint = _get_endpoint()
    health_url = f"{endpoint}/v2/health/ready"
    rerank_url = f"{endpoint}/v1/rerank"

    health_ok, health_status_code, health_error, health_payload = _probe_url(health_url)
    rerank_ok, rerank_status_code, rerank_error, rerank_payload = _probe_url(
        rerank_url,
        method="POST",
        payload={
            "query": "蓝牙耳机",
            "documents": ["降噪蓝牙耳机", "不锈钢水杯"],
            "top_k": 1,
        },
    )

    environment_connected = health_ok and rerank_ok
    blocking_reason = None
    if not health_ok:
        blocking_reason = "triton_endpoint_unreachable"
    elif not rerank_ok:
        blocking_reason = "rerank_route_unreachable"

    detected_mode = None
    if isinstance(health_payload, dict):
        detected_mode = health_payload.get("mode")
    if detected_mode is None and isinstance(rerank_payload, dict):
        detected_mode = rerank_payload.get("mode")

    return {
        "triton_smoke": True,
        "endpoint": endpoint,
        "health_url": health_url,
        "rerank_url": rerank_url,
        "environment_connected": environment_connected,
        "healthcheck_ok": health_ok,
        "health_status_code": health_status_code,
        "health_error": health_error,
        "rerank_ok": rerank_ok,
        "rerank_status_code": rerank_status_code,
        "rerank_error": rerank_error,
        "rerank_result_sample": rerank_payload,
        "smoke_test_passed": health_ok and rerank_ok,
        "blocking_reason": blocking_reason,
        "detected_mode": detected_mode,
        "local_compatible": detected_mode == "local-compatible",
    }


def main() -> int:
    print(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
