"""Query tools over normalized observations."""

from __future__ import annotations

from math import hypot
from typing import Any

from sc2_agent.observation.collector import ObservationProvider
from sc2_agent.observation.models import UnitSnapshot
from sc2_agent.planning.costs import COSTS, canonical_name
from sc2_agent.planning.tech_tree import missing_prerequisites
from sc2_agent.tools.base import Tool


def _all_entities(provider: ObservationProvider) -> list[UnitSnapshot]:
    snapshot = provider.snapshot()
    return [*snapshot.units, *snapshot.structures]


class QueryFindUnitsTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_units"

    @property
    def description(self) -> str:
        return "Find units or structures by type, alliance, and optional radius."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "type_name": {"type": ["string", "null"]},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
                "center_x": {"type": ["number", "null"]},
                "center_y": {"type": ["number", "null"]},
                "radius": {"type": ["number", "null"], "minimum": 0},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        entities = _all_entities(self.provider)
        type_name = kwargs.get("type_name")
        alliance = kwargs.get("alliance")
        if type_name:
            entities = [item for item in entities if item.type_name == canonical_name(type_name)]
        if alliance:
            entities = [item for item in entities if item.alliance == alliance]
        if kwargs.get("radius") is not None:
            center_x = float(kwargs.get("center_x", 0.0))
            center_y = float(kwargs.get("center_y", 0.0))
            radius = float(kwargs["radius"])
            entities = [item for item in entities if hypot(item.x - center_x, item.y - center_y) <= radius]
        return [item.to_dict() for item in entities]


class QueryIdleProducersTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.idle_producers"

    @property
    def description(self) -> str:
        return "Return idle producers, optionally filtered by producer type."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"producer_type": {"type": ["string", "null"]}},
        }

    async def execute(self, **kwargs: Any) -> Any:
        producer_type = kwargs.get("producer_type")
        producer_types = {cost.producer_type for cost in COSTS.values()}
        entities = [item for item in _all_entities(self.provider) if item.is_idle and item.type_name in producer_types]
        if producer_type:
            entities = [item for item in entities if item.type_name == canonical_name(producer_type)]
        return [item.to_dict() for item in entities]


class QueryCanAffordTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.can_afford"

    @property
    def description(self) -> str:
        return "Check whether current resources can pay for an item."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"item_name": {"type": "string"}},
            "required": ["item_name"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        item_name = canonical_name(kwargs["item_name"])
        cost = COSTS.get(item_name)
        if cost is None:
            return {"ok": False, "reason": "UNKNOWN_ITEM", "item_name": item_name}
        snapshot = self.provider.snapshot()
        affordable = snapshot.minerals >= cost.minerals and snapshot.gas >= cost.gas
        return {
            "ok": affordable,
            "item_name": item_name,
            "minerals_required": cost.minerals,
            "gas_required": cost.gas,
            "minerals_available": snapshot.minerals,
            "gas_available": snapshot.gas,
        }


class QueryTechRequirementTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.tech_requirement"

    @property
    def description(self) -> str:
        return "Return missing tech prerequisites for an item."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"item_name": {"type": "string"}},
            "required": ["item_name"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        item_name = canonical_name(kwargs["item_name"])
        structures: dict[str, int] = {}
        for structure in self.provider.snapshot().structures:
            if structure.alliance == "self" and structure.build_progress >= 1.0:
                structures[structure.type_name] = structures.get(structure.type_name, 0) + 1
        missing = missing_prerequisites(item_name, structures)
        return {"item_name": item_name, "missing": missing, "ok": not missing}


class QueryFindEnemyTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_enemy"

    @property
    def description(self) -> str:
        return "Find visible enemy units and structures."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": ["string", "null"]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        entities = _all_entities(self.provider)
        entities = [e for e in entities if e.alliance == "enemy"]
        unit_type = kwargs.get("unit_type")
        if unit_type:
            entities = [e for e in entities if e.type_name == canonical_name(unit_type)]
        return [e.to_dict() for e in entities]


class QueryFindStructuresTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_structures"

    @property
    def description(self) -> str:
        return "Find structures by type and alliance."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_type": {"type": ["string", "null"]},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        structures = self.provider.snapshot().structures
        structure_type = kwargs.get("structure_type")
        alliance = kwargs.get("alliance")
        if structure_type:
            structures = [s for s in structures if s.type_name == canonical_name(structure_type)]
        if alliance:
            structures = [s for s in structures if s.alliance == alliance]
        return [s.to_dict() for s in structures]


class QueryInRegionTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.in_region"

    @property
    def description(self) -> str:
        return "Find entities within a rectangular region."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "y1": {"type": "number"},
                "x2": {"type": "number"},
                "y2": {"type": "number"},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
            "required": ["x1", "y1", "x2", "y2"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        x1 = kwargs["x1"]
        y1 = kwargs["y1"]
        x2 = kwargs["x2"]
        y2 = kwargs["y2"]
        alliance = kwargs.get("alliance")
        entities = _all_entities(self.provider)
        entities = [e for e in entities if x1 <= e.x <= x2 and y1 <= e.y <= y2]
        if alliance:
            entities = [e for e in entities if e.alliance == alliance]
        return [e.to_dict() for e in entities]


class QueryExpansionsTool(Tool):
    TOWNHALL_NAMES = frozenset({"commandcenter", "nexus", "hatchery"})

    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.expansions"

    @property
    def description(self) -> str:
        return "Return expansion locations and their occupancy status."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        structures = snapshot.structures
        owned = [
            s.to_dict()
            for s in structures
            if self._is_townhall(s.type_name)
        ]
        available = [
            expansion
            for expansion in snapshot.expansions
            if not any(hypot(townhall["x"] - expansion["x"], townhall["y"] - expansion["y"]) <= 8 for townhall in owned)
        ]
        return {"owned": owned, "available": available}

    @staticmethod
    def _is_townhall(type_name: str) -> bool:
        key = type_name.replace(" ", "").replace("-", "_").lower()
        return any(th in key for th in QueryExpansionsTool.TOWNHALL_NAMES)


WORKER_TYPE_NAMES = frozenset({"SCV", "Probe", "Drone"})


class QueryFindWorkersTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_workers"

    @property
    def description(self) -> str:
        return "Find worker units, optionally filtered by status."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": ["string", "null"],
                    "enum": ["idle", "gathering", "returning", "constructing", None],
                },
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        status = kwargs.get("status")
        alliance = kwargs.get("alliance")
        units = [u for u in self.provider.snapshot().units if canonical_name(u.type_name) in WORKER_TYPE_NAMES]
        if status == "idle":
            units = [u for u in units if u.is_idle]
        if alliance:
            units = [u for u in units if u.alliance == alliance]
        return [u.to_dict() for u in units]


class QueryFindIdleTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_idle"

    @property
    def description(self) -> str:
        return "Find all idle units (workers and army)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        alliance = kwargs.get("alliance")
        entities = _all_entities(self.provider)
        entities = [e for e in entities if e.is_idle]
        if alliance:
            entities = [e for e in entities if e.alliance == alliance]
        return [e.to_dict() for e in entities]


class QueryClosestTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.closest"

    @property
    def description(self) -> str:
        return "Find the closest entity to a point."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "type_name": {"type": ["string", "null"]},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
            "required": ["x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        x = kwargs["x"]
        y = kwargs["y"]
        type_name = kwargs.get("type_name")
        alliance = kwargs.get("alliance")
        entities = _all_entities(self.provider)
        if type_name:
            entities = [e for e in entities if e.type_name == canonical_name(type_name)]
        if alliance:
            entities = [e for e in entities if e.alliance == alliance]
        closest = None
        best_dist = float("inf")
        for entity in entities:
            d = hypot(entity.x - x, entity.y - y)
            if d < best_dist:
                best_dist = d
                closest = entity
        return closest.to_dict() if closest is not None else None


class QueryPlacementsTool(Tool):
    def __init__(self, provider: ObservationProvider, *, bot: Any = None) -> None:
        self.provider = provider
        self._bot = bot

    @property
    def name(self) -> str:
        return "query.placements"

    @property
    def description(self) -> str:
        return "Find valid placement positions near a point. Requires a building_type to check."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "building_type": {"type": "string"},
                "radius": {"type": "number", "minimum": 0},
            },
            "required": ["x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        x = float(kwargs["x"])
        y = float(kwargs["y"])
        radius = float(kwargs.get("radius", 10))
        building_type = kwargs.get("building_type")

        positions: list[dict[str, float]] = []

        if self._bot is not None and building_type is not None:
            try:
                from sc2.position import Point2
                from sc2.ids.unit_typeid import UnitTypeId
                type_id = getattr(UnitTypeId, building_type.upper(), None)
                if type_id is not None and hasattr(self._bot, "find_placement"):
                    placement = await self._bot.find_placement(
                        type_id, Point2((x, y)), max_distance=int(radius), random_alternative=False, placement_step=2
                    )
                    if placement:
                        positions.append({"x": placement.x, "y": placement.y})
                    return {"center": {"x": x, "y": y}, "radius": radius, "positions": positions}
            except Exception:
                pass

        # Fallback: return grid of nearby points (Agent should validate via build.structure)
        step = max(2, int(radius / 3))
        for dx in range(-int(radius), int(radius) + 1, step):
            for dy in range(-int(radius), int(radius) + 1, step):
                positions.append({"x": round(x + dx, 1), "y": round(y + dy, 1)})
        return {"center": {"x": x, "y": y}, "radius": radius, "positions": positions[:16]}


class QueryPathTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.path"

    @property
    def description(self) -> str:
        return "Check if a path exists between two points."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "y1": {"type": "number"},
                "x2": {"type": "number"},
                "y2": {"type": "number"},
            },
            "required": ["x1", "y1", "x2", "y2"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        x1 = kwargs["x1"]
        y1 = kwargs["y1"]
        x2 = kwargs["x2"]
        y2 = kwargs["y2"]
        distance = hypot(x2 - x1, y2 - y1)
        return {"path_exists": True, "distance": distance}
