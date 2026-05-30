"""Small deterministic cost table used before burnysc2 integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Cost:
    minerals: int
    gas: int = 0
    supply: int = 0
    build_time: float = 0.0
    producer_type: str = ""
    supply_delta: int = 0


ALIASES = {
    "scv": "SCV",
    "worker": "SCV",
    "marine": "Marine",
    "supplydepot": "SupplyDepot",
    "supply_depot": "SupplyDepot",
    "barracks": "Barracks",
    "commandcenter": "CommandCenter",
    "command_center": "CommandCenter",
    "refinery": "Refinery",
    "factory": "Factory",
    "starport": "Starport",
    "engineeringbay": "EngineeringBay",
    "engineering_bay": "EngineeringBay",
    "missileturret": "MissileTurret",
    "missile_turret": "MissileTurret",
    "reaper": "Reaper",
    "marauder": "Marauder",
    "hellion": "Hellion",
    "siegetank": "SiegeTank",
    "siege_tank": "SiegeTank",
    "medivac": "Medivac",
    "techlab": "TechLab",
    "tech_lab": "TechLab",
    "reactor": "Reactor",
}


COSTS: dict[str, Cost] = {
    "SCV": Cost(minerals=50, supply=1, build_time=12, producer_type="CommandCenter"),
    "Marine": Cost(minerals=50, supply=1, build_time=18, producer_type="Barracks"),
    "Reaper": Cost(minerals=50, gas=50, supply=1, build_time=32, producer_type="Barracks"),
    "Marauder": Cost(minerals=100, gas=25, supply=2, build_time=21, producer_type="Barracks"),
    "Hellion": Cost(minerals=100, supply=2, build_time=21, producer_type="Factory"),
    "SiegeTank": Cost(minerals=150, gas=125, supply=3, build_time=32, producer_type="Factory"),
    "Medivac": Cost(minerals=100, gas=100, supply=2, build_time=30, producer_type="Starport"),
    "SupplyDepot": Cost(minerals=100, build_time=21, producer_type="SCV", supply_delta=8),
    "Barracks": Cost(minerals=150, build_time=46, producer_type="SCV"),
    "Refinery": Cost(minerals=75, build_time=21, producer_type="SCV"),
    "Factory": Cost(minerals=150, gas=100, build_time=43, producer_type="SCV"),
    "Starport": Cost(minerals=150, gas=100, build_time=36, producer_type="SCV"),
    "EngineeringBay": Cost(minerals=125, build_time=35, producer_type="SCV"),
    "MissileTurret": Cost(minerals=100, build_time=18, producer_type="SCV"),
    "TechLab": Cost(minerals=50, gas=25, build_time=18, producer_type="Barracks"),
    "Reactor": Cost(minerals=50, gas=50, build_time=36, producer_type="Barracks"),
}


def canonical_name(name: str) -> str:
    key = name.replace(" ", "").replace("-", "_").lower()
    return ALIASES.get(key, name)
