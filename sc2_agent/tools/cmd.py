"""Command tools -- execute unit actions by tag."""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.tools.base import Tool

try:
    from sc2.position import Point2
except ImportError:
    Point2 = None  # tests will mock

try:
    from sc2.ids.ability_id import AbilityId
except ImportError:
    AbilityId = None

try:
    from sc2.ids.unit_typeid import UnitTypeId
except ImportError:
    UnitTypeId = None


class _BotAIProtocol(Protocol):
    """Minimal protocol for the bot so tests can use a fake."""

    def find_by_tag(self, tag: int) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_units(
    bot: _BotAIProtocol, tags: list[int]
) -> tuple[list, list]:
    """Resolve unit objects from tags.

    Returns ``(units, errors)`` where *errors* is a list of dicts with
    ``code`` and ``tag`` keys for every tag that could not be resolved.
    """
    units: list = []
    errors: list[dict] = []
    for tag in tags:
        unit = bot.find_by_tag(tag)
        if unit is None:
            errors.append({"code": "TAG_NOT_FOUND", "tag": tag})
        else:
            units.append(unit)
    return units, errors


def _result(ok: bool, success_count: int, errors: list) -> dict:
    """Return a standardised result dict."""
    return {"ok": ok, "success_count": success_count, "errors": errors}


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------


class CmdMoveTool(Tool):
    """Move units to a position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.move"

    @property
    def description(self) -> str:
        return "Move one or more units to a target position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "x": {"type": "number", "description": "Target X coordinate."},
                "y": {"type": "number", "description": "Target Y coordinate."},
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        x: float = kwargs["x"]
        y: float = kwargs["y"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                unit.move(Point2((x, y)), queue=queue)
                success += 1
            except Exception as e:
                errors.append({"code": "EXECUTION_ERROR", "detail": str(e), "tag": unit.tag})
        return _result(True, success, errors)


class CmdAttackTargetTool(Tool):
    """Attack a specific target unit/structure."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.attack_target"

    @property
    def description(self) -> str:
        return "Order one or more units to attack a specific target."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "target_tag": {
                    "type": "integer",
                    "description": "Tag of the target to attack.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "target_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        target_tag: int = kwargs["target_tag"]
        queue: bool = kwargs.get("queue", False)

        target = self._bot.find_by_tag(target_tag)
        if target is None:
            return _result(
                False, 0, [{"code": "TAG_NOT_FOUND", "tag": target_tag}]
            )

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.attack(target, queue=queue)
            success += 1
        return _result(True, success, errors)


class CmdAttackMoveTool(Tool):
    """Attack-move to a position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.attack_move"

    @property
    def description(self) -> str:
        return "Order one or more units to attack-move to a position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "x": {"type": "number", "description": "Target X coordinate."},
                "y": {"type": "number", "description": "Target Y coordinate."},
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        x: float = kwargs["x"]
        y: float = kwargs["y"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                unit.attack(Point2((x, y)), queue=queue)
                success += 1
            except Exception as e:
                errors.append({"code": "EXECUTION_ERROR", "detail": str(e), "tag": unit.tag})
        return _result(True, success, errors)


class CmdStopTool(Tool):
    """Stop units."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.stop"

    @property
    def description(self) -> str:
        return "Order one or more units to stop."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.stop(queue=queue)
            success += 1
        return _result(True, success, errors)


class CmdHoldTool(Tool):
    """Hold position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.hold"

    @property
    def description(self) -> str:
        return "Order one or more units to hold position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.hold_position(queue=queue)
            success += 1
        return _result(True, success, errors)


class CmdSmartTool(Tool):
    """Smart command -- either target a unit or a position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.smart"

    @property
    def description(self) -> str:
        return (
            "Issue a smart command to one or more units. "
            "Provide either target_tag or (x, y)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "target_tag": {
                    "type": ["integer", "null"],
                    "description": "Tag of the target unit/structure.",
                },
                "x": {
                    "type": ["number", "null"],
                    "description": "Target X coordinate.",
                },
                "y": {
                    "type": ["number", "null"],
                    "description": "Target Y coordinate.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        target_tag: int | None = kwargs.get("target_tag")
        x: float | None = kwargs.get("x")
        y: float | None = kwargs.get("y")
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        if target_tag is not None:
            target = self._bot.find_by_tag(target_tag)
            if target is None:
                return _result(
                    False, 0, [{"code": "TAG_NOT_FOUND", "tag": target_tag}]
                )
        elif x is not None and y is not None:
            target = Point2((x, y))
        else:
            return _result(
                False,
                0,
                [{"code": "INVALID_ARGS", "detail": "Provide target_tag or (x, y)."}],
            )

        success = 0
        for unit in units:
            unit.smart(target, queue=queue)
            success += 1
        return _result(True, success, errors)


class CmdUseAbilityTool(Tool):
    """Use an arbitrary ability, optionally targeting a unit or position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.use_ability"

    @property
    def description(self) -> str:
        return (
            "Order one or more units to use an ability by ID. "
            "Optionally provide target_tag or (x, y)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "ability_id": {
                    "type": "integer",
                    "description": "Ability ID to use.",
                },
                "target_tag": {
                    "type": ["integer", "null"],
                    "description": "Tag of the target unit/structure.",
                },
                "x": {
                    "type": ["number", "null"],
                    "description": "Target X coordinate.",
                },
                "y": {
                    "type": ["number", "null"],
                    "description": "Target Y coordinate.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "ability_id"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        ability_id: int = kwargs["ability_id"]
        target_tag: int | None = kwargs.get("target_tag")
        x: float | None = kwargs.get("x")
        y: float | None = kwargs.get("y")
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        target = None
        if target_tag is not None:
            target = self._bot.find_by_tag(target_tag)
            if target is None:
                return _result(
                    False, 0, [{"code": "TAG_NOT_FOUND", "tag": target_tag}]
                )
        elif x is not None and y is not None:
            target = Point2((x, y))

        success = 0
        for unit in units:
            try:
                from sc2.ids.ability_id import AbilityId
                aid = AbilityId(ability_id)
            except (ImportError, ValueError):
                aid = ability_id
            unit(aid, target=target, queue=queue)
            success += 1
        return _result(True, success, errors)


class CmdRepairTool(Tool):
    """Repair a target with SCVs."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.repair"

    @property
    def description(self) -> str:
        return "Order worker units to repair a target structure or unit."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Worker tags to issue the repair command to.",
                },
                "target_tag": {
                    "type": "integer",
                    "description": "Tag of the target to repair.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["worker_tags", "target_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        worker_tags: list[int] = kwargs["worker_tags"]
        target_tag: int = kwargs["target_tag"]
        queue: bool = kwargs.get("queue", False)

        target = self._bot.find_by_tag(target_tag)
        if target is None:
            return _result(
                False, 0, [{"code": "TAG_NOT_FOUND", "tag": target_tag}]
            )

        units, errors = _resolve_units(self._bot, worker_tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.repair(target, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdPatrolTool
# ---------------------------------------------------------------------------


class CmdPatrolTool(Tool):
    """Patrol units between their current position and a target position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.patrol"

    @property
    def description(self) -> str:
        return (
            "Order one or more units to patrol between their "
            "current position and a target position."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "x": {
                    "type": "number",
                    "description": "Patrol target X coordinate.",
                },
                "y": {
                    "type": "number",
                    "description": "Patrol target Y coordinate.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        x: float = kwargs["x"]
        y: float = kwargs["y"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        target = Point2((x, y))
        for unit in units:
            unit.patrol(target, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdLoadTool
# ---------------------------------------------------------------------------


class CmdLoadTool(Tool):
    """Load units into a transport."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.load"

    @property
    def description(self) -> str:
        return "Order one or more units to load into a transport."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to load into the transport.",
                },
                "transport_tag": {
                    "type": "integer",
                    "description": "Tag of the transport unit.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "transport_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        transport_tag: int = kwargs["transport_tag"]
        queue: bool = kwargs.get("queue", False)

        transport = self._bot.find_by_tag(transport_tag)
        if transport is None:
            return _result(
                False, 0, [{"code": "TAG_NOT_FOUND", "tag": transport_tag}]
            )

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.smart(transport, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdUnloadTool
# ---------------------------------------------------------------------------


class CmdUnloadTool(Tool):
    """Unload units from a transport."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.unload"

    @property
    def description(self) -> str:
        return "Unload units from a transport at a position or immediately."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "transport_tag": {
                    "type": "integer",
                    "description": "Tag of the transport to unload.",
                },
                "x": {
                    "type": ["number", "null"],
                    "description": "Target X coordinate to unload at.",
                },
                "y": {
                    "type": ["number", "null"],
                    "description": "Target Y coordinate to unload at.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["transport_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        transport_tag: int = kwargs["transport_tag"]
        x: float | None = kwargs.get("x")
        y: float | None = kwargs.get("y")
        queue: bool = kwargs.get("queue", False)

        transport = self._bot.find_by_tag(transport_tag)
        if transport is None:
            return _result(
                False, 0, [{"code": "TAG_NOT_FOUND", "tag": transport_tag}]
            )

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.UNLOADALLAT
        except ImportError:
            aid = 0
        try:
            if x is not None and y is not None:
                transport(aid, target=Point2((x, y)), queue=queue)
            else:
                transport(aid, queue=queue)
        except Exception as e:
            return _result(False, 0, [{"code": "EXECUTION_ERROR", "detail": str(e)}])
        return _result(True, 1, [])


# ---------------------------------------------------------------------------
# CmdSiegeTool
# ---------------------------------------------------------------------------


class CmdSiegeTool(Tool):
    """Siege a Siege Tank."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.siege"

    @property
    def description(self) -> str:
        return "Order Siege Tanks to enter Siege Mode."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                from sc2.ids.ability_id import AbilityId
                aid = AbilityId.SIEGEMODE_SIEGEMODE
            except ImportError:
                aid = 0
            unit(aid, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdUnsiegeTool
# ---------------------------------------------------------------------------


class CmdUnsiegeTool(Tool):
    """Unsiege a Siege Tank."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.unsiege"

    @property
    def description(self) -> str:
        return "Order Siege Tanks to exit Siege Mode."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                from sc2.ids.ability_id import AbilityId
                aid = AbilityId.UNSIEGE_UNSIEGE
            except ImportError:
                aid = 0
            unit(aid, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdCloakTool
# ---------------------------------------------------------------------------


class CmdCloakTool(Tool):
    """Cloak a unit (e.g. Banshee, Ghost)."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.cloak"

    @property
    def description(self) -> str:
        return "Order one or more units to cloak."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                from sc2.ids.ability_id import AbilityId
                aid = AbilityId.BEHAVIOR_CLOAKON
            except ImportError:
                aid = 0
            unit(aid, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdDecloakTool
# ---------------------------------------------------------------------------


class CmdDecloakTool(Tool):
    """Decloak a cloaked unit."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.decloak"

    @property
    def description(self) -> str:
        return "Order one or more units to decloak."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            try:
                from sc2.ids.ability_id import AbilityId
                aid = AbilityId.BEHAVIOR_CLOAKOFF
            except ImportError:
                aid = 0
            unit(aid, queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdMorphTool
# ---------------------------------------------------------------------------


class CmdMorphTool(Tool):
    """Morph a unit into a different type (Zerg)."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.morph"

    @property
    def description(self) -> str:
        return (
            "Order Zerg units to morph into a different unit type "
            "(e.g. Drone -> building, Larva -> unit)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Unit tags to issue the command to.",
                },
                "morph_target": {
                    "type": "string",
                    "description": (
                        "Target unit type for the morph "
                        "(e.g. 'Baneling', 'Overlord')."
                    ),
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags", "morph_target"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        units, errors = _resolve_units(self._bot, kwargs["tags"])
        morph_target = kwargs["morph_target"]
        queue = bool(kwargs.get("queue", False))
        try:
            from sc2.ids.ability_id import AbilityId
            _MORPH_MAP = {
                "OVERSEER": AbilityId.MORPH_OVERSEER,
                "LURKER": AbilityId.MORPH_LURKER,
                "BROODLORD": AbilityId.MORPHTOBROODLORD_BROODLORD,
                "RAVAGER": AbilityId.MORPHTORAVAGER_RAVAGER,
                "ORBITAL": AbilityId.UPGRADETOORBITAL_ORBITALCOMMAND,
                "PLANETARY": AbilityId.UPGRADETOPLANETARYFORTRESS_PLANETARYFORTRESS,
            }
            aid = _MORPH_MAP.get(morph_target.upper(), None)
        except ImportError:
            aid = None
        if aid is None:
            errors.append({"code": "UNKNOWN_MORPH_TARGET", "morph_target": morph_target})
            return _result(False, 0, errors)
        for unit in units:
            unit(aid, queue=queue)
        return _result(not errors, len(units), errors)


# ---------------------------------------------------------------------------
# CmdReturnCargoTool
# ---------------------------------------------------------------------------


class CmdReturnCargoTool(Tool):
    """Return cargo (workers return minerals/gas)."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.return_cargo"

    @property
    def description(self) -> str:
        return "Order worker units to return their cargo (minerals/gas)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Worker tags to issue the command to.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["tags"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tags: list[int] = kwargs["tags"]
        queue: bool = kwargs.get("queue", False)

        units, errors = _resolve_units(self._bot, tags)
        if errors:
            return _result(False, 0, errors)

        success = 0
        for unit in units:
            unit.return_resource(queue=queue)
            success += 1
        return _result(True, success, errors)


# ---------------------------------------------------------------------------
# CmdCancelOrderTool
# ---------------------------------------------------------------------------


class CmdCancelOrderTool(Tool):
    """Cancel a specific order for a unit."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "cmd.cancel_order"

    @property
    def description(self) -> str:
        return "Cancel a specific order queue slot for a unit."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "integer",
                    "description": "Tag of the unit.",
                },
                "order_index": {
                    "type": ["integer", "null"],
                    "description": (
                        "Index of the order to cancel. Defaults to 0."
                    ),
                },
            },
            "required": ["tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tag: int = kwargs["tag"]
        order_index: int | None = kwargs.get("order_index")

        unit = self._bot.find_by_tag(tag)
        if unit is None:
            return {
                "ok": False,
                "success_count": 0,
                "errors": [{"code": "TAG_NOT_FOUND", "tag": tag}],
            }

        try:
            from sc2.ids.ability_id import AbilityId
            cancel_abilities = [
                AbilityId.CANCELSLOT_QUEUE1,
                AbilityId.CANCELSLOT_QUEUE5,
            ]
            idx = max(0, min((order_index or 0), len(cancel_abilities) - 1))
            aid = cancel_abilities[idx]
        except ImportError:
            aid = 0
        unit(aid, queue=True)

        return {"ok": True, "success_count": 1, "errors": []}
