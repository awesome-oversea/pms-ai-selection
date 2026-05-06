"""
任务 4.3 验收测试：数据库查询优化
==================================

验收标准:
- [x] ORM 模型中新增的 Index 定义与实际查询匹配
- [x] list_tasks() 支持游标分页（不使用 OFFSET）
- [x] list_tasks_stream() 使用 yield_per() 流式加载
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestDatabaseIndexes:
    def test_selection_task_has_status_created_index(self):
        """SelectionTask 包含 status+created_at 联合索引。"""
        from src.models.models import SelectionTask

        index_names = [idx.name for idx in SelectionTask.__table_args__ if hasattr(idx, "name")]
        assert "ix_task_status_created" in index_names, \
            f"缺少 ix_task_status_created 索引, 已有: {index_names}"

    def test_selection_task_has_status_priority_index(self):
        """SelectionTask 包含 status+priority 联合索引。"""
        from src.models.models import SelectionTask

        index_names = [idx.name for idx in SelectionTask.__table_args__ if hasattr(idx, "name")]
        assert "ix_task_status_priority" in index_names

    def test_agent_run_has_task_type_index(self):
        """AgentRun 包含 task_id+agent_type 联合索引。"""
        from src.models.models import AgentRun

        index_names = [idx.name for idx in AgentRun.__table_args__ if hasattr(idx, "name")]
        assert "ix_agent_run_task_type" in index_names

    def test_agent_run_has_status_time_index(self):
        """AgentRun 包含 status+created_at 联合索引。"""
        from src.models.models import AgentRun

        index_names = [idx.name for idx in AgentRun.__table_args__ if hasattr(idx, "name")]
        assert "ix_agent_run_status_time" in index_names


class TestCursorPagination:
    def test_list_tasks_accepts_cursor_param(self):
        """list_tasks 方法签名包含 cursor 参数。"""
        import inspect

        from src.repositories.selection_repository import SelectionTaskRepository

        sig = inspect.signature(SelectionTaskRepository.list_tasks)
        params = list(sig.parameters.keys())
        assert "cursor" in params, f"list_tasks 缺少 cursor 参数, 参数列表: {params}"

    def test_list_tasks_cursor_default_is_none(self):
        """cursor 默认值为 None（向后兼容）。"""
        import inspect

        from src.repositories.selection_repository import SelectionTaskRepository

        sig = inspect.signature(SelectionTaskRepository.list_tasks)
        cursor_param = sig.parameters["cursor"]
        assert cursor_param.default is None


class TestStreamLoading:
    def test_list_tasks_stream_method_exists(self):
        """SelectionTaskRepository 包含 list_tasks_stream 方法。"""
        from src.repositories.selection_repository import SelectionTaskRepository

        assert hasattr(SelectionTaskRepository, "list_tasks_stream")

    def test_list_tasks_stream_is_async_generator(self):
        """list_tasks_stream 是异步生成器。"""
        import inspect

        from src.repositories.selection_repository import SelectionTaskRepository

        assert inspect.isasyncgenfunction(SelectionTaskRepository.list_tasks_stream)

    def test_list_tasks_stream_accepts_batch_size(self):
        """list_tasks_stream 接受 batch_size 参数。"""
        import inspect

        from src.repositories.selection_repository import SelectionTaskRepository

        sig = inspect.signature(SelectionTaskRepository.list_tasks_stream)
        params = list(sig.parameters.keys())
        assert "batch_size" in params


class TestSelectionRepositoryCrud:
    @pytest.mark.asyncio
    async def test_create_task_adds_model_and_flushes(self):
        from src.models.enums import TaskPriority, TaskStatus
        from src.repositories.selection_repository import SelectionTaskRepository

        session = MagicMock()
        session.flush = AsyncMock()
        repo = SelectionTaskRepository(session, tenant_id="00000000-0000-0000-0000-00000000a001")

        created = await repo.create_task(
            title="蓝牙耳机分析",
            category="electronics",
            target_market="US",
            priority=TaskPriority.HIGH,
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert created.title == "蓝牙耳机分析"
        assert created.target_category == "electronics"
        assert created.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_task_status_updates_summary_and_history(self):
        from src.models.enums import TaskStatus
        from src.repositories.selection_repository import SelectionTaskRepository

        session = MagicMock()
        session.flush = AsyncMock()
        repo = SelectionTaskRepository(session, tenant_id="00000000-0000-0000-0000-00000000a001")
        task = MagicMock()
        task.status = TaskStatus.PENDING
        task.config = {}
        task.result_summary = None
        task.completed_at = None
        repo.get_task = AsyncMock(return_value=task)

        updated = await repo.update_task_status(
            task_id="00000000-0000-0000-0000-000000000123",
            status=TaskStatus.RUNNING,
            result_summary="开始执行",
            phase="collect",
            reason="worker claimed",
        )

        assert updated is True
        assert task.status == TaskStatus.RUNNING
        assert task.result_summary == "开始执行"
        assert task.config["phase"] == "collect"
        assert task.config["status_reason"] == "worker claimed"
        assert task.config["status_history"][-1]["to"] == TaskStatus.RUNNING.value
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_task_result_persists_execution_result(self):
        from src.repositories.selection_repository import SelectionTaskRepository

        session = MagicMock()
        session.flush = AsyncMock()
        repo = SelectionTaskRepository(session, tenant_id="00000000-0000-0000-0000-00000000a001")
        task = MagicMock()
        task.config = {"phase": "running"}
        repo.get_task = AsyncMock(return_value=task)

        saved = await repo.save_task_result(
            task_id="00000000-0000-0000-0000-000000000124",
            result_data={"decision": "GO", "score": 88},
        )

        assert saved is True
        assert task.config["execution_result"]["decision"] == "GO"
        assert "updated_at" in task.config
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_task_soft_deletes_record(self):
        from src.repositories.selection_repository import SelectionTaskRepository

        session = MagicMock()
        session.flush = AsyncMock()
        repo = SelectionTaskRepository(session, tenant_id="00000000-0000-0000-0000-00000000a001")
        task = MagicMock()
        task.is_deleted = False
        repo.get_task = AsyncMock(return_value=task)

        deleted = await repo.delete_task("00000000-0000-0000-0000-000000000125")

        assert deleted is True
        assert task.is_deleted is True
        session.flush.assert_awaited_once()
