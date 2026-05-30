from sc2_agent.timer.models import TimerCommand, TimerMonitor
from sc2_agent.timer.staging import TimerStaging


def _command(at_time: float = 1.0) -> TimerCommand:
    return TimerCommand(
        id="cmd1",
        at_time=at_time,
        tool_name="build.train",
        arguments={"structure_tag": 1, "unit_type": "SCV"},
        created_at=0.0,
        wake_id=1,
    )


def _monitor(value: float = 10.0) -> TimerMonitor:
    return TimerMonitor(
        id="mon1",
        metric="game_time",
        op=">=",
        value=value,
        reason="wake",
        created_at=0.0,
        wake_id=1,
    )


def test_staging_hash_is_stable_for_same_content() -> None:
    a = TimerStaging(commands=[_command()], monitors=[_monitor()])
    b = TimerStaging(commands=[_command()], monitors=[_monitor()])

    assert a.hash() == b.hash()


def test_staging_hash_changes_when_content_changes() -> None:
    a = TimerStaging(commands=[_command(1.0)], monitors=[_monitor()])
    b = TimerStaging(commands=[_command(2.0)], monitors=[_monitor()])

    assert a.hash() != b.hash()


def test_mark_reviewed_stores_current_hash() -> None:
    staging = TimerStaging(commands=[_command()], monitors=[_monitor()])

    staging_hash = staging.mark_reviewed()

    assert staging.review_hash == staging_hash
    assert staging_hash == staging.hash()


def test_clear_removes_commands_monitors_and_review() -> None:
    staging = TimerStaging(commands=[_command()], monitors=[_monitor()])
    staging.mark_reviewed()

    staging.clear()

    assert staging.commands == []
    assert staging.monitors == []
    assert staging.review_hash is None
