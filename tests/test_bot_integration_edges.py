from __future__ import annotations

import asyncio

from sc2_agent.bot import SC2AgentBot, _StubConsolidationProvider
from sc2_agent.observation.collector import ObservationStore
from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot


class FakeAdapter:
    def __init__(self, snapshot: ObservationSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> ObservationSnapshot:
        return self._snapshot


class FakeScheduler:
    def __init__(self) -> None:
        self.seen_game_time: float | None = None

    async def tick(self, game_time: float):
        self.seen_game_time = game_time

        class Result:
            executed: list[str] = []
            triggered: list[str] = []
            expired: list[str] = []
            failed: list[str] = []

        return Result()


class FakeCollection:
    def __init__(self, items: dict[int, object]) -> None:
        self.items = items

    def find_by_tag(self, tag: int):
        return self.items.get(tag)


def test_bot_tick_scheduler_refreshes_observation_store_before_tick() -> None:
    bot = SC2AgentBot.__new__(SC2AgentBot)
    fresh = ObservationSnapshot(game_time=22, minerals=99, gas=7, supply_used=12, supply_cap=23)
    bot._obs_adapter = FakeAdapter(fresh)
    bot._obs_store = ObservationStore(
        ObservationSnapshot(game_time=1, minerals=0, gas=0, supply_used=0, supply_cap=0)
    )
    bot._timer_scheduler = FakeScheduler()

    asyncio.run(bot._tick_scheduler())

    assert bot._obs_store.snapshot() == fresh
    assert bot._timer_scheduler.seen_game_time == 22


def test_bot_constructor_uses_unavailable_llm_when_client_specs_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SC2_AGENT_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(SC2AgentBot, "_load_llm_clients", staticmethod(lambda: []))

    bot = SC2AgentBot()

    response = asyncio.run(bot._llm_adapter.chat(messages=[], tools=[]))
    assert response.finish_reason == "error"
    assert "client" in response.content.lower()


def test_bot_find_by_tag_searches_enemy_and_resource_collections() -> None:
    bot = SC2AgentBot.__new__(SC2AgentBot)
    enemy = object()
    mineral = object()
    geyser = object()
    bot.units = FakeCollection({})
    bot.structures = FakeCollection({})
    bot.enemy_units = FakeCollection({11: enemy})
    bot.enemy_structures = FakeCollection({})
    bot.mineral_field = FakeCollection({22: mineral})
    bot.vespene_geyser = FakeCollection({33: geyser})
    bot.destructables = FakeCollection({})

    assert bot.find_by_tag(11) is enemy
    assert bot.find_by_tag(22) is mineral
    assert bot.find_by_tag(33) is geyser
    assert bot.find_by_tag(44) is None


def test_stub_consolidation_provider_preserves_existing_strategy_sections() -> None:
    current_state = {
        "strategic_judgement": {"content": ["enemy unknown", "macro stable"]},
        "current_priorities": {"content": ["make workers", "scout"]},
    }

    update = _StubConsolidationProvider().consolidate(messages=[], current_state=current_state)

    assert update == {
        "strategic_judgement": ["enemy unknown", "macro stable"],
        "current_priorities": ["make workers", "scout"],
    }


def test_bot_simulation_state_includes_income_busy_producers_and_visible_queue() -> None:
    bot = SC2AgentBot.__new__(SC2AgentBot)
    snapshot = ObservationSnapshot(
        game_time=100,
        minerals=250,
        gas=125,
        supply_used=20,
        supply_cap=31,
        units=[
            UnitSnapshot(tag=index, type_name="SCV", x=0, y=0, is_idle=True)
            for index in range(1, 13)
        ],
        structures=[
            UnitSnapshot(tag=101, type_name="CommandCenter", x=0, y=0, is_idle=True),
            UnitSnapshot(
                tag=201,
                type_name="Barracks",
                x=0,
                y=0,
                is_idle=False,
                orders=[{"ability": "BARRACKSTRAIN_MARINE", "progress": 0.5}],
            ),
            UnitSnapshot(tag=301, type_name="Refinery", x=0, y=0, is_idle=True),
        ],
    )
    bot._obs_store = ObservationStore(snapshot)

    state = bot._make_simulation_state()

    assert state.mineral_income_rate == 9 * 0.75
    assert state.gas_income_rate == 3 * 0.63
    assert state.producer_available_at["Barracks:201"] == 109
    assert state.producer_available_at["201"] == 109
    assert state.production[0].item_name == "Marine"
    assert state.production[0].complete_at == 109
