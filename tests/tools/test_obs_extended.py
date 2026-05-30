"""Tests for the 5 new obs.* tools (Task 3)."""

from __future__ import annotations

import asyncio

from sc2_agent.observation.collector import StaticObservationProvider
from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot
from sc2_agent.tools.obs import (
    ObsBasesTool,
    ObsEnemyVisibleTool,
    ObsGameTimeTool,
    ObsMapTool,
    ObsUpgradesTool,
)


def _make_provider() -> StaticObservationProvider:
    return StaticObservationProvider(
        ObservationSnapshot(
            game_time=120.0,
            minerals=500,
            gas=200,
            supply_used=30,
            supply_cap=46,
            units=[
                UnitSnapshot(
                    tag=1,
                    type_name="Marine",
                    x=10,
                    y=20,
                    health=45,
                    shield=0,
                    is_idle=False,
                    build_progress=1.0,
                    alliance="self",
                ),
                UnitSnapshot(
                    tag=99,
                    type_name="Zergling",
                    x=50,
                    y=60,
                    health=35,
                    shield=0,
                    is_idle=False,
                    build_progress=1.0,
                    alliance="enemy",
                ),
            ],
            structures=[
                UnitSnapshot(
                    tag=100,
                    type_name="CommandCenter",
                    x=30,
                    y=30,
                    health=1500,
                    shield=0,
                    is_idle=False,
                    build_progress=1.0,
                    alliance="self",
                ),
                UnitSnapshot(
                    tag=101,
                    type_name="SupplyDepot",
                    x=35,
                    y=35,
                    health=400,
                    shield=0,
                    is_idle=True,
                    build_progress=1.0,
                    alliance="self",
                ),
            ],
            map_width=200,
            map_height=180,
            playable_area={"x": 10, "y": 12, "width": 160, "height": 140},
            expansions=[{"id": 0, "x": 30, "y": 30}, {"id": 1, "x": 80, "y": 80}],
            upgrades=["Stimpack"],
        )
    )


class TestObsGameTime:
    def test_returns_game_time(self) -> None:
        tool = ObsGameTimeTool(_make_provider())
        result = asyncio.run(tool.execute())
        assert result == {"game_time": 120.0}


class TestObsMap:
    def test_returns_map_dimensions(self) -> None:
        tool = ObsMapTool(_make_provider(), map_width=256, map_height=256)
        result = asyncio.run(tool.execute())
        assert result == {
            "width": 200,
            "height": 180,
            "playable": {"x": 10, "y": 12, "width": 160, "height": 140},
        }

    def test_custom_dimensions(self) -> None:
        tool = ObsMapTool(_make_provider(), map_width=128, map_height=64)
        result = asyncio.run(tool.execute())
        assert result["width"] == 200
        assert result["height"] == 180


class TestObsBases:
    def test_returns_townhalls(self) -> None:
        tool = ObsBasesTool(_make_provider())
        result = asyncio.run(tool.execute())
        assert len(result["townhalls"]) == 1
        assert result["townhalls"][0]["type_name"] == "CommandCenter"
        assert result["expansions"] == [{"id": 0, "x": 30, "y": 30}, {"id": 1, "x": 80, "y": 80}]

    def test_expansions_are_snapshot_backed(self) -> None:
        tool = ObsBasesTool(_make_provider())
        result = asyncio.run(tool.execute())
        assert isinstance(result["expansions"], list)
        assert len(result["expansions"]) == 2


class TestObsEnemyVisible:
    def test_returns_enemy_units(self) -> None:
        tool = ObsEnemyVisibleTool(_make_provider())
        result = asyncio.run(tool.execute())
        assert len(result) == 1
        assert result[0]["type_name"] == "Zergling"
        assert result[0]["tag"] == 99

    def test_filtered_by_type_no_match(self) -> None:
        tool = ObsEnemyVisibleTool(_make_provider())
        result = asyncio.run(tool.execute(unit_type="Marine"))
        assert len(result) == 0  # no enemy Marine

    def test_filtered_by_type_match(self) -> None:
        tool = ObsEnemyVisibleTool(_make_provider())
        result = asyncio.run(tool.execute(unit_type="Zergling"))
        assert len(result) == 1
        assert result[0]["type_name"] == "Zergling"

    def test_includes_structures(self) -> None:
        """Verify enemy structures are also returned."""
        provider = StaticObservationProvider(
            ObservationSnapshot(
                game_time=60.0,
                minerals=0,
                gas=0,
                supply_used=0,
                supply_cap=0,
                units=[],
                structures=[
                    UnitSnapshot(
                        tag=200,
                        type_name="Hatchery",
                        x=40,
                        y=40,
                        health=2500,
                        shield=0,
                        is_idle=False,
                        build_progress=1.0,
                        alliance="enemy",
                    ),
                ],
            )
        )
        tool = ObsEnemyVisibleTool(provider)
        result = asyncio.run(tool.execute())
        assert len(result) == 1
        assert result[0]["type_name"] == "Hatchery"


class TestObsUpgrades:
    def test_returns_completed_upgrades(self) -> None:
        tool = ObsUpgradesTool(_make_provider())
        result = asyncio.run(tool.execute())
        assert result == {"completed": ["Stimpack"]}
