from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.local_flink_checkpoint_acceptance_service import LocalFlinkCheckpointAcceptanceService


class _StubService(LocalFlinkCheckpointAcceptanceService):
    def _inspect_environment(self):
        return {
            "containers": {
                self.JOBMANAGER_CONTAINER: {"running": True, "status": "running"},
                self.TASKMANAGER_CONTAINER: {"running": True, "status": "running"},
                self.KAFKA_CONTAINER: {"running": True, "status": "running"},
            },
            "kafka_connectors": [],
            "ready": True,
            "stream_runtime_ready": True,
        }

    def _build_job(self, run_dir: Path):
        jar_path = run_dir / "job.jar"
        jar_path.write_bytes(b"jar")
        payload = {"jar_path": str(jar_path)}
        self._write_json(run_dir / "job_build_manifest.json", payload)
        return payload

    def _ensure_topic(self, topic: str) -> None:
        return None

    def _submit_job(self, *, job_jar: Path, topic: str, group_id: str, run_dir_name: str):
        return {
            "job_id": "job-001",
            "output_dir": "/tmp/output",
            "submit_output": "submitted",
        }

    def _wait_for_running(self, job_id: str, *, timeout_seconds: float = 90.0):
        return {"state": "RUNNING", "history": [{"state": "RUNNING"}], "payload": {"state": "RUNNING"}}

    def _produce_events(self, topic: str, events, artifact_path: Path) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events), encoding="utf-8")

    def _wait_for_checkpoint(self, job_id: str, *, timeout_seconds: float = 120.0):
        return {
            "completed": 1,
            "payload": {"counts": {"completed": 1}, "latest": {"completed": {"id": 1}}},
            "history": [{"completed": 1}],
        }

    def _describe_consumer_group(self, group_id: str):
        return {"raw": "", "rows": [{"group": group_id, "topic": "topic-001", "lag": 0}]}

    def _wait_for_recovery(self, job_id: str, *, timeout_seconds: float = 120.0):
        return {
            "recovered": True,
            "history": [
                {"state": "RUNNING"},
                {"state": "FAILING"},
                {"state": "RUNNING"},
            ],
            "payload": {"state": "RUNNING"},
        }

    def _wait_for_projection(self, *, output_dir: str, product_id: str, expected_event_count: int, timeout_seconds: float = 120.0):
        latest = self.expected_projection(product_id)
        latest["updated_at"] = "2026-05-05T00:00:00+00:00"
        return {"rows": [latest], "latest": latest}

    def _checkpoint_payload(self, job_id: str):
        return {"counts": {"completed": 1}, "latest": {"completed": {"id": 1}}}

    def _exceptions_payload(self, job_id: str):
        return {"all-exceptions": [{"exception": "intentional checkpoint recovery trigger"}]}

    def _cancel_job(self, job_id: str) -> str:
        return "cancelled"


def test_run_writes_latest_data_platform_artifact(tmp_path: Path):
    service = _StubService(root=tmp_path, runtime_mode="docker-wsl")

    summary = service.run(output_root=tmp_path / "artifacts" / "local_flink_checkpoint")

    latest_path = tmp_path / "artifacts" / "data_platform" / "flink_checkpoint_acceptance_latest.json"
    assert summary["accepted"] is True
    assert latest_path.exists()
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["job_id"] == "job-001"
    assert latest["checkpoint_summary"]["completed"] == 1
    assert latest["recovery_summary"]["recovered"] is True
    assert any(item["name"] == "flink_job_has_completed_checkpoint" for item in latest["checks"])
    assert any(item["name"] == "flink_job_recovers_after_controlled_failure" for item in latest["checks"])


def test_windows_host_run_writes_runtime_summary_without_container_fields(tmp_path: Path):
    service = _StubService(root=tmp_path, runtime_mode="windows-host")

    summary = service.run(output_root=tmp_path / "artifacts" / "local_flink_checkpoint")

    assert summary["accepted"] is True
    assert summary["environment"]["jobmanager"] is None
    assert summary["environment"]["taskmanager"] is None
    assert summary["environment"]["kafka"] is None
    assert summary["environment"]["runtime_mode"] == "windows-host"


class _WindowsHostCommandService(LocalFlinkCheckpointAcceptanceService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands: list[list[str]] = []

    def _run(self, args, *, timeout_seconds: float = 120.0, check: bool = True):
        self.commands.append(list(args))
        stdout = ""
        if len(args) >= 2 and args[1] == "run":
            stdout = "Job has been submitted with JobID job-001\n"
        elif len(args) >= 2 and args[1] == "cancel":
            stdout = "Cancelled job job-001\n"
        elif "--describe" in args:
            stdout = (
                "GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG\n"
                "group-001 topic-001 0 5 5 0\n"
            )

        class _Completed:
            def __init__(self, stdout: str):
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ""

        return _Completed(stdout)


@pytest.mark.parametrize("method_name", ["_submit_job", "_describe_consumer_group", "_cancel_job"])
def test_windows_host_runtime_uses_local_cli_paths_instead_of_docker(tmp_path: Path, monkeypatch, method_name: str):
    monkeypatch.setenv("FLINK_HOME", str(tmp_path / "flink"))
    monkeypatch.setenv("KAFKA_HOME", str(tmp_path / "kafka"))
    service = _WindowsHostCommandService(root=tmp_path, runtime_mode="windows-host")

    if method_name == "_submit_job":
        result = service._submit_job(
            job_jar=tmp_path / "job.jar",
            topic="topic-001",
            group_id="group-001",
            run_dir_name="run-001",
        )
        assert result["job_id"] == "job-001"
        assert Path(result["output_dir"]).name == "output"
        assert service.commands[0][1] == "run"
    elif method_name == "_describe_consumer_group":
        result = service._describe_consumer_group("group-001")
        assert result["rows"][0]["group"] == "group-001"
        assert "--describe" in service.commands[0]
    else:
        result = service._cancel_job("job-001")
        assert "Cancelled job" in result
        assert service.commands[0][1:] == ["cancel", "job-001"]


class _WindowsHostBuildService(LocalFlinkCheckpointAcceptanceService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands: list[list[str]] = []
        self.uber_jar_calls: list[dict[str, object]] = []

    def _download(self, spec):
        target = self.dependency_root / spec.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jar")
        return target

    def _run(self, args, *, timeout_seconds: float = 120.0, check: bool = True):
        self.commands.append(list(args))
        if args and str(args[0]).endswith("javac.exe"):
            classes_dir = self.build_root / "current" / "classes"
            classes_dir.mkdir(parents=True, exist_ok=True)
            (classes_dir / "Example.class").write_bytes(b"class")

        class _Completed:
            def __init__(self):
                self.returncode = 0
                self.stdout = "ok"
                self.stderr = ""

        return _Completed()

    def _build_uber_jar(self, *, classes_dir: Path, dependency_jars: list[Path], jar_path: Path) -> None:
        self.uber_jar_calls.append(
            {
                "classes_dir": classes_dir,
                "dependency_jars": dependency_jars,
                "jar_path": jar_path,
            }
        )
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        jar_path.write_bytes(b"jar")


def test_windows_host_build_job_uses_local_jdk_without_docker(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "jdk"))
    service = _WindowsHostBuildService(root=tmp_path, runtime_mode="windows-host")
    source_dir = service.java_source_root / "com" / "example"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "Example.java").write_text("class Example {}", encoding="utf-8")

    manifest = service._build_job(tmp_path / "run-001")

    assert Path(service.commands[0][0]).name == "javac.exe"
    assert manifest["reused_cached_jar"] is False
    assert Path(manifest["jar_path"]).exists()
    assert service.uber_jar_calls
