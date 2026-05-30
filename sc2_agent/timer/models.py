"""Timer data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


TimerStatus = Literal["pending", "done", "failed", "cancelled"]
MonitorMetric = Literal[
    "game_time",
    "minerals",
    "gas",
    "supply_available",
    "unit_count",
    "enemy_count",
    "building_progress",
    "unit_distance",
    "unit_in_region",
]
MonitorOp = Literal[">", ">=", "<", "<=", "==", "!="]


@dataclass(frozen=True, slots=True)
class TimerCommand:
    id: str
    at_time: float
    tool_name: str
    arguments: dict[str, Any]
    created_at: float
    wake_id: int
    reason: str | None = None
    status: TimerStatus = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TimerMonitor:
    id: str
    metric: MonitorMetric
    op: MonitorOp
    value: float | int | bool
    reason: str
    created_at: float
    wake_id: int
    before_time: float | None = None
    unit_type: str | None = None
    building_type: str | None = None
    unit_tag: int | None = None
    target_x: float | None = None
    target_y: float | None = None
    region: tuple[float, float, float, float] | None = None
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TimerRunRecord:
    timer_id: str
    game_time: float
    status: Literal["ok", "error"]
    error: str | None = None
    error_code: str | None = None
    error_meta: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
