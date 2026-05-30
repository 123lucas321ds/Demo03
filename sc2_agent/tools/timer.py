"""Timer staging tools exposed to the agent."""

from __future__ import annotations

from itertools import count
from typing import Any, Callable

from sc2_agent.timer.models import TimerCommand, TimerMonitor
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.base import Tool


IdFactory = Callable[[str], str]


class _CounterIds:
    def __init__(self) -> None:
        self._counter = count(1)

    def __call__(self, prefix: str) -> str:
        return f"{prefix}{next(self._counter)}"


class TimerCommandTool(Tool):
    read_only = False

    def __init__(self, staging: TimerStaging, *, id_factory: IdFactory | None = None, registry=None) -> None:
        self.staging = staging
        self.id_factory = id_factory or _CounterIds()
        self._registry = registry

    @property
    def name(self) -> str:
        return "timer.command"

    @property
    def description(self) -> str:
        return "Stage a command to run while the game is in RUNNING_SLEEP."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {"type": ["string", "null"]},
                "at_time": {"type": "number", "minimum": 0},
                "tool_name": {"type": "string", "minLength": 1},
                "arguments": {"type": "object"},
                "reason": {"type": ["string", "null"]},
                "wake_id": {"type": "integer", "minimum": 0},
            },
            "required": ["at_time", "tool_name", "arguments"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tool_name = kwargs["tool_name"]
        if self._registry is not None and not self._registry.has(tool_name):
            return {"ok": False, "code": "TOOL_NOT_FOUND", "tool_name": tool_name}
        timer_id = kwargs.get("id") or self.id_factory("cmd")
        command = TimerCommand(
            id=timer_id,
            at_time=float(kwargs["at_time"]),
            tool_name=kwargs["tool_name"],
            arguments=dict(kwargs["arguments"]),
            created_at=float(kwargs.get("created_at", 0.0)),
            wake_id=int(kwargs.get("wake_id", 0)),
            reason=kwargs.get("reason"),
        )
        self.staging.add_command(command)
        return {"timer_id": timer_id, "staging_hash": self.staging.hash()}


class TimerMonitorTool(Tool):
    read_only = False

    def __init__(self, staging: TimerStaging, *, id_factory: IdFactory | None = None) -> None:
        self.staging = staging
        self.id_factory = id_factory or _CounterIds()

    @property
    def name(self) -> str:
        return "timer.monitor"

    @property
    def description(self) -> str:
        return "Stage a monitor that wakes the agent when its condition is met."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {"type": ["string", "null"]},
                "metric": {
                    "type": "string",
                    "enum": [
                        "game_time",
                        "minerals",
                        "gas",
                        "supply_available",
                        "unit_count",
                        "enemy_count",
                        "building_progress",
                        "unit_distance",
                        "unit_in_region",
                    ],
                },
                "op": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!="]},
                "value": {"type": "number"},
                "reason": {"type": "string"},
                "before_time": {"type": ["number", "null"]},
                "unit_type": {"type": ["string", "null"]},
                "building_type": {"type": ["string", "null"]},
                "wake_id": {"type": "integer", "minimum": 0},
            },
            "required": ["metric", "op", "value", "reason"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        timer_id = kwargs.get("id") or self.id_factory("mon")
        monitor = TimerMonitor(
            id=timer_id,
            metric=kwargs["metric"],
            op=kwargs["op"],
            value=kwargs["value"],
            reason=kwargs["reason"],
            created_at=float(kwargs.get("created_at", 0.0)),
            wake_id=int(kwargs.get("wake_id", 0)),
            before_time=kwargs.get("before_time"),
            unit_type=kwargs.get("unit_type"),
            building_type=kwargs.get("building_type"),
        )
        self.staging.add_monitor(monitor)
        return {"timer_id": timer_id, "staging_hash": self.staging.hash()}


class TimerListTool(Tool):
    read_only = True

    def __init__(self, staging: TimerStaging, timer_store: TimerStore) -> None:
        self.staging = staging
        self.timer_store = timer_store

    @property
    def name(self) -> str:
        return "timer.list"

    @property
    def description(self) -> str:
        return "List staged and committed timers."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        return {
            "staging_hash": self.staging.hash(),
            "staged": {
                "commands": [command.to_dict() for command in self.staging.commands],
                "monitors": [monitor.to_dict() for monitor in self.staging.monitors],
                "review_hash": self.staging.review_hash,
            },
            "active": {
                "commands": [command.to_dict() for command in self.timer_store.commands],
                "monitors": [monitor.to_dict() for monitor in self.timer_store.monitors],
            },
            "run_history": [record.to_dict() for record in self.timer_store.run_history],
        }


class TimerCancelTool(Tool):
    read_only = False

    def __init__(self, staging: TimerStaging, timer_store: TimerStore) -> None:
        self.staging = staging
        self.timer_store = timer_store

    @property
    def name(self) -> str:
        return "timer.cancel"

    @property
    def description(self) -> str:
        return "Cancel a staged or committed timer by id."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"timer_id": {"type": "string", "minLength": 1}},
            "required": ["timer_id"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        timer_id = kwargs["timer_id"]
        before_commands = len(self.staging.commands)
        before_monitors = len(self.staging.monitors)
        self.staging.commands = [command for command in self.staging.commands if command.id != timer_id]
        self.staging.monitors = [monitor for monitor in self.staging.monitors if monitor.id != timer_id]
        removed_staged = before_commands != len(self.staging.commands) or before_monitors != len(self.staging.monitors)
        cancelled_active = self.timer_store.cancel(timer_id)
        if removed_staged:
            self.staging.review_hash = None
        return {
            "ok": removed_staged or cancelled_active,
            "timer_id": timer_id,
            "removed_staged": removed_staged,
            "cancelled_active": cancelled_active,
            "staging_hash": self.staging.hash(),
        }
