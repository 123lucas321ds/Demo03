"""Enemy tracker — inferred enemy information beyond direct observation."""

from __future__ import annotations

from typing import Any


class EnemyTracker:
    """Track inferred enemy state — start location, expansion times, unit count estimates."""

    def __init__(self, enemy_race: str = "unknown") -> None:
        self._enemy_race = enemy_race
        self._enemy_start_location: tuple[float, float] | None = None
        self._visible_units: dict[int, dict[str, Any]] = {}
        self._last_seen: dict[str, float] = {}

    def set_enemy_race(self, race: str) -> None:
        self._enemy_race = race

    def set_start_location(self, x: float, y: float) -> None:
        self._enemy_start_location = (x, y)

    def update_visible(self, game_time: float, enemy_units: list[dict[str, Any]]) -> None:
        for unit in enemy_units:
            tag = unit.get("tag")
            if tag is not None:
                self._visible_units[tag] = unit
                self._last_seen[unit.get("type_name", "unknown")] = game_time

    @property
    def enemy_race(self) -> str:
        return self._enemy_race

    @property
    def enemy_start_location(self) -> tuple[float, float] | None:
        return self._enemy_start_location

    @property
    def visible_count(self) -> int:
        return len(self._visible_units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enemy_race": self._enemy_race,
            "enemy_start_location": list(self._enemy_start_location) if self._enemy_start_location else None,
            "visible_units": len(self._visible_units),
            "last_seen_types": dict(self._last_seen),
        }
