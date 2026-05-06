from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "perf"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def run_sample(url: str, requests_count: int, timeout: float) -> dict:
    started = time.perf_counter()
    rows = []
    for _ in range(requests_count):
        begin = time.perf_counter()
        ok = False
        status_code = None
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status_code = getattr(resp, "status", 200)
                ok = 200 <= int(status_code) < 400
        except URLError:
            ok = False
        latency_ms = round((time.perf_counter() - begin) * 1000, 2)
        rows.append({"ok": ok, "status_code": status_code, "latency_ms": latency_ms})
    duration_seconds = round(time.perf_counter() - started, 4)
    return {
        "scenario": "api_health_smoke",
        "target": url,
        "duration_seconds": duration_seconds,
        "requests": rows,
    }


def run_selection_sse_sample(url: str, timeout: float, auth_token: str, event_limit: int) -> dict:
    started = time.perf_counter()
    req = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Accept": "text/event-stream",
        },
    )
    first_byte_ms = None
    status_code = None
    events = 0
    keep_alive_events = 0
    retry_line_seen = False
    protocol_detected = False
    completed = False
    error = None

    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status_code = getattr(resp, "status", 200)
            while True:
                chunk_started = time.perf_counter()
                line = resp.readline()
                if not line:
                    break
                if first_byte_ms is None:
                    first_byte_ms = round((chunk_started - started) * 1000, 2)
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded.startswith("retry:"):
                    retry_line_seen = True
                elif decoded.startswith(": keep-alive"):
                    keep_alive_events += 1
                elif decoded.startswith("data: "):
                    events += 1
                    if '"protocol": "sse"' in decoded or '"protocol":"sse"' in decoded:
                        protocol_detected = True
                    if events >= event_limit:
                        completed = True
                        break
    except Exception as exc:  # pragma: no cover - network dependent
        error = str(exc)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "scenario": "selection_sse_smoke",
        "target": url,
        "status_code": status_code,
        "first_byte_ms": first_byte_ms,
        "duration_ms": duration_ms,
        "events": events,
        "keep_alive_events": keep_alive_events,
        "retry_line_seen": retry_line_seen,
        "protocol_detected": protocol_detected,
        "completed": completed,
        "event_limit": event_limit,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--selection-sse", action="store_true")
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--event-limit", type=int, default=1)
    args = parser.parse_args()

    if args.selection_sse:
        report = run_selection_sse_sample(args.url, args.timeout, args.auth_token, args.event_limit)
        target = ARTIFACT_DIR / "selection_sse_latest.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"artifact": str(target).replace('\\', '/'), "scenario": report["scenario"], "events": report["events"], "first_byte_ms": report["first_byte_ms"]}, ensure_ascii=False))
        return 0 if report["status_code"] and 200 <= int(report["status_code"]) < 400 and report["events"] >= 1 else 1

    report = run_sample(args.url, args.requests, args.timeout)
    target = ARTIFACT_DIR / "latest.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(target).replace('\\', '/'), "scenario": report["scenario"], "requests": len(report["requests"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
