from __future__ import annotations

import asyncio

from sc2_agent.runtime.commit import CommitController, CommitServices
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.models import TimerCommand, TimerMonitor
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore


def _command() -> TimerCommand:
    return TimerCommand(
        id="cmd1",
        at_time=1.0,
        tool_name="build.train",
        arguments={"structure_tag": 1, "unit_type": "SCV"},
        created_at=0.0,
        wake_id=1,
    )


def _monitor() -> TimerMonitor:
    return TimerMonitor(
        id="mon1",
        metric="game_time",
        op=">=",
        value=10.0,
        reason="wake",
        created_at=0.0,
        wake_id=1,
    )


def _controller(events: list[str], staging: TimerStaging | None = None) -> tuple[CommitController, TimerStore, RuntimeStateMachine]:
    runtime = RuntimeStateMachine()
    timer_store = TimerStore()
    staging = staging or TimerStaging(commands=[_command()], monitors=[_monitor()])

    def step(name: str):
        def _inner() -> None:
            events.append(name)
        return _inner

    services = CommitServices(
        save_snapshot_and_events=step("snapshot_events"),
        append_session=step("session"),
        update_game_state=step("game_state_json"),
        consolidate_memory=step("consolidate"),
        render_game_state_markdown=step("render_markdown"),
    )
    return CommitController(runtime=runtime, staging=staging, timer_store=timer_store, services=services), timer_store, runtime


def test_commit_rejects_unreviewed_staging() -> None:
    events: list[str] = []
    controller, timer_store, runtime = _controller(events)
    staging_hash = controller.staging.hash()

    result = asyncio.run(controller.commit(staging_hash))

    assert not result.ok
    assert result.code == "STAGING_NOT_REVIEWED"
    assert timer_store.commands == []
    assert runtime.state is RuntimeState.PAUSED_THINKING


def test_commit_rejects_hash_mismatch() -> None:
    events: list[str] = []
    controller, timer_store, _ = _controller(events)
    controller.staging.mark_reviewed()

    result = asyncio.run(controller.commit("sha256:wrong"))

    assert not result.ok
    assert result.code == "STAGING_HASH_MISMATCH"
    assert timer_store.commands == []


def test_commit_runs_order_then_registers_timer_and_sleeps() -> None:
    events: list[str] = []
    controller, timer_store, runtime = _controller(events)
    staging_hash = controller.staging.mark_reviewed()

    result = asyncio.run(controller.commit(staging_hash))

    assert result.ok
    assert events == ["snapshot_events", "session", "game_state_json", "consolidate", "render_markdown"]
    assert len(timer_store.commands) == 1
    assert len(timer_store.monitors) == 1
    assert controller.staging.commands == []
    assert runtime.state is RuntimeState.RUNNING_SLEEP


def test_commit_failure_before_timer_registration_does_not_register_timer() -> None:
    staging = TimerStaging(commands=[_command()], monitors=[_monitor()])
    staging_hash = staging.mark_reviewed()
    timer_store = TimerStore()
    runtime = RuntimeStateMachine()

    def fail() -> None:
        raise RuntimeError("boom")

    services = CommitServices(
        save_snapshot_and_events=lambda: None,
        append_session=fail,
        update_game_state=lambda: None,
        consolidate_memory=lambda: None,
        render_game_state_markdown=lambda: None,
    )
    controller = CommitController(runtime=runtime, staging=staging, timer_store=timer_store, services=services)

    result = asyncio.run(controller.commit(staging_hash))

    assert not result.ok
    assert result.code == "COMMIT_FAILED"
    assert timer_store.commands == []
    assert staging.commands != []
    assert runtime.state is RuntimeState.PAUSED_THINKING


def test_abort_clears_staging_without_touching_timer_store() -> None:
    events: list[str] = []
    controller, timer_store, runtime = _controller(events)
    timer_store.register([_command()], [_monitor()])

    result = controller.abort("user_cancelled")

    assert result.ok
    assert controller.staging.commands == []
    assert len(timer_store.commands) == 1
    assert runtime.state is RuntimeState.PAUSED_THINKING
