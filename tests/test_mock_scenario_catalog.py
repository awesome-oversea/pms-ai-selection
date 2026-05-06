from __future__ import annotations

import json
from pathlib import Path

SCENARIO_ROOT = Path("D:/Project/fms/artifacts/mock_scenarios")


def _read(name: str) -> dict:
    return json.loads((SCENARIO_ROOT / name).read_text(encoding="utf-8"))


def test_external_scenario_catalog_contains_growth_and_rate_limit_cases():
    amazon = _read("external_api/amazon_rate_limited.json")
    tiktok = _read("external_api/tiktok_trend_spike.json")
    google = _read("external_api/google_trends_growth.json")
    ali = _read("external_api/ali1688_supplier_unstable.json")

    assert amazon["behavior"]["error"] == "rate_limited"
    assert tiktok["response"]["trends"][0]["growth_rate_7d"] > 1.0
    assert google["response"]["growth_rate_30d"] > 0
    assert ali["behavior"]["error"] == "partial_data"


def test_erp_scenario_catalog_contains_success_and_timeout_cases():
    success = _read("erp/adoption_success.json")
    timeout = _read("erp/supplier_timeout.json")

    assert success["response"]["accepted"] is True
    assert timeout["behavior"]["error"] == "timeout"
