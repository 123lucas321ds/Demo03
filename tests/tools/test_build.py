"""Tests for build tools."""

import asyncio
from unittest import mock

# Provide a stand-in for Point2 so the tool code can call Point2((x, y))
# even when burnysc2 is not installed.
import sc2_agent.tools.build as _build_mod


class _FakePoint2:
    """Duck-typed stand-in for ``sc2.position.Point2``."""

    def __init__(self, pos):
        self.x, self.y = pos[0], pos[1]

    def __repr__(self):
        return f"_FakePoint2({self.x}, {self.y})"


_build_mod.Point2 = _FakePoint2


from sc2_agent.tools.build import (  # noqa: E402
    BuildStructureTool,
    BuildTrainTool,
    BuildLandTool,
    BuildLiftTool,
    BuildCancelTool,
)


class FakeUnit:
    def __init__(self, tag, type_name, x=0, y=0):
        self.tag = tag
        self.type_name = type_name
        self.position = type("P", (), {"x": x, "y": y})()

    def train(self, unit_type, queue=False, can_afford_check=False):
        self._last_train = (unit_type, queue)
        return True

    def build(self, unit_type, position, queue=False, can_afford_check=False):
        self._last_build = (unit_type, position)
        return True

    def land(self, position, queue=False):
        return True

    def lift(self, queue=False):
        return True

    def cancel(self, queue_index):
        pass

    def __call__(self, ability_id, target=None, queue=False):
        return True


class FakeBot:
    def __init__(self):
        self._units = {}

    def register_unit(self, tag, type_name, x=0, y=0):
        self._units[tag] = FakeUnit(tag, type_name, x, y)

    def find_by_tag(self, tag):
        return self._units.get(tag)


# ---------------------------------------------------------------------------
# BuildTrainTool
# ---------------------------------------------------------------------------


def test_build_train_by_structure_tag():
    bot = FakeBot()
    bot.register_unit(88, "Barracks", x=30, y=30)
    tool = BuildTrainTool(bot)
    result = asyncio.run(tool.execute(structure_tag=88, unit_type="Marine"))
    assert result["ok"] is True


def test_build_train_bad_tag():
    bot = FakeBot()
    tool = BuildTrainTool(bot)
    result = asyncio.run(tool.execute(structure_tag=999, unit_type="Marine"))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# BuildStructureTool
# ---------------------------------------------------------------------------


def test_build_structure():
    bot = FakeBot()
    bot.register_unit(10, "SCV", x=30, y=30)
    tool = BuildStructureTool(bot)
    result = asyncio.run(
        tool.execute(
            worker_tag=10, building_type="SupplyDepot", x=35.0, y=35.0
        )
    )
    assert result["ok"] is True


def test_build_structure_bad_worker():
    bot = FakeBot()
    tool = BuildStructureTool(bot)
    result = asyncio.run(
        tool.execute(
            worker_tag=999, building_type="SupplyDepot", x=35.0, y=35.0
        )
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# BuildLandTool
# ---------------------------------------------------------------------------


def test_build_land():
    bot = FakeBot()
    bot.register_unit(200, "CommandCenter")
    tool = BuildLandTool(bot)
    result = asyncio.run(tool.execute(structure_tag=200, x=50.0, y=50.0))
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# BuildLiftTool
# ---------------------------------------------------------------------------


def test_build_lift():
    bot = FakeBot()
    bot.register_unit(200, "CommandCenter")
    tool = BuildLiftTool(bot)
    result = asyncio.run(tool.execute(structure_tag=200))
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# BuildCancelTool
# ---------------------------------------------------------------------------


def test_build_cancel():
    bot = FakeBot()
    bot.register_unit(88, "Barracks")
    tool = BuildCancelTool(bot)
    result = asyncio.run(tool.execute(structure_tag=88))
    assert result["ok"] is True
