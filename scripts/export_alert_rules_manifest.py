from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "ops" / "alert_rules.json"
ARTIFACT = ROOT / "artifacts" / "ops" / "alert_rules_manifest.json"
PROMETHEUS_RULES = ROOT / "artifacts" / "ops" / "prometheus_alert_rules.yml"


def _render_prometheus_rules(payload: dict, rules: list[dict]) -> str:
    lines = [
        "groups:",
        f"  - name: {payload.get('rule_group', 'pms-core-observability')}",
        "    rules:",
    ]
    for item in rules:
        labels = {"severity": item.get("severity", "warning")}
        annotations = {
            "summary": item.get("summary", ""),
            "description": item.get("description", ""),
            "runbook": item.get("runbook", "docs/runbook_oncall_sla_change.md"),
        }
        lines.extend(
            [
                f"      - alert: {item.get('name')}",
                f"        expr: {item.get('expr')}",
                f"        for: {item.get('for', '5m')}",
                "        labels:",
                *[f"          {key}: {value}" for key, value in labels.items()],
                "        annotations:",
                *[f"          {key}: {json.dumps(value, ensure_ascii=False)}" for key, value in annotations.items()],
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    PROMETHEUS_RULES.write_text(_render_prometheus_rules(payload, rules), encoding="utf-8")
    manifest = {
        "rule_tool": "prometheus-compatible",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": "artifacts/ops/alert_rules.json",
        "prometheus_rule_artifact": "artifacts/ops/prometheus_alert_rules.yml",
        "rule_group": payload.get("rule_group", "pms-core-observability"),
        "rule_count": len(rules),
        "rules": [
            {
                "name": item.get("name"),
                "severity": item.get("severity"),
                "expr": item.get("expr"),
                "for": item.get("for"),
            }
            for item in rules
        ],
        "notification_channels": payload.get("notification_channels", []),
        "runbook": "docs/runbook_oncall_sla_change.md",
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
