from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.perf_report_parser import parse_report

ROOT = Path(__file__).resolve().parents[1]
LATEST_ARTIFACT = ROOT / "artifacts" / "perf" / "latest.json"


def _fallback_report() -> dict:
    api_latencies = [180, 220, 260, 310, 420]
    knowledge_latencies = [120, 150, 180, 210, 260]
    worker_latencies = [90, 110, 120, 140, 160]

    def percentile(values: list[int], p: float) -> int:
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
        return ordered[index]

    return {
        "execution_mode": "fallback-sample",
        "scenarios": [
            {
                "name": "api_selection_create",
                "throughput_rps": 30,
                "latency_ms": {
                    "avg": round(mean(api_latencies), 2),
                    "p95": percentile(api_latencies, 0.95),
                    "p99": percentile(api_latencies, 0.99),
                },
                "error_rate": 0.0,
            },
            {
                "name": "api_knowledge_query",
                "throughput_rps": 45,
                "latency_ms": {
                    "avg": round(mean(knowledge_latencies), 2),
                    "p95": percentile(knowledge_latencies, 0.95),
                    "p99": percentile(knowledge_latencies, 0.99),
                },
                "error_rate": 0.0,
            },
            {
                "name": "worker_dead_letter_requeue",
                "throughput_rps": 12,
                "latency_ms": {
                    "avg": round(mean(worker_latencies), 2),
                    "p95": percentile(worker_latencies, 0.95),
                    "p99": percentile(worker_latencies, 0.99),
                },
                "error_rate": 0.0,
            },
        ],
        "capacity_baseline": {
            "api_rps_recommended": 30,
            "knowledge_query_rps_recommended": 45,
            "worker_parallelism_recommended": 4,
            "scale_out_thresholds": {
                "api_latency_p95_ms": 800,
                "error_rate_percent": 1.0,
                "worker_backlog": 50,
            },
        },
        "slo_summary": {
            "availability": ">= 99.0% / 30d",
            "latency_p95": "<= 800ms / 7d",
            "latency_p99": "<= 1500ms / 7d",
            "error_rate": "<= 1.0% / 7d",
        },
    }


def build_report() -> dict:
    report = _fallback_report()
    if LATEST_ARTIFACT.exists():
        latest = parse_report(LATEST_ARTIFACT)
        report["execution_mode"] = "latest-artifact"
        report["latest_run"] = latest
    return report


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
