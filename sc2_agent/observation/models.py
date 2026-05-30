"""Serializable observation snapshots decoupled from burnysc2 objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from sc2_agent.planning.costs import canonical_name


Alliance = Literal["self", "enemy", "neutral"]


@dataclass(frozen=True, slots=True)
class UnitSnapshot:
    tag: int
    type_name: str
    x: float
    y: float
    health: float = 0.0
    shield: float = 0.0
    is_idle: bool = False
    build_progress: float = 1.0
    alliance: Alliance = "self"
    orders: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnitSnapshot":
        return cls(
            tag=int(data["tag"]),
            type_name=canonical_name(str(data["type_name"])),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            health=float(data.get("health", 0.0)),
            shield=float(data.get("shield", 0.0)),
            is_idle=bool(data.get("is_idle", False)),
            build_progress=float(data.get("build_progress", 1.0)),
            alliance=data.get("alliance", "self"),
            orders=[dict(item) for item in data.get("orders", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    game_time: float
    minerals: int
    gas: int
    supply_used: int
    supply_cap: int
    units: list[UnitSnapshot] = field(default_factory=list)
    structures: list[UnitSnapshot] = field(default_factory=list)
    map_width: int = 0
    map_height: int = 0
    playable_area: dict[str, float] = field(default_factory=dict)
    expansions: list[dict[str, float]] = field(default_factory=list)
    upgrades: list[str] = field(default_factory=list)
    enemy_start_locations: list[dict[str, float]] = field(default_factory=list)
    player_race: str = "Terran"
    opponent_race: str = "unknown"
    game_loop: int = 0
    score: int = 0
    score_details: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObservationSnapshot":
        return cls(
            game_time=float(data.get("game_time", 0.0)),
            minerals=int(data.get("minerals", 0)),
            gas=int(data.get("gas", 0)),
            supply_used=int(data.get("supply_used", 0)),
            supply_cap=int(data.get("supply_cap", 0)),
            units=[UnitSnapshot.from_dict(item) for item in data.get("units", [])],
            structures=[UnitSnapshot.from_dict(item) for item in data.get("structures", [])],
            map_width=int(data.get("map_width", 0)),
            map_height=int(data.get("map_height", 0)),
            playable_area=dict(data.get("playable_area", {})),
            expansions=[dict(item) for item in data.get("expansions", [])],
            upgrades=[str(item) for item in data.get("upgrades", [])],
            enemy_start_locations=[dict(item) for item in data.get("enemy_start_locations", [])],
            player_race=str(data.get("player_race", "Terran")),
            opponent_race=str(data.get("opponent_race", "unknown")),
            game_loop=int(data.get("game_loop", 0)),
            score=int(data.get("score", 0)),
            score_details=dict(data.get("score_details", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_time": self.game_time,
            "minerals": self.minerals,
            "gas": self.gas,
            "supply_used": self.supply_used,
            "supply_cap": self.supply_cap,
            "units": [unit.to_dict() for unit in self.units],
            "structures": [structure.to_dict() for structure in self.structures],
            "map_width": self.map_width,
            "map_height": self.map_height,
            "playable_area": dict(self.playable_area),
            "expansions": [dict(item) for item in self.expansions],
            "upgrades": list(self.upgrades),
            "enemy_start_locations": [dict(item) for item in self.enemy_start_locations],
            "player_race": self.player_race,
            "opponent_race": self.opponent_race,
            "game_loop": self.game_loop,
            "score": self.score,
            "score_details": dict(self.score_details),
        }
