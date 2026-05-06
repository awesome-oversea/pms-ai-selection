from __future__ import annotations

import json
from pathlib import Path

from src.services.local_proxy_runtime_service import LocalProxyRuntimeService


def test_local_proxy_runtime_service_runs_self_hosted_proxy_acceptance(tmp_path: Path):
    artifact_path = tmp_path / "local_proxy_provider_acceptance.json"
    service = LocalProxyRuntimeService(artifact_path=artifact_path)

    result = service.run_acceptance()

    assert result["accepted"] is True
    assert artifact_path.exists()
    persisted = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert persisted["accepted"] is True
    assert persisted["provider_runtime"]["provider"] == "self_hosted"
    assert persisted["provider_runtime"]["probe"]["success_count"] == 2
    assert persisted["runtime"]["proxy_nodes"][0]["name"] == "proxy-node-a"
