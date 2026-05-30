from __future__ import annotations

import asyncio

from sc2_agent.planning.simulator import SimulationState
from sc2_agent.runtime.commit import CommitController, CommitServices
from sc2_agent.runtime.state import RuntimeStateMachine
from sc2_agent.timer.models import TimerCommand
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.review import ReviewLogicTool, ReviewParamsTool, ReviewPlanTool


def _state(**overrides) -> SimulationState:
    data = {
        "game_time": 0,
        "minerals": 200,
        "gas": 0,
        "supply_used": 12,
        "supply_cap": 15,
        "mineral_income_rate": 0,
        "gas_income_rate": 0,
        "units": {"SCV": 12},
        "structures": {"CommandCenter": 1, "SupplyDepot": 1, "Barracks": 1},
    }
    data.update(overrides)
    return SimulationState.from_dict(data)


def _train_scv(timer_id: str = "cmd1", at_time: float = 0, producer: str = "cc1") -> TimerCommand:
    return TimerCommand(
        id=timer_id,
        at_time=at_time,
        tool_name="build.train",
        arguments={"unit_type": "SCV", "structure_tag": producer},
        created_at=0,
        wake_id=1,
    )


def test_review_params_rejects_missing_tag() -> None:
    result = asyncio.run(
        ReviewParamsTool().execute(tool_name="build.train", arguments={"unit_type": "SCV"})
    )

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "TAG_MISSING"


def test_review_params_rejects_invalid_coordinates() -> None:
    result = asyncio.run(
        ReviewParamsTool().execute(
            tool_name="build.structure",
            arguments={"structure_type": "SupplyDepot", "worker_tag": 1, "target_x": 300, "target_y": 4},
            map_width=200,
            map_height=200,
        )
    )

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "COORDINATE_OUT_OF_BOUNDS"


def test_review_plan_rejects_resource_shortage() -> None:
    staging = TimerStaging(commands=[_train_scv()])
    tool = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state(minerals=0))

    result = asyncio.run(tool.execute(staging_hash=staging.hash()))

    assert not result.ok
    assert result.code == "PLAN_REVIEW_FAILED"
    assert result.meta["failure"]["code"] == "INSUFFICIENT_RESOURCES"
    assert staging.review_hash is None


def test_review_plan_rejects_supply_shortage() -> None:
    staging = TimerStaging(commands=[_train_scv()])
    tool = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state(supply_used=15, supply_cap=15))

    result = asyncio.run(tool.execute(staging_hash=staging.hash()))

    assert not result.ok
    assert result.meta["failure"]["code"] == "INSUFFICIENT_SUPPLY"


def test_review_plan_rejects_missing_tech() -> None:
    marine = TimerCommand(
        id="cmd1",
        at_time=0,
        tool_name="build.train",
        arguments={"unit_type": "Marine", "structure_tag": "rax1"},
        created_at=0,
        wake_id=1,
    )
    staging = TimerStaging(commands=[marine])
    tool = ReviewPlanTool(
        staging=staging,
        initial_state_provider=lambda: _state(structures={"CommandCenter": 1, "SupplyDepot": 1}),
    )

    result = asyncio.run(tool.execute(staging_hash=staging.hash()))

    assert not result.ok
    assert result.meta["failure"]["code"] == "TECH_PREREQUISITE_MISSING"


def test_review_plan_rejects_production_conflict() -> None:
    staging = TimerStaging(commands=[_train_scv("cmd1", 0, "cc1"), _train_scv("cmd2", 1, "cc1")])
    tool = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state(minerals=500))

    result = asyncio.run(tool.execute(staging_hash=staging.hash()))

    assert not result.ok
    assert result.meta["failure"]["code"] == "PRODUCER_BUSY"


def test_review_plan_marks_matching_hash_as_reviewed() -> None:
    staging = TimerStaging(commands=[_train_scv()])
    staging_hash = staging.hash()
    tool = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state())

    result = asyncio.run(tool.execute(staging_hash=staging_hash))

    assert result.ok
    assert staging.review_hash == staging_hash
    assert result.data["logic_review"]["verdict"] == "PASS"


def test_review_logic_warns_on_empty_staging() -> None:
    staging = TimerStaging()

    result = asyncio.run(ReviewLogicTool(staging).execute(staging_hash=staging.hash()))

    assert result["verdict"] == "WARN"
    assert result["issues"][0]["code"] == "NO_COMMANDS"


def test_review_logic_rejects_hash_mismatch() -> None:
    staging = TimerStaging(commands=[_train_scv()])

    result = asyncio.run(ReviewLogicTool(staging).execute(staging_hash="sha256:wrong"))

    assert not result.ok
    assert result.code == "STAGING_HASH_MISMATCH"


def test_commit_rejects_when_staging_changes_after_review() -> None:
    staging = TimerStaging(commands=[_train_scv()])
    reviewed_hash = staging.hash()
    review = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state())
    asyncio.run(review.execute(staging_hash=reviewed_hash))
    staging.add_command(_train_scv("cmd2", 20, "cc1"))
    controller = _commit_controller(staging)

    result = asyncio.run(controller.commit(reviewed_hash))

    assert not result.ok
    assert result.code == "STAGING_HASH_MISMATCH"


def test_commit_accepts_same_reviewed_hash() -> None:
    staging = TimerStaging(commands=[_train_scv()])
    staging_hash = staging.hash()
    review = ReviewPlanTool(staging=staging, initial_state_provider=lambda: _state())
    asyncio.run(review.execute(staging_hash=staging_hash))
    controller = _commit_controller(staging)

    result = asyncio.run(controller.commit(staging_hash))

    assert result.ok


def _commit_controller(staging: TimerStaging) -> CommitController:
    services = CommitServices(
        save_snapshot_and_events=lambda: None,
        append_session=lambda: None,
        update_game_state=lambda: None,
        consolidate_memory=lambda: None,
        render_game_state_markdown=lambda: None,
    )
    return CommitController(
        runtime=RuntimeStateMachine(),
        staging=staging,
        timer_store=TimerStore(),
        services=services,
    )
