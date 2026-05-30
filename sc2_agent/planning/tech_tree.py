"""Minimal tech prerequisites for deterministic planning."""

from __future__ import annotations

from sc2_agent.planning.costs import canonical_name


PREREQUISITES: dict[str, tuple[str, ...]] = {
    "Marine": ("Barracks",),
    "Reaper": ("Barracks",),
    "Marauder": ("Barracks",),
    "Barracks": ("SupplyDepot",),
    "Factory": ("Barracks",),
    "Starport": ("Factory",),
    "Hellion": ("Factory",),
    "SiegeTank": ("Factory",),
    "Medivac": ("Starport",),
    "MissileTurret": ("EngineeringBay",),
    "TechLab": ("Barracks",),
    "Reactor": ("Barracks",),
}


def missing_prerequisites(item_name: str, completed_structures: dict[str, int]) -> list[str]:
    item = canonical_name(item_name)
    missing: list[str] = []
    for prerequisite in PREREQUISITES.get(item, ()):
        if completed_structures.get(prerequisite, 0) <= 0:
            missing.append(prerequisite)
    return missing
