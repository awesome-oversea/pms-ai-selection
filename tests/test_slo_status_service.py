import json

from src.services.slo_status_service import SLOStatusService


def test_slo_status_reads_latest_artifact(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "artifacts" / "perf"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "scenario": "api_health_smoke",
        "target": "http://127.0.0.1:8000/health",
        "duration_seconds": 1.0,
        "requests": [
            {"ok": True, "latency_ms": 100.0},
            {"ok": True, "latency_ms": 120.0},
        ],
    }
    latest = artifacts_dir / "latest.json"
    latest.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("src.services.slo_status_service.LATEST_ARTIFACT", latest)
    service = SLOStatusService()
    data = service.build_status()
    assert data["recent_run"] is not None
    assert data["recent_run"]["scenario"] == "api_health_smoke"
    assert data["perf_baseline"]["runner"] == "scripts/perf_run_sample.py"
