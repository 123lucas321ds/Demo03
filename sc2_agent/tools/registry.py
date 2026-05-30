"""Tool registry and execution policy."""

from __future__ import annotations

import asyncio
from typing import Any

from sc2_agent.models import Result
from sc2_agent.tools.base import Tool, ToolCall


class ToolRegistry:
    """Registry for schema-validated tools with progressive namespace disclosure."""

    # Namespaces always visible in every LLM call.
    _DEFAULT_ACTIVE: set[str] = {"ctrl"}

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._active_namespaces: set[str] = set(self._DEFAULT_ACTIVE)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def activate_namespace(self, namespace: str) -> int:
        """Mark a namespace as active and return how many tools were added."""
        if namespace in self._active_namespaces:
            return 0
        self._active_namespaces.add(namespace)
        return sum(1 for name in self._tools if name.startswith(namespace + "."))

    def schemas(self) -> list[dict[str, Any]]:
        """Return schemas for tools in active namespaces only."""
        return [
            tool.to_schema()
            for name, tool in self._tools.items()
            if name.split(".", 1)[0] in self._active_namespaces
        ]

    async def execute(self, name: str, arguments: dict[str, Any] | None = None) -> Result:
        """Execute one tool with schema cast and validation."""

        tool = self._tools.get(name)
        if tool is None:
            return Result.failure(
                "TOOL_NOT_FOUND",
                f"Tool {name!r} not found",
                available=self.tool_names,
            )

        args = arguments or {}
        try:
            args = tool.cast_params(args)
            errors = tool.validate_params(args)
            if errors:
                return Result.failure(
                    "INVALID_ARGUMENT",
                    f"Invalid parameters for {name!r}: " + "; ".join(errors),
                    errors=errors,
                )
            data = await tool.execute(**args)
            if isinstance(data, Result):
                return data
            if isinstance(data, dict) and isinstance(data.get("ok"), bool):
                payload = dict(data)
                ok = bool(payload.pop("ok"))
                errors = payload.pop("errors", None)
                if ok:
                    if errors is not None:
                        payload["errors"] = errors
                    return Result.success(payload)
                code = self._failure_code(payload, errors)
                error = self._failure_error(code, payload, errors)
                meta = dict(payload)
                meta.pop("code", None)
                meta.pop("error", None)
                meta.pop("message", None)
                meta.pop("reason", None)
                if errors is not None:
                    meta["errors"] = errors
                return Result.failure(code, error, **meta)
            return Result.success(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return Result.failure("TOOL_EXECUTION_ERROR", str(exc), tool=name)

    async def execute_calls(self, calls: list[ToolCall]) -> list[Result]:
        """Execute a batch of tool calls with read/write ordering rules.

        - ctrl.commit must be the only call in its batch.
        - Read-only calls may run concurrently.
        - Any batch containing a write call executes serially in model order.
        """

        if any(call.name == "ctrl.commit" for call in calls) and len(calls) != 1:
            return [
                Result.failure(
                    "COMMIT_MUST_BE_SOLE_TOOL_CALL",
                    "ctrl.commit must be the only tool_call in the final iteration",
                    tool=call.name,
                )
                for call in calls
            ]

        tools = [self._tools.get(call.name) for call in calls]
        if all(tool is not None and tool.read_only for tool in tools):
            return await asyncio.gather(*(self.execute(call.name, call.arguments) for call in calls))

        results: list[Result] = []
        for call in calls:
            results.append(await self.execute(call.name, call.arguments))
        return results

    def __len__(self) -> int:
        return len(self._tools)

    @staticmethod
    def _failure_code(payload: dict[str, Any], errors: Any) -> str:
        if payload.get("code"):
            return str(payload["code"])
        if payload.get("reason"):
            return str(payload["reason"])
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict) and first.get("code"):
                return str(first["code"])
        return "TOOL_REPORTED_FAILURE"

    @staticmethod
    def _failure_error(code: str, payload: dict[str, Any], errors: Any) -> str:
        if payload.get("error"):
            return str(payload["error"])
        if payload.get("message"):
            return str(payload["message"])
        if isinstance(errors, list) and errors:
            return f"Tool reported failure {code}: {errors}"
        return f"Tool reported failure {code}"
