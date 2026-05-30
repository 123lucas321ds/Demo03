"""Squad management tools — create, modify, and command groups of units."""

from __future__ import annotations

from itertools import count
from typing import Any, Protocol

from sc2_agent.tools.base import Tool


class _BotAIProtocol(Protocol):
    def find_by_tag(self, tag: int) -> Any: ...


_cid = count(1)


class SquadCreateTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol, squads: dict[str, list[int]] | None = None) -> None:
        self._bot = bot
        self._squads = squads if squads is not None else {}

    @property
    def name(self) -> str:
        return "squad.create"

    @property
    def description(self) -> str:
        return "Create a named squad from unit tags."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["name", "tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs["name"]
        tags = kwargs["tags"]
        valid = [t for t in tags if self._bot.find_by_tag(t) is not None]
        self._squads[name] = valid
        return {"ok": True, "squad_name": name, "member_count": len(valid), "missing": len(tags) - len(valid)}


class SquadAddTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol, squads: dict[str, list[int]]) -> None:
        self._bot = bot
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.add"

    @property
    def description(self) -> str:
        return "Add units to an existing squad."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "squad_name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["squad_name", "tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs["squad_name"]
        if name not in self._squads:
            return {"ok": False, "code": "SQUAD_NOT_FOUND", "squad_name": name}
        tags = kwargs["tags"]
        valid = [t for t in tags if self._bot.find_by_tag(t) is not None]
        self._squads[name].extend(valid)
        return {"ok": True, "added": len(valid)}


class SquadRemoveTool(Tool):
    read_only = False

    def __init__(self, squads: dict[str, list[int]]) -> None:
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.remove"

    @property
    def description(self) -> str:
        return "Remove specific tags from a squad."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "squad_name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["squad_name", "tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs["squad_name"]
        if name not in self._squads:
            return {"ok": False, "code": "SQUAD_NOT_FOUND"}
        tags = set(kwargs["tags"])
        self._squads[name] = [t for t in self._squads[name] if t not in tags]
        return {"ok": True}


class SquadDisbandTool(Tool):
    read_only = False

    def __init__(self, squads: dict[str, list[int]]) -> None:
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.disband"

    @property
    def description(self) -> str:
        return "Disband an entire squad."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"squad_name": {"type": "string"}},
            "required": ["squad_name"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs["squad_name"]
        if name not in self._squads:
            return {"ok": False, "code": "SQUAD_NOT_FOUND"}
        del self._squads[name]
        return {"ok": True}


class SquadOrderTool(Tool):
    read_only = False

    def __init__(self, bot: _BotAIProtocol, squads: dict[str, list[int]]) -> None:
        self._bot = bot
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.order"

    @property
    def description(self) -> str:
        return "Issue an order to all members of a squad."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "squad_name": {"type": "string"},
                "order": {"type": "string", "enum": ["move", "attack_move", "stop", "hold"]},
                "x": {"type": ["number", "null"]},
                "y": {"type": ["number", "null"]},
                "target_tag": {"type": ["integer", "null"]},
                "queue": {"type": "boolean"},
            },
            "required": ["squad_name", "order"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        name = kwargs["squad_name"]
        if name not in self._squads:
            return {"ok": False, "code": "SQUAD_NOT_FOUND"}
        tags = self._squads[name]
        order = kwargs["order"]
        queue = bool(kwargs.get("queue", False))
        from sc2.position import Point2

        target = None
        if kwargs.get("target_tag") is not None:
            target = self._bot.find_by_tag(kwargs["target_tag"])
        elif kwargs.get("x") is not None and kwargs.get("y") is not None:
            target = Point2((float(kwargs["x"]), float(kwargs["y"])))

        count = 0
        for tag in tags:
            unit = self._bot.find_by_tag(tag)
            if unit is None:
                continue
            if order == "move" and target is not None:
                unit.move(target, queue=queue)
            elif order == "attack_move" and target is not None:
                unit.attack(target, queue=queue)
            elif order == "stop":
                unit.stop(queue=queue)
            elif order == "hold":
                unit.hold_position(queue=queue)
            count += 1
        return {"ok": True, "ordered": count}


class SquadListTool(Tool):
    """List all squads and their member counts."""
    read_only = True

    def __init__(self, squads: dict[str, list[int]]) -> None:
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.list"

    @property
    def description(self) -> str:
        return "List all current squads with their names and member counts."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        result = {
            name: {"count": len(tags), "tags": tags}
            for name, tags in self._squads.items()
        }
        return {"squads": result, "total": len(result)}


class SquadAutoBalanceTool(Tool):
    """Evenly distribute members across all existing squads."""
    read_only = False

    def __init__(self, squads: dict[str, list[int]]) -> None:
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.auto_balance"

    @property
    def description(self) -> str:
        return "Evenly redistribute all unit tags across all existing squads."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> Any:
        if not self._squads:
            return {"ok": False, "code": "NO_SQUADS", "message": "No squads exist"}
        all_tags = []
        for tags in self._squads.values():
            all_tags.extend(tags)
        n = len(self._squads)
        for i, name in enumerate(self._squads):
            self._squads[name] = all_tags[i::n]
        return {"ok": True, "squad_count": n, "total_members": len(all_tags)}


class SquadSetCountTool(Tool):
    """Adjust squad count and redistribute members."""
    read_only = False

    def __init__(self, squads: dict[str, list[int]]) -> None:
        self._squads = squads

    @property
    def name(self) -> str:
        return "squad.set_count"

    @property
    def description(self) -> str:
        return "Set the number of squads to n, auto-balancing members."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1}},
            "required": ["n"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        n = kwargs["n"]
        all_tags = []
        for tags in self._squads.values():
            all_tags.extend(tags)
        old_names = list(self._squads.keys())
        self._squads.clear()
        for i in range(n):
            name = old_names[i] if i < len(old_names) else f"squad_{i+1}"
            self._squads[name] = all_tags[i::n]
        return {"ok": True, "squad_count": n, "total_members": len(all_tags)}
