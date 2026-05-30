"""Planning tools."""

from __future__ import annotations

from typing import Any, Callable

from sc2_agent.planning.costs import COSTS, canonical_name
from sc2_agent.planning.tech_tree import PREREQUISITES
from sc2_agent.planning.simulator import PlanSimulator, SimulationState
from sc2_agent.tools.base import Tool


BUILD_ORDER_TEMPLATES: dict[str, dict[str, Any]] = {
    "terran_1rax_expand": {
        "name": "terran_1rax_expand",
        "race": "Terran",
        "purpose": "standard economic opener with one Barracks before expansion",
        "targets": [
            {"step": 1, "item_name": "SCV", "target_count": 14, "reason": "keep worker production continuous"},
            {"step": 2, "item_name": "SupplyDepot", "target_count": 1, "reason": "avoid first supply block"},
            {"step": 3, "item_name": "Barracks", "target_count": 1, "reason": "unlock early Marine/Reaper production"},
            {"step": 4, "item_name": "Refinery", "target_count": 1, "reason": "support early tech options"},
            {"step": 5, "item_name": "CommandCenter", "target_count": 2, "reason": "expand economy"},
            {"step": 6, "item_name": "Marine", "target_count": 2, "reason": "basic defense while expanding"},
        ],
        "notes": [
            "Template is a target list, not a timed schedule.",
            "Agent must call plan.build_time and plan.simulate to produce exact at_time commands.",
        ],
    },
    "terran_reaper_expand": {
        "name": "terran_reaper_expand",
        "race": "Terran",
        "purpose": "early Reaper scout into expansion",
        "targets": [
            {"step": 1, "item_name": "SCV", "target_count": 14, "reason": "keep worker production continuous"},
            {"step": 2, "item_name": "SupplyDepot", "target_count": 1, "reason": "avoid first supply block"},
            {"step": 3, "item_name": "Barracks", "target_count": 1, "reason": "unlock Reaper"},
            {"step": 4, "item_name": "Refinery", "target_count": 1, "reason": "fund Reaper gas cost"},
            {"step": 5, "item_name": "Reaper", "target_count": 1, "reason": "scout and deny early information"},
            {"step": 6, "item_name": "CommandCenter", "target_count": 2, "reason": "transition into economy"},
        ],
        "notes": [
            "Template is a target list, not a timed schedule.",
            "Agent must verify resources, supply, producer availability, and active timers with plan.simulate.",
        ],
    },
}


class PlanSimulateTool(Tool):
    read_only = True

    def __init__(self, simulator: PlanSimulator | None = None) -> None:
        self.simulator = simulator or PlanSimulator()

    @property
    def name(self) -> str:
        return "plan.simulate"

    @property
    def description(self) -> str:
        return "Deterministically simulate resources, supply, prerequisites, and producer occupancy."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "initial_state": {"type": "object"},
                "commands": {"type": "array", "items": {"type": "object"}},
                "active_timers": {"type": "array", "items": {"type": "object"}},
                "horizon": {"type": ["number", "null"]},
            },
            "required": ["initial_state", "commands"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        result = self.simulator.simulate(
            initial_state=SimulationState.from_dict(kwargs["initial_state"]),
            commands=kwargs["commands"],
            active_timers=kwargs.get("active_timers") or [],
            horizon=kwargs.get("horizon"),
        )
        return result.to_dict()


class PlanBuildTimeTool(Tool):
    read_only = True

    @property
    def name(self) -> str:
        return "plan.build_time"

    @property
    def description(self) -> str:
        return "Return deterministic cost, duration, supply, and prerequisites for a unit or structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"unit_or_building_type": {"type": "string", "minLength": 1}},
            "required": ["unit_or_building_type"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        item_name = canonical_name(kwargs["unit_or_building_type"])
        cost = COSTS.get(item_name)
        if cost is None:
            return {"ok": False, "code": "UNKNOWN_ITEM", "item_name": item_name}
        return {
            "item_name": item_name,
            "duration": cost.build_time,
            "cost": {"minerals": cost.minerals, "gas": cost.gas, "supply": cost.supply},
            "producer_type": cost.producer_type,
            "supply_delta": cost.supply_delta,
            "requires": list(PREREQUISITES.get(item_name, ())),
        }


class PlanBuildOrderTool(Tool):
    read_only = True

    @property
    def name(self) -> str:
        return "plan.build_order"

    @property
    def description(self) -> str:
        return "Return standard opener target lists; use plan.build_time and plan.simulate to schedule them."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Optional template name. Omit to list available templates.",
                }
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs.get("name")
        if not name:
            return {
                "templates": [
                    {
                        "name": template["name"],
                        "race": template["race"],
                        "purpose": template["purpose"],
                    }
                    for template in BUILD_ORDER_TEMPLATES.values()
                ]
            }
        template = BUILD_ORDER_TEMPLATES.get(str(name))
        if template is None:
            return {
                "ok": False,
                "code": "UNKNOWN_BUILD_ORDER",
                "available": sorted(BUILD_ORDER_TEMPLATES),
            }
        return template


class PlanInitialStateTool(Tool):
    """Return the complete SimulationState for the current game frame."""

    read_only = True

    def __init__(self, state_provider: Callable[[], dict[str, Any]]) -> None:
        self._state_provider = state_provider

    @property
    def name(self) -> str:
        return "plan.initial_state"

    @property
    def description(self) -> str:
        return (
            "Return a complete initial state for plan.simulate, including "
            "mineral_income_rate and gas_income_rate computed from current "
            "worker count. Always call this before plan.simulate — do not "
            "manually construct the initial_state dictionary."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        state = self._state_provider()
        if hasattr(state, "to_dict"):
            return state.to_dict()
        return state

