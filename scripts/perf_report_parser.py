from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return float(ordered[index])


def parse_report(report_path: str | Path) -> dict[str, Any]:
    path = Path(report_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    requests = payload.get("requests", [])
    latencies = [float(item.get("latency_ms", 0.0)) for item in requests]
    total = len(requests)
    success = sum(1 for item in requests if item.get("ok", False))
    duration_seconds = float(payload.get("duration_seconds", 1.0) or 1.0)
    throughput_rps = round(success / duration_seconds, 2) if duration_seconds > 0 else 0.0
    error_rate = round(((total - success) / total) * 100, 4) if total else 0.0
    return {
        "scenario": payload.get("scenario", "unknown"),
        "target": payload.get("target"),
        "total_requests": total,
        "success_requests": success,
        "throughput_rps": throughput_rps,
        "error_rate_percent": error_rate,
        "latency_ms": {
            "avg": round(mean(latencies), 2) if latencies else 0.0,
            "p95": round(_percentile(latencies, 0.95), 2),
            "p99": round(_percentile(latencies, 0.99), 2),
        },
    }
