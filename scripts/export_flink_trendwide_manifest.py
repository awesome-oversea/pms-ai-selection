from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "data_platform" / "flink_trendwide_manifest.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_type": "flink_trend_wide_table",
        "engine": "flink-sql-compatible",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_topics": ["google_trends", "amazon_bsr", "media_rss"],
        "outputs": ["trend_wide_table", "growth_7d_vs_30d", "peak_heat", "lifecycle_stage"],
        "output_tables": ["trend_wide_table"],
        "metrics": ["growth_7d", "growth_30d", "peak_heat", "lifecycle_stage"],
        "entrypoint": "sql-client.sh -f sql/flink_trend_wide_table.sql",
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
