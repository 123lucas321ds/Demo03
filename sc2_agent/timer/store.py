"""Committed timer storage."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sc2_agent.timer.models import TimerCommand, TimerMonitor, TimerRunRecord


@dataclass(slots=True)
class TimerStore:
    """In-memory timer store for early phases."""

    commands: list[TimerCommand] = field(default_factory=list)
    monitors: list[TimerMonitor] = field(default_factory=list)
    run_history: list[TimerRunRecord] = field(default_factory=list)

    def register(self, commands: list[TimerCommand], monitors: list[TimerMonitor]) -> None:
        self.commands.extend(commands)
        self.monitors.extend(monitors)

    def update_command_status(self, timer_id: str, status: str) -> None:
        self.commands = [
            replace(command, status=status) if command.id == timer_id else command
            for command in self.commands
        ]

    def deactivate_monitor(self, timer_id: str) -> None:
        self.monitors = [
            replace(monitor, active=False) if monitor.id == timer_id else monitor
            for monitor in self.monitors
        ]

    def cancel(self, timer_id: str) -> bool:
        found = False
        self.commands = [
            replace(command, status="cancelled") if command.id == timer_id else command
            for command in self.commands
        ]
        self.monitors = [
            replace(monitor, active=False) if monitor.id == timer_id else monitor
            for monitor in self.monitors
        ]
        for command in self.commands:
            found = found or command.id == timer_id
        for monitor in self.monitors:
            found = found or monitor.id == timer_id
        return found

    def append_run(self, record: TimerRunRecord) -> None:
        self.run_history.append(record)

    def clear(self) -> None:
        self.commands.clear()
        self.monitors.clear()
        self.run_history.clear()
