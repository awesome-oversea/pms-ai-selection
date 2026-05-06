from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import scripts.observability_smoke_check as observability_smoke_check
from scripts import release_quality_gates


def test_release_quality_gates_unknown_mode_returns_2(monkeypatch):
    monkeypatch.setattr("sys.argv", ["release_quality_gates.py", "unknown"])
    assert release_quality_gates.main() == 2


def test_release_quality_gates_all_contains_expected_steps(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def _fake_run(command):
        calls.append(tuple(command))
        return 0

    monkeypatch.setattr(release_quality_gates, "_run", _fake_run)
    monkeypatch.setattr("sys.argv", ["release_quality_gates.py", "all"])

    assert release_quality_gates.main() == 0
    joined = [" ".join(cmd) for cmd in calls]
    assert any("py_compile src/main.py" in item for item in joined)
    assert any("tests/test_api_integration.py -k selection_execution_status or local_feedback_loop or model_finetune or graph or ollama or agent_platform_message_bus or agent_platform_operations or embedding_benchmark or gateway or service_split_status -q" in item for item in joined)
    assert any("scripts/perf_run_sample.py --smoke" in item for item in joined)
    assert any("scripts/perf_baseline.py" in item for item in joined)
    assert any("tests/test_d106_d110.py tests/test_security_config.py tests/test_rate_limit.py -q" in item for item in joined)


def test_perf_baseline_script_outputs_capacity_and_slo():
    result = subprocess.run([sys.executable, "scripts/perf_baseline.py"], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert "scenarios" in data
    assert "capacity_baseline" in data
    assert "slo_summary" in data
    assert len(data["scenarios"]) >= 1


def test_perf_run_sample_supports_selection_sse_mode(tmp_path):
    script = Path("scripts/perf_run_sample.py").read_text(encoding="utf-8")
    assert "selection_sse_latest.json" in script
    assert "--selection-sse" in script
    assert "first_byte_ms" in script


def test_gateway_validate_script_exists_and_passes():
    result = subprocess.run([sys.executable, "scripts/validate_gateway_config.py"], capture_output=True, text=True, check=True)
    assert "gateway_config_validation=ok" in result.stdout
    assert "checksum:kong-routes.yml=" in result.stdout


def test_gateway_smoke_and_observability_scripts_exist_and_pass():
    gateway = subprocess.run([sys.executable, "scripts/gateway_smoke_check.py"], capture_output=True, text=True, check=True)
    observability = subprocess.run([sys.executable, "scripts/observability_smoke_check.py"], capture_output=True, text=True, check=True)
    triton = subprocess.run([sys.executable, "scripts/triton_smoke_check.py"], capture_output=True, text=True, check=True)
    erp = subprocess.run([sys.executable, "scripts/erp_smoke_test.py"], capture_output=True, text=True, check=True)

    gateway_data = json.loads(gateway.stdout)
    observability_data = json.loads(observability.stdout)
    triton_data = json.loads(triton.stdout)
    erp_data = json.loads(erp.stdout)

    assert gateway_data["gateway_validation_ok"] is True
    if gateway_data["checklist"]["remote_targets"]["any_configured"]:
        assert gateway_data["blocking_reason"] in {None, "remote_probe_unreachable"}
    else:
        assert gateway_data["environment_connected"] is False
        assert gateway_data["blocking_reason"] in {None, "docker_or_kubectl_missing_and_no_remote_probe", "local_reboot_required_after_feature_enable", "docker_engine_unavailable", "docker_linux_backend_unavailable", "remote_probe_unreachable"}

    assert observability_data["observability_smoke"] is True
    if observability_data["environment_connected"]:
        assert observability_data["smoke_test_passed"] is True
        assert observability_data["blocking_reason"] is None
        assert observability_data["remote_targets"]["all_required_connected"] is True
    else:
        assert observability_data["smoke_test_passed"] is False
        if observability_data["remote_targets"]["any_configured"]:
            assert observability_data["blocking_reason"] == "remote_probe_unreachable"
        else:
            assert observability_data["blocking_reason"] == "docker_or_kubectl_missing_and_no_remote_probe"

    assert triton_data["triton_smoke"] is True
    assert triton_data["endpoint"]
    assert triton_data["blocking_reason"] in {None, "triton_endpoint_unreachable", "rerank_route_unreachable"}
    if triton_data["health_status_code"] == 404 or triton_data["rerank_status_code"] == 404:
        assert triton_data["environment_connected"] is False
        assert triton_data["smoke_test_passed"] is False
    assert set(erp_data["systems"].keys()) >= {"oms", "wms", "crm", "fms", "bi"}


def test_observability_probe_url_falls_back_to_settings(monkeypatch):
    monkeypatch.delenv("OPS_PROBE_PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.setattr(
        observability_smoke_check,
        "OpsProbeSettings",
        lambda: SimpleNamespace(
            prometheus_url="https://prometheus.example.com",
            grafana_url=None,
            alertmanager_url=None,
        ),
    )
    assert observability_smoke_check._get_probe_url("OPS_PROBE_PROMETHEUS_URL", ("PROMETHEUS_URL",)) == "https://prometheus.example.com"


def test_triton_smoke_script_does_not_fake_success_when_endpoint_unreachable(monkeypatch):
    import scripts.triton_smoke_check as triton_smoke_check

    monkeypatch.setattr(
        triton_smoke_check,
        "_probe_url",
        lambda url, method="GET", payload=None: (False, 404, None, None),
    )
    data = triton_smoke_check.build_payload()
    assert data["environment_connected"] is False
    assert data["smoke_test_passed"] is False
    assert data["blocking_reason"] == "triton_endpoint_unreachable"
    assert data["local_compatible"] is False


def test_triton_smoke_script_detects_local_compatible_mode(monkeypatch):
    import scripts.triton_smoke_check as triton_smoke_check

    def _fake_probe(url, method="GET", payload=None):
        if url.endswith("/v2/health/ready"):
            return True, 200, None, {"mode": "local-compatible"}
        return True, 200, None, {
            "mode": "local-compatible",
            "results": [{"index": 0, "score": 1.0, "document": "降噪蓝牙耳机"}],
        }

    monkeypatch.setattr(triton_smoke_check, "_probe_url", _fake_probe)
    data = triton_smoke_check.build_payload()
    assert data["environment_connected"] is True
    assert data["smoke_test_passed"] is True
    assert data["detected_mode"] == "local-compatible"
    assert data["local_compatible"] is True


def test_ci_workflow_contains_release_gates_job():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "lint-type:" in ci
    assert "release-gates:" in ci
    assert "python scripts/validate_gateway_config.py" in ci
    assert "python scripts/release_quality_gates.py all" in ci


def test_release_workflow_exists_and_uses_deploy_script():
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in release
    assert "python scripts/release_deploy.py" in release
    assert "python scripts/release_rollback.py" in release
