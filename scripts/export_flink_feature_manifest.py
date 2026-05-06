from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "data_platform" / "flink_feature_job_manifest.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_type": "flink_feature_processing",
        "engine": "flink-sql-compatible",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_topics": ["pms-agent-event", "cdc.oms", "cdc.crm"],
        "outputs": [
            "selection_feature_store",
            "selection_supply_demand_metrics",
            "sales_growth_rate",
            "review_sentiment_score",
            "demand_supply_ratio",
        ],
        "output_tables": ["selection_feature_store", "selection_supply_demand_metrics"],
        "features": ["sales_growth_rate", "review_sentiment_score", "demand_supply_ratio"],
        "entrypoint": "sql-client.sh -f sql/flink_feature_processing.sql",
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
