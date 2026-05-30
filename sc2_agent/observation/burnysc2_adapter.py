"""Thin adapter from burnysc2 objects to normalized observations."""

from __future__ import annotations

from typing import Any

from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot
from sc2_agent.planning.costs import canonical_name


class BurnySC2ObservationAdapter:
    """Read the small BotAI/Unit surface verified in local burnysc2 sources."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            game_time=float(getattr(self.bot, "time", 0.0)),
            minerals=int(getattr(self.bot, "minerals", 0)),
            gas=int(getattr(self.bot, "vespene", 0)),
            supply_used=int(getattr(self.bot, "supply_used", 0)),
            supply_cap=int(getattr(self.bot, "supply_cap", 0)),
            units=[self._unit_snapshot(unit) for unit in getattr(self.bot, "units", [])]
            + self._neutral_units(),
            structures=[self._unit_snapshot(unit) for unit in getattr(self.bot, "structures", [])],
            **self._map_fields(),
            expansions=self._expansions(),
            upgrades=self._upgrades(),
            enemy_start_locations=self._enemy_start_locations(),
            player_race=self._player_race(),
            opponent_race=self._opponent_race(),
            game_loop=self._game_loop(),
            score=self._score(),
            score_details=self._score_details(),
        )

    def _neutral_units(self) -> list[UnitSnapshot]:
        """Read neutral resource units (mineral fields, vespene geysers, destructables)
        and return them as UnitSnapshots with alliance='neutral'.
        """
        result: list[UnitSnapshot] = []
        for attr in ("mineral_field", "vespene_geyser", "destructables"):
            result.extend(
                self._unit_snapshot(unit) for unit in getattr(self.bot, attr, [])
            )
        return result

    def _unit_snapshot(self, unit: Any) -> UnitSnapshot:
        position = getattr(unit, "position", None)
        if position is None and hasattr(unit, "position_tuple"):
            x, y = unit.position_tuple
        else:
            x = getattr(position, "x", 0.0)
            y = getattr(position, "y", 0.0)

        return UnitSnapshot(
            tag=int(getattr(unit, "tag")),
            type_name=canonical_name(self._type_name(getattr(unit, "type_id", ""))),
            x=float(x),
            y=float(y),
            health=float(getattr(unit, "health", 0.0)),
            shield=float(getattr(unit, "shield", 0.0)),
            is_idle=bool(getattr(unit, "is_idle", False)),
            build_progress=float(getattr(unit, "build_progress", 1.0)),
            alliance=self._alliance(unit),
            orders=self._orders(unit),
        )

    @staticmethod
    def _type_name(type_id: Any) -> str:
        return str(getattr(type_id, "name", type_id))

    @staticmethod
    def _alliance(unit: Any) -> str:
        if bool(getattr(unit, "is_mine", False)):
            return "self"
        if bool(getattr(unit, "is_enemy", False)):
            return "enemy"
        return "neutral"

    def _orders(self, unit: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for order in getattr(unit, "orders", []) or []:
            ability = getattr(order, "ability", None)
            ability_id = getattr(ability, "id", ability)
            result.append(
                {
                    "ability": self._type_name(ability_id),
                    "progress": float(getattr(order, "progress", 0.0) or 0.0),
                    "target": self._order_target(getattr(order, "target", None)),
                }
            )
        return result

    @staticmethod
    def _order_target(target: Any) -> int | dict[str, float] | None:
        if target is None or isinstance(target, int):
            return target
        return {"x": float(getattr(target, "x", 0.0)), "y": float(getattr(target, "y", 0.0))}

    def _map_fields(self) -> dict[str, Any]:
        game_info = getattr(self.bot, "game_info", None)
        map_size = getattr(game_info, "map_size", None)
        playable = getattr(game_info, "playable_area", None)
        width = int(getattr(map_size, "x", 0) or 0)
        height = int(getattr(map_size, "y", 0) or 0)
        playable_area = {
            "x": float(getattr(playable, "x", 0.0) or 0.0),
            "y": float(getattr(playable, "y", 0.0) or 0.0),
            "width": float(getattr(playable, "width", width) or width),
            "height": float(getattr(playable, "height", height) or height),
        }
        return {"map_width": width, "map_height": height, "playable_area": playable_area}

    def _expansions(self) -> list[dict[str, float]]:
        result: list[dict[str, float]] = []
        for index, point in enumerate(getattr(self.bot, "expansion_locations_list", []) or []):
            result.append({"id": index, "x": float(getattr(point, "x", 0.0)), "y": float(getattr(point, "y", 0.0))})
        return result

    def _upgrades(self) -> list[str]:
        state = getattr(self.bot, "state", None)
        upgrades = getattr(state, "upgrades", []) or []
        return [self._type_name(upgrade) for upgrade in upgrades]

    def _enemy_start_locations(self) -> list[dict[str, float]]:
        locations = getattr(self.bot, "enemy_start_locations", []) or []
        return [{"x": float(getattr(p, "x", 0.0)), "y": float(getattr(p, "y", 0.0))} for p in locations]

    def _player_race(self) -> str:
        race = getattr(self.bot, "race", None)
        if race is not None:
            return str(race).split(".")[-1]
        return "Terran"

    def _opponent_race(self) -> str:
        enemy_race = getattr(self.bot, "enemy_race", None)
        if enemy_race is not None:
            return str(enemy_race).split(".")[-1]
        return "unknown"

    def _game_loop(self) -> int:
        state = getattr(self.bot, "state", None)
        return int(getattr(state, "game_loop", 0) or 0)

    def _score(self) -> int:
        state = getattr(self.bot, "state", None)
        score_obj = getattr(state, "score", None)
        return int(getattr(score_obj, "score", 0) or 0)

    def _score_details(self) -> dict[str, int]:
        state = getattr(self.bot, "state", None)
        score_obj = getattr(state, "score", None)
        if score_obj is None:
            return {}
        details = {}
        for field in ("score", "idle_production_time", "idle_worker_time", "total_value_units",
                      "total_value_structures", "killed_value_units", "killed_value_structures",
                      "collected_minerals", "collected_vespene"):
            val = getattr(score_obj, field, 0) or 0
            details[field] = int(val)
        return details
