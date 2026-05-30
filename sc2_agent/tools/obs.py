"""Observation tools."""

from __future__ import annotations

from typing import Any

from sc2_agent.observation.collector import ObservationProvider
from sc2_agent.planning.costs import canonical_name
from sc2_agent.tools.base import Tool


class ObsResourcesTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.resources"

    @property
    def description(self) -> str:
        return "Return current resources and supply."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        # Estimate income from worker counts.
        scv_count = sum(
            1 for u in snapshot.units
            if u.alliance == "self" and u.type_name == "SCV"
        )
        refinery_count = sum(
            1 for s in snapshot.structures
            if s.type_name == "Refinery"
        )
        gas_workers = min(scv_count, refinery_count * 3)
        mineral_workers = scv_count - gas_workers
        return {
            "game_time": snapshot.game_time,
            "minerals": snapshot.minerals,
            "gas": snapshot.gas,
            "supply_used": snapshot.supply_used,
            "supply_cap": snapshot.supply_cap,
            "supply_available": snapshot.supply_cap - snapshot.supply_used,
            "income_min": mineral_workers * 0.75,
            "income_gas": gas_workers * 0.63,
        }


class ObsUnitsTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.units"

    @property
    def description(self) -> str:
        return "Return observed units."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": ["string", "null"]},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        unit_type = kwargs.get("unit_type")
        alliance = kwargs.get("alliance")
        units = self.provider.snapshot().units
        if unit_type:
            units = [unit for unit in units if unit.type_name == canonical_name(unit_type)]
        if alliance:
            units = [unit for unit in units if unit.alliance == alliance]
        return [unit.to_dict() for unit in units]


class ObsStructuresTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.structures"

    @property
    def description(self) -> str:
        return "Return observed structures."

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
        structure_type = kwargs.get("structure_type")
        alliance = kwargs.get("alliance")
        structures = self.provider.snapshot().structures
        if structure_type:
            structures = [item for item in structures if item.type_name == canonical_name(structure_type)]
        if alliance:
            structures = [item for item in structures if item.alliance == alliance]
        return [item.to_dict() for item in structures]


class ObsGameTimeTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.game_time"

    @property
    def description(self) -> str:
        return "Return the current game time in seconds."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        return {"game_time": snapshot.game_time}


class ObsMapTool(Tool):
    def __init__(
        self, provider: ObservationProvider, *, map_width: int = 256, map_height: int = 256
    ) -> None:
        self.provider = provider
        self._width = map_width
        self._height = map_height

    @property
    def name(self) -> str:
        return "obs.map"

    @property
    def description(self) -> str:
        return "Return map dimensions and playable area."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        width = snapshot.map_width or self._width
        height = snapshot.map_height or self._height
        playable = snapshot.playable_area or {"x": 0, "y": 0, "width": width, "height": height}
        return {
            "width": width,
            "height": height,
            "playable": playable,
        }


class ObsBasesTool(Tool):
    TOWNHALL_NAMES = frozenset({"commandcenter", "nexus", "hatchery"})

    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.bases"

    @property
    def description(self) -> str:
        return "Return expansion locations and owned townhalls."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        townhalls = [
            s.to_dict()
            for s in snapshot.structures
            if self._is_townhall(s.type_name)
        ]
        return {"townhalls": townhalls, "expansions": list(snapshot.expansions)}

    @staticmethod
    def _is_townhall(type_name: str) -> bool:
        key = type_name.replace(" ", "").replace("-", "_").lower()
        return any(th in key for th in ObsBasesTool.TOWNHALL_NAMES)


class ObsEnemyVisibleTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.enemy_visible"

    @property
    def description(self) -> str:
        return "Return currently visible enemy units and structures."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": ["string", "null"]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        unit_type = kwargs.get("unit_type")
        snapshot = self.provider.snapshot()
        entities = list(snapshot.units) + list(snapshot.structures)
        entities = [e for e in entities if e.alliance == "enemy"]
        if unit_type:
            canon = canonical_name(unit_type)
            entities = [e for e in entities if e.type_name == canon]
        return [e.to_dict() for e in entities]


class ObsUpgradesTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.upgrades"

    @property
    def description(self) -> str:
        return "Return completed upgrades."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        return {"completed": list(self.provider.snapshot().upgrades)}


class ObsEnemyInferredTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.enemy_inferred"

    @property
    def description(self) -> str:
        return "Return inferred enemy information (start location, possible expansions)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        return {
            "enemy_start_locations": snapshot.enemy_start_locations,
            "enemy_race": snapshot.opponent_race,
        }


class ObsControllerTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.controller"

    @property
    def description(self) -> str:
        return "Return player controller information (race, opponent race, game loop)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        return {
            "player_race": snapshot.player_race,
            "opponent_race": snapshot.opponent_race,
            "game_loop": snapshot.game_loop,
        }


class ObsScoresTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.scores"

    @property
    def description(self) -> str:
        return "Return current score information."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        return {
            "score": snapshot.score,
            "score_details": snapshot.score_details,
        }


class ObsUnitTool(Tool):
    """Return full details of a single unit by its tag."""

    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.unit"

    @property
    def description(self) -> str:
        return "Return the full property set of a single unit identified by its tag."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"tag": {"type": "integer"}},
            "required": ["tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tag = kwargs["tag"]
        for entity in self.provider.snapshot().units:
            if entity.tag == tag:
                return entity.to_dict()
        for entity in self.provider.snapshot().structures:
            if entity.tag == tag:
                return entity.to_dict()
        return {"ok": False, "code": "TAG_NOT_FOUND", "tag": tag}
