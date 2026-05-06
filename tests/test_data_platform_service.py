"""数据平台服务单元测试

验证DataLakeService的行为逻辑:
    - build_status返回正确的数据结构
    - 静态工具方法(_coerce_number/_normalize_iso_prefix/_enum_value)
    - 快照查询过滤逻辑
    - 不依赖真实DB连接
"""

from __future__ import annotations

import os

os.environ.setdefault("SEC_SECRET_KEY", "test-secret-key-for-phase14-validation-32chars")

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.data_lake_service import DataLakeService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return DataLakeService(mock_session)


class TestDataLakeServiceStaticHelpers:
    """静态工具方法测试: 不依赖任何外部资源"""

    def test_coerce_number_from_int(self):
        assert DataLakeService._coerce_number(42) == 42.0

    def test_coerce_number_from_float(self):
        assert DataLakeService._coerce_number(3.14) == 3.14

    def test_coerce_number_from_string(self):
        assert DataLakeService._coerce_number("100") == 100.0

    def test_coerce_number_from_percentage_string(self):
        assert DataLakeService._coerce_number("85%") == 85.0

    def test_coerce_number_returns_none_for_none(self):
        assert DataLakeService._coerce_number(None) is None

    def test_coerce_number_returns_none_for_empty_string(self):
        assert DataLakeService._coerce_number("") is None

    def test_coerce_number_returns_none_for_non_numeric(self):
        assert DataLakeService._coerce_number("abc") is None

    def test_coerce_number_handles_bool(self):
        assert DataLakeService._coerce_number(True) == 1.0
        assert DataLakeService._coerce_number(False) == 0.0

    def test_normalize_iso_prefix_returns_stripped_value(self):
        assert DataLakeService._normalize_iso_prefix("  2024-01-01  ") == "2024-01-01"

    def test_normalize_iso_prefix_returns_none_for_none(self):
        assert DataLakeService._normalize_iso_prefix(None) is None

    def test_normalize_iso_prefix_returns_none_for_empty(self):
        assert DataLakeService._normalize_iso_prefix("") is None

    def test_enum_value_extracts_value_from_enum(self):
        class FakeEnum:
            value = "active"
        assert DataLakeService._enum_value(FakeEnum()) == "active"

    def test_enum_value_returns_raw_when_not_enum(self):
        assert DataLakeService._enum_value("plain_string") == "plain_string"


class TestBuildCatalog:
    """build_catalog行为测试: 验证目录结构"""

    def test_build_catalog_returns_dict(self, service):
        catalog = service.build_catalog()
        assert isinstance(catalog, dict)


class TestBuildStatusWithMockedSession:
    """build_status行为测试: 使用mock隔离DB依赖"""

    @pytest.mark.asyncio
    async def test_build_status_returns_required_keys(self, service, mock_session, tmp_path):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, "build_catalog", return_value={}), \
             patch.object(service, "_read_json_artifact", return_value=None), \
             patch("src.services.data_lake_service.Path"):
            status = await service.build_status()

        assert "table_formats" in status
        assert "processing_engines" in status
        assert "pipeline_readiness" in status
        assert "downstream_consumers" in status

    @pytest.mark.asyncio
    async def test_build_status_pipeline_readiness_structure(self, service, mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(service, "build_catalog", return_value={}), \
             patch.object(service, "_read_json_artifact", return_value=None):
            status = await service.build_status()

        readiness = status.get("pipeline_readiness", {})
        assert "quality_checks_ready" in readiness


class TestSnapshotQueryFiltering:
    """快照查询过滤逻辑测试: 验证过滤条件正确应用"""

    def test_query_selection_tasks_snapshot_filters_by_status(self, service, tmp_path):
        snapshot_dir = tmp_path / "selection_tasks" / "snapshots" / "20240101"
        snapshot_dir.mkdir(parents=True)
        rows = [
            {"task_id": "1", "status": "completed", "target_market": "US", "created_at": "2024-01-01"},
            {"task_id": "2", "status": "pending", "target_market": "UK", "created_at": "2024-01-02"},
        ]
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        (snapshot_dir / "selection_tasks.jsonl").write_text(content, encoding="utf-8")

        service.object_store._root = tmp_path

        result = service.query_selection_tasks_snapshot(status="completed")
        assert result["total"] == 1
        assert result["items"][0]["task_id"] == "1"

    def test_query_selection_tasks_snapshot_filters_by_target_market(self, service, tmp_path):
        snapshot_dir = tmp_path / "selection_tasks" / "snapshots" / "20240101"
        snapshot_dir.mkdir(parents=True)
        rows = [
            {"task_id": "1", "status": "completed", "target_market": "US", "created_at": "2024-01-01"},
            {"task_id": "2", "status": "pending", "target_market": "UK", "created_at": "2024-01-02"},
        ]
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        (snapshot_dir / "selection_tasks.jsonl").write_text(content, encoding="utf-8")

        service.object_store._root = tmp_path

        result = service.query_selection_tasks_snapshot(target_market="UK")
        assert result["total"] == 1
        assert result["items"][0]["target_market"] == "UK"

    def test_query_selection_tasks_snapshot_returns_empty_when_no_data(self, service, tmp_path):
        service.object_store._root = tmp_path
        result = service.query_selection_tasks_snapshot()
        assert result["total"] == 0
        assert result["items"] == []


class TestReadJsonl:
    """_read_jsonl行为测试: 验证JSONL文件读取"""

    def test_read_jsonl_parses_valid_file(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
        rows = DataLakeService._read_jsonl(path)
        assert len(rows) == 2
        assert rows[0]["a"] == 1

    def test_read_jsonl_skips_empty_lines(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
        rows = DataLakeService._read_jsonl(path)
        assert len(rows) == 2

    def test_read_jsonl_skips_invalid_json(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\ninvalid json\n{"b": 2}\n', encoding="utf-8")
        rows = DataLakeService._read_jsonl(path)
        assert len(rows) == 2

    def test_read_jsonl_returns_empty_for_missing_file(self):
        rows = DataLakeService._read_jsonl(Path("/nonexistent/file.jsonl"))
        assert rows == []
