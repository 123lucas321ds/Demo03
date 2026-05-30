from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sc2_agent.agent.runner import AgentRunner, AgentRunSpec, LLMResponse
from sc2_agent.agent.session import Session
from sc2_agent.memory.store import MemoryStore
from sc2_agent.observation.collector import ObservationStore
from sc2_agent.observation.models import ObservationSnapshot
from sc2_agent.planning.simulator import SimulationState
from sc2_agent.runtime.commit import CommitController, CommitServices
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.scheduler import TimerScheduler
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.base import Tool, ToolCall
from sc2_agent.tools.ctrl import AbortTool, CommitTool
from sc2_agent.tools.registry import ToolRegistry
from sc2_agent.tools.review import ReviewPlanTool
from sc2_agent.tools.timer import TimerCommandTool, TimerMonitorTool


class FakeLLM:
    def __init__(self, staging: TimerStaging) -> None:
        self.calls = 0
        self.staging = staging

    async def chat(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_cmd",
                        name="timer.command",
                        arguments={
                            "id": "cmd1",
                            "at_time": 5,
                            "tool_name": "build.train",
                            "arguments": {"unit_type": "SCV", "structure_tag": "cc1"},
                            "wake_id": 1,
                        },
                    ),
                    ToolCall(
                        id="call_mon",
                        name="timer.monitor",
                        arguments={
                            "id": "mon1",
                            "metric": "game_time",
                            "op": ">=",
                            "value": 10,
                            "reason": "scheduled wake",
                            "wake_id": 1,
                        },
                    ),
                ]
            )
        if self.calls == 2:
            return LLMResponse(
                tool_calls=[
                    ToolCall(id="call_review", name="review.plan", arguments={"staging_hash": self.staging.hash()})
                ]
            )
        return LLMResponse(
            tool_calls=[
                ToolCall(id="call_commit", name="ctrl.commit", arguments={"staging_hash": self.staging.hash()})
            ]
        )


class BuildTrainTool(Tool):
    read_only = False

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    @property
    def name(self) -> str:
        return "build.train"

    @property
    def description(self) -> str:
        return "fake build train"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": "string"},
                "structure_tag": {"type": "string"},
            },
            "required": ["unit_type", "structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return {"accepted": True}


def test_minimal_wake_commit_sleep_monitor_wake_loop(tmp_path: Path) -> None:
    runtime = RuntimeStateMachine()
    staging = TimerStaging()
    timer_store = TimerStore()
    session = Session(key="integration")
    memory_store = MemoryStore(tmp_path / "memory")
    memory_store.initialize(wake_id=0, game_time=0)
    commit_events: list[str] = []

    def record(name: str):
        def _inner() -> None:
            commit_events.append(name)
        return _inner

    services = CommitServices(
        save_snapshot_and_events=record("snapshot_events"),
        append_session=lambda: session.append_messages([{"role": "system", "content": "session appended"}]),
        update_game_state=lambda: memory_store.append_key_events(["[5s] staged train SCV"], wake_id=1, game_time=5),
        consolidate_memory=record("consolidate"),
        render_game_state_markdown=lambda: memory_store.render_markdown(),
    )
    controller = CommitController(runtime=runtime, staging=staging, timer_store=timer_store, services=services)
    initial_state = SimulationState.from_dict(
        {
            "game_time": 0,
            "minerals": 100,
            "gas": 0,
            "supply_used": 12,
            "supply_cap": 15,
            "units": {"SCV": 12},
            "structures": {"CommandCenter": 1, "SupplyDepot": 1},
        }
    )

    agent_tools = ToolRegistry()
    agent_tools.register(TimerCommandTool(staging))
    agent_tools.register(TimerMonitorTool(staging))
    agent_tools.register(ReviewPlanTool(staging=staging, initial_state_provider=lambda: initial_state))
    agent_tools.register(CommitTool(controller))
    agent_tools.register(AbortTool(controller))

    result = asyncio.run(
        AgentRunner(FakeLLM(staging)).run(
            AgentRunSpec(
                initial_messages=[{"role": "user", "content": "wake and make a minimal plan"}],
                tools=agent_tools,
                max_iterations=5,
            )
        )
    )

    assert result.stop_reason == "committed"
    assert result.tools_used == ["timer.command", "timer.monitor", "review.plan", "ctrl.commit"]
    assert runtime.state is RuntimeState.RUNNING_SLEEP
    assert len(timer_store.commands) == 1
    assert len(timer_store.monitors) == 1
    assert session.messages == [{"role": "system", "content": "session appended"}]
    assert "staged train SCV" in memory_store.markdown_path.read_text(encoding="utf-8")
    assert commit_events == ["snapshot_events", "consolidate"]

    command_calls: list[dict[str, Any]] = []
    scheduler_tools = ToolRegistry()
    scheduler_tools.register(BuildTrainTool(command_calls))
    scheduler = TimerScheduler(
        runtime=runtime,
        timer_store=timer_store,
        tool_registry=scheduler_tools,
        observation_provider=ObservationStore(
            ObservationSnapshot(game_time=10, minerals=50, gas=0, supply_used=13, supply_cap=15)
        ),
    )

    first_tick = asyncio.run(scheduler.tick(5))
    second_tick = asyncio.run(scheduler.tick(10))

    assert first_tick.executed == ["cmd1"]
    assert command_calls == [{"unit_type": "SCV", "structure_tag": "cc1"}]
    assert runtime.state is RuntimeState.PAUSED_THINKING
    assert second_tick.triggered == ["mon1"]
    assert timer_store.run_history[0].status == "ok"
