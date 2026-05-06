from __future__ import annotations

from pathlib import Path

from src.services.local_flink_checkpoint_acceptance_service import LocalFlinkCheckpointAcceptanceService


def test_latest_projection_prefers_highest_processed_event_count():
    rows = [
        {
            "product_id": "sku-001",
            "processed_event_count": 2,
            "sales_units": 5,
            "updated_at": "2026-04-21T00:00:01+00:00",
        },
        {
            "product_id": "sku-001",
            "processed_event_count": 5,
            "sales_units": 8,
            "updated_at": "2026-04-21T00:00:03+00:00",
        },
        {
            "product_id": "sku-001",
            "processed_event_count": 4,
            "sales_units": 7,
            "updated_at": "2026-04-21T00:00:02+00:00",
        },
    ]

    latest = LocalFlinkCheckpointAcceptanceService.latest_projection(rows, product_id="sku-001")

    assert latest is not None
    assert latest["processed_event_count"] == 5
    assert latest["sales_units"] == 8


def test_projection_check_validates_expected_business_metrics():
    expected = LocalFlinkCheckpointAcceptanceService.expected_projection("selection-task-flink-checkpoint-us-001")
    actual = {
        "product_id": "selection-task-flink-checkpoint-us-001",
        "processed_event_count": 5,
        "sales_units": 8,
        "inventory_units": 20,
        "demand_supply_ratio": 0.4,
        "review_count": 2,
        "review_sentiment_score": 0.8,
        "updated_at": "2026-04-21T00:00:05+00:00",
    }

    check = LocalFlinkCheckpointAcceptanceService.projection_check(expected, actual)

    assert check["passed"] is True
    assert check["evidence"]["expected"]["processed_event_count"] == 5


def test_parse_consumer_group_extracts_lag_rows():
    raw = """
GROUP                                    TOPIC                              PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
pms-flink-checkpoint-group-20260421t0000 pms-flink-checkpoint-20260421t0000 0          5               5               0
"""

    rows = LocalFlinkCheckpointAcceptanceService.parse_consumer_group(raw)

    assert len(rows) == 1
    assert rows[0]["topic"] == "pms-flink-checkpoint-20260421t0000"
    assert rows[0]["lag"] == 0


def test_projection_check_fails_when_projection_missing():
    expected = LocalFlinkCheckpointAcceptanceService.expected_projection("selection-task-flink-checkpoint-us-001")

    check = LocalFlinkCheckpointAcceptanceService.projection_check(expected, None)

    assert check["passed"] is False
    assert check["detail"] == "projection missing"


def test_parse_consumer_group_ignores_headers_and_errors():
    raw = """
GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
Error: group not found
pms-group test-topic 0 5 5 0
"""

    rows = LocalFlinkCheckpointAcceptanceService.parse_consumer_group(raw)

    assert rows == [
        {
            "group": "pms-group",
            "topic": "test-topic",
            "partition": 0,
            "current_offset": 5,
            "log_end_offset": 5,
            "lag": 0,
        }
    ]


def test_windows_runtime_profile_uses_host_rest_and_cli_paths(tmp_path: Path):
    service = LocalFlinkCheckpointAcceptanceService(root=tmp_path, runtime_mode="windows-host")

    assert service.JOBMANAGER_CONTAINER is None
    assert service.TASKMANAGER_CONTAINER is None
    assert service.KAFKA_CONTAINER is None
    assert service.FLINK_JOB_BOOTSTRAP == "localhost:9092"
    assert service.flink_rest_endpoint() == "http://127.0.0.1:18081"


def test_latest_projection_reads_windows_host_output_files(tmp_path: Path):
    service = LocalFlinkCheckpointAcceptanceService(root=tmp_path, runtime_mode="windows-host")
    output_dir = tmp_path / "flink-output"
    nested = output_dir / "part-00000"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text(
        '{"product_id":"sku-001","processed_event_count":3,"updated_at":"2026-04-21T00:00:03+00:00"}\n'
        '{"product_id":"sku-001","processed_event_count":5,"updated_at":"2026-04-21T00:00:05+00:00"}\n',
        encoding="utf-8",
    )

    rows = service._read_output_rows(str(output_dir))

    assert len(rows) == 2
    assert service.latest_projection(rows, product_id="sku-001")["processed_event_count"] == 5


def test_windows_submit_command_uses_local_flink_cli_and_host_paths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FLINK_HOME", str(tmp_path / "flink"))
    service = LocalFlinkCheckpointAcceptanceService(root=tmp_path, runtime_mode="windows-host")

    submit_command = service._host_flink_submit_args(
        job_jar=tmp_path / "job.jar",
        topic="topic-001",
        group_id="group-001",
        output_dir=tmp_path / "output",
        fail_marker_path=tmp_path / "fail.marker",
    )

    assert Path(submit_command[0]).name in {"flink", "flink.bat"}
    assert Path(submit_command[0]).parent.name == "bin"
    assert "run" in submit_command
    assert str(tmp_path / "job.jar") in submit_command
    assert "--brokers" in submit_command
    assert "localhost:9092" in submit_command
    assert f"file://{(tmp_path / 'output').as_posix()}" in submit_command


def test_windows_consumer_group_command_uses_local_kafka_cli(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KAFKA_HOME", str(tmp_path / "kafka"))
    service = LocalFlinkCheckpointAcceptanceService(root=tmp_path, runtime_mode="windows-host")

    command = service._host_consumer_group_describe_args("group-001")

    assert Path(command[0]).name in {"kafka-consumer-groups", "kafka-consumer-groups.bat"}
    assert Path(command[0]).parent.name == "bin"
    assert "--bootstrap-server" in command
    assert "localhost:9092" in command
    assert command[-1] == "group-001"


def test_windows_cancel_command_uses_local_flink_cli(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FLINK_HOME", str(tmp_path / "flink"))
    service = LocalFlinkCheckpointAcceptanceService(root=tmp_path, runtime_mode="windows-host")

    command = service._host_flink_cancel_args("job-001")

    assert Path(command[0]).name in {"flink", "flink.bat"}
    assert command[1:] == ["cancel", "job-001"]
