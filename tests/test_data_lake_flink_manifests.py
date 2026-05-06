from __future__ import annotations

import asyncio

from src.services.data_lake_service import DataLakeService


class _DummySession:
    async def execute(self, *args, **kwargs):
        class _Result:
            class _Scalars:
                def all(self):
                    return []

                def __iter__(self):
                    return iter([])

            def scalars(self):
                return self._Scalars()

        return _Result()


def test_data_lake_status_exposes_flink_manifests():
    service = DataLakeService(_DummySession())
    status = asyncio.run(service.build_status())
    batch_engine = status["processing_engines"]["batch_engine"]
    stream_engine = status["processing_engines"]["stream_engine"]
    assert "scheduler_manifest" in batch_engine
    assert "kettle_etl_manifest" in batch_engine
    assert "flink_feature_manifest" in stream_engine
    assert "flink_trendwide_manifest" in stream_engine
    assert "flink_forum_topic_manifest" in stream_engine


def test_data_lake_status_exposes_flink_checkpoint_acceptance(monkeypatch):
    service = DataLakeService(_DummySession())
    checkpoint_artifact = {
        "accepted": True,
        "job_id": "job-001",
        "checkpoint_summary": {"completed": 1},
    }
    original = service._read_json_artifact

    def _fake_read(path):
        if str(path).replace("\\", "/").endswith("artifacts/data_platform/flink_checkpoint_acceptance_latest.json"):
            return checkpoint_artifact
        return original(path)

    monkeypatch.setattr(service, "_read_json_artifact", _fake_read)

    status = asyncio.run(service.build_status())

    assert status["processing_engines"]["stream_engine"]["checkpoint_acceptance"]["accepted"] is True
    assert status["processing_engines"]["stream_engine"]["checkpoint_acceptance"]["job_id"] == "job-001"
