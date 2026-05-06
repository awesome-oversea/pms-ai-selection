from __future__ import annotations

import asyncio
from pathlib import Path

from src.agents.message_protocol import AgentMessage, MessageBus, MessageType


def test_message_bus_query_and_replay_preserve_offsets(tmp_path: Path):
    persistence_path = tmp_path / "tenant-a.jsonl"
    bus = MessageBus(persistence_path=persistence_path)

    async def _scenario():
        await bus.send(AgentMessage.from_agent("planner", "collector", {"task": "amazon"}, message_type=MessageType.CONTROL_COMMAND))
        await bus.send(AgentMessage.from_agent("collector", "planner", {"records": 3}, message_type=MessageType.STATUS_UPDATE))
        await bus.send(AgentMessage.from_agent("collector", "planner", {"records": 5}, message_type=MessageType.STATUS_UPDATE))

    asyncio.run(_scenario())

    queried = bus.query(receiver="planner", after_offset=0, limit=10)
    replayed = bus.replay(receiver="planner", after_offset=0, limit=10)

    assert len(queried) == 2
    assert replayed["next_offset"] >= 3
    assert replayed["items"][0].metadata["bus_offset"] >= 1
    assert persistence_path.exists()


def test_message_bus_restores_persisted_offsets(tmp_path: Path):
    persistence_path = tmp_path / "tenant-b.jsonl"
    bus = MessageBus(persistence_path=persistence_path)

    async def _scenario():
        await bus.send(AgentMessage.from_agent("agent-a", "agent-b", {"value": 1}))
        await bus.send(AgentMessage.from_agent("agent-a", "agent-b", {"value": 2}))

    asyncio.run(_scenario())
    restored = MessageBus(persistence_path=persistence_path)
    replay = restored.replay(receiver="agent-b", after_offset=0, limit=10)

    assert replay["next_offset"] == 2
    assert len(replay["items"]) == 2


def test_message_bus_trace_summary_exposes_correlation_and_task_routes(tmp_path: Path):
    persistence_path = tmp_path / "tenant-c.jsonl"
    bus = MessageBus(persistence_path=persistence_path)

    async def _scenario():
        await bus.send(
            AgentMessage.from_agent(
                "planner",
                "collector",
                {"task_id": "task-001", "stage": "collect"},
                message_type=MessageType.CONTROL_COMMAND,
                correlation_id="corr-001",
            )
        )
        await bus.send(
            AgentMessage.from_agent(
                "collector",
                "planner",
                {"task_id": "task-001", "records": 3},
                message_type=MessageType.STATUS_UPDATE,
                correlation_id="corr-001",
            )
        )

    asyncio.run(_scenario())

    trace_summary = bus.build_trace_summary()
    assert trace_summary["trace_ready"] is True
    assert trace_summary["offset_monotonic"] is True
    assert trace_summary["offset_gap_count"] == 0
    assert trace_summary["correlation_groups"][0]["correlation_id"] == "corr-001"
    assert trace_summary["correlation_groups"][0]["message_count"] == 2
    assert trace_summary["task_associations"][0]["task_key"] == "task-001"
    assert {item["route"] for item in trace_summary["recent_routes"]} >= {"planner->collector", "collector->planner"}
