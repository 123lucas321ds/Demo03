from __future__ import annotations

import asyncio

from sc2_agent.observation.collector import StaticObservationProvider
from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot
from sc2_agent.tools.obs import ObsResourcesTool, ObsStructuresTool, ObsUnitsTool
from sc2_agent.tools.query import (
    QueryCanAffordTool,
    QueryExpansionsTool,
    QueryFindEnemyTool,
    QueryFindStructuresTool,
    QueryFindUnitsTool,
    QueryIdleProducersTool,
    QueryInRegionTool,
    QueryTechRequirementTool,
)


def _provider(*, minerals: int = 150) -> StaticObservationProvider:
    snapshot = ObservationSnapshot(
        game_time=42,
        minerals=minerals,
        gas=0,
        supply_used=13,
        supply_cap=23,
        units=[
            UnitSnapshot(tag=1, type_name="SCV", x=0, y=0, health=45, is_idle=True),
            UnitSnapshot(tag=2, type_name="SCV", x=20, y=20, health=45, is_idle=False),
            UnitSnapshot(tag=3, type_name="Marine", x=8, y=8, health=45, alliance="enemy"),
        ],
        structures=[
            UnitSnapshot(tag=101, type_name="CommandCenter", x=1, y=1, health=1500, is_idle=True),
            UnitSnapshot(tag=102, type_name="Barracks", x=5, y=5, health=1000, is_idle=False),
        ],
        expansions=[{"id": 0, "x": 1, "y": 1}, {"id": 1, "x": 80, "y": 80}],
    )
    return StaticObservationProvider(snapshot)


def test_obs_resources_returns_resource_summary() -> None:
    result = asyncio.run(ObsResourcesTool(_provider()).execute())

    assert result == {
        "game_time": 42,
        "minerals": 150,
        "gas": 0,
        "supply_used": 13,
        "supply_cap": 23,
        "supply_available": 10,
        "income_min": 1.5,
        "income_gas": 0.0,
    }


def test_obs_units_filters_by_type_and_alliance() -> None:
    result = asyncio.run(ObsUnitsTool(_provider()).execute(unit_type="Marine", alliance="enemy"))

    assert len(result) == 1
    assert result[0]["tag"] == 3


def test_obs_structures_filters_by_type() -> None:
    result = asyncio.run(ObsStructuresTool(_provider()).execute(structure_type="Barracks"))

    assert len(result) == 1
    assert result[0]["tag"] == 102


def test_query_find_units_supports_radius_filter() -> None:
    result = asyncio.run(QueryFindUnitsTool(_provider()).execute(alliance="self", center_x=0, center_y=0, radius=2))

    assert {item["tag"] for item in result} == {1, 101}


def test_query_idle_producers_returns_idle_producer_entities() -> None:
    result = asyncio.run(QueryIdleProducersTool(_provider()).execute())

    assert {item["type_name"] for item in result} == {"SCV", "CommandCenter"}


def test_query_can_afford_reports_affordability() -> None:
    ok = asyncio.run(QueryCanAffordTool(_provider(minerals=150)).execute(item_name="Barracks"))
    no = asyncio.run(QueryCanAffordTool(_provider(minerals=100)).execute(item_name="Barracks"))

    assert ok["ok"] is True
    assert no["ok"] is False
    assert no["minerals_required"] == 150


def test_query_tech_requirement_reports_missing_and_satisfied_prerequisites() -> None:
    provider = _provider()

    marine = asyncio.run(QueryTechRequirementTool(provider).execute(item_name="Marine"))
    barracks = asyncio.run(QueryTechRequirementTool(provider).execute(item_name="Barracks"))

    assert marine == {"item_name": "Marine", "missing": [], "ok": True}
    assert barracks == {"item_name": "Barracks", "missing": ["SupplyDepot"], "ok": False}


def test_query_find_enemy() -> None:
    provider = _provider()
    tool = QueryFindEnemyTool(provider)
    result = asyncio.run(tool.execute())
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["tag"] == 3


def test_query_find_structures() -> None:
    provider = _provider()
    tool = QueryFindStructuresTool(provider)
    result = asyncio.run(tool.execute(structure_type="Barracks"))
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["tag"] == 102


def test_query_in_region() -> None:
    provider = _provider()
    tool = QueryInRegionTool(provider)
    result = asyncio.run(tool.execute(x1=0, y1=0, x2=100, y2=100))
    assert isinstance(result, list)
    assert len(result) == 5  # all entities in the default snapshot


def test_query_expansions() -> None:
    provider = _provider()
    tool = QueryExpansionsTool(provider)
    result = asyncio.run(tool.execute())
    assert "owned" in result
    assert "available" in result
    assert len(result["owned"]) == 1
    assert result["owned"][0]["tag"] == 101
    assert result["available"] == [{"id": 1, "x": 80, "y": 80}]
