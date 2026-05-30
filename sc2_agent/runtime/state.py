"""Stop-the-world runtime state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sc2_agent.exceptions import InvalidRuntimeTransition


class RuntimeState(StrEnum):
    """Top-level runtime states.

    PAUSED_THINKING: game time is stopped; LLM/tools/subagents may run.
    RUNNING_SLEEP: game time advances; Timer Scheduler may execute commands
    and monitor wake conditions; LLM calls are forbidden.
    """

    PAUSED_THINKING = "PAUSED_THINKING"
    RUNNING_SLEEP = "RUNNING_SLEEP"


@dataclass(slots=True)
class RuntimeStateMachine:
    """Minimal state machine enforcing the stop-the-world invariant."""

    state: RuntimeState = RuntimeState.PAUSED_THINKING

    def commit_to_sleep(self) -> RuntimeState:
        """Transition from paused thinking to running sleep."""

        if self.state is not RuntimeState.PAUSED_THINKING:
            raise InvalidRuntimeTransition(
                f"ctrl.commit is only valid from PAUSED_THINKING, got {self.state}"
            )
        self.state = RuntimeState.RUNNING_SLEEP
        return self.state

    def wake_to_thinking(self) -> RuntimeState:
        """Transition from running sleep to paused thinking."""

        if self.state is not RuntimeState.RUNNING_SLEEP:
            raise InvalidRuntimeTransition(
                f"timer wake is only valid from RUNNING_SLEEP, got {self.state}"
            )
        self.state = RuntimeState.PAUSED_THINKING
        return self.state

    def require(self, expected: RuntimeState) -> None:
        """Raise if the runtime is not in the expected state."""

        if self.state is not expected:
            raise InvalidRuntimeTransition(f"Expected {expected}, got {self.state}")
