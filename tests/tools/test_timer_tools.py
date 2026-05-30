from __future__ import annotations

import asyncio

from sc2_agent.timer.models import TimerCommand, TimerMonitor, TimerRunRecord
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.timer import TimerCancelTool, TimerListTool


def _command(timer_id: str) -> TimerCommand:
    return TimerCommand(
        id=timer_id,
        at_time=5,
        tool_name="build.train",
        arguments={"unit_type": "SCV", "structure_tag": 1},
        created_at=0,
        wake_id=1,
    )


def _monitor(timer_id: str) -> TimerMonitor:
    return TimerMonitor(
        id=timer_id,
        metric="game_time",
        op=">=",
        value=10,
        reason="wake",
        created_at=0,
        wake_id=1,
    )


def test_timer_list_returns_staged_active_and_history() -> None:
    staging = TimerStaging(commands=[_command("staged_cmd")], monitors=[_monitor("staged_mon")])
    store = TimerStore(commands=[_command("active_cmd")], monitors=[_monitor("active_mon")])
    store.append_run(TimerRunRecord(timer_id="active_cmd", game_time=5, status="ok"))

    result = asyncio.run(TimerListTool(staging, store).execute())

    assert result["staged"]["commands"][0]["id"] == "staged_cmd"
    assert result["staged"]["monitors"][0]["id"] == "staged_mon"
    assert result["active"]["commands"][0]["id"] == "active_cmd"
    assert result["active"]["monitors"][0]["id"] == "active_mon"
    assert result["run_history"][0]["timer_id"] == "active_cmd"


def test_timer_cancel_removes_staged_timer_and_clears_review_hash() -> None:
    staging = TimerStaging(commands=[_command("cmd1")])
    staging.mark_reviewed()
    store = TimerStore()

    result = asyncio.run(TimerCancelTool(staging, store).execute(timer_id="cmd1"))

    assert result["ok"] is True
    assert result["removed_staged"] is True
    assert staging.commands == []
    assert staging.review_hash is None


def test_timer_cancel_marks_active_command_and_monitor_inactive() -> None:
    staging = TimerStaging()
    store = TimerStore(commands=[_command("cmd1")], monitors=[_monitor("mon1")])
    tool = TimerCancelTool(staging, store)

    command_result = asyncio.run(tool.execute(timer_id="cmd1"))
    monitor_result = asyncio.run(tool.execute(timer_id="mon1"))

    assert command_result["cancelled_active"] is True
    assert store.commands[0].status == "cancelled"
    assert monitor_result["cancelled_active"] is True
    assert store.monitors[0].active is False


def test_timer_cancel_unknown_timer_returns_standard_failure_dict() -> None:
    result = asyncio.run(TimerCancelTool(TimerStaging(), TimerStore()).execute(timer_id="missing"))

    assert result["ok"] is False
    assert result["timer_id"] == "missing"
