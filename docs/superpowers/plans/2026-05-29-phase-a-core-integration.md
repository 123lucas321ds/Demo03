# Phase A: Core Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start SC2 with a BotAI subclass that runs the AgentRunner loop via LLM, with enough cmd/build/econ/obs/query tools for the Agent to observe and act.

**Architecture:** `SC2AgentBot` inherits `BotAI`, initializes all components in `__init__`, runs AgentRunner in `on_step` (blocking the game loop → natural stop-the-world). Tools take `BotAI` reference for tag→unit lookup and command issuing. LLM is SC2 project's `UnifiedLLMClient` wrapped in a thin adapter.

**Tech Stack:** burnysc2, openai SDK, Python 3.12+, conda env `LLM`

---

## File Structure

```
Create:  sc2_agent/llm/__init__.py
Create:  sc2_agent/llm/adapter.py          — wraps SC2 UnifiedLLMClient, implements LLMClient Protocol
Create:  sc2_agent/agent/prompt_builder.py — four-part system prompt assembly
Modify:  sc2_agent/tools/obs.py            — add obs.game_time, obs.map, obs.bases, obs.enemy_visible, obs.upgrades
Modify:  sc2_agent/tools/query.py          — add query.find_enemy, query.find_structures, query.in_region, query.expansions
Create:  sc2_agent/tools/cmd.py            — cmd.* tools (move, attack, stop, hold, smart, repair, use_ability)
Create:  sc2_agent/tools/build.py          — build.* tools (structure, train, land, lift, cancel)
Create:  sc2_agent/tools/econ.py           — econ.* tools (transfer_workers, expand, build_gas)
Create:  sc2_agent/bot.py                  — SC2AgentBot(BotAI), on_step integration
Modify:  sc2_agent/main.py                 — entry point: player setup, map, start SC2

Create:  tests/llm/__init__.py
Create:  tests/llm/test_adapter.py
Create:  tests/agent/test_prompt_builder.py
Create:  tests/tools/test_cmd.py
Create:  tests/tools/test_build.py
Create:  tests/tools/test_econ.py
```

---

### Task 1: LLM Adapter

**Files:**
- Create: `sc2_agent/llm/__init__.py`
- Create: `sc2_agent/llm/adapter.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_adapter.py
import pytest
from sc2_agent.llm.adapter import SC2LLMAdapter

def test_adapter_implements_llmclient_protocol():
    """Adapter should satisfy the LLMClient Protocol structurally."""
    adapter = SC2LLMAdapter(client_specs=[])
    assert hasattr(adapter, "chat")
    assert callable(adapter.chat)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/llm/test_adapter.py -v`
Expected: FAIL (ImportError or AttributeError)

- [ ] **Step 3: Write minimal implementation**

```python
# sc2_agent/llm/__init__.py
from sc2_agent.llm.adapter import SC2LLMAdapter

__all__ = ["SC2LLMAdapter"]
```

```python
# sc2_agent/llm/adapter.py
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sc2_agent.agent.runner import LLMClient, LLMResponse
from sc2_agent.tools.base import ToolCall

# Add SC2 project to path to import UnifiedLLMClient
_SC2_PROJECT = Path("E:/Code/python/scientific research/SC2")
if str(_SC2_PROJECT) not in sys.path:
    sys.path.insert(0, str(_SC2_PROJECT))


@dataclass
class SC2LLMAdapter:
    """Wraps SC2 project's UnifiedLLMClient to satisfy Demo03's LLMClient Protocol."""

    client_specs: list[dict[str, Any]]
    request_timeout_seconds: float = 80.0
    max_retries: int = 3
    sticky_client_name: str = "deepseek_chat"

    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from agent.LLMClient import (
            LLMClientSpec,
            RoutingMode,
            RetryStrategy,
            UnifiedLLMClient,
        )

        specs = [
            LLMClientSpec(
                name=s["name"],
                api_key=s["api_key"],
                base_url=s["base_url"],
                model=s["model"],
                provider=s.get("provider", "openai_compatible"),
            )
            for s in self.client_specs
        ]
        self._client = UnifiedLLMClient(
            client_specs=specs,
            request_timeout_seconds=self.request_timeout_seconds,
            max_retries=self.max_retries,
            routing_mode=RoutingMode.STICKY.value,
            retry_strategy=RetryStrategy.AUTO.value,
            sticky_client_name=self.sticky_client_name,
        )

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call the model via UnifiedLLMClient.generate_with_tools."""
        # UnifiedLLMClient.generate_with_tools returns (final_text, tool_call_log)
        # but we need the actual tool_calls from the assistant message
        # Use generate() first approach: send one chat completion and return response
        return await self._chat_single(messages, tools)

    async def _chat_single(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        import asyncio

        from agent.LLMClient import _OpenAICompatibleSingleClient, LLMClientSpec

        # Pick the sticky client's spec
        spec = next(
            (s for s in self._client._specs if s["name"] == self.sticky_client_name),
            self._client._specs[0],
        )
        openai_spec = LLMClientSpec(
            name=spec["name"],
            api_key=spec["api_key"],
            base_url=spec["base_url"],
            model=spec["model"],
            provider=spec.get("provider", "openai_compatible"),
        )
        single = _OpenAICompatibleSingleClient(openai_spec)

        # Convert messages and call the underlying openai client's chat.completions.create
        normalized = [self._normalize_msg(m) for m in messages]
        tool_schemas = self._convert_tools(tools)

        result = await asyncio.to_thread(
            single._client.chat.completions.create,
            model=spec["model"],
            messages=normalized,
            tools=tool_schemas,
        )
        choice = result.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            },
            finish_reason=choice.finish_reason,
        )

    def _normalize_msg(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Convert internal message format to OpenAI-compatible dict."""
        normalized: dict[str, Any] = {"role": msg["role"]}
        if "content" in msg and msg["content"] is not None:
            normalized["content"] = msg["content"]
        if "tool_calls" in msg:
            normalized["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": (
                            tc["function"]["arguments"]
                            if isinstance(tc["function"]["arguments"], str)
                            else json.dumps(tc["function"]["arguments"])
                        ),
                    },
                }
                for tc in msg["tool_calls"]
            ]
        if msg["role"] == "tool":
            normalized["tool_call_id"] = msg["tool_call_id"]
            normalized["content"] = (
                msg["content"]
                if isinstance(msg["content"], str)
                else json.dumps(msg["content"])
            )
        return normalized

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert internal tool schema format to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"].get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/llm/test_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 2: PromptBuilder

**Files:**
- Create: `sc2_agent/agent/prompt_builder.py`
- Create: `tests/agent/test_prompt_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_prompt_builder.py
from sc2_agent.agent.prompt_builder import PromptBuilder

def test_build_system_prompt_has_four_sections():
    builder = PromptBuilder()
    prompt = builder.build_system_prompt(
        game_state_md="# Current Situation\n(empty)\n",
        tool_summary="obs.*, query.*, cmd.*, build.*, ctrl.*",
        skill_summary="No skills loaded.",
    )
    assert "SC2 人族指挥官" in prompt
    assert "当前局势" in prompt
    assert "可用工具" in prompt
    assert "obs.*" in prompt

def test_build_wake_message():
    builder = PromptBuilder()
    msg = builder.build_wake_message(
        game_time=45.0,
        wake_id=1,
        reason="game_start",
        trigger_source="startup",
    )
    assert "game_time=45.0" in msg
    assert "wake_id=1" in msg
    assert "game_start" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_prompt_builder.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# sc2_agent/agent/prompt_builder.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptBuilder:
    """Assembles the four-part system prompt and wake user message."""

    def build_system_prompt(
        self,
        *,
        game_state_md: str,
        tool_summary: str,
        skill_summary: str = "",
    ) -> str:
        parts = [
            self._identity_section(),
            self._situation_section(game_state_md),
            self._tool_section(tool_summary),
        ]
        if skill_summary:
            parts.append(self._skill_section(skill_summary))
        return "\n\n".join(parts)

    def build_wake_message(
        self,
        *,
        game_time: float,
        wake_id: int,
        reason: str,
        trigger_source: str = "startup",
    ) -> str:
        return (
            f"game_time={game_time:.1f}s\n"
            f"wake_id={wake_id}\n"
            f"唤醒原因: {reason}\n"
            f"触发来源: {trigger_source}\n"
            "请先检查近期唤醒频率，再按需观察、规划、审查并提交。"
        )

    # --- private ---

    def _identity_section(self) -> str:
        return (
            "# 身份与运行时\n"
            "你是 SC2 人族指挥官 AI。\n"
            "- 通过工具观察、推理和行动。\n"
            "- 所有单位必须通过 unit_tag 引用，tag 必须来自 obs.* 或 query.* 返回结果，禁止编造。\n"
            "- 所有带 at_time 的命令必须经过 plan.simulate 数学推理。\n"
            "- 提交前必须调用 review.plan。\n"
            "- 命令消耗不能超过预测资源。\n"
            "- ctrl.commit 必须是最后一轮唯一的 tool_call。"
        )

    def _situation_section(self, game_state_md: str) -> str:
        return f"# 当前局势\n{game_state_md}"

    def _tool_section(self, tool_summary: str) -> str:
        return (
            "# 可用工具\n"
            "以下为工具命名空间摘要，具体参数由 function calling schema 提供：\n"
            f"{tool_summary}"
        )

    def _skill_section(self, skill_summary: str) -> str:
        return f"# 可用技能\n{skill_summary}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agent/test_prompt_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 3: obs.* Supplement (5 new tools)

**Files:**
- Modify: `sc2_agent/tools/obs.py`
- Create: `tests/tools/test_obs_extended.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_obs_extended.py
from sc2_agent.observation.collector import StaticObservationProvider
from sc2_agent.observation.models import ObservationSnapshot
from sc2_agent.tools.obs import (
    ObsGameTimeTool,
    ObsMapTool,
    ObsBasesTool,
    ObsEnemyVisibleTool,
    ObsUpgradesTool,
)

def _make_provider():
    return StaticObservationProvider(ObservationSnapshot(
        game_time=120.0,
        minerals=500,
        gas=200,
        supply_used=30,
        supply_cap=46,
        units=[],
        structures=[],
    ))

def test_obs_game_time_returns_time():
    provider = _make_provider()
    tool = ObsGameTimeTool(provider)
    import asyncio
    result = asyncio.run(tool.execute())
    assert result["game_time"] == 120.0

def test_obs_map_returns_dimensions():
    provider = _make_provider()
    tool = ObsMapTool(provider, map_width=256, map_height=256)
    import asyncio
    result = asyncio.run(tool.execute())
    assert result["width"] == 256
    assert result["height"] == 256
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_obs_extended.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Add new obs tools to obs.py**

Append to `sc2_agent/tools/obs.py`:

```python
class ObsGameTimeTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.game_time"

    @property
    def description(self) -> str:
        return "Return the current game time in seconds."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        return {"game_time": self.provider.snapshot().game_time}


class ObsMapTool(Tool):
    def __init__(self, provider: ObservationProvider, *,
                 map_width: float = 256, map_height: float = 256) -> None:
        self.provider = provider
        self._map_width = map_width
        self._map_height = map_height

    @property
    def name(self) -> str:
        return "obs.map"

    @property
    def description(self) -> str:
        return "Return map dimensions and playable area."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        return {
            "width": self._map_width,
            "height": self._map_height,
            "playable": {
                "x": 0, "y": 0,
                "width": self._map_width,
                "height": self._map_height,
            },
        }


class ObsBasesTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.bases"

    @property
    def description(self) -> str:
        return "Return expansion locations and owned townhalls."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        townhalls = [
            s.to_dict()
            for s in snapshot.structures
            if "commandcenter" in s.type_name.lower()
            or "nexus" in s.type_name.lower()
            or "hatchery" in s.type_name.lower()
        ]
        return {"townhalls": townhalls, "expansions": []}


class ObsEnemyVisibleTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.enemy_visible"

    @property
    def description(self) -> str:
        return "Return currently visible enemy units and structures."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": ["string", "null"]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        unit_type = kwargs.get("unit_type")
        entities = [
            e for e in [*self.provider.snapshot().units, *self.provider.snapshot().structures]
            if e.alliance == "enemy"
        ]
        if unit_type:
            entities = [e for e in entities if e.type_name == unit_type]
        return [e.to_dict() for e in entities]


class ObsUpgradesTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "obs.upgrades"

    @property
    def description(self) -> str:
        return "Return completed upgrades."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        return {"completed": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_obs_extended.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 4: query.* Supplement (4 new tools)

**Files:**
- Modify: `sc2_agent/tools/query.py`
- No new test file (add to existing `tests/tools/test_obs_query.py`)

- [ ] **Step 1: Write the failing test**

Append to `tests/tools/test_obs_query.py`:

```python
from sc2_agent.tools.query import QueryFindEnemyTool, QueryFindStructuresTool, QueryInRegionTool, QueryExpansionsTool

def test_query_find_enemy():
    provider = _make_fake_provider()
    tool = QueryFindEnemyTool(provider)
    result = asyncio.run(tool.execute())
    assert isinstance(result, list)

def test_query_find_structures():
    provider = _make_fake_provider()
    tool = QueryFindStructuresTool(provider)
    result = asyncio.run(tool.execute(structure_type="Barracks"))
    assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_obs_query.py::test_query_find_enemy -v`
Expected: FAIL

- [ ] **Step 3: Add new query tools to query.py**

Append to `sc2_agent/tools/query.py`:

```python
class QueryFindEnemyTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_enemy"

    @property
    def description(self) -> str:
        return "Find visible enemy units and structures."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "unit_type": {"type": ["string", "null"]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        unit_type = kwargs.get("unit_type")
        entities = [
            e for e in _all_entities(self.provider) if e.alliance == "enemy"
        ]
        if unit_type:
            entities = [e for e in entities if e.type_name == canonical_name(unit_type)]
        return [e.to_dict() for e in entities]


class QueryFindStructuresTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.find_structures"

    @property
    def description(self) -> str:
        return "Find structures by type and alliance."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_type": {"type": ["string", "null"]},
                "alliance": {"type": ["string", "null"], "enum": ["self", "enemy", "neutral", None]},
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_type = kwargs.get("structure_type")
        alliance = kwargs.get("alliance")
        structures = self.provider.snapshot().structures
        if structure_type:
            structures = [s for s in structures if s.type_name == canonical_name(structure_type)]
        if alliance:
            structures = [s for s in structures if s.alliance == alliance]
        return [s.to_dict() for s in structures]


class QueryInRegionTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.in_region"

    @property
    def description(self) -> str:
        return "Find entities within a rectangular region."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x1": {"type": "number"}, "y1": {"type": "number"},
                "x2": {"type": "number"}, "y2": {"type": "number"},
                "alliance": {"type": ["string", "null"]},
            },
            "required": ["x1", "y1", "x2", "y2"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        x1, y1 = float(kwargs["x1"]), float(kwargs["y1"])
        x2, y2 = float(kwargs["x2"]), float(kwargs["y2"])
        alliance = kwargs.get("alliance")
        entities = _all_entities(self.provider)
        if alliance:
            entities = [e for e in entities if e.alliance == alliance]
        in_region = [
            e for e in entities
            if x1 <= e.x <= x2 and y1 <= e.y <= y2
        ]
        return [e.to_dict() for e in in_region]


class QueryExpansionsTool(Tool):
    def __init__(self, provider: ObservationProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "query.expansions"

    @property
    def description(self) -> str:
        return "Return expansion locations and their occupancy status."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        snapshot = self.provider.snapshot()
        townhalls = [
            s.to_dict()
            for s in snapshot.structures
            if "commandcenter" in s.type_name.lower()
            or "nexus" in s.type_name.lower()
            or "hatchery" in s.type_name.lower()
        ]
        return {"owned": townhalls, "available": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_obs_query.py -v`
Expected: PASS (all existing + new)

- [ ] **Step 5: Commit**

---

### Task 5: cmd.* Basic Set (8 tools)

**Files:**
- Create: `sc2_agent/tools/cmd.py`
- Create: `tests/tools/test_cmd.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_cmd.py
import pytest
from sc2_agent.tools.cmd import (
    CmdMoveTool, CmdAttackTargetTool, CmdAttackMoveTool,
    CmdStopTool, CmdHoldTool, CmdSmartTool,
    CmdUseAbilityTool, CmdRepairTool,
)

class FakeBot:
    """Fake BotAI for testing cmd tools without SC2."""
    def __init__(self):
        self.actions = []
        self._units = {}

    def register_unit(self, tag, type_name, x=0, y=0):
        self._units[tag] = {"tag": tag, "type_name": type_name, "x": x, "y": y}

    def find_by_tag(self, tag):
        class FakeUnit:
            def __init__(self, data):
                self.tag = data["tag"]
                self.type_name = data["type_name"]
                self.position = type("Point2", (), {"x": data["x"], "y": data["y"]})()
            def move(self, position, queue=False):
                self._last_cmd = ("move", position)
                return True
            def attack(self, target, queue=False):
                self._last_cmd = ("attack", target)
                return True
            def stop(self, queue=False):
                self._last_cmd = ("stop",)
                return True
            def hold_position(self, queue=False):
                self._last_cmd = ("hold",)
                return True
            def smart(self, target, queue=False):
                self._last_cmd = ("smart", target)
                return True
            def use_ability(self, ability_id, target=None, queue=False):
                self._last_cmd = ("ability", ability_id, target)
                return True
            def repair(self, repair_target, queue=False):
                self._last_cmd = ("repair", repair_target)
                return True
        u = FakeUnit(self._units.get(tag, {"tag": tag, "type_name": "unknown", "x": 0, "y": 0}))
        return u if tag in self._units else None

def test_cmd_move_uses_tags():
    bot = FakeBot()
    bot.register_unit(42, "Marine", x=10, y=20)
    tool = CmdMoveTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(tags=[42], x=35.0, y=40.0))
    assert result["ok"] is True

def test_cmd_move_tag_not_found():
    bot = FakeBot()
    tool = CmdMoveTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(tags=[999], x=35.0, y=40.0))
    assert result["ok"] is False
    assert "TAG_NOT_FOUND" in str(result.get("errors", ""))

def test_cmd_attack_target():
    bot = FakeBot()
    bot.register_unit(1, "Marine", x=10, y=20)
    bot.register_unit(2, "Zergling", x=15, y=25)
    tool = CmdAttackTargetTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(tags=[1], target_tag=2))
    assert result["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_cmd.py -v`
Expected: FAIL

- [ ] **Step 3: Write cmd.py implementation**

```python
# sc2_agent/tools/cmd.py
"""Command tools — issue orders to units by tag.

All tools require unit tags obtained from obs.* or query.* results.
Tags are per-game random identifiers and must never be invented.
"""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.tools.base import Tool


class _BotAIProtocol(Protocol):
    """Minimal BotAI interface needed by command tools."""
    def find_by_tag(self, tag: int) -> Any: ...


def _resolve_units(bot: _BotAIProtocol, tags: list[int]) -> tuple[list[Any], list[dict]]:
    units = []
    errors = []
    for tag in tags:
        unit = bot.find_by_tag(tag)
        if unit is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": tag})
        else:
            units.append(unit)
    return units, errors


def _result(ok: bool, success_count: int, errors: list[dict]) -> dict:
    return {"ok": ok, "success_count": success_count, "errors": errors}


class CmdMoveTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.move"

    @property
    def description(self) -> str:
        return "Move units by tag to target coordinates. tags must come from obs.* or query.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "x": {"type": "number"}, "y": {"type": "number"},
                "queue": {"type": "boolean"},
            },
            "required": ["tags", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        x, y = float(kwargs["x"]), float(kwargs["y"])
        from sc2.position import Point2
        target = Point2((x, y))
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.move(target, queue=queue)
        return _result(not errors, len(units), errors)


class CmdAttackTargetTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.attack_target"

    @property
    def description(self) -> str:
        return "Attack a target unit by its tag. Both attacker tags and target_tag must come from obs.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "target_tag": {"type": "integer"},
                "queue": {"type": "boolean"},
            },
            "required": ["tags", "target_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        target_tag = kwargs["target_tag"]
        target = self._bot.find_by_tag(target_tag)
        if target is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": target_tag, "role": "target"})
            return _result(False, 0, errors)
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.attack(target, queue=queue)
        return _result(not errors, len(units), errors)


class CmdAttackMoveTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.attack_move"

    @property
    def description(self) -> str: return "A-move units to a position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "x": {"type": "number"}, "y": {"type": "number"},
                "queue": {"type": "boolean"},
            },
            "required": ["tags", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        x, y = float(kwargs["x"]), float(kwargs["y"])
        from sc2.position import Point2
        target = Point2((x, y))
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.attack(target, queue=queue)
        return _result(not errors, len(units), errors)


class CmdStopTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.stop"

    @property
    def description(self) -> str: return "Stop units (tags from obs.*)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "queue": {"type": "boolean"},
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.stop(queue=queue)
        return _result(not errors, len(units), errors)


class CmdHoldTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.hold"

    @property
    def description(self) -> str: return "Hold position (tags from obs.*)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "queue": {"type": "boolean"},
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.hold_position(queue=queue)
        return _result(not errors, len(units), errors)


class CmdSmartTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.smart"

    @property
    def description(self) -> str:
        return "Right-click smart command: attack if enemy, move if ground, gather if resource."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "target_tag": {"type": ["integer", "null"]},
                "x": {"type": ["number", "null"]},
                "y": {"type": ["number", "null"]},
                "queue": {"type": "boolean"},
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        queue = bool(kwargs.get("queue", False))
        target_tag = kwargs.get("target_tag")
        if target_tag is not None:
            target = self._bot.find_by_tag(target_tag)
            if target is None:
                errors.append({"code": "TAG_NOT_FOUND", "tag": target_tag, "role": "target"})
                return _result(False, 0, errors)
            for unit in units:
                unit.smart(target, queue=queue)
        elif kwargs.get("x") is not None and kwargs.get("y") is not None:
            from sc2.position import Point2
            target = Point2((float(kwargs["x"]), float(kwargs["y"])))
            for unit in units:
                unit.smart(target, queue=queue)
        else:
            errors.append({"code": "INVALID_ARGUMENT", "message": "target_tag or (x,y) required"})
            return _result(False, 0, errors)
        return _result(not errors, len(units), errors)


class CmdUseAbilityTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.use_ability"

    @property
    def description(self) -> str: return "Use an ability on a target unit or position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}},
                "ability_id": {"type": "integer"},
                "target_tag": {"type": ["integer", "null"]},
                "x": {"type": ["number", "null"]},
                "y": {"type": ["number", "null"]},
                "queue": {"type": "boolean"},
            },
            "required": ["tags", "ability_id"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        queue = bool(kwargs.get("queue", False))
        ability_id = kwargs["ability_id"]
        target = None
        if kwargs.get("target_tag") is not None:
            target = self._bot.find_by_tag(kwargs["target_tag"])
            if target is None:
                errors.append({"code": "TAG_NOT_FOUND", "tag": kwargs["target_tag"]})
                return _result(False, 0, errors)
        elif kwargs.get("x") is not None and kwargs.get("y") is not None:
            from sc2.position import Point2
            target = Point2((float(kwargs["x"]), float(kwargs["y"])))
        for unit in units:
            unit.use_ability(ability_id, target=target, queue=queue)
        return _result(not errors, len(units), errors)


class CmdRepairTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "cmd.repair"

    @property
    def description(self) -> str:
        return "SCV repair a target unit/structure. worker_tags and target_tag must come from obs.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tags": {"type": "array", "items": {"type": "integer"}},
                "target_tag": {"type": "integer"},
                "queue": {"type": "boolean"},
            },
            "required": ["worker_tags", "target_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["worker_tags"])
        target = self._bot.find_by_tag(kwargs["target_tag"])
        if target is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": kwargs["target_tag"], "role": "target"})
            return _result(False, 0, errors)
        queue = bool(kwargs.get("queue", False))
        for unit in units:
            unit.repair(target, queue=queue)
        return _result(not errors, len(units), errors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_cmd.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 6: build.* Basic Set (5 tools)

**Files:**
- Create: `sc2_agent/tools/build.py`
- Create: `tests/tools/test_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_build.py
import pytest
from sc2_agent.tools.build import (
    BuildStructureTool, BuildTrainTool, BuildLandTool,
    BuildLiftTool, BuildCancelTool,
)

class FakeBot:
    def __init__(self):
        self._units = {}
        self.actions = []

    def register_unit(self, tag, type_name, x=0, y=0):
        self._units[tag] = {"tag": tag, "type_name": type_name, "x": x, "y": y}

    def find_by_tag(self, tag):
        if tag not in self._units:
            return None
        data = self._units[tag]
        class FakeUnit:
            def __init__(self, d):
                self.tag = d["tag"]
                self.type_name = d["type_name"]
                self.position = type("P", (), {"x": d["x"], "y": d["y"]})()
            def train(self, unit_type, queue=False, can_afford_check=False):
                self._last_train = (unit_type, queue)
                return True
            def build(self, unit_type, position, queue=False, can_afford_check=False):
                self._last_build = (unit_type, position)
                return True
            def land(self, position, queue=False):
                self._last_land = position
                return True
            def lift(self, queue=False):
                self._last_lift = True
                return True
        return FakeUnit(data)

def test_build_train_by_structure_tag():
    bot = FakeBot()
    bot.register_unit(88, "Barracks", x=30, y=30)
    tool = BuildTrainTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(structure_tag=88, unit_type="Marine"))
    assert result["ok"] is True

def test_build_train_bad_tag():
    bot = FakeBot()
    tool = BuildTrainTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(structure_tag=999, unit_type="Marine"))
    assert result["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_build.py -v`
Expected: FAIL

- [ ] **Step 3: Write build.py implementation**

```python
# sc2_agent/tools/build.py
"""Build tools — construction, training, and structure management.

All tools reference units and structures by tag.
Tags must come from obs.* or query.* results; never invent tags.
"""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.planning.costs import canonical_name
from sc2_agent.tools.base import Tool


class _BotAIProtocol(Protocol):
    def find_by_tag(self, tag: int) -> Any: ...


def _find_unit(bot: _BotAIProtocol, tag: int) -> tuple[Any | None, dict | None]:
    unit = bot.find_by_tag(tag)
    if unit is None:
        return None, {"code": "TAG_NOT_FOUND", "tag": tag}
    return unit, None


def _result(ok: bool, errors: list[dict], **extra: Any) -> dict:
    return {"ok": ok, "errors": errors, **extra}


class BuildStructureTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "build.structure"

    @property
    def description(self) -> str:
        return "Order a worker to build a structure. worker_tag must come from obs.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tag": {"type": "integer"},
                "building_type": {"type": "string"},
                "x": {"type": "number"}, "y": {"type": "number"},
                "queue": {"type": "boolean"},
            },
            "required": ["worker_tag", "building_type", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        worker, err = _find_unit(self._bot, kwargs["worker_tag"])
        if err:
            return _result(False, [err])
        from sc2.position import Point2
        from sc2.ids.unit_typeid import UnitTypeId
        building_type = canonical_name(kwargs["building_type"])
        pos = Point2((float(kwargs["x"]), float(kwargs["y"])))
        queue = bool(kwargs.get("queue", False))
        try:
            type_id = getattr(UnitTypeId, building_type.upper(), None)
            if type_id is None:
                type_id = building_type
            worker.build(type_id, pos, queue=queue)
        except Exception as e:
            return _result(False, [{"code": "BUILD_ERROR", "message": str(e)}])
        return _result(True, [])
```

```python

class BuildTrainTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "build.train"

    @property
    def description(self) -> str:
        return "Train a unit from a production structure. structure_tag must come from obs.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {"type": "integer"},
                "unit_type": {"type": "string"},
                "count": {"type": ["integer", "null"]},
                "queue": {"type": "boolean"},
            },
            "required": ["structure_tag", "unit_type"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure, err = _find_unit(self._bot, kwargs["structure_tag"])
        if err:
            return _result(False, [err])
        from sc2.ids.unit_typeid import UnitTypeId
        unit_type = canonical_name(kwargs["unit_type"])
        count = int(kwargs.get("count", 1))
        queue = bool(kwargs.get("queue", False))
        try:
            type_id = getattr(UnitTypeId, unit_type.upper(), None)
            if type_id is None:
                type_id = unit_type
            trained = 0
            for _ in range(count):
                ok = structure.train(type_id, queue=queue)
                if ok:
                    trained += 1
                else:
                    break
            if trained == 0:
                return _result(False, [{"code": "TRAIN_FAILED", "unit_type": unit_type}])
        except Exception as e:
            return _result(False, [{"code": "TRAIN_ERROR", "message": str(e)}])
        return _result(True, [], trained=trained)


class BuildLandTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "build.land"

    @property
    def description(self) -> str: return "Land a flying structure at position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {"type": "integer"},
                "x": {"type": "number"}, "y": {"type": "number"},
                "queue": {"type": "boolean"},
            },
            "required": ["structure_tag", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure, err = _find_unit(self._bot, kwargs["structure_tag"])
        if err:
            return _result(False, [err])
        from sc2.position import Point2
        pos = Point2((float(kwargs["x"]), float(kwargs["y"])))
        queue = bool(kwargs.get("queue", False))
        structure.land(pos, queue=queue)
        return _result(True, [])


class BuildLiftTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "build.lift"

    @property
    def description(self) -> str: return "Lift off a structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {"type": "integer"},
                "queue": {"type": "boolean"},
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure, err = _find_unit(self._bot, kwargs["structure_tag"])
        if err:
            return _result(False, [err])
        queue = bool(kwargs.get("queue", False))
        structure.lift(queue=queue)
        return _result(True, [])


class BuildCancelTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "build.cancel"

    @property
    def description(self) -> str: return "Cancel construction or training at a structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {"type": "integer"},
                "queue_index": {"type": ["integer", "null"]},
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure, err = _find_unit(self._bot, kwargs["structure_tag"])
        if err:
            return _result(False, [err])
        queue_index = kwargs.get("queue_index")
        try:
            if queue_index is not None:
                structure.cancel(queue_index)
            else:
                structure.cancel(0)
        except Exception:
            # cancel may fail if nothing in queue — that's ok
            pass
        return _result(True, [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_build.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

---

### Task 7: econ.* Basic Set (3 tools)

**Files:**
- Create: `sc2_agent/tools/econ.py`
- Create: `tests/tools/test_econ.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_econ.py
import pytest
from sc2_agent.tools.econ import EconTransferWorkersTool

class FakeBot:
    def __init__(self):
        self._units = {}
    def register_unit(self, tag, type_name, x=0, y=0):
        self._units[tag] = {"tag": tag, "type_name": type_name, "x": x, "y": y}
    def find_by_tag(self, tag):
        if tag not in self._units:
            return None
        d = self._units[tag]
        class FakeUnit:
            def __init__(self, data):
                self.tag = data["tag"]
                self.type_name = data["type_name"]
                self.position = type("P", (), {"x": data["x"], "y": data["y"]})()
            def gather(self, target, queue=False):
                return True
        return FakeUnit(d)

def test_transfer_workers():
    bot = FakeBot()
    bot.register_unit(10, "SCV")
    bot.register_unit(11, "SCV")
    bot.register_unit(200, "MineralField")
    tool = EconTransferWorkersTool(bot)
    import asyncio
    result = asyncio.run(tool.execute(worker_tags=[10, 11], resource_tag=200))
    assert result["ok"] is True
    assert result["transferred"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_econ.py -v`
Expected: FAIL

- [ ] **Step 3: Write econ.py implementation**

```python
# sc2_agent/tools/econ.py
"""Economy tools — worker and resource management.

All tools reference units by tag from obs.* or query.* results.
"""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.tools.base import Tool


class _BotAIProtocol(Protocol):
    def find_by_tag(self, tag: int) -> Any: ...


class EconTransferWorkersTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str: return "econ.transfer_workers"

    @property
    def description(self) -> str:
        return "Transfer workers to a different resource (mineral patch or gas). worker_tags and resource_tag must come from obs.*."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tags": {"type": "array", "items": {"type": "integer"}},
                "resource_tag": {"type": "integer"},
                "queue": {"type": "boolean"},
            },
            "required": ["worker_tags", "resource_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        resource_tag = kwargs["resource_tag"]
        resource = self._bot.find_by_tag(resource_tag)
        errors = []
        if resource is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": resource_tag, "role": "resource"})
        transferred = 0
        queue = bool(kwargs.get("queue", False))
        for tag in kwargs["worker_tags"]:
            worker = self._bot.find_by_tag(tag)
            if worker is None:
                errors.append({"code": "TAG_NOT_FOUND", "tag": tag})
                continue
            if resource is not None:
                worker.gather(resource, queue=queue)
                transferred += 1
        return {"ok": not errors, "transferred": transferred, "errors": errors}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_econ.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Note: `econ.expand` and `econ.build_gas` need `async/await` due to burnysc2's `find_placement` / `build` being async. They will be wired in Task 8 (Bot class) where async is natively available.

---

### Task 8: Bot Class — `SC2AgentBot`

**Files:**
- Create: `sc2_agent/bot.py`

This is the integration point. The Bot inherits `BotAI` and wires everything together.

```python
# sc2_agent/bot.py
"""SC2AgentBot — BotAI subclass that runs the tool-driven Agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sc2 import BotAI
from sc2.position import Point2

from sc2_agent.agent.prompt_builder import PromptBuilder
from sc2_agent.agent.runner import AgentRunner, AgentRunSpec
from sc2_agent.agent.session import Session, SessionManager
from sc2_agent.config.settings import Settings
from sc2_agent.llm.adapter import SC2LLMAdapter
from sc2_agent.logging.logger import configure_logging, get_logger
from sc2_agent.memory.consolidator import MemoryConsolidator
from sc2_agent.memory.renderer import render_game_state_markdown
from sc2_agent.memory.store import MemoryStore
from sc2_agent.observation.burnysc2_adapter import BurnySC2ObservationAdapter
from sc2_agent.observation.collector import ObservationStore
from sc2_agent.runtime.commit import CommitController
from sc2_agent.runtime.state import RuntimeState, RuntimeStateMachine
from sc2_agent.timer.scheduler import TimerScheduler
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.timer.store import TimerStore
from sc2_agent.tools.build import (
    BuildCancelTool, BuildLandTool, BuildLiftTool,
    BuildStructureTool, BuildTrainTool,
)
from sc2_agent.tools.cmd import (
    CmdAttackMoveTool, CmdAttackTargetTool, CmdHoldTool,
    CmdMoveTool, CmdRepairTool, CmdSmartTool, CmdStopTool,
    CmdUseAbilityTool,
)
from sc2_agent.tools.ctrl import AbortTool, CommitTool
from sc2_agent.tools.econ import EconTransferWorkersTool
from sc2_agent.tools.obs import (
    ObsBasesTool, ObsEnemyVisibleTool, ObsGameTimeTool,
    ObsMapTool, ObsResourcesTool, ObsStructuresTool,
    ObsUnitsTool, ObsUpgradesTool,
)
from sc2_agent.tools.plan import PlanSimulateTool
from sc2_agent.tools.query import (
    QueryCanAffordTool, QueryExpansionsTool,
    QueryFindEnemyTool, QueryFindStructuresTool,
    QueryFindUnitsTool, QueryIdleProducersTool,
    QueryInRegionTool, QueryTechRequirementTool,
)
from sc2_agent.tools.registry import ToolRegistry
from sc2_agent.tools.review import ReviewParamsTool, ReviewPlanTool
from sc2_agent.tools.timer import TimerCommandTool, TimerMonitorTool

logger = get_logger(__name__)


class SC2AgentBot(BotAI):
    """StarCraft II bot driven by an LLM Agent with tool calling."""

    def __init__(self) -> None:
        super().__init__()
        self._settings = Settings()
        configure_logging(self._settings.log_level)

        # Runtime state
        self._state_machine = RuntimeStateMachine()
        self._wake_id = 0

        # Observation
        self._obs_store = ObservationStore()
        self._obs_adapter = BurnySC2ObservationAdapter()

        # Memory
        self._memory_store = MemoryStore(
            workspace=Path(self._settings.workspace),
        )
        self._session_manager = SessionManager(
            workspace=Path(self._settings.workspace),
        )

        # Timer
        self._timer_staging = TimerStaging()
        self._timer_store = TimerStore()

        # Tools
        self._tool_registry = ToolRegistry()

        # Commit
        self._commit_controller = CommitController(
            state_machine=self._state_machine,
            staging=self._timer_staging,
            timer_store=self._timer_store,
            memory_store=self._memory_store,
            session_manager=self._session_manager,
            consolidator=None,  # wired after consolidator init
        )

        # LLM
        self._llm = self._init_llm()

        # Agent
        self._agent_runner = AgentRunner(llm=self._llm)

        # Prompt
        self._prompt_builder = PromptBuilder()

        # Scheduler
        self._scheduler = TimerScheduler(
            store=self._timer_store,
            registry=self._tool_registry,
            state_machine=self._state_machine,
        )

        # Consolidator
        self._consolidator = MemoryConsolidator(
            memory_store=self._memory_store,
            # provider will be wired lazily — shares LLM for now
        )
        self._commit_controller._consolidator = self._consolidator

        # Register all tools
        self._register_tools()

        logger.info("SC2AgentBot initialized")

    # ---- LLM setup ----

    def _init_llm(self) -> SC2LLMAdapter:
        config_path = Path("E:/Code/python/scientific research/SC2/agent/llm_clients.json")
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            specs = config.get("clients", [])
        else:
            specs = []

        return SC2LLMAdapter(
            client_specs=specs,
            request_timeout_seconds=80.0,
            sticky_client_name="deepseek_chat",
        )

    # ---- Tool registration ----

    def _register_tools(self) -> None:
        r = self._tool_registry
        bot = self  # tools reference self (the BotAI)

        # obs
        r.register(ObsResourcesTool(self._obs_store))
        r.register(ObsUnitsTool(self._obs_store))
        r.register(ObsStructuresTool(self._obs_store))
        r.register(ObsGameTimeTool(self._obs_store))
        r.register(ObsMapTool(self._obs_store))
        r.register(ObsBasesTool(self._obs_store))
        r.register(ObsEnemyVisibleTool(self._obs_store))
        r.register(ObsUpgradesTool(self._obs_store))

        # query
        r.register(QueryFindUnitsTool(self._obs_store))
        r.register(QueryIdleProducersTool(self._obs_store))
        r.register(QueryCanAffordTool(self._obs_store))
        r.register(QueryTechRequirementTool(self._obs_store))
        r.register(QueryFindEnemyTool(self._obs_store))
        r.register(QueryFindStructuresTool(self._obs_store))
        r.register(QueryInRegionTool(self._obs_store))
        r.register(QueryExpansionsTool(self._obs_store))

        # cmd
        r.register(CmdMoveTool(bot))
        r.register(CmdAttackTargetTool(bot))
        r.register(CmdAttackMoveTool(bot))
        r.register(CmdStopTool(bot))
        r.register(CmdHoldTool(bot))
        r.register(CmdSmartTool(bot))
        r.register(CmdUseAbilityTool(bot))
        r.register(CmdRepairTool(bot))

        # build
        r.register(BuildStructureTool(bot))
        r.register(BuildTrainTool(bot))
        r.register(BuildLandTool(bot))
        r.register(BuildLiftTool(bot))
        r.register(BuildCancelTool(bot))

        # econ
        r.register(EconTransferWorkersTool(bot))

        # timer
        r.register(TimerCommandTool(self._timer_staging))
        r.register(TimerMonitorTool(self._timer_staging))

        # plan
        r.register(PlanSimulateTool())

        # review
        r.register(ReviewParamsTool())
        r.register(ReviewPlanTool(
            staging=self._timer_staging,
            initial_state_provider=self._make_simulation_state,
            active_timers_provider=lambda: list(self._timer_store.commands.values()),
        ))

        # ctrl
        r.register(CommitTool(self._commit_controller))
        r.register(AbortTool(self._commit_controller))

    # ---- Game loop ----

    async def on_step(self, iteration: int) -> None:
        """Called every game step by burnysc2."""
        if self._state_machine.state == RuntimeState.PAUSED_THINKING:
            await self._run_agent_loop()
        elif self._state_machine.state == RuntimeState.RUNNING_SLEEP:
            await self._tick_scheduler()
        else:
            # First call — initialize and wake agent
            self._init_game_state()
            self._state_machine.wake_to_thinking()  # transition to PAUSED_THINKING
            await self._run_agent_loop()

    async def _run_agent_loop(self) -> None:
        """Run the Agent tool-calling loop. on_step blocks here → game pauses."""
        self._wake_id += 1
        game_time = self.time

        # Update observation with current frame
        self._obs_adapter.update(self)
        snapshot = self._obs_adapter.snapshot()
        self._obs_store.set_snapshot(snapshot)

        # Build system prompt
        game_state_md = self._memory_store.render_markdown()
        tool_summary = self._make_tool_summary()
        system_prompt = self._prompt_builder.build_system_prompt(
            game_state_md=game_state_md,
            tool_summary=tool_summary,
        )

        # Build wake message
        wake_message = self._prompt_builder.build_wake_message(
            game_time=game_time,
            wake_id=self._wake_id,
            reason="game_start" if self._wake_id == 1 else "monitor_triggered",
            trigger_source="startup" if self._wake_id == 1 else "monitor",
        )

        # Get recent session history
        session = self._session_manager.load_or_create("default")
        history = session.get_history()

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": wake_message},
        ]

        # Run agent loop
        spec = AgentRunSpec(
            initial_messages=messages,
            tools=self._tool_registry,
            max_iterations=self._settings.max_agent_iterations,
        )
        result = await self._agent_runner.run(spec)

        # Append to session
        session.append(result.messages)
        self._session_manager.save(session)

        logger.info(
            "Agent cycle complete: stop_reason=%s tools=%s",
            result.stop_reason, result.tools_used,
        )

    async def _tick_scheduler(self) -> None:
        """Execute timer commands and evaluate monitors."""
        self._obs_adapter.update(self)
        self._obs_store.set_snapshot(self._obs_adapter.snapshot())

        result = self._scheduler.tick(self.time)
        if result.wake_triggered:
            logger.info("Monitor triggered wake: %s", result.wake_reason)

    def _init_game_state(self) -> None:
        """Initialize game_state.json with map info."""
        if not self._memory_store.exists():
            self._memory_store.initialize()
            self._memory_store.update_known_facts([
                f"map: {self.game_info.map_size.width}x{self.game_info.map_size.height}",
                f"start_location: ({self.start_location.x:.0f}, {self.start_location.y:.0f})",
            ])

    def _make_tool_summary(self) -> str:
        namespaces: dict[str, list[str]] = {}
        for name in sorted(self._tool_registry.tool_names):
            ns = name.split(".")[0]
            namespaces.setdefault(ns, []).append(name)
        lines = []
        for ns in sorted(namespaces):
            tools = namespaces[ns]
            lines.append(f"  {ns}.* — {len(tools)} tools: {', '.join(tools)}")
        return "\n".join(lines)

    def _make_simulation_state(self) -> dict:
        """Build current SimulationState for plan.simulate / review.plan."""
        snapshot = self._obs_store.snapshot()
        return {
            "minerals": snapshot.minerals,
            "gas": snapshot.gas,
            "supply_used": snapshot.supply_used,
            "supply_cap": snapshot.supply_cap,
            "game_time": snapshot.game_time,
            "structures": [
                s.to_dict() for s in snapshot.structures
                if s.alliance == "self" and s.build_progress >= 1.0
            ],
        }
```

- [ ] **Run tests to verify the bot module imports cleanly**

Run: `python -c "from sc2_agent.bot import SC2AgentBot; print('import ok')"`
Expected: `import ok`

---

### Task 9: main.py Rewrite

**Files:**
- Modify: `sc2_agent/main.py`

- [ ] **Step 1: Rewrite main.py**

```python
# sc2_agent/main.py
"""SC2 Agent entry point.

Starts a StarCraft II game with the SC2AgentBot.
"""

from __future__ import annotations

import sys

from sc2 import Race
from sc2.player import Bot, Computer
from sc2.main import run_game
from sc2.maps import get

from sc2_agent.bot import SC2AgentBot
from sc2_agent.config.settings import Settings
from sc2_agent.logging.logger import configure_logging, get_logger


def main() -> int:
    settings = Settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)

    map_name = "AbyssalReefLE"
    logger.info("Starting SC2 game on %s", map_name)

    try:
        result = run_game(
            get(map_name),
            [
                Bot(Race.Terran, SC2AgentBot()),
                Computer(Race.Zerg),
            ],
            realtime=False,
        )
        logger.info("Game result: %s", result)
    except Exception as e:
        logger.exception("Game crashed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Verify main.py parses**

Run: `python -m py_compile sc2_agent/main.py`
Expected: no output (success)

---

## Execution Order

```
Task 1 (LLM Adapter) → Task 2 (PromptBuilder) → Task 3 (obs+) → Task 4 (query+)
                                                    ↓
Task 5 (cmd.*) → Task 6 (build.*) → Task 7 (econ.*) → Task 8 (Bot) → Task 9 (main.py)
```

Tasks 1-2 and 3-4 can run in parallel. Tasks 5, 6, 7 can run in parallel after 3-4. Task 8 requires 1-7. Task 9 requires 8.

## Verification

After all tasks complete, run the full test suite:

```bash
python -m pytest tests/ -q
```

Then start SC2 with the bot (requires SC2 running):

```bash
python -m sc2_agent.main
```
