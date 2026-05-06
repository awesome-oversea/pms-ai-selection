from __future__ import annotations

from src.services.event_driven_scheduler_service import EventDrivenSchedulerService


def test_event_driven_scheduler_service_evaluates_three_trigger_types(tmp_path):
    service = EventDrivenSchedulerService(state_path=tmp_path / "event-scheduler-state.json")
    result = service.evaluate(
        {
            "source": "unit-test",
            "kafka_backlog": 12001,
            "kafka_backlog_threshold": 10000,
            "google_trends_growth_percent": 230.0,
            "google_trends_threshold_percent": 200.0,
            "negative_review_rate": 0.35,
            "negative_review_threshold": 0.2,
        }
    )
    assert result["triggered"] is True
    assert result["trigger_count"] == 3
    trigger_types = {item["trigger_type"] for item in result["executions"]}
    assert trigger_types == {"backlog_spike", "google_trends_spike", "negative_review_spike"}

    status = service.build_status()
    assert status["execution_count"] == 1
    assert status["trigger_counts"]["google_trends_spike"] == 1
