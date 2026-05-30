"""Economic tools -- manage workers and resource gathering."""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.tools.base import Tool


class _BotAIProtocol(Protocol):
    """Minimal protocol for the bot so tests can use a fake."""

    def find_by_tag(self, tag: int) -> Any: ...


class EconTransferWorkersTool(Tool):
    """Transfer workers to gather from a specific resource."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "econ.transfer_workers"

    @property
    def description(self) -> str:
        return (
            "Transfer workers to gather from a specific resource. "
            "Use query.find_workers to get worker tags first. "
            "For cross-base bulk transfer, use econ.set_mining instead."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Tags of the workers to transfer.",
                },
                "resource_tag": {
                    "type": "integer",
                    "description": "Tag of the resource to gather from.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the gather command instead of replacing.",
                },
            },
            "required": ["worker_tags", "resource_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        worker_tags: list[int] = kwargs["worker_tags"]
        resource_tag: int = kwargs["resource_tag"]
        queue: bool = kwargs.get("queue", False)

        # Resolve the target resource.
        resource = self._bot.find_by_tag(resource_tag)
        errors: list[dict] = []
        if resource is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": resource_tag})

        transferred = 0
        for tag in worker_tags:
            worker = self._bot.find_by_tag(tag)
            if worker is None:
                errors.append({"code": "TAG_NOT_FOUND", "tag": tag})
                continue
            # If the resource was not resolved, skip gathering but still
            # check remaining workers (best-effort behaviour).
            if resource is None:
                continue
            worker.gather(resource, queue=queue)
            transferred += 1

        return {"ok": transferred > 0, "transferred": transferred, "errors": errors}


class EconExpandTool(Tool):
    """Build a Command Center at the next expansion location."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "econ.expand"

    @property
    def description(self) -> str:
        return "Build a Command Center at the next available expansion location."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        try:
            if hasattr(self._bot, "expand_now"):
                await self._bot.expand_now()
                return {"ok": True}
            return {"ok": False, "code": "NOT_SUPPORTED", "error": "expand_now not available"}
        except Exception as exc:
            return {"ok": False, "code": "EXPAND_FAILED", "error": str(exc)}


class EconBuildGasTool(Tool):
    """Build a Refinery on a vespene geyser."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "econ.build_gas"

    @property
    def description(self) -> str:
        return "Build a Refinery on the specified vespene geyser."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "geyser_tag": {"type": "integer", "description": "Tag of the vespene geyser."},
                "worker_tag": {"type": ["integer", "null"], "description": "Optional specific worker tag."},
            },
            "required": ["geyser_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        geyser_tag = kwargs["geyser_tag"]
        geyser = self._bot.find_by_tag(geyser_tag)
        if geyser is None:
            return {"ok": False, "code": "TAG_NOT_FOUND", "tag": geyser_tag}

        worker_tag = kwargs.get("worker_tag")
        worker = None
        if worker_tag is not None:
            worker = self._bot.find_by_tag(worker_tag)
            if worker is None:
                return {"ok": False, "code": "TAG_NOT_FOUND", "tag": worker_tag}

        try:
            if worker is not None:
                worker.build_gas(geyser)
            elif hasattr(self._bot, "do") and hasattr(self._bot, "workers"):
                w = self._bot.workers.closest_to(geyser.position)
                if w:
                    w.build_gas(geyser)
                else:
                    return {"ok": False, "code": "NO_WORKER_AVAILABLE"}
            else:
                return {"ok": False, "code": "NO_WORKER_AVAILABLE"}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "code": "BUILD_GAS_FAILED", "error": str(exc)}


class EconGatherTool(Tool):
    """Gather from a specific resource with worker units."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "econ.gather"

    @property
    def description(self) -> str:
        return "Order workers to gather from a specific resource."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Tags of the workers to issue the gather command to.",
                },
                "resource_tag": {
                    "type": "integer",
                    "description": "Tag of the resource to gather from.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the gather command instead of replacing.",
                },
            },
            "required": ["worker_tags", "resource_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        worker_tags: list[int] = kwargs["worker_tags"]
        resource_tag: int = kwargs["resource_tag"]
        queue: bool = kwargs.get("queue", False)

        # Resolve the target resource.
        resource = self._bot.find_by_tag(resource_tag)
        errors: list[dict] = []
        if resource is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": resource_tag})

        gathered = 0
        for tag in worker_tags:
            worker = self._bot.find_by_tag(tag)
            if worker is None:
                errors.append({"code": "TAG_NOT_FOUND", "tag": tag})
                continue
            # If the resource was not resolved, skip gathering but still
            # check remaining workers (best-effort behaviour).
            if resource is None:
                continue
            worker.gather(resource, queue=queue)
            gathered += 1

        return {"ok": gathered > 0, "gathered": gathered, "errors": errors}


class EconSetMiningTool(Tool):
    """Adjust gas worker count at a base."""
    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "econ.set_mining"

    @property
    def description(self) -> str:
        return "Adjust the number of workers assigned to gas at a base."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_id": {"type": "integer", "description": "Tag of the townhall at this base."},
                "gas_count": {"type": ["integer", "null"], "description": "Desired workers per gas. Default 3."},
            },
            "required": ["base_id"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        # Simplified: return not-yet-implemented for now
        return {"ok": False, "code": "NOT_IMPLEMENTED", "message": "Full implementation requires burnysc2 gas assignment API"}
