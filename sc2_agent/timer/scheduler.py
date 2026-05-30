"""Timer command scheduler and monitor evaluator."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sc2_agent.observation.collector import ObservationProvider
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.models import TimerMonitor, TimerRunRecord
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class SchedulerResult:
    executed: list[str] = field(default_factory=list)
    triggered: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    failed_details: list[dict] = field(default_factory=list)
    skipped: bool = False


class TimerScheduler:
    """Execute due timer commands and wake the agent on monitor triggers."""

    def __init__(
        self,
        *,
        runtime: RuntimeStateMachine,
        timer_store: TimerStore,
        tool_registry: ToolRegistry,
        observation_provider: ObservationProvider,
    ) -> None:
        self.runtime = runtime
        self.timer_store = timer_store
        self.tool_registry = tool_registry
        self.observation_provider = observation_provider

    async def tick(self, game_time: float) -> SchedulerResult:
        if self.runtime.state is not RuntimeState.RUNNING_SLEEP:
            return SchedulerResult(skipped=True)

        executed: list[str] = []
        triggered: list[str] = []
        expired: list[str] = []
        failed: list[str] = []
        failed_details: list[dict] = []

        for command in sorted(self.timer_store.commands, key=lambda item: item.at_time):
            if command.status != "pending" or command.at_time > game_time:
                continue
            result = await self.tool_registry.execute(command.tool_name, command.arguments)
            status = "done" if result.ok else "failed"
            self.timer_store.update_command_status(command.id, status)

            # R-040 / R-044: 记录错误码和部分失败
            error_code = result.code if not result.ok else None
            error_meta = dict(result.meta) if not result.ok and result.meta else None
            if result.ok and isinstance(result.data, dict) and result.data.get("errors"):
                error_code = "PARTIAL_FAILURE"
                error_meta = {"partial_errors": result.data["errors"]}

            self.timer_store.append_run(
                TimerRunRecord(
                    timer_id=command.id,
                    game_time=game_time,
                    status="ok" if result.ok else "error",
                    error=result.error,
                    error_code=error_code,
                    error_meta=error_meta,
                )
            )
            executed.append(command.id)
            if not result.ok:
                failed.append(command.id)
                failed_details.append({
                    "timer_id": command.id,
                    "tool_name": command.tool_name,
                    "error_code": result.code,
                    "error": result.error,
                })

        for monitor in list(self.timer_store.monitors):
            if not monitor.active:
                continue
            if monitor.before_time is not None and game_time > monitor.before_time:
                self.timer_store.deactivate_monitor(monitor.id)
                expired.append(monitor.id)
                continue
            if self._monitor_matches(monitor, game_time):
                self.timer_store.deactivate_monitor(monitor.id)
                triggered.append(monitor.id)
                self.runtime.wake_to_thinking()
                break

        return SchedulerResult(executed=executed, triggered=triggered, expired=expired, failed=failed, failed_details=failed_details)

    def _monitor_matches(self, monitor: TimerMonitor, game_time: float) -> bool:
        actual = self._monitor_value(monitor, game_time)
        if actual is None:
            return False
        return self._compare(actual, monitor.op, monitor.value)

    def _monitor_value(self, monitor: TimerMonitor, game_time: float) -> float | int | bool | None:
        snapshot = self.observation_provider.snapshot()
        if monitor.metric == "game_time":
            return game_time
        if monitor.metric == "minerals":
            return snapshot.minerals
        if monitor.metric == "gas":
            return snapshot.gas
        if monitor.metric == "supply_available":
            return snapshot.supply_cap - snapshot.supply_used
        if monitor.metric == "unit_count":
            return sum(
                1
                for unit in snapshot.units
                if unit.alliance == "self" and (monitor.unit_type is None or unit.type_name == monitor.unit_type)
            )
        if monitor.metric == "enemy_count":
            return sum(1 for unit in [*snapshot.units, *snapshot.structures] if unit.alliance == "enemy")
        if monitor.metric == "building_progress":
            values = [
                structure.build_progress
                for structure in snapshot.structures
                if monitor.building_type is None or structure.type_name == monitor.building_type
            ]
            return max(values) if values else None
        if monitor.metric == "unit_distance":
            if monitor.unit_tag is None or monitor.target_x is None or monitor.target_y is None:
                return None
            for unit in snapshot.units:
                if unit.tag == monitor.unit_tag:
                    return math.hypot(unit.x - monitor.target_x, unit.y - monitor.target_y)
            return None
        if monitor.metric == "unit_in_region":
            if monitor.unit_tag is None or monitor.region is None:
                return None
            x1, y1, x2, y2 = monitor.region
            for unit in snapshot.units:
                if unit.tag == monitor.unit_tag:
                    return x1 <= unit.x <= x2 and y1 <= unit.y <= y2
            return None
        return None

    @staticmethod
    def _compare(actual: Any, op: str, expected: Any) -> bool:
        if op == ">":
            return actual > expected
        if op == ">=":
            return actual >= expected
        if op == "<":
            return actual < expected
        if op == "<=":
            return actual <= expected
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        return False
