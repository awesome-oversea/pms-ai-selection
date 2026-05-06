from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.business_defaults import (
    get_commercial_decision_rules,
    get_rag_evaluation_config,
    get_scheduled_selection_config,
    get_feedback_schedule_config,
    get_kpi_schedule_config,
)


def build_payload() -> dict:
    return {
        "configs": {
            "selection.commercial.decision_rules": get_commercial_decision_rules(),
            "selection.scheduler.defaults": get_scheduled_selection_config(),
            "selection.feedback.defaults": get_feedback_schedule_config(),
            "selection.kpi.defaults": get_kpi_schedule_config(),
            "knowledge.rag_evaluation.defaults": get_rag_evaluation_config(),
        }
    }


def main() -> int:
    payload = build_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
