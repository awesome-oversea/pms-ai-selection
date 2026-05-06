from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import scripts.gateway_environment_checklist as gateway_environment_checklist
from src.services.gateway_governance_service import GatewayGovernanceService


def _fast_probe_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("OPS_PROBE_DOCKER_TIMEOUT_SECONDS", "0.5")
    env.setdefault("OPS_PROBE_HTTP_TIMEOUT_SECONDS", "0.5")
    return env


def test_gateway_governance_environment_targets_expose_evidence_requirements():
    service = GatewayGovernanceService()
    data = service.get_status()
    assert "prod" in data["environment_targets"]
    assert data["environment_targets"]["test"]["environment_connected"] is False
    assert "rollback_record" in data["environment_targets"]["prod"]["evidence_required"]


def test_gateway_environment_checklist_script_outputs_handoff_pack():
    result = subprocess.run(
        [sys.executable, "scripts/gateway_environment_checklist.py"],
        capture_output=True,
        text=True,
        check=True,
        env=_fast_probe_env(),
    )
    data = json.loads(result.stdout)
    assert data["gateway_delivery_pack"] is True
    assert set(data["environments"].keys()) == {"test", "preprod", "prod"}
    assert data["environments"]["test"]["ready_for_handoff"] is True
    assert data["local_tooling"]["environment_connected"] in {False, True}
    if data["remote_targets"]["any_configured"]:
        assert data["environments"]["test"]["blocking_reason"] in {None, "remote_probe_unreachable"}
    else:
        assert data["environments"]["test"]["blocking_reason"] in {None, "docker_or_kubectl_missing_and_no_remote_probe", "local_reboot_required_after_feature_enable", "docker_engine_unavailable", "docker_linux_backend_unavailable", "remote_probe_unreachable"}
    assert "k8s/gateway/kong.yml" in data["source_files"]


def test_gateway_smoke_check_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/gateway_smoke_check.py"],
        capture_output=True,
        text=True,
        check=True,
        env=_fast_probe_env(),
    )
    data = json.loads(result.stdout)
    assert data["gateway_validation_ok"] is True
    assert data["checklist_ready"] is True
    assert data["environment_connected"] in {False, True}
    assert data["local_runtime"]["expected_service_host"] == "host.docker.internal"
    assert data["local_runtime"]["expected_service_port"] == 18000
    assert "runtime_config_matches_files" in data["local_runtime"]
    assert isinstance(data["local_runtime"]["route_probes"], list)
    if "OPS_PROBE_KONG_LOCAL_PROXY_URL" not in os.environ:
        assert data["local_runtime"]["proxy_status"]["url"] == "http://127.0.0.1:8000/docs"
        assert [item["route_key"] for item in data["local_runtime"]["route_probes"]] == [
            "internal_llm_inference_health",
            "bff_auth",
            "openapi_docs",
        ]
    if data["environment_connected"]:
        assert data["smoke_test_passed"] is True
    else:
        assert data["smoke_test_passed"] is False


def test_gateway_probe_url_falls_back_to_settings(monkeypatch):
    monkeypatch.delenv("OPS_PROBE_KONG_TEST_URL", raising=False)
    monkeypatch.delenv("KONG_TEST_URL", raising=False)
    monkeypatch.setattr(
        gateway_environment_checklist,
        "OpsProbeSettings",
        lambda: SimpleNamespace(
            kong_test_url="https://kong-test.example.com",
            kong_preprod_url=None,
            kong_prod_url=None,
        ),
    )
    assert gateway_environment_checklist._get_probe_url("OPS_PROBE_KONG_TEST_URL", ("KONG_TEST_URL",)) == "https://kong-test.example.com"


def test_gateway_docker_probe_cleans_up_on_timeout(monkeypatch):
    cleanup_calls = []

    class HangingProcess:
        pid = 1234
        returncode = None

        def __init__(self) -> None:
            self.cleaned_up = False

        def communicate(self, timeout=None):  # noqa: ANN001
            if not self.cleaned_up:
                raise subprocess.TimeoutExpired(cmd="docker", timeout=timeout)
            return "", ""

    process = HangingProcess()

    def fake_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        return process

    def fake_cleanup(target):
        target.cleaned_up = True
        cleanup_calls.append(target.pid)

    monkeypatch.setattr(gateway_environment_checklist.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(gateway_environment_checklist, "_terminate_process_tree", fake_cleanup)
    monkeypatch.setattr(gateway_environment_checklist, "DOCKER_PROBE_TIMEOUT_SECONDS", 0.01)

    ready, error = gateway_environment_checklist._probe_docker_engine(Path("docker"), context="desktop-linux")

    assert ready is False
    assert error == "docker probe timed out after 0.01s"
    assert cleanup_calls == [1234]
