from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "data_platform" / "flink_forum_topic_manifest.json"


def main() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_type": "flink_forum_topic_modeling",
        "engine": "flink-nlp-compatible",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_topics": ["forum_collection", "media_rss"],
        "outputs": ["forum_topic_heat_table", "topic_extraction", "keyword_count", "topic_heat_ranking"],
        "output_tables": ["forum_topic_heat_table"],
        "tasks": ["topic_extraction", "keyword_count", "heat_ranking"],
        "entrypoint": "sql-client.sh -f sql/flink_forum_topic_modeling.sql",
    }
    ARTIFACT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
