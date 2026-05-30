from __future__ import annotations

import asyncio
from typing import Any

from sc2_agent.observation.collector import ObservationStore
from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.models import TimerCommand, TimerMonitor
from sc2_agent.timer.scheduler import TimerScheduler
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.base import Tool
from sc2_agent.tools.registry import ToolRegistry


class RecordingTool(Tool):
    read_only = False

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    @property
    def name(self) -> str:
        return "cmd.fake"

    @property
    def description(self) -> str:
        return "fake command tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"value": {"type": "integer"}}}

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return {"called": True}


def _snapshot(*, minerals: int = 50, supply_used: int = 10, supply_cap: int = 15) -> ObservationSnapshot:
    return ObservationSnapshot(
        game_time=10,
        minerals=minerals,
        gas=0,
        supply_used=supply_used,
        supply_cap=supply_cap,
        units=[
            UnitSnapshot(tag=1, type_name="SCV", x=0, y=0, alliance="self"),
            UnitSnapshot(tag=2, type_name="Marine", x=10, y=10, alliance="enemy"),
        ],
        structures=[UnitSnapshot(tag=101, type_name="Barracks", x=5, y=5, build_progress=0.8)],
    )


def _scheduler(store: TimerStore, provider: ObservationStore, calls: list[dict[str, Any]] | None = None):
    runtime = RuntimeStateMachine()
    runtime.commit_to_sleep()
    registry = ToolRegistry()
    if calls is not None:
        registry.register(RecordingTool(calls))
    return TimerScheduler(
        runtime=runtime,
        timer_store=store,
        tool_registry=registry,
        observation_provider=provider,
    ), runtime


def test_due_command_executes_once_and_records_history() -> None:
    calls: list[dict[str, Any]] = []
    store = TimerStore(
        commands=[
            TimerCommand(id="cmd1", at_time=5, tool_name="cmd.fake", arguments={"value": 7}, created_at=0, wake_id=1)
        ]
    )
    scheduler, _ = _scheduler(store, ObservationStore(_snapshot()), calls)

    result = asyncio.run(scheduler.tick(10))
    second = asyncio.run(scheduler.tick(11))

    assert result.executed == ["cmd1"]
    assert second.executed == []
    assert calls == [{"value": 7}]
    assert store.commands[0].status == "done"
    assert store.run_history[0].status == "ok"


def test_not_due_command_does_not_execute() -> None:
    calls: list[dict[str, Any]] = []
    store = TimerStore(
        commands=[
            TimerCommand(id="cmd1", at_time=15, tool_name="cmd.fake", arguments={"value": 7}, created_at=0, wake_id=1)
        ]
    )
    scheduler, _ = _scheduler(store, ObservationStore(_snapshot()), calls)

    result = asyncio.run(scheduler.tick(10))

    assert result.executed == []
    assert calls == []
    assert store.commands[0].status == "pending"


def test_failed_command_records_error_history() -> None:
    store = TimerStore(
        commands=[
            TimerCommand(id="cmd1", at_time=5, tool_name="cmd.missing", arguments={}, created_at=0, wake_id=1)
        ]
    )
    scheduler, _ = _scheduler(store, ObservationStore(_snapshot()))

    result = asyncio.run(scheduler.tick(10))

    assert result.executed == ["cmd1"]
    assert store.commands[0].status == "failed"
    assert store.run_history[0].status == "error"
    assert store.run_history[0].error is not None


def test_command_returning_standard_failure_dict_is_marked_failed() -> None:
    class FailingDictTool(Tool):
        read_only = False

        @property
        def name(self) -> str:
            return "cmd.dict_fail"

        @property
        def description(self) -> str:
            return "dict failure"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs: Any) -> dict[str, Any]:
            return {"ok": False, "errors": [{"code": "TAG_NOT_FOUND", "tag": 9}]}

    store = TimerStore(
        commands=[
            TimerCommand(id="cmd1", at_time=5, tool_name="cmd.dict_fail", arguments={}, created_at=0, wake_id=1)
        ]
    )
    runtime = RuntimeStateMachine()
    runtime.commit_to_sleep()
    registry = ToolRegistry()
    registry.register(FailingDictTool())
    scheduler = TimerScheduler(
        runtime=runtime,
        timer_store=store,
        tool_registry=registry,
        observation_provider=ObservationStore(_snapshot()),
    )

    result = asyncio.run(scheduler.tick(10))

    assert result.executed == ["cmd1"]
    assert store.commands[0].status == "failed"
    assert store.run_history[0].status == "error"
    assert store.run_history[0].error is not None


def test_monitor_trigger_wakes_runtime_and_deactivates_monitor() -> None:
    store = TimerStore(
        monitors=[
            TimerMonitor(id="mon1", metric="minerals", op=">=", value=50, reason="enough money", created_at=0, wake_id=1)
        ]
    )
    scheduler, runtime = _scheduler(store, ObservationStore(_snapshot(minerals=75)), [])

    result = asyncio.run(scheduler.tick(10))

    assert result.triggered == ["mon1"]
    assert runtime.state is RuntimeState.PAUSED_THINKING
    assert store.monitors[0].active is False


def test_monitor_before_time_expires_without_wake() -> None:
    store = TimerStore(
        monitors=[
            TimerMonitor(
                id="mon1",
                metric="minerals",
                op=">=",
                value=999,
                reason="too late",
                created_at=0,
                wake_id=1,
                before_time=9,
            )
        ]
    )
    scheduler, runtime = _scheduler(store, ObservationStore(_snapshot()), [])

    result = asyncio.run(scheduler.tick(10))

    assert result.expired == ["mon1"]
    assert result.triggered == []
    assert runtime.state is RuntimeState.RUNNING_SLEEP
    assert store.monitors[0].active is False


def test_scheduler_is_skipped_when_runtime_paused() -> None:
    calls: list[dict[str, Any]] = []
    runtime = RuntimeStateMachine()
    store = TimerStore(
        commands=[
            TimerCommand(id="cmd1", at_time=5, tool_name="cmd.fake", arguments={"value": 7}, created_at=0, wake_id=1)
        ]
    )
    registry = ToolRegistry()
    registry.register(RecordingTool(calls))
    scheduler = TimerScheduler(
        runtime=runtime,
        timer_store=store,
        tool_registry=registry,
        observation_provider=ObservationStore(_snapshot()),
    )

    result = asyncio.run(scheduler.tick(10))

    assert result.skipped is True
    assert calls == []
    assert store.commands[0].status == "pending"
