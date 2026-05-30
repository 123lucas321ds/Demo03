"""Per-turn timer staging."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sc2_agent.timer.models import TimerCommand, TimerMonitor


@dataclass(slots=True)
class TimerStaging:
    """Commands and monitors proposed in the current paused turn."""

    commands: list[TimerCommand] = field(default_factory=list)
    monitors: list[TimerMonitor] = field(default_factory=list)
    review_hash: str | None = None

    def add_command(self, command: TimerCommand) -> None:
        self.commands.append(command)

    def add_monitor(self, monitor: TimerMonitor) -> None:
        self.monitors.append(monitor)

    def hash(self) -> str:
        payload = {
            "commands": [command.to_dict() for command in self.commands],
            "monitors": [monitor.to_dict() for monitor in self.monitors],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def mark_reviewed(self, staging_hash: str | None = None) -> str:
        current_hash = staging_hash or self.hash()
        self.review_hash = current_hash
        return current_hash

    def clear(self) -> None:
        self.commands.clear()
        self.monitors.clear()
        self.review_hash = None
