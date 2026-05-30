import pytest

from sc2_agent.exceptions import InvalidRuntimeTransition
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine


def test_runtime_initial_state_is_paused_thinking() -> None:
    machine = RuntimeStateMachine()

    assert machine.state is RuntimeState.PAUSED_THINKING


def test_commit_to_sleep_then_wake_to_thinking() -> None:
    machine = RuntimeStateMachine()

    assert machine.commit_to_sleep() is RuntimeState.RUNNING_SLEEP
    assert machine.wake_to_thinking() is RuntimeState.PAUSED_THINKING


def test_commit_to_sleep_rejects_running_sleep() -> None:
    machine = RuntimeStateMachine(RuntimeState.RUNNING_SLEEP)

    with pytest.raises(InvalidRuntimeTransition, match="ctrl.commit"):
        machine.commit_to_sleep()


def test_wake_to_thinking_rejects_paused_thinking() -> None:
    machine = RuntimeStateMachine(RuntimeState.PAUSED_THINKING)

    with pytest.raises(InvalidRuntimeTransition, match="timer wake"):
        machine.wake_to_thinking()


def test_require_rejects_wrong_state() -> None:
    machine = RuntimeStateMachine(RuntimeState.PAUSED_THINKING)

    with pytest.raises(InvalidRuntimeTransition, match="Expected"):
        machine.require(RuntimeState.RUNNING_SLEEP)
