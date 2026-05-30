"""Integration BotAI that wires all phases together for the SC2 Agent system.

Inherits from ``sc2.BotAI`` (burnysc2) and composes every subsystem:
observation, memory, timer staging/scheduling, tool registry, LLM adapter,
agent runner, prompt builder, commit controller, and the stop-the-world
runtime state machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sc2_agent.logging import LogManager, get_logger

try:
    from sc2.bot_ai import BotAI
except ImportError:
    class BotAI:  # type: ignore[no-redef]
        """Fallback base class for unit tests outside the burnysc2 environment."""

        pass

from sc2_agent.agent.prompt_builder import PromptBuilder
from sc2_agent.agent.runner import AgentRunner, AgentRunSpec, LLMResponse
from sc2_agent.agent.session import Session, SessionManager
from sc2_agent.config.settings import Settings
from sc2_agent.history.store import EventStore, SnapshotRecorder
from sc2_agent.llm.adapter import SC2LLMAdapter
from sc2_agent.memory.consolidator import ConsolidationUpdate, MemoryConsolidator
from sc2_agent.memory.store import MemoryStore
from sc2_agent.observation.burnysc2_adapter import BurnySC2ObservationAdapter
from sc2_agent.observation.collector import ObservationStore
from sc2_agent.observation.models import ObservationSnapshot, UnitSnapshot
from sc2_agent.planning.costs import COSTS
from sc2_agent.planning.simulator import ProductionItem, SimulationState
from sc2_agent.runtime.commit import CommitController, CommitServices
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.skills.loader import SkillLoader
from sc2_agent.timer.scheduler import TimerScheduler
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.build import (
    BuildAddonTool,
    BuildCancelResearchTool,
    BuildCancelTool,
    BuildCancelTrainTool,
    BuildLandTool,
    BuildLiftTool,
    BuildResearchTool,
    BuildStructureTool,
    BuildTrainTool,
)
from sc2_agent.tools.cmd import (
    CmdAttackMoveTool,
    CmdAttackTargetTool,
    CmdCancelOrderTool,
    CmdCloakTool,
    CmdDecloakTool,
    CmdHoldTool,
    CmdLoadTool,
    CmdMorphTool,
    CmdMoveTool,
    CmdPatrolTool,
    CmdRepairTool,
    CmdReturnCargoTool,
    CmdSiegeTool,
    CmdSmartTool,
    CmdStopTool,
    CmdUnloadTool,
    CmdUnsiegeTool,
    CmdUseAbilityTool,
)
from sc2_agent.tools.ctrl import CommitTool, AbortTool, DiscoverToolsTool
from sc2_agent.tools.econ import (
    EconBuildGasTool,
    EconExpandTool,
    EconGatherTool,
    EconSetMiningTool,
    EconTransferWorkersTool,
)
from sc2_agent.tools.hist import (
    HistCompareTool,
    HistEventsTool,
    HistSnapshotTool,
    HistTrendTool,
    HistUnitTool,
)
from sc2_agent.tools.obs import (
    ObsBasesTool,
    ObsControllerTool,
    ObsEnemyInferredTool,
    ObsEnemyVisibleTool,
    ObsGameTimeTool,
    ObsMapTool,
    ObsResourcesTool,
    ObsScoresTool,
    ObsStructuresTool,
    ObsUnitTool,
    ObsUnitsTool,
    ObsUpgradesTool,
)
from sc2_agent.tools.plan import PlanBuildOrderTool, PlanBuildTimeTool, PlanInitialStateTool, PlanSimulateTool
from sc2_agent.tools.query import (
    QueryCanAffordTool,
    QueryClosestTool,
    QueryExpansionsTool,
    QueryFindEnemyTool,
    QueryFindIdleTool,
    QueryFindStructuresTool,
    QueryFindUnitsTool,
    QueryFindWorkersTool,
    QueryIdleProducersTool,
    QueryInRegionTool,
    QueryPathTool,
    QueryPlacementsTool,
    QueryTechRequirementTool,
)
from sc2_agent.tools.registry import ToolRegistry
from sc2_agent.tools.review import ReviewLogicTool, ReviewParamsTool, ReviewPlanTool
from sc2_agent.tools.skill import SkillLoadTool
from sc2_agent.tools.squad import (
    SquadAddTool,
    SquadAutoBalanceTool,
    SquadCreateTool,
    SquadDisbandTool,
    SquadListTool,
    SquadOrderTool,
    SquadRemoveTool,
    SquadSetCountTool,
)
from sc2_agent.tools.timer import TimerCancelTool, TimerCommandTool, TimerListTool, TimerMonitorTool

_logger = get_logger(__name__)

MINERAL_INCOME_PER_WORKER_PER_SECOND = 0.75
GAS_INCOME_PER_WORKER_PER_SECOND = 0.63

LLM_CLIENTS_PATH = Path(__file__).resolve().parent / "config" / "llm_clients.json"


def _resolve_llm_clients_path() -> Path:
    import os
    env_path = os.getenv("SC2_LLM_CLIENTS_PATH", "")
    if env_path:
        return Path(env_path)
    return LLM_CLIENTS_PATH


class _LLMConsolidationProvider:
    """Consolidation provider that calls the LLM to update strategic memory."""

    def __init__(self, llm_adapter: SC2LLMAdapter) -> None:
        self._llm = llm_adapter

    def consolidate(
        self,
        *,
        messages: list[dict[str, Any]],
        current_state: dict[str, Any],
    ) -> ConsolidationUpdate | dict[str, Any]:
        import asyncio
        prompt = self._build_prompt(messages, current_state)
        try:
            resp = asyncio.run(self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
            ))
            return ConsolidationUpdate.from_raw(json.loads(resp.content or "{}"))
        except Exception:
            return ConsolidationUpdate.from_raw(current_state)

    @staticmethod
    def _build_prompt(messages: list[dict[str, Any]], current_state: dict[str, Any]) -> str:
        return json.dumps({
            "task": "Update strategic_judgement and current_priorities only. Do not modify known_facts or key_events.",
            "current_state": current_state,
            "recent_summary": f"Consolidating {len(messages)} messages",
        }, ensure_ascii=False)


class _StubConsolidationProvider:
    """Fallback provider — preserves existing strategic state (no-op)."""

    def consolidate(
        self,
        *,
        messages: list[dict[str, Any]],
        current_state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategic_judgement": list(current_state.get("strategic_judgement", {}).get("content", [])),
            "current_priorities": list(current_state.get("current_priorities", {}).get("content", [])),
        }


class _UnavailableLLM:
    """LLMClient fallback used when local client configuration is unavailable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def chat(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        return LLMResponse(content=self.reason, tool_calls=[], usage={}, finish_reason="error")


class SC2AgentBot(BotAI):
    """BotAI subclass integrating all SC2 Agent subsystems.

    Composes the runtime state machine, observation pipeline, memory store,
    timer staging / scheduling, tool registry, commit controller, LLM
    adapter, agent runner, and prompt builder into a single ``BotAI``
    that the burnysc2 game loop drives via ``on_step``.
    """

    def __init__(self) -> None:
        super().__init__()

        # 1. Settings & logging ------------------------------------------------
        self._settings = Settings.from_env()
        LogManager.setup(
            log_dir=self._settings.workspace / "logs",
            console_level=self._settings.log_level,
        )

        # 2. Runtime state machine ---------------------------------------------
        # Start in RUNNING_SLEEP so that the first-call path can init game
        # state and then call wake_to_thinking() (which requires RUNNING_SLEEP)
        # to transition into PAUSED_THINKING without raising.
        self._state_machine = RuntimeStateMachine()
        self._state_machine.state = RuntimeState.RUNNING_SLEEP
        self._game_initialized = False

        # 3. Observation -------------------------------------------------------
        # The adapter reads directly from ``self`` (BotAI), whose attributes
        # are populated by the SC2 engine on the first ``on_step`` call.
        self._obs_adapter = BurnySC2ObservationAdapter(self)
        zero_snapshot = ObservationSnapshot(
            game_time=0.0,
            minerals=0,
            gas=0,
            supply_used=0,
            supply_cap=0,
        )
        self._obs_store = ObservationStore(zero_snapshot)

        # 4. Memory ------------------------------------------------------------
        memory_dir = self._settings.workspace / "memory"
        self._memory_store = MemoryStore(memory_dir)
        history_dir = self._settings.workspace / "history"
        self._event_store = EventStore(history_dir)
        self._snapshot_recorder = SnapshotRecorder(history_dir)

        # 5. Timer staging / store ---------------------------------------------
        self._timer_staging = TimerStaging()
        self._timer_store = TimerStore()

        # 6. Tool registry -----------------------------------------------------
        self._tool_registry = ToolRegistry()

        # 7. LLM adapter -------------------------------------------------------
        client_specs = self._load_llm_clients()
        try:
            self._llm_adapter = SC2LLMAdapter(client_specs=client_specs)
        except (ImportError, ValueError, OSError, KeyError, IndexError) as exc:
            _logger.warning("LLM adapter unavailable; agent loop will abort gracefully: %s", exc)
            self._llm_adapter = _UnavailableLLM(str(exc))

        # 8. Agent runner ------------------------------------------------------
        self._agent_runner = AgentRunner(llm=self._llm_adapter)

        # 9. Prompt builder ----------------------------------------------------
        self._prompt_builder = PromptBuilder()
        self._skill_loader = SkillLoader(self._settings.workspace)

        # 10. Session manager --------------------------------------------------
        sessions_dir = self._settings.workspace / "sessions"
        self._session_manager = SessionManager(sessions_dir)
        self._session: Session | None = None
        self._committed_run_message_count = 0

        # 11. Memory consolidator ----------------------------------------------
        # NOTE: Uses primary LLM for consolidation. Design doc suggests a cheaper
        # model (qwen-turbo) for cost savings. Consider adding a second sticky client
        # when budget becomes a concern.
        self._memory_consolidator = MemoryConsolidator(
            provider=_LLMConsolidationProvider(self._llm_adapter),
            trigger_tokens=6000,
        )

        # 12. Commit controller ------------------------------------------------
        self._commit_controller = CommitController(
            runtime=self._state_machine,
            staging=self._timer_staging,
            timer_store=self._timer_store,
            services=CommitServices(
                save_snapshot_and_events=self._save_snapshot_and_events,
                append_session=self._append_session,
                update_game_state=self._update_game_state,
                consolidate_memory=self._consolidate_memory,
                render_game_state_markdown=self._render_game_state_markdown,
                pending_messages=lambda: [],
            ),
        )

        # 13. Timer scheduler --------------------------------------------------
        self._timer_scheduler = TimerScheduler(
            runtime=self._state_machine,
            timer_store=self._timer_store,
            tool_registry=self._tool_registry,
            observation_provider=self._obs_store,
        )

        # 14. Register all tools -----------------------------------------------
        self._register_all_tools()

        # 15. Wake counter -----------------------------------------------------
        self._wake_id: int = 0

    # ------------------------------------------------------------------
    # BotAI helper — satisfies the ``_BotAIProtocol`` used by
    # ``cmd.*`` / ``build.*`` / ``econ.*`` tools.
    # ------------------------------------------------------------------

    def find_by_tag(self, tag: int) -> Any:
        """Resolve a unit or structure by its numeric tag.

        Delegates to burnysc2 collections that expose ``find_by_tag``.
        Includes own units/structures, visible enemy units/structures and
        resource collections so command/economy tools can resolve every tag
        they are allowed to receive from obs/query results.
        """
        for attr in (
            "units",
            "structures",
            "enemy_units",
            "enemy_structures",
            "mineral_field",
            "vespene_geyser",
            "destructables",
        ):
            collection = getattr(self, attr, None)
            finder = getattr(collection, "find_by_tag", None)
            if finder is None:
                continue
            item = finder(tag)
            if item is not None:
                return item
        return None

    # ------------------------------------------------------------------
    # LLM config loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_llm_clients() -> list[dict[str, Any]]:
        """Read client specs from ``llm_clients.json``.

        Returns an empty list when the file is missing or unparseable so
        that the bot can be instantiated without a working LLM config
        (it will fail gracefully at runtime).
        """
        try:
            path = _resolve_llm_clients_path()
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data.get("clients", []) if isinstance(data, dict) else data
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            _logger.warning(
                "Failed to load LLM clients from %s: %s",
                _resolve_llm_clients_path(),
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_all_tools(self) -> None:
        """Register every tool with the shared ``ToolRegistry``."""
        # -- observation tools (all 12) ----------------------------------------
        self._tool_registry.register(ObsResourcesTool(self._obs_store))
        self._tool_registry.register(ObsUnitsTool(self._obs_store))
        self._tool_registry.register(ObsUnitTool(self._obs_store))
        self._tool_registry.register(ObsStructuresTool(self._obs_store))
        self._tool_registry.register(ObsGameTimeTool(self._obs_store))
        self._tool_registry.register(ObsMapTool(self._obs_store, map_width=256, map_height=256))
        self._tool_registry.register(ObsBasesTool(self._obs_store))
        self._tool_registry.register(ObsEnemyVisibleTool(self._obs_store))
        self._tool_registry.register(ObsEnemyInferredTool(self._obs_store))
        self._tool_registry.register(ObsControllerTool(self._obs_store))
        self._tool_registry.register(ObsScoresTool(self._obs_store))
        self._tool_registry.register(ObsUpgradesTool(self._obs_store))

        # -- query tools (all 13) ----------------------------------------------
        self._tool_registry.register(QueryFindUnitsTool(self._obs_store))
        self._tool_registry.register(QueryFindEnemyTool(self._obs_store))
        self._tool_registry.register(QueryFindStructuresTool(self._obs_store))
        self._tool_registry.register(QueryFindWorkersTool(self._obs_store))
        self._tool_registry.register(QueryFindIdleTool(self._obs_store))
        self._tool_registry.register(QueryIdleProducersTool(self._obs_store))
        self._tool_registry.register(QueryInRegionTool(self._obs_store))
        self._tool_registry.register(QueryClosestTool(self._obs_store))
        self._tool_registry.register(QueryPlacementsTool(self._obs_store, bot=self))
        self._tool_registry.register(QueryExpansionsTool(self._obs_store))
        self._tool_registry.register(QueryPathTool(self._obs_store))
        self._tool_registry.register(QueryCanAffordTool(self._obs_store))
        self._tool_registry.register(QueryTechRequirementTool(self._obs_store))

        # -- command tools (all 18) --------------------------------------------
        for tool_cls in (
            CmdMoveTool, CmdAttackTargetTool, CmdAttackMoveTool,
            CmdStopTool, CmdHoldTool, CmdSmartTool, CmdPatrolTool,
            CmdUseAbilityTool, CmdRepairTool, CmdReturnCargoTool,
            CmdLoadTool, CmdUnloadTool, CmdSiegeTool, CmdUnsiegeTool,
            CmdCloakTool, CmdDecloakTool, CmdMorphTool, CmdCancelOrderTool,
        ):
            self._tool_registry.register(tool_cls(self))

        # -- build tools (all 9) -----------------------------------------------
        for tool_cls in (
            BuildStructureTool, BuildTrainTool, BuildLandTool, BuildLiftTool,
            BuildCancelTool, BuildAddonTool, BuildCancelTrainTool,
            BuildResearchTool, BuildCancelResearchTool,
        ):
            self._tool_registry.register(tool_cls(self))

        # -- econ tools (all 5) ------------------------------------------------
        self._tool_registry.register(EconTransferWorkersTool(self))
        self._tool_registry.register(EconGatherTool(self))
        self._tool_registry.register(EconExpandTool(self))
        self._tool_registry.register(EconBuildGasTool(self))
        self._tool_registry.register(EconSetMiningTool(self))

        # -- squad tools (all 8) -----------------------------------------------
        squads: dict[str, list[int]] = {}
        self._tool_registry.register(SquadCreateTool(self, squads))
        self._tool_registry.register(SquadAddTool(self, squads))
        self._tool_registry.register(SquadRemoveTool(squads))
        self._tool_registry.register(SquadDisbandTool(squads))
        self._tool_registry.register(SquadOrderTool(self, squads))
        self._tool_registry.register(SquadListTool(squads))
        self._tool_registry.register(SquadAutoBalanceTool(squads))
        self._tool_registry.register(SquadSetCountTool(squads))

        # -- timer staging tools -----------------------------------------------
        self._tool_registry.register(TimerCommandTool(self._timer_staging, registry=self._tool_registry))
        self._tool_registry.register(TimerMonitorTool(self._timer_staging))
        self._tool_registry.register(TimerListTool(self._timer_staging, self._timer_store))
        self._tool_registry.register(TimerCancelTool(self._timer_staging, self._timer_store))

        # -- hist tools (all 5) ------------------------------------------------
        self._tool_registry.register(HistSnapshotTool(self._snapshot_recorder))
        self._tool_registry.register(HistTrendTool(self._snapshot_recorder))
        self._tool_registry.register(HistUnitTool(self._snapshot_recorder))
        self._tool_registry.register(HistCompareTool(self._snapshot_recorder))
        self._tool_registry.register(HistEventsTool(self._event_store))

        # -- plan / review / control tools -------------------------------------
        self._tool_registry.register(PlanInitialStateTool(self._make_simulation_state))
        self._tool_registry.register(PlanSimulateTool())
        self._tool_registry.register(PlanBuildTimeTool())
        self._tool_registry.register(PlanBuildOrderTool())
        self._tool_registry.register(ReviewParamsTool())
        self._tool_registry.register(ReviewLogicTool(self._timer_staging))
        self._tool_registry.register(
            ReviewPlanTool(
                staging=self._timer_staging,
                initial_state_provider=self._make_simulation_state,
                active_timers_provider=lambda: list(self._timer_store.commands),
            )
        )
        self._tool_registry.register(CommitTool(self._commit_controller))
        self._tool_registry.register(AbortTool(self._commit_controller))
        self._tool_registry.register(DiscoverToolsTool(self._tool_registry))
        self._tool_registry.register(SkillLoadTool(self._skill_loader))

    # ------------------------------------------------------------------
    # Tool summary helper
    # ------------------------------------------------------------------

    def _make_tool_summary(self) -> str:
        """Group registered tools by namespace and return a human-readable summary.

        Each line in the output has the form::

            ns.* -- N tools: ns.tool_a, ns.tool_b, ...
        """
        names = self._tool_registry.tool_names
        groups: dict[str, list[str]] = {}
        for name in names:
            ns = name.split(".")[0] if "." in name else "other"
            groups.setdefault(ns, []).append(name)

        lines: list[str] = []
        for ns in sorted(groups):
            tool_list = sorted(groups[ns])
            lines.append(
                f"{ns}.* -- {len(tool_list)} tools: {', '.join(tool_list)}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Skill summary helper
    # ------------------------------------------------------------------

    def _make_skill_summary(self) -> str:
        """Build the 可用技能 section for the system prompt.

        Includes full content of always-loaded skills and a listing of
        on-demand skills the Agent can load with skill.load(name).
        Returns empty string when no skills are available.
        """
        parts: list[str] = []

        # -- always-loaded skills (full content) --
        try:
            always = self._skill_loader.get_always_skills()
        except Exception:
            always = []
        if always:
            for skill in always:
                parts.append(skill["content"])

        # -- on-demand skills (main Agent only) --
        try:
            all_skills = self._skill_loader.scan_skills()
        except Exception:
            all_skills = []

        # Filter: only show skills the main Agent uses (exclude subsystem skills)
        SUBSYSTEM_SKILLS = {
            "review-knowledge", "review-dimensions", "consolidation-guide",
        }
        agent_skills = [
            s for s in all_skills
            if not s.get("always") and s["name"] not in SUBSYSTEM_SKILLS
        ]

        if agent_skills:
            parts.append("## 按需加载")
            parts.append("使用 skill.load(\"名称\") 按需加载：")
            for s in agent_skills:
                desc = s.get("description", "")
                parts.append(f"- {s['name']} — {desc}")

        # -- subsystem skills note --
        parts.append("")
        parts.append("以下由子系统自动加载，无需手动调用：")
        parts.append("- review-knowledge / review-dimensions — review.logic 审查 Sub-Agent")
        parts.append("- consolidation-guide — MemoryConsolidator")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Simulation-state provider for ``review.plan``
    # ------------------------------------------------------------------

    def _make_simulation_state(self) -> SimulationState:
        """Build a ``SimulationState`` from the current observation snapshot.

        Fully completed self structures remain the authoritative tech state.
        Producer tags, visible orders, and simple worker income estimates are
        folded in so ``review.plan`` starts from the current visible timeline.
        """
        snapshot = self._obs_store.snapshot()

        structures: dict[str, int] = {}
        producer_available_at: dict[str, float] = {}
        production: list[ProductionItem] = []
        now = float(snapshot.game_time)
        for s in snapshot.structures:
            if s.alliance == "self" and s.build_progress >= 1.0:
                structures[s.type_name] = structures.get(s.type_name, 0) + 1
                self._track_producer(s, producer_available_at, production, now)

        units: dict[str, int] = {}
        for u in snapshot.units:
            if u.alliance == "self":
                units[u.type_name] = units.get(u.type_name, 0) + 1
                self._track_producer(u, producer_available_at, production, now)

        gas_worker_count = min(units.get("SCV", 0), structures.get("Refinery", 0) * 3)
        mineral_worker_count = max(0, units.get("SCV", 0) - gas_worker_count)

        return SimulationState(
            game_time=now,
            minerals=float(snapshot.minerals),
            gas=float(snapshot.gas),
            supply_used=snapshot.supply_used,
            supply_cap=snapshot.supply_cap,
            mineral_income_rate=mineral_worker_count * MINERAL_INCOME_PER_WORKER_PER_SECOND,
            gas_income_rate=gas_worker_count * GAS_INCOME_PER_WORKER_PER_SECOND,
            structures=structures,
            units=units,
            production=production,
            producer_available_at=producer_available_at,
        )

    def _track_producer(
        self,
        unit: UnitSnapshot,
        producer_available_at: dict[str, float],
        production: list[ProductionItem],
        now: float,
    ) -> None:
        tag = str(unit.tag)
        producer_key = f"{unit.type_name}:{tag}"
        producer_available_at.setdefault(producer_key, now)
        producer_available_at.setdefault(tag, now)
        for order in unit.orders:
            item_name = self._item_from_order(order)
            busy_until = now + self._remaining_order_time(item_name, order)
            if unit.type_name == "SCV" and not self._worker_order_occupies_build_slot(order):
                continue
            producer_available_at[producer_key] = max(producer_available_at[producer_key], busy_until)
            producer_available_at[tag] = max(producer_available_at[tag], busy_until)
            if item_name:
                production.append(
                    ProductionItem(
                        item_name=item_name,
                        kind="train" if COSTS[item_name].supply > 0 else "build",
                        complete_at=busy_until,
                        producer_id=tag,
                    )
                )
        if not unit.is_idle and unit.type_name != "SCV" and not unit.orders:
            producer_available_at[producer_key] = max(producer_available_at[producer_key], now + 1.0)
            producer_available_at[tag] = max(producer_available_at[tag], now + 1.0)

    @staticmethod
    def _item_from_order(order: dict[str, Any]) -> str | None:
        ability = str(order.get("ability", "")).upper().replace("_", "")
        suffixes: list[str] = []
        for marker in ("TRAIN", "BUILD", "RESEARCH"):
            if marker in ability:
                suffixes.append(ability.split(marker, 1)[1])
        for item_name in sorted(COSTS, key=len, reverse=True):
            normalized = item_name.upper()
            if any(normalized in suffix for suffix in suffixes):
                return item_name
        for item_name in sorted(COSTS, key=len, reverse=True):
            if item_name.upper() in ability:
                return item_name
        return None

    @staticmethod
    def _remaining_order_time(item_name: str | None, order: dict[str, Any]) -> float:
        if item_name is None:
            return 1.0
        progress = max(0.0, min(1.0, float(order.get("progress", 0.0) or 0.0)))
        return max(1.0, COSTS[item_name].build_time * (1.0 - progress))

    @staticmethod
    def _worker_order_occupies_build_slot(order: dict[str, Any]) -> bool:
        ability = str(order.get("ability", "")).upper()
        return "BUILD" in ability or "CONSTRUCT" in ability or "REPAIR" in ability

    # ------------------------------------------------------------------
    # CommitServices callbacks
    #
    # These are wired into ``CommitServices`` and called during
    # ``CommitController.commit()`` in the specified order.
    # ------------------------------------------------------------------

    def _save_snapshot_and_events(self) -> None:
        """Persist the current observation snapshot and log staged timers as key events."""
        snapshot = self._obs_adapter.snapshot()
        self._obs_store.update(snapshot)
        self._snapshot_recorder.save(
            kind="decision",
            game_time=snapshot.game_time,
            wake_id=self._wake_id,
            payload=snapshot.to_dict(),
        )

        events: list[str] = []
        for cmd in self._timer_staging.commands:
            self._event_store.append(
                game_time=snapshot.game_time,
                wake_id=self._wake_id,
                event_type="timer_command_staged",
                payload=cmd.to_dict(),
            )
            events.append(
                f"[{snapshot.game_time:.0f}s] staged command: "
                f"{cmd.tool_name} @ {cmd.at_time} (id={cmd.id})"
            )
        for mon in self._timer_staging.monitors:
            self._event_store.append(
                game_time=snapshot.game_time,
                wake_id=self._wake_id,
                event_type="timer_monitor_staged",
                payload=mon.to_dict(),
            )
            events.append(
                f"[{snapshot.game_time:.0f}s] staged monitor: "
                f"{mon.metric} {mon.op} {mon.value} (id={mon.id})"
            )
        if events:
            self._memory_store.append_key_events(
                events,
                wake_id=self._wake_id,
                game_time=snapshot.game_time,
            )

    def _append_session(self) -> None:
        """Persist the current session to disk."""
        if self._session is not None:
            pending_messages = self._commit_controller.services.pending_messages
            if pending_messages is not None:
                messages = pending_messages()
                if messages:
                    self._session.append_messages(messages)
                    self._committed_run_message_count += len(messages)
            self._session_manager.save(self._session)

    def _update_game_state(self) -> None:
        """Refresh the known-facts section from the current observation."""
        snapshot = self._obs_store.snapshot()
        facts: list[str] = [
            f"resources: {snapshot.minerals}m / {snapshot.gas}g",
            f"supply: {snapshot.supply_used} / {snapshot.supply_cap}",
            f"self units visible: {len([u for u in snapshot.units if u.alliance == 'self'])}",
            f"self structures: {len([s for s in snapshot.structures if s.alliance == 'self'])}",
        ]
        self._memory_store.update_known_facts(
            facts, wake_id=self._wake_id, game_time=snapshot.game_time,
        )

    def _consolidate_memory(self) -> None:
        """Run memory consolidation when the unconsolidated token budget is exceeded."""
        if self._session is None:
            return
        self._memory_consolidator.consolidate_session(
            session=self._session,
            memory_store=self._memory_store,
            wake_id=self._wake_id,
            game_time=self._obs_store.snapshot().game_time,
        )

    def _render_game_state_markdown(self) -> None:
        """Re-render ``game_state.md`` from the persisted JSON state."""
        self._memory_store.render_markdown()

    # ------------------------------------------------------------------
    # Game state initialisation
    # ------------------------------------------------------------------

    def _init_game_state(self) -> None:
        """Initialise memory, observation store, and session for a new game.

        Called once on the first ``on_step`` invocation.  Idempotent
        because ``MemoryStore.initialize`` only creates the JSON file if
        it does not already exist.
        """
        snapshot = self._obs_adapter.snapshot()
        self._obs_store.update(snapshot)
        self._memory_store.initialize(
            wake_id=self._wake_id, game_time=snapshot.game_time,
        )
        self._session = self._session_manager.load("default") or Session(
            key="default"
        )
        _logger.info("Game state initialised at %.0fs", snapshot.game_time)

    # ------------------------------------------------------------------
    # Agent thinking loop
    # ------------------------------------------------------------------

    async def _run_agent_loop(self) -> None:
        """Run the LLM tool-calling loop for one thinking turn.

        Flow:
        1. Increment ``_wake_id`` and update the observation snapshot.
        2. Build the system prompt from current game-state markdown and
           tool summary.
        3. Build the user wake message.
        4. Load unconsolidated session history.
        5. Create an ``AgentRunSpec`` with
           ``[system, *history, user_wake]``.
        6. Delegate to ``AgentRunner.run()``.
        7. Append result messages to the session and persist.
        """
        self._wake_id += 1
        snapshot = self._obs_adapter.snapshot()
        self._obs_store.update(snapshot)

        game_state_md = self._memory_store.render_markdown()
        tool_summary = self._make_tool_summary()
        system_prompt = self._prompt_builder.build_system_prompt(
            game_state_md=game_state_md,
            tool_summary=tool_summary,
            skill_summary=self._make_skill_summary(),
        )

        wake_message = self._prompt_builder.build_wake_message(
            game_time=snapshot.game_time,
            wake_id=self._wake_id,
            reason="Agent thinking turn started",
            trigger_source="on_step",
        )

        history = self._session.get_history() if self._session else []
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": wake_message},
            ],
            tools=self._tool_registry,
            max_iterations=self._settings.max_agent_iterations,
        )

        result = await self._agent_runner.run(spec)
        game_time = snapshot.game_time

        if self._session is not None:
            remaining_messages = result.messages[self._committed_run_message_count :]
            if remaining_messages:
                self._session.append_messages(remaining_messages)
            self._session_manager.save(self._session)
            # Save ALL timing entries for this wake (messages already saved
            # during commit inside the runner need timing too).
            if result.timings:
                self._append_timings(game_time, result.messages, result.timings)
        self._committed_run_message_count = 0
        self._commit_controller.services.pending_messages = lambda: []

        if result.error:
            _logger.error("Agent run error: %s", result.error)
        _logger.info(
            "Agent run completed: wake=%d stop=%s tools=%d tokens=%d",
            self._wake_id,
            result.stop_reason,
            len(result.tools_used),
            sum(result.usage.values()),
        )

        # If the agent did not commit, abort and transition to sleep so
        # the game continues. Otherwise the engine keeps calling on_step
        # and the agent burns tokens in an infinite error loop.
        if result.stop_reason != "committed":
            if self._state_machine.state == RuntimeState.PAUSED_THINKING:
                _logger.info("Agent did not commit — aborting and sleeping")
                self._commit_controller.abort(reason=result.stop_reason)
                self._state_machine.commit_to_sleep()

    # ------------------------------------------------------------------
    # Timing recorder
    # ------------------------------------------------------------------

    def _append_timings(
        self,
        game_time: float,
        messages: list[dict[str, Any]],
        timings: list[dict[str, Any]],
    ) -> None:
        """Write ``timing.jsonl`` with wall-clock time, game time, and per-step latency.

        Each line corresponds 1:1 with a session message.
        """
        import time as _time
        import json as _json
        now = _time.time()
        path = self._settings.workspace / "sessions" / "timing.jsonl"
        for msg, tmr in zip(messages, timings):
            row = {
                "game_time": game_time,
                "wall_time": now,
                "role": msg.get("role"),
                "tool_name": msg.get("name") or tmr.get("tool_name"),
                "elapsed_ms": tmr.get("elapsed_ms", 0),
                "finish_reason": tmr.get("finish_reason"),
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(_json.dumps(row, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Timer scheduler tick
    # ------------------------------------------------------------------

    async def _tick_scheduler(self) -> None:
        """Execute due timer commands and evaluate monitors.

        Called on each ``on_step`` while the runtime is in
        ``RUNNING_SLEEP``.
        """
        snapshot = self._obs_adapter.snapshot()
        self._obs_store.update(snapshot)
        game_time = snapshot.game_time
        sched_result = await self._timer_scheduler.tick(game_time)
        if sched_result.executed:
            _logger.debug("Executed timer commands: %s", sched_result.executed)
        if sched_result.triggered:
            _logger.info("Monitor triggers: %s", sched_result.triggered)
        if sched_result.expired:
            _logger.debug("Expired monitors: %s", sched_result.expired)
        if sched_result.failed:
            _logger.warning("Timer commands failed: %s", sched_result.failed)
            self._state_machine.wake_to_thinking()

        # Periodic snapshots
        self._maybe_capture_periodic_snapshot(game_time)

    def _maybe_capture_periodic_snapshot(self, game_time: float) -> None:
        """Capture minute-level (every 60s) and 5sec-level (every 5s) snapshots."""
        if not hasattr(self, "_snapshot_recorder"):
            return
        if not hasattr(self, "_last_minute_snap"):
            self._last_minute_snap = -60.0
            self._last_5sec_snap = -5.0

        if game_time - self._last_5sec_snap >= 5.0:
            self._snapshot_recorder.save(
                kind="5sec", game_time=game_time, wake_id=None,
                payload=self._make_snapshot_payload(),
            )
            self._last_5sec_snap = game_time
            self._snapshot_recorder.prune(kind="5sec", keep=self._settings.snapshot_recent_keep)

        if game_time - self._last_minute_snap >= 60.0:
            self._snapshot_recorder.save(
                kind="minute", game_time=game_time, wake_id=None,
                payload=self._make_snapshot_payload(),
            )
            self._last_minute_snap = game_time

    def _make_snapshot_payload(self) -> dict[str, Any]:
        snapshot = self._obs_store.snapshot()
        return {
            "game_time": snapshot.game_time,
            "minerals": snapshot.minerals,
            "gas": snapshot.gas,
            "supply_used": snapshot.supply_used,
            "supply_cap": snapshot.supply_cap,
            "units": [u.to_dict() for u in snapshot.units],
            "structures": [s.to_dict() for s in snapshot.structures],
        }

    # ------------------------------------------------------------------
    # Main entry point -- called by the burnysc2 game loop every step.
    # ------------------------------------------------------------------

    async def on_step(self, iteration: int) -> None:
        """Main entry point invoked by the SC2 engine each game step.

        Routing logic
        -------------
        * **First call** (``_game_initialized is False``):
          initialise game state, transition to ``PAUSED_THINKING``, run
          the agent loop.
        * **PAUSED_THINKING**: run the agent loop (blocks the game).
        * **RUNNING_SLEEP**: tick the timer scheduler (commands +
          monitors).
        """
        # Stop after 60 seconds of game time (for development testing).
        if self.time >= 60.0 and self._game_initialized and not getattr(self, '_time_limit_logged', False):
            _logger.info("Game time limit reached (60s), bot going idle")
            self._time_limit_logged = True
        if self.time >= 60.0 and self._game_initialized:
            if self._state_machine.state == RuntimeState.PAUSED_THINKING:
                self._state_machine.commit_to_sleep()
            return

        if not self._game_initialized:
            self._init_game_state()
            self._game_initialized = True
            self._state_machine.wake_to_thinking()
            await self._run_agent_loop()
        elif self._state_machine.state == RuntimeState.PAUSED_THINKING:
            await self._run_agent_loop()
        elif self._state_machine.state == RuntimeState.RUNNING_SLEEP:
            await self._tick_scheduler()
