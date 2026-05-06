from __future__ import annotations

import json

from scripts.mock_services import SCENARIO_ROOT, _load_scenario


def test_mock_scenario_file_can_be_loaded():
    scenario = _load_scenario("external_api", "amazon_hot_selling")
    assert scenario is not None
    assert scenario["scenario_id"] == "amazon_hot_selling"
    assert scenario["behavior"]["status_code"] == 200
    assert len(scenario["response"]["products"]) >= 1


def test_mock_scenario_readme_exists():
    readme = SCENARIO_ROOT / "README.md"
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "X-Scenario-ID" in content
    assert "scenario-driven" in content


def test_mock_scenario_example_file_exists():
    scenario_file = SCENARIO_ROOT / "external_api" / "amazon_hot_selling.json"
    assert scenario_file.exists()
    payload = json.loads(scenario_file.read_text(encoding="utf-8"))
    assert payload["scenario_id"] == "amazon_hot_selling"
    assert payload["response"]["products"][0]["id"] == "B0HOTSELL001"
