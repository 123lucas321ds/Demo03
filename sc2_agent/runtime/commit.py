"""Commit controller for paused turns."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable

from sc2_agent.models import Result
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore


Step = Callable[[], object]
PendingMessagesProvider = Callable[[], list[dict]]


@dataclass(slots=True)
class CommitServices:
    """Callbacks executed in the simplified commit order."""

    save_snapshot_and_events: Step
    append_session: Step
    update_game_state: Step
    consolidate_memory: Step
    render_game_state_markdown: Step
    pending_messages: PendingMessagesProvider | None = None


class CommitController:
    """Validate and apply `ctrl.commit(staging_hash)`."""

    def __init__(
        self,
        *,
        runtime: RuntimeStateMachine,
        staging: TimerStaging,
        timer_store: TimerStore,
        services: CommitServices,
    ) -> None:
        self.runtime = runtime
        self.staging = staging
        self.timer_store = timer_store
        self.services = services

    async def commit(self, staging_hash: str) -> Result:
        try:
            self.runtime.require(RuntimeState.PAUSED_THINKING)
        except Exception as exc:
            return Result.failure("INVALID_RUNTIME_STATE", str(exc))

        current_hash = self.staging.hash()
        if staging_hash != current_hash:
            return Result.failure(
                "STAGING_HASH_MISMATCH",
                "ctrl.commit staging_hash does not match current staging",
                expected=current_hash,
                actual=staging_hash,
            )
        if self.staging.review_hash != current_hash:
            return Result.failure(
                "STAGING_NOT_REVIEWED",
                "current staging must be reviewed before commit",
                staging_hash=current_hash,
                review_hash=self.staging.review_hash,
            )

        step_names = [
            "save_snapshot_and_events",
            "append_session",
            "update_game_state",
            "consolidate_memory",
            "render_game_state_markdown",
        ]
        steps = [
            self.services.save_snapshot_and_events,
            self.services.append_session,
            self.services.update_game_state,
            self.services.consolidate_memory,
            self.services.render_game_state_markdown,
        ]
        try:
            for i, step in enumerate(steps):
                value = step()
                if inspect.isawaitable(value):
                    await value
            self.timer_store.register(list(self.staging.commands), list(self.staging.monitors))
            self.staging.clear()
            self.runtime.commit_to_sleep()
            return Result.success({"state": self.runtime.state.value})
        except Exception as exc:
            return Result.failure(
                "COMMIT_FAILED",
                str(exc),
                failed_at_step=i,
                step_name=step_names[i] if i < len(step_names) else "unknown",
                completed_steps=step_names[:i],
                failed_before_timer_registration=True,
            )

    def abort(self, reason: str) -> Result:
        self.staging.clear()
        return Result.success({"reason": reason})
