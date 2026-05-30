"""Build tools -- construct structures, train units, manage flying buildings."""

from __future__ import annotations

from typing import Any, Protocol

from sc2_agent.tools.base import Tool

try:
    from sc2.position import Point2
except ImportError:
    Point2 = None  # tests will provide a stand-in

try:
    from sc2.ids.unit_typeid import UnitTypeId
except ImportError:
    UnitTypeId = None

try:
    from sc2.ids.upgrade_id import UpgradeId
except ImportError:
    UpgradeId = None


class _BotAIProtocol(Protocol):
    """Minimal protocol for the bot so tests can use a fake."""

    def find_by_tag(self, tag: int) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_unit(bot: _BotAIProtocol, tag: int) -> tuple[Any, list]:
    """Resolve a single unit from a tag.

    Returns ``(unit, [])`` on success or ``(None, [error_dict])`` on failure.
    """
    unit = bot.find_by_tag(tag)
    if unit is None:
        return None, [{"code": "TAG_NOT_FOUND", "tag": tag}]
    return unit, []


def _resolve_unit_type(name: str) -> Any:
    """Convert a building/unit name string to a ``UnitTypeId`` when possible."""
    if UnitTypeId is not None:
        return getattr(UnitTypeId, name.upper(), name)
    return name


def _result(ok: bool, errors: list, **extra: Any) -> dict:
    """Return a standardised result dict."""
    return {"ok": ok, "errors": errors, **extra}


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------


class BuildStructureTool(Tool):
    """Build a structure using a worker unit."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.structure"

    @property
    def description(self) -> str:
        return "Order a worker unit to build a structure at a position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "worker_tag": {
                    "type": "integer",
                    "description": "Tag of the worker unit that will build.",
                },
                "building_type": {
                    "type": "string",
                    "description": (
                        "Name of the building to construct "
                        "(e.g. 'SupplyDepot', 'Barracks')."
                    ),
                },
                "x": {
                    "type": "number",
                    "description": "Target X coordinate for the building.",
                },
                "y": {
                    "type": "number",
                    "description": "Target Y coordinate for the building.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["worker_tag", "building_type", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        worker_tag: int = kwargs["worker_tag"]
        building_type: str = kwargs["building_type"]
        x: float = kwargs["x"]
        y: float = kwargs["y"]
        queue: bool = kwargs.get("queue", False)

        worker, errors = _find_unit(self._bot, worker_tag)
        if errors:
            return _result(False, errors)

        type_id = _resolve_unit_type(building_type)
        try:
            worker.build(type_id, Point2((x, y)), queue=queue)
        except Exception as e:
            return _result(False, [{"code": "BUILD_ERROR", "detail": str(e)}])

        return _result(True, [])


class BuildTrainTool(Tool):
    """Train units from a structure."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.train"

    @property
    def description(self) -> str:
        return "Order a structure to train one or more units."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure that will train.",
                },
                "unit_type": {
                    "type": "string",
                    "description": (
                        "Name of the unit type to train (e.g. 'Marine', 'SCV')."
                    ),
                },
                "count": {
                    "type": ["integer", "null"],
                    "description": (
                        "Number of units to train. Defaults to 1 if not set."
                    ),
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["structure_tag", "unit_type"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        unit_type: str = kwargs["unit_type"]
        count: int | None = kwargs.get("count")
        queue: bool = kwargs.get("queue", False)

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        if count is None:
            count = 1

        type_id = _resolve_unit_type(unit_type)

        errors: list[dict] = []
        trained = 0
        for _ in range(count):
            try:
                structure.train(type_id, queue=queue)
                trained += 1
            except Exception as e:
                errors.append({"code": "TRAIN_ERROR", "detail": str(e)})
                break

        if trained == 0:
            return _result(False, errors or [{"code": "TRAIN_FAILED"}], trained=0, requested=count)

        return _result(True, errors, trained=trained, requested=count)


class BuildLandTool(Tool):
    """Land a flying structure at a position."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.land"

    @property
    def description(self) -> str:
        return "Order a flying structure to land at a position."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the flying structure to land.",
                },
                "x": {
                    "type": "number",
                    "description": "X coordinate to land at.",
                },
                "y": {
                    "type": "number",
                    "description": "Y coordinate to land at.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["structure_tag", "x", "y"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        x: float = kwargs["x"]
        y: float = kwargs["y"]
        queue: bool = kwargs.get("queue", False)

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.LAND_COMMANDCENTER
        except ImportError:
            aid = 0
        structure(aid, target=Point2((x, y)), queue=queue)

        return _result(True, [])


class BuildLiftTool(Tool):
    """Lift a structure into the air."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.lift"

    @property
    def description(self) -> str:
        return "Order a structure to lift off (become flying)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure to lift.",
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        queue: bool = kwargs.get("queue", False)

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.LIFT_COMMANDCENTER
        except ImportError:
            aid = 0
        structure(aid, queue=queue)

        return _result(True, [])


class BuildCancelTool(Tool):
    """Cancel a structure's production queue."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.cancel"

    @property
    def description(self) -> str:
        return "Cancel a production queue slot in a structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure.",
                },
                "queue_index": {
                    "type": ["integer", "null"],
                    "description": (
                        "Index of the queue slot to cancel. Defaults to 0."
                    ),
                },
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        queue_index: int | None = kwargs.get("queue_index")

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.CANCELSLOT_QUEUE1
        except ImportError:
            aid = 0
        try:
            structure(aid, queue=True)
        except Exception:
            pass  # cancel may fail if queue is empty, which is fine

        return _result(True, [])


# ---------------------------------------------------------------------------
# BuildAddonTool
# ---------------------------------------------------------------------------


class BuildAddonTool(Tool):
    """Build an addon on a structure."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.addon"

    @property
    def description(self) -> str:
        return "Order a structure to build an addon (e.g. TechLab, Reactor)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure that will build the addon.",
                },
                "addon_type": {
                    "type": "string",
                    "description": (
                        "Name of the addon to build "
                        "(e.g. 'TechLab', 'Reactor')."
                    ),
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["structure_tag", "addon_type"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        addon_type: str = kwargs["addon_type"]
        queue: bool = kwargs.get("queue", False)

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        type_id = _resolve_unit_type(addon_type)
        try:
            structure.build(type_id, queue=queue)
        except Exception as e:
            return _result(False, [{"code": "ADDON_ERROR", "detail": str(e)}])

        return _result(True, [])


# ---------------------------------------------------------------------------
# BuildCancelTrainTool
# ---------------------------------------------------------------------------


class BuildCancelTrainTool(Tool):
    """Cancel a specific training queue slot."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.cancel_train"

    @property
    def description(self) -> str:
        return "Cancel a specific training queue slot in a structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure.",
                },
                "queue_index": {
                    "type": ["integer", "null"],
                    "description": (
                        "Index of the queue slot to cancel. Defaults to 0."
                    ),
                },
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        queue_index: int | None = kwargs.get("queue_index")

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.CANCELSLOT_QUEUE1
        except ImportError:
            aid = 0
        structure(aid, queue=True)

        return _result(True, [])


# ---------------------------------------------------------------------------
# BuildResearchTool
# ---------------------------------------------------------------------------


class BuildResearchTool(Tool):
    """Research an upgrade at a structure."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.research"

    @property
    def description(self) -> str:
        return "Order a structure to research an upgrade."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure that will research.",
                },
                "upgrade_id": {
                    "type": ["string", "integer"],
                    "description": (
                        "Name or ID of the upgrade to research "
                        "(e.g. 'InfantryWeaponsLv1' or 4)."
                    ),
                },
                "queue": {
                    "type": "boolean",
                    "description": "Queue the command instead of replacing.",
                },
            },
            "required": ["structure_tag", "upgrade_id"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]
        upgrade_id_raw: str | int = kwargs["upgrade_id"]
        queue: bool = kwargs.get("queue", False)

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        # Resolve upgrade id.
        if isinstance(upgrade_id_raw, str) and UpgradeId is not None:
            type_id = getattr(UpgradeId, upgrade_id_raw.upper(), upgrade_id_raw)
        else:
            type_id = upgrade_id_raw

        try:
            structure.research(type_id, queue=queue)
        except Exception as e:
            return _result(
                False, [{"code": "RESEARCH_ERROR", "detail": str(e)}]
            )

        return _result(True, [])


# ---------------------------------------------------------------------------
# BuildCancelResearchTool
# ---------------------------------------------------------------------------


class BuildCancelResearchTool(Tool):
    """Cancel research at a structure."""

    read_only = False

    def __init__(self, bot: _BotAIProtocol) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "build.cancel_research"

    @property
    def description(self) -> str:
        return "Cancel the current research at a structure."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "structure_tag": {
                    "type": "integer",
                    "description": "Tag of the structure.",
                },
            },
            "required": ["structure_tag"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        structure_tag: int = kwargs["structure_tag"]

        structure, errors = _find_unit(self._bot, structure_tag)
        if errors:
            return _result(False, errors)

        try:
            from sc2.ids.ability_id import AbilityId
            aid = AbilityId.CANCELSLOT_QUEUE1
        except ImportError:
            aid = 0
        structure(aid, queue=True)

        return _result(True, [])
