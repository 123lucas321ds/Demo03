"""Tests for command tools (cmd.*)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

# sc2 is not installed in this test environment, so cmd.Point2 will be None
# after import.  We replace it with a simple callable so that the tools can
# construct position objects at runtime.
import sc2_agent.tools.cmd as _cmd_mod

_cmd_mod.Point2 = lambda pos: type("Point2", (), {"x": pos[0], "y": pos[1]})()

from sc2_agent.tools.cmd import (
    CmdMoveTool,
    CmdAttackTargetTool,
    CmdAttackMoveTool,
    CmdStopTool,
    CmdHoldTool,
    CmdSmartTool,
    CmdUseAbilityTool,
    CmdRepairTool,
)


class FakeUnit:
    def __init__(self, tag, type_name, x=0, y=0):
        self.tag = tag
        self.type_name = type_name
        self.position = type("P", (), {"x": x, "y": y})()

    def move(self, position, queue=False):
        return True

    def attack(self, target, queue=False):
        return True

    def stop(self, queue=False):
        return True

    def hold_position(self, queue=False):
        return True

    def smart(self, target, queue=False):
        return True

    def use_ability(self, ability_id, target=None, queue=False):
        return True

    def repair(self, repair_target, queue=False):
        return True

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
# CmdMoveTool
# ---------------------------------------------------------------------------


def test_cmd_move_uses_tags():
    bot = FakeBot()
    bot.register_unit(42, "Marine", x=10, y=20)
    tool = CmdMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[42], x=35.0, y=40.0))
    assert result["ok"] is True


def test_cmd_move_tag_not_found():
    bot = FakeBot()
    tool = CmdMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[999], x=35.0, y=40.0))
    assert result["ok"] is False


def test_cmd_move_multiple_units():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    bot.register_unit(2, "Marauder")
    tool = CmdMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[1, 2], x=0.0, y=0.0))
    assert result["ok"] is True
    assert result["success_count"] == 2


def test_cmd_move_partial_failure():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[1, 999], x=0.0, y=0.0))
    assert result["ok"] is False
    assert result["success_count"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["code"] == "TAG_NOT_FOUND"
    assert result["errors"][0]["tag"] == 999


# ---------------------------------------------------------------------------
# CmdAttackTargetTool
# ---------------------------------------------------------------------------


def test_cmd_attack_target():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    bot.register_unit(2, "Zergling")
    tool = CmdAttackTargetTool(bot)
    result = asyncio.run(tool.execute(tags=[1], target_tag=2))
    assert result["ok"] is True


def test_cmd_attack_target_not_found():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdAttackTargetTool(bot)
    result = asyncio.run(tool.execute(tags=[1], target_tag=999))
    assert result["ok"] is False


def test_cmd_attack_target_attacker_not_found():
    bot = FakeBot()
    tool = CmdAttackTargetTool(bot)
    result = asyncio.run(tool.execute(tags=[1], target_tag=2))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdAttackMoveTool
# ---------------------------------------------------------------------------


def test_cmd_attack_move():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdAttackMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[1], x=50.0, y=60.0))
    assert result["ok"] is True


def test_cmd_attack_move_tag_not_found():
    bot = FakeBot()
    tool = CmdAttackMoveTool(bot)
    result = asyncio.run(tool.execute(tags=[999], x=0.0, y=0.0))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdStopTool
# ---------------------------------------------------------------------------


def test_cmd_stop():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    bot.register_unit(2, "Marine")
    tool = CmdStopTool(bot)
    result = asyncio.run(tool.execute(tags=[1, 2]))
    assert result["ok"] is True
    assert result["success_count"] == 2


def test_cmd_stop_tag_not_found():
    bot = FakeBot()
    tool = CmdStopTool(bot)
    result = asyncio.run(tool.execute(tags=[999]))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdHoldTool
# ---------------------------------------------------------------------------


def test_cmd_hold():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdHoldTool(bot)
    result = asyncio.run(tool.execute(tags=[1]))
    assert result["ok"] is True


def test_cmd_hold_tag_not_found():
    bot = FakeBot()
    tool = CmdHoldTool(bot)
    result = asyncio.run(tool.execute(tags=[999]))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdSmartTool
# ---------------------------------------------------------------------------


def test_cmd_smart_target_tag():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    bot.register_unit(2, "Zergling")
    tool = CmdSmartTool(bot)
    result = asyncio.run(tool.execute(tags=[1], target_tag=2))
    assert result["ok"] is True


def test_cmd_smart_position():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdSmartTool(bot)
    result = asyncio.run(tool.execute(tags=[1], x=30.0, y=40.0))
    assert result["ok"] is True


def test_cmd_smart_no_target():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdSmartTool(bot)
    result = asyncio.run(tool.execute(tags=[1]))
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "INVALID_ARGS"


def test_cmd_smart_target_not_found():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdSmartTool(bot)
    result = asyncio.run(tool.execute(tags=[1], target_tag=999))
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdUseAbilityTool
# ---------------------------------------------------------------------------


def test_cmd_use_ability_no_target():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdUseAbilityTool(bot)
    result = asyncio.run(tool.execute(tags=[1], ability_id=123))
    assert result["ok"] is True


def test_cmd_use_ability_with_target_tag():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    bot.register_unit(2, "Zergling")
    tool = CmdUseAbilityTool(bot)
    result = asyncio.run(
        tool.execute(tags=[1], ability_id=456, target_tag=2)
    )
    assert result["ok"] is True


def test_cmd_use_ability_with_position():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdUseAbilityTool(bot)
    result = asyncio.run(
        tool.execute(tags=[1], ability_id=456, x=10.0, y=20.0)
    )
    assert result["ok"] is True


def test_cmd_use_ability_target_not_found():
    bot = FakeBot()
    bot.register_unit(1, "Marine")
    tool = CmdUseAbilityTool(bot)
    result = asyncio.run(
        tool.execute(tags=[1], ability_id=456, target_tag=999)
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# CmdRepairTool
# ---------------------------------------------------------------------------


def test_cmd_repair():
    bot = FakeBot()
    bot.register_unit(1, "SCV")
    bot.register_unit(2, "CommandCenter")
    tool = CmdRepairTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[1], target_tag=2))
    assert result["ok"] is True


def test_cmd_repair_multiple_workers():
    bot = FakeBot()
    bot.register_unit(1, "SCV")
    bot.register_unit(2, "SCV")
    bot.register_unit(3, "CommandCenter")
    tool = CmdRepairTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[1, 2], target_tag=3))
    assert result["ok"] is True
    assert result["success_count"] == 2


def test_cmd_repair_target_not_found():
    bot = FakeBot()
    bot.register_unit(1, "SCV")
    tool = CmdRepairTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[1], target_tag=999))
    assert result["ok"] is False


def test_cmd_repair_worker_not_found():
    bot = FakeBot()
    bot.register_unit(1, "CommandCenter")
    tool = CmdRepairTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[999], target_tag=1))
    assert result["ok"] is False
