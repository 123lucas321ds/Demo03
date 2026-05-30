"""Deterministic resource and production simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sc2_agent.planning.costs import COSTS, Cost, canonical_name
from sc2_agent.planning.tech_tree import missing_prerequisites
from sc2_agent.timer.models import TimerCommand


CommandKind = Literal["train", "build"]


@dataclass(frozen=True, slots=True)
class ProductionItem:
    item_name: str
    kind: CommandKind
    complete_at: float
    producer_id: str | None = None


@dataclass(slots=True)
class SimulationState:
    game_time: float = 0.0
    minerals: float = 0.0
    gas: float = 0.0
    supply_used: int = 0
    supply_cap: int = 0
    mineral_income_rate: float = 0.0
    gas_income_rate: float = 0.0
    units: dict[str, int] = field(default_factory=dict)
    structures: dict[str, int] = field(default_factory=dict)
    production: list[ProductionItem] = field(default_factory=list)
    producer_available_at: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimulationState":
        return cls(
            game_time=float(data.get("game_time", 0.0)),
            minerals=float(data.get("minerals", 0.0)),
            gas=float(data.get("gas", 0.0)),
            supply_used=int(data.get("supply_used", 0)),
            supply_cap=int(data.get("supply_cap", 0)),
            mineral_income_rate=float(data.get("mineral_income_rate", 0.0)),
            gas_income_rate=float(data.get("gas_income_rate", 0.0)),
            units=cls._normalize_entity_counts(data.get("units", {})),
            structures=cls._normalize_entity_counts(data.get("structures", {})),
            production=[
                ProductionItem(
                    item_name=canonical_name(item["item_name"]),
                    kind=item["kind"],
                    complete_at=float(item["complete_at"]),
                    producer_id=item.get("producer_id"),
                )
                for item in data.get("production", [])
            ],
            producer_available_at={
                str(key): float(value) for key, value in data.get("producer_available_at", {}).items()
            },
        )

    @staticmethod
    def _normalize_entity_counts(data: Any) -> dict[str, int]:
        """Convert list-of-dict or dict format to canonical ``{type: count}``."""
        if isinstance(data, dict):
            result: dict[str, int] = {}
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    result[canonical_name(str(key))] = int(value)
                elif isinstance(value, list):
                    result[canonical_name(str(key))] = len(value)
                else:
                    result[canonical_name(str(key))] = int(value) if value else 0
            return result
        if isinstance(data, list):
            counts: dict[str, int] = {}
            for item in data:
                if isinstance(item, dict):
                    name = canonical_name(str(item.get("type_name") or item.get("type") or item.get("item_name") or "unknown"))
                    counts[name] = counts.get(name, 0) + 1
            return counts
        return {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_time": self.game_time,
            "minerals": self.minerals,
            "gas": self.gas,
            "supply_used": self.supply_used,
            "supply_cap": self.supply_cap,
            "mineral_income_rate": self.mineral_income_rate,
            "gas_income_rate": self.gas_income_rate,
            "units": dict(self.units),
            "structures": dict(self.structures),
            "production": [
                {
                    "item_name": item.item_name,
                    "kind": item.kind,
                    "complete_at": item.complete_at,
                    "producer_id": item.producer_id,
                }
                for item in self.production
            ],
            "producer_available_at": dict(self.producer_available_at),
        }


@dataclass(frozen=True, slots=True)
class PlanCommand:
    at_time: float
    kind: CommandKind
    item_name: str
    producer_id: str | None = None
    source: str = "staged"

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "staged") -> "PlanCommand":
        # Also look inside "arguments" sub-dict (timer.command format)
        args = data.get("arguments", {}) if isinstance(data.get("arguments"), dict) else {}

        item_name = (
            data.get("item_name")
            or data.get("unit_type") or data.get("structure_type") or data.get("building_type")
            or args.get("unit_type") or args.get("structure_type") or args.get("building_type") or args.get("item_name")
        )
        if not item_name:
            raise ValueError("plan command requires item_name, unit_type, structure_type, or building_type")
        kind = data.get("kind") or args.get("kind")
        if kind is None:
            kind = "train" if (data.get("unit_type") or args.get("unit_type")) else "build"
        producer_id = (
            data.get("producer_id") or data.get("producer_tag")
            or args.get("producer_id") or args.get("producer_tag")
            or args.get("structure_tag") or args.get("worker_tag")
        )
        return cls(
            at_time=float(data.get("at_time", 0.0)),
            kind=kind,
            item_name=canonical_name(str(item_name)),
            producer_id=str(producer_id) if producer_id is not None else None,
            source=source,
        )

    @classmethod
    def from_timer(cls, command: TimerCommand, *, source: str = "active_timer") -> "PlanCommand | None":
        if command.status != "pending":
            return None
        data = dict(command.arguments)
        data.setdefault("at_time", command.at_time)
        data.setdefault("producer_id", data.get("structure_tag") or data.get("worker_tag"))
        if "kind" not in data:
            if "unit_type" in data or "train" in command.tool_name:
                data["kind"] = "train"
            else:
                data["kind"] = "build"
        return cls.from_dict(data, source=source)


@dataclass(frozen=True, slots=True)
class ResourcePoint:
    time: float
    minerals: float
    gas: float
    supply_used: int
    supply_cap: int
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "minerals": self.minerals,
            "gas": self.gas,
            "supply_used": self.supply_used,
            "supply_cap": self.supply_cap,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class PlanFailure:
    code: str
    message: str
    command_index: int
    at_time: float
    item_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "command_index": self.command_index,
            "at_time": self.at_time,
            "item_name": self.item_name,
        }


@dataclass(frozen=True, slots=True)
class SimulationResult:
    points: list[ResourcePoint]
    final_state: SimulationState
    first_failure: PlanFailure | None
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [point.to_dict() for point in self.points],
            "final_state": self.final_state.to_dict(),
            "first_failure": self.first_failure.to_dict() if self.first_failure else None,
            "assumptions": list(self.assumptions),
        }


class PlanSimulator:
    """Simulate resources, supply, prerequisites, and producer occupancy."""

    assumptions = [
        "income is linear between command timestamps",
        "supply is consumed when unit production starts",
        "structure supply bonuses apply when construction completes",
        "only a minimal Terran cost and tech table is available before burnysc2 integration",
    ]

    def simulate(
        self,
        *,
        initial_state: SimulationState,
        commands: list[PlanCommand | dict[str, Any] | TimerCommand],
        active_timers: list[TimerCommand] | None = None,
        horizon: float | None = None,
    ) -> SimulationResult:
        state = self._copy_state(initial_state)
        points = [self._point(state, "start")]
        normalized = self._normalize_commands(commands, source="staged")
        normalized.extend(self._normalize_commands(active_timers or [], source="active_timer"))
        normalized.sort(key=lambda item: item.at_time)

        for index, command in enumerate(normalized):
            if horizon is not None and command.at_time > horizon:
                break
            self._advance_to(state, command.at_time, points)
            failure = self._apply_command(state, command, index)
            if failure:
                return SimulationResult(points=points, final_state=state, first_failure=failure, assumptions=self.assumptions)
            points.append(self._point(state, f"{command.kind}:{command.item_name}"))

        if horizon is not None:
            self._advance_to(state, horizon, points)
        return SimulationResult(points=points, final_state=state, first_failure=None, assumptions=self.assumptions)

    def _apply_command(self, state: SimulationState, command: PlanCommand, index: int) -> PlanFailure | None:
        cost = COSTS.get(command.item_name)
        if cost is None:
            return self._failure("UNKNOWN_ITEM", f"unknown item {command.item_name}", command, index)

        missing = missing_prerequisites(command.item_name, state.structures)
        if missing:
            return self._failure(
                "TECH_PREREQUISITE_MISSING",
                f"missing prerequisites: {', '.join(missing)}",
                command,
                index,
            )
        if state.minerals < cost.minerals or state.gas < cost.gas:
            return self._failure("INSUFFICIENT_RESOURCES", "not enough minerals or gas", command, index)
        if command.kind == "train" and state.supply_used + cost.supply > state.supply_cap:
            return self._failure("INSUFFICIENT_SUPPLY", "not enough supply", command, index)

        producer_failure = self._reserve_producer(state, command, cost, index)
        if producer_failure:
            return producer_failure

        state.minerals -= cost.minerals
        state.gas -= cost.gas
        if command.kind == "train":
            state.supply_used += cost.supply
        state.production.append(
            ProductionItem(
                item_name=command.item_name,
                kind=command.kind,
                complete_at=command.at_time + cost.build_time,
                producer_id=command.producer_id,
            )
        )
        return None

    def _reserve_producer(
        self,
        state: SimulationState,
        command: PlanCommand,
        cost: Cost,
        index: int,
    ) -> PlanFailure | None:
        producer_id = command.producer_id
        if producer_id:
            available_at = state.producer_available_at.get(producer_id, state.game_time)
            if available_at > command.at_time:
                return self._failure("PRODUCER_BUSY", f"producer {producer_id} busy until {available_at}", command, index)
            state.producer_available_at[producer_id] = command.at_time + cost.build_time
            for key in list(state.producer_available_at):
                if key.endswith(f":{producer_id}"):
                    state.producer_available_at[key] = command.at_time + cost.build_time
            return None

        available = state.structures.get(cost.producer_type, 0) + state.units.get(cost.producer_type, 0)
        if available <= 0:
            return self._failure("PRODUCER_UNAVAILABLE", f"no available {cost.producer_type}", command, index)
        producer_key = self._find_available_producer_key(state, cost.producer_type, command.at_time)
        if producer_key:
            state.producer_available_at[producer_key] = command.at_time + cost.build_time
            _, tag = producer_key.split(":", 1)
            state.producer_available_at[tag] = command.at_time + cost.build_time
            return None
        tracked_count = self._tracked_producer_count(state, cost.producer_type)
        if tracked_count >= available:
            return self._failure("PRODUCER_BUSY", f"all {cost.producer_type} producers are busy", command, index)
        return None

    def _advance_to(self, state: SimulationState, target_time: float, points: list[ResourcePoint]) -> None:
        if target_time < state.game_time:
            return
        elapsed = target_time - state.game_time
        state.minerals += elapsed * state.mineral_income_rate
        state.gas += elapsed * state.gas_income_rate
        state.game_time = target_time
        completed = [item for item in state.production if item.complete_at <= target_time]
        if completed:
            for item in completed:
                self._complete_item(state, item)
            state.production = [item for item in state.production if item.complete_at > target_time]
            points.append(self._point(state, "completion"))
        elif elapsed > 0:
            points.append(self._point(state, "advance"))

    def _complete_item(self, state: SimulationState, item: ProductionItem) -> None:
        cost = COSTS.get(item.item_name)
        if item.kind == "train":
            state.units[item.item_name] = state.units.get(item.item_name, 0) + 1
        else:
            state.structures[item.item_name] = state.structures.get(item.item_name, 0) + 1
            state.supply_cap += cost.supply_delta if cost else 0

    @staticmethod
    def _normalize_commands(
        commands: list[PlanCommand | dict[str, Any] | TimerCommand],
        *,
        source: str,
    ) -> list[PlanCommand]:
        result: list[PlanCommand] = []
        for command in commands:
            if isinstance(command, PlanCommand):
                result.append(command)
            elif isinstance(command, TimerCommand):
                converted = PlanCommand.from_timer(command, source=source)
                if converted:
                    result.append(converted)
            else:
                result.append(PlanCommand.from_dict(command, source=source))
        return result

    @staticmethod
    def _copy_state(state: SimulationState) -> SimulationState:
        return SimulationState.from_dict(state.to_dict())

    @staticmethod
    def _point(state: SimulationState, label: str) -> ResourcePoint:
        return ResourcePoint(
            time=state.game_time,
            minerals=state.minerals,
            gas=state.gas,
            supply_used=state.supply_used,
            supply_cap=state.supply_cap,
            label=label,
        )

    @staticmethod
    def _failure(code: str, message: str, command: PlanCommand, index: int) -> PlanFailure:
        return PlanFailure(
            code=code,
            message=message,
            command_index=index,
            at_time=command.at_time,
            item_name=command.item_name,
        )

    @staticmethod
    def _find_available_producer_key(state: SimulationState, producer_type: str, at_time: float) -> str | None:
        prefix = f"{producer_type}:"
        candidates = [
            (key, available_at)
            for key, available_at in state.producer_available_at.items()
            if key.startswith(prefix)
        ]
        if not candidates:
            return None
        ready = [(key, available_at) for key, available_at in candidates if available_at <= at_time]
        if not ready:
            return ""
        ready.sort(key=lambda item: item[1])
        return ready[0][0]

    @staticmethod
    def _tracked_producer_count(state: SimulationState, producer_type: str) -> int:
        prefix = f"{producer_type}:"
        return sum(1 for key in state.producer_available_at if key.startswith(prefix))
