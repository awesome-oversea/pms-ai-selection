from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_script(script_name: str) -> tuple[dict, Path]:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / script_name
    completed = subprocess.run([sys.executable, str(script)], cwd=root, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    return payload, root


def test_export_kong_canary_manifest_script_generates_artifact():
    payload, root = _run_script("export_kong_canary_manifest.py")
    artifact = root / "artifacts" / "ops" / "kong_canary_manifest.json"
    assert payload["gateway"] == "kong"
    assert payload["strategy"] == "canary"
    assert payload["routes"][0]["traffic_split"]["canary"] == 10
    assert artifact.exists()


def test_export_grafana_import_manifest_script_generates_artifact():
    payload, root = _run_script("export_grafana_import_manifest.py")
    artifact = root / "artifacts" / "ops" / "grafana_import_manifest.json"
    assert payload["dashboard_tool"] == "grafana"
    assert payload["dashboards"][0]["source_artifact"] == "artifacts/ops/metrics_dashboard.json"
    assert payload["alert_rules_artifact"] == "artifacts/ops/alert_rules.json"
    assert payload["prometheus_rule_artifact"] == "artifacts/ops/prometheus_alert_rules.yml"
    assert artifact.exists()


def test_export_alert_rules_manifest_script_generates_prometheus_rules():
    payload, root = _run_script("export_alert_rules_manifest.py")
    artifact = root / "artifacts" / "ops" / "alert_rules_manifest.json"
    rules_yml = root / "artifacts" / "ops" / "prometheus_alert_rules.yml"
    rule_names = {item["name"] for item in payload["rules"]}
    assert payload["rule_tool"] == "prometheus-compatible"
    assert payload["rule_count"] == 4
    assert {"vllm_latency_p99_high", "qdrant_search_rt_high", "kafka_consumer_lag_high", "agent_failure_rate_high"}.issubset(rule_names)
    assert artifact.exists()
    assert rules_yml.exists()
    rules_text = rules_yml.read_text(encoding="utf-8")
    assert "histogram_quantile(0.99" in rules_text
    assert "kafka_consumer_lag" in rules_text
    assert "agent_executions_total" in rules_text


def test_export_efk_stack_manifest_script_generates_artifact():
    payload, root = _run_script("export_efk_stack_manifest.py")
    artifact = root / "artifacts" / "ops" / "efk_stack_manifest.json"
    assert payload["logging_stack"] == "efk"
    assert payload["component_count"] == 3
    assert payload["components"]["elasticsearch"]["index_pattern"] == "pms-app-*"
    assert payload["components"]["kibana"]["endpoint"] == "http://127.0.0.1:5601"
    assert artifact.exists()


def test_metrics_dashboard_artifact_is_real_grafana_dashboard_json():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "artifacts" / "ops" / "metrics_dashboard.json").read_text(encoding="utf-8"))
    assert payload["title"] == "PMS Metrics Dashboard"
    assert payload["schemaVersion"] >= 39
    assert len(payload["panels"]) >= 4
    assert payload["templating"]["list"][0]["name"] == "environment"
    assert payload["__meta__"]["technical"]["api"]["metrics_endpoint"] == "/metrics"
