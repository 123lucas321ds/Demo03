from __future__ import annotations

import asyncio

from sc2_agent.planning.simulator import PlanCommand, PlanSimulator, SimulationState
from sc2_agent.timer.models import TimerCommand
from sc2_agent.tools.plan import PlanBuildOrderTool, PlanBuildTimeTool, PlanSimulateTool


def _state(**overrides) -> SimulationState:
    data = {
        "game_time": 0,
        "minerals": 50,
        "gas": 0,
        "supply_used": 12,
        "supply_cap": 15,
        "mineral_income_rate": 1.0,
        "gas_income_rate": 0.0,
        "units": {"SCV": 12},
        "structures": {"CommandCenter": 1},
    }
    data.update(overrides)
    return SimulationState.from_dict(data)


def test_empty_plan_simulates_resource_growth() -> None:
    result = PlanSimulator().simulate(initial_state=_state(), commands=[], horizon=10)

    assert result.first_failure is None
    assert result.final_state.minerals == 60
    assert result.points[-1].time == 10


def test_train_command_deducts_resources_and_supply() -> None:
    command = PlanCommand(at_time=0, kind="train", item_name="SCV", producer_id="cc1")

    result = PlanSimulator().simulate(initial_state=_state(minerals=75), commands=[command], horizon=0)

    assert result.first_failure is None
    assert result.final_state.minerals == 25
    assert result.final_state.supply_used == 13


def test_resource_shortage_returns_first_failure() -> None:
    command = PlanCommand(at_time=0, kind="build", item_name="SupplyDepot", producer_id="scv1")

    result = PlanSimulator().simulate(initial_state=_state(minerals=50), commands=[command], horizon=0)

    assert result.first_failure is not None
    assert result.first_failure.code == "INSUFFICIENT_RESOURCES"
    assert result.first_failure.item_name == "SupplyDepot"


def test_supply_shortage_returns_first_failure() -> None:
    command = PlanCommand(at_time=0, kind="train", item_name="SCV", producer_id="cc1")

    result = PlanSimulator().simulate(initial_state=_state(supply_used=15, supply_cap=15), commands=[command], horizon=0)

    assert result.first_failure is not None
    assert result.first_failure.code == "INSUFFICIENT_SUPPLY"


def test_same_producer_time_conflict_returns_failure() -> None:
    commands = [
        PlanCommand(at_time=0, kind="train", item_name="SCV", producer_id="cc1"),
        PlanCommand(at_time=1, kind="train", item_name="SCV", producer_id="cc1"),
    ]

    result = PlanSimulator().simulate(initial_state=_state(minerals=200), commands=commands, horizon=1)

    assert result.first_failure is not None
    assert result.first_failure.code == "PRODUCER_BUSY"


def test_tech_prerequisite_missing_returns_failure() -> None:
    command = PlanCommand(at_time=0, kind="train", item_name="Marine", producer_id="rax1")

    result = PlanSimulator().simulate(initial_state=_state(minerals=200), commands=[command], horizon=0)

    assert result.first_failure is not None
    assert result.first_failure.code == "TECH_PREREQUISITE_MISSING"


def test_structure_completion_can_satisfy_later_prerequisite_and_supply() -> None:
    commands = [
        PlanCommand(at_time=0, kind="build", item_name="SupplyDepot", producer_id="scv1"),
        PlanCommand(at_time=22, kind="build", item_name="Barracks", producer_id="scv1"),
    ]

    result = PlanSimulator().simulate(initial_state=_state(minerals=300, supply_used=15, supply_cap=15), commands=commands, horizon=22)

    assert result.first_failure is None
    assert result.final_state.structures["SupplyDepot"] == 1
    assert result.final_state.supply_cap == 23
    assert result.final_state.minerals == 72


def test_active_timer_commands_are_included_in_simulation() -> None:
    active = TimerCommand(
        id="timer1",
        at_time=0,
        tool_name="build.train",
        arguments={"unit_type": "SCV", "structure_tag": "cc1"},
        created_at=0,
        wake_id=1,
    )
    staged = [PlanCommand(at_time=1, kind="train", item_name="SCV", producer_id="cc1")]

    result = PlanSimulator().simulate(initial_state=_state(minerals=200), commands=staged, active_timers=[active], horizon=1)

    assert result.first_failure is not None
    assert result.first_failure.code == "PRODUCER_BUSY"


def test_plan_simulate_tool_returns_dict_result() -> None:
    tool = PlanSimulateTool()

    result = asyncio.run(
        tool.execute(
            initial_state=_state(minerals=75).to_dict(),
            commands=[{"at_time": 0, "kind": "train", "unit_type": "SCV", "producer_id": "cc1"}],
            horizon=0,
        )
    )

    assert result["first_failure"] is None
    assert result["final_state"]["minerals"] == 25
    assert result["final_state"]["supply_used"] == 13


def test_plan_build_time_tool_returns_cost_duration_and_requirements() -> None:
    result = asyncio.run(PlanBuildTimeTool().execute(unit_or_building_type="Marine"))

    assert result["item_name"] == "Marine"
    assert result["duration"] == 18
    assert result["cost"] == {"minerals": 50, "gas": 0, "supply": 1}
    assert result["producer_type"] == "Barracks"
    assert result["requires"] == ["Barracks"]


def test_extended_terran_cost_and_tech_table_is_available() -> None:
    result = asyncio.run(PlanBuildTimeTool().execute(unit_or_building_type="SiegeTank"))

    assert result["item_name"] == "SiegeTank"
    assert result["duration"] == 32
    assert result["cost"] == {"minerals": 150, "gas": 125, "supply": 3}
    assert result["producer_type"] == "Factory"
    assert result["requires"] == ["Factory"]


def test_extended_tech_prerequisites_are_enforced() -> None:
    command = PlanCommand(at_time=0, kind="train", item_name="Medivac", producer_id="starport1")

    result = PlanSimulator().simulate(
        initial_state=_state(
            minerals=300,
            gas=300,
            supply_used=12,
            supply_cap=23,
            structures={"CommandCenter": 1, "Barracks": 1, "Factory": 1},
        ),
        commands=[command],
        horizon=0,
    )

    assert result.first_failure is not None
    assert result.first_failure.code == "TECH_PREREQUISITE_MISSING"
    assert "Medivac" == result.first_failure.item_name


def test_generic_commands_reserve_tracked_available_producer() -> None:
    commands = [
        PlanCommand(at_time=0, kind="train", item_name="Marine"),
        PlanCommand(at_time=1, kind="train", item_name="Marine"),
    ]

    result = PlanSimulator().simulate(
        initial_state=_state(
            minerals=300,
            supply_used=12,
            supply_cap=23,
            structures={"CommandCenter": 1, "Barracks": 1},
            producer_available_at={"Barracks:rax1": 0, "rax1": 0},
        ),
        commands=commands,
        horizon=1,
    )

    assert result.first_failure is not None
    assert result.first_failure.code == "PRODUCER_BUSY"


def test_plan_build_time_tool_reports_unknown_item() -> None:
    result = asyncio.run(PlanBuildTimeTool().execute(unit_or_building_type="Battlecruiser"))

    assert result["ok"] is False
    assert result["code"] == "UNKNOWN_ITEM"


def test_plan_build_order_tool_lists_and_returns_templates() -> None:
    listed = asyncio.run(PlanBuildOrderTool().execute())
    detail = asyncio.run(PlanBuildOrderTool().execute(name="terran_reaper_expand"))

    assert {"name": "terran_reaper_expand", "race": "Terran", "purpose": "early Reaper scout into expansion"} in listed["templates"]
    assert detail["name"] == "terran_reaper_expand"
    assert detail["targets"][0]["item_name"] == "SCV"
    assert any(target["item_name"] == "Reaper" for target in detail["targets"])
    assert "plan.simulate" in detail["notes"][1]


def test_plan_build_order_tool_reports_unknown_template() -> None:
    result = asyncio.run(PlanBuildOrderTool().execute(name="unknown"))

    assert result["ok"] is False
    assert result["code"] == "UNKNOWN_BUILD_ORDER"
    assert "terran_1rax_expand" in result["available"]
