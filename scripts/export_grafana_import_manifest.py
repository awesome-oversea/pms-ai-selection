from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "ops" / "grafana_import_manifest.json"
ALERT_RULES_MANIFEST = ROOT / "artifacts" / "ops" / "alert_rules_manifest.json"


def _load_alert_rules_manifest() -> dict:
    script = ROOT / "scripts" / "export_alert_rules_manifest.py"
    if script.exists():
        result = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                pass
    if ALERT_RULES_MANIFEST.exists():
        return json.loads(ALERT_RULES_MANIFEST.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    alert_rules = _load_alert_rules_manifest()
    payload = {
        "dashboard_tool": "grafana",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasources": [
            {"name": "Prometheus", "type": "prometheus", "url": "http://127.0.0.1:9090"},
            {"name": "Alertmanager", "type": "alertmanager", "url": "http://127.0.0.1:9093"},
        ],
        "dashboards": [
            {"title": "PMS Metrics Dashboard", "source_artifact": "artifacts/ops/metrics_dashboard.json", "import_mode": "overwrite"},
        ],
        "alerts": [
            {"name": item.get("name"), "severity": item.get("severity")}
            for item in alert_rules.get("rules", [])
        ],
        "alert_rules_artifact": alert_rules.get("source_artifact"),
        "prometheus_rule_artifact": alert_rules.get("prometheus_rule_artifact"),
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
