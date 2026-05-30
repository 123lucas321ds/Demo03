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
        return (
            "Activate a tool namespace and return its tool schemas. "
            "Available namespaces: build, cmd, econ, squad, plan, review, hist. "
            "obs, query, ctrl, timer are always active."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to activate (e.g. 'build', 'plan', 'review').",
                },
            },
            "required": ["namespace"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        namespace = kwargs["namespace"]
        added = self._registry.activate_namespace(namespace)
        ns_tools = [n for n in self._registry.tool_names if n.startswith(namespace + ".")]
        return {
            "namespace": namespace,
            "activated": added > 0,
            "tool_count": len(ns_tools),
            "tools": ns_tools,
            "schemas": [self._registry.get(n).to_schema() for n in ns_tools if self._registry.get(n)],
        }
