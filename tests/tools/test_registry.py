from __future__ import annotations

import asyncio
from typing import Any

from sc2_agent.tools.base import Tool, ToolCall
from sc2_agent.tools.ctrl import DiscoverToolsTool
from sc2_agent.tools.registry import ToolRegistry


class RecordingTool(Tool):
    def __init__(self, name: str, events: list[str], *, read_only: bool = True, delay: float = 0.0):
        self._name = name
        self._events = events
        self.read_only = read_only
        self._delay = delay

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} test tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
        }

    async def execute(self, **kwargs: Any) -> str:
        self._events.append(f"start:{self.name}")
        if self._delay:
            await asyncio.sleep(self._delay)
        self._events.append(f"end:{self.name}")
        return f"{self.name}:{kwargs['value']}"


class DictFailureTool(Tool):
    read_only = False

    @property
    def name(self) -> str:
        return "cmd.fail"

    @property
    def description(self) -> str:
        return "dict failure"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "errors": [{"code": "TAG_NOT_FOUND", "tag": 7}], "extra": "kept"}


def test_execute_unknown_tool() -> None:
    result = asyncio.run(ToolRegistry().execute("missing", {}))

    assert not result.ok
    assert result.code == "TOOL_NOT_FOUND"


def test_execute_validates_arguments() -> None:
    registry = ToolRegistry()
    registry.register(RecordingTool("sample", []))

    result = asyncio.run(registry.execute("sample", {}))

    assert not result.ok
    assert result.code == "INVALID_ARGUMENT"


def test_execute_casts_and_runs_tool() -> None:
    registry = ToolRegistry()
    registry.register(RecordingTool("sample", []))

    result = asyncio.run(registry.execute("sample", {"value": "7"}))

    assert result.ok
    assert result.data == "sample:7"


def test_execute_converts_standard_failure_dict_to_failed_result() -> None:
    registry = ToolRegistry()
    registry.register(DictFailureTool())

    result = asyncio.run(registry.execute("cmd.fail", {}))

    assert not result.ok
    assert result.code == "TAG_NOT_FOUND"
    assert "TAG_NOT_FOUND" in result.error
    assert result.meta["errors"] == [{"code": "TAG_NOT_FOUND", "tag": 7}]
    assert result.meta["extra"] == "kept"


def test_read_only_calls_run_concurrently() -> None:
    events: list[str] = []
    registry = ToolRegistry()
    registry.register(RecordingTool("a", events, read_only=True, delay=0.03))
    registry.register(RecordingTool("b", events, read_only=True, delay=0.01))

    results = asyncio.run(registry.execute_calls([
        ToolCall(id="1", name="a", arguments={"value": 1}),
        ToolCall(id="2", name="b", arguments={"value": 2}),
    ]))

    assert [r.ok for r in results] == [True, True]
    assert events[:2] == ["start:a", "start:b"]


def test_write_calls_run_serially_in_model_order() -> None:
    events: list[str] = []
    registry = ToolRegistry()
    registry.register(RecordingTool("a", events, read_only=False, delay=0.01))
    registry.register(RecordingTool("b", events, read_only=False, delay=0.01))

    results = asyncio.run(registry.execute_calls([
        ToolCall(id="1", name="a", arguments={"value": 1}),
        ToolCall(id="2", name="b", arguments={"value": 2}),
    ]))

    assert [r.ok for r in results] == [True, True]
    assert events == ["start:a", "end:a", "start:b", "end:b"]


def test_commit_must_be_sole_tool_call() -> None:
    events: list[str] = []
    registry = ToolRegistry()
    registry.register(RecordingTool("ctrl.commit", events, read_only=False))
    registry.register(RecordingTool("obs.resources", events, read_only=True))

    results = asyncio.run(registry.execute_calls([
        ToolCall(id="1", name="ctrl.commit", arguments={"value": 1}),
        ToolCall(id="2", name="obs.resources", arguments={"value": 2}),
    ]))

    assert [r.ok for r in results] == [False, False]
    assert all(r.code == "COMMIT_MUST_BE_SOLE_TOOL_CALL" for r in results)
    assert events == []


def test_discover_tools_lists_registered_names_and_optional_schemas() -> None:
    registry = ToolRegistry()
    registry.register(RecordingTool("obs.echo", []))
    registry.register(DiscoverToolsTool(registry))

    names = asyncio.run(registry.execute("ctrl.discover_tools", {"include_schemas": False}))
    schemas = asyncio.run(registry.execute("ctrl.discover_tools", {"include_schemas": True}))

    assert names.ok
    assert names.data["tool_names"] == ["obs.echo", "ctrl.discover_tools"]
    assert names.data["schemas"] == []
    assert schemas.data["schemas"][0]["function"]["name"] == "obs.echo"
