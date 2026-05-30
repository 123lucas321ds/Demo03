"""Control tools."""

from __future__ import annotations

from typing import Any

from sc2_agent.runtime.commit import CommitController
from sc2_agent.tools.base import Tool
from sc2_agent.tools.registry import ToolRegistry


class CommitTool(Tool):
    read_only = False

    def __init__(self, controller: CommitController) -> None:
        self._controller = controller

    @property
    def name(self) -> str:
        return "ctrl.commit"

    @property
    def description(self) -> str:
        return "Commit the reviewed timer staging and let the game resume."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"staging_hash": {"type": "string", "minLength": 1}},
            "required": ["staging_hash"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        return await self._controller.commit(kwargs["staging_hash"])


class AbortTool(Tool):
    read_only = False

    def __init__(self, controller: CommitController) -> None:
        self._controller = controller

    @property
    def name(self) -> str:
        return "ctrl.abort"

    @property
    def description(self) -> str:
        return "Abort the current paused turn and clear timer staging."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        return self._controller.abort(kwargs["reason"])


class DiscoverToolsTool(Tool):
    read_only = True

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "ctrl.discover_tools"

    @property
    def description(self) -> str:
        return "List currently registered tool schemas or names."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"include_schemas": {"type": "boolean"}},
        }

    async def execute(self, **kwargs: Any) -> Any:
        include_schemas = bool(kwargs.get("include_schemas", False))
        return {
            "tool_names": self._registry.tool_names,
            "schemas": self._registry.schemas() if include_schemas else [],
        }
