from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script_name: str) -> dict:
    script = ROOT / "scripts" / script_name
    completed = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


def test_export_flink_feature_manifest_script():
    payload = _run("export_flink_feature_manifest.py")
    assert payload["job_type"] == "flink_feature_processing"
    assert "review_sentiment_score" in payload["outputs"]
    assert (ROOT / payload["entrypoint"].split()[-1]).exists()


def test_export_flink_trendwide_manifest_script():
    payload = _run("export_flink_trendwide_manifest.py")
    assert payload["job_type"] == "flink_trend_wide_table"
    assert "growth_7d_vs_30d" in payload["outputs"]
    assert (ROOT / payload["entrypoint"].split()[-1]).exists()


def test_export_flink_forum_topic_manifest_script():
    payload = _run("export_flink_forum_topic_manifest.py")
    assert payload["job_type"] == "flink_forum_topic_modeling"
    assert "topic_heat_ranking" in payload["outputs"]
    assert (ROOT / payload["entrypoint"].split()[-1]).exists()
