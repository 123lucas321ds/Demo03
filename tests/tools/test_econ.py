"""Tests for economic tools (econ.*)."""

from __future__ import annotations

import asyncio

from sc2_agent.tools.econ import EconTransferWorkersTool


class FakeUnit:
    def __init__(self, tag, type_name, x=0, y=0):
        self.tag = tag
        self.type_name = type_name
        self.position = type("P", (), {"x": x, "y": y})()

    def gather(self, target, queue=False):
        return True


class FakeBot:
    def __init__(self):
        self._units = {}

    def register_unit(self, tag, type_name, x=0, y=0):
        self._units[tag] = FakeUnit(tag, type_name, x, y)

    def find_by_tag(self, tag):
        return self._units.get(tag)


# ---------------------------------------------------------------------------
# EconTransferWorkersTool
# ---------------------------------------------------------------------------


def test_transfer_workers():
    bot = FakeBot()
    bot.register_unit(10, "SCV")
    bot.register_unit(11, "SCV")
    bot.register_unit(200, "MineralField")
    tool = EconTransferWorkersTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[10, 11], resource_tag=200))
    assert result["ok"] is True
    assert result["transferred"] == 2


def test_transfer_bad_resource():
    bot = FakeBot()
    bot.register_unit(10, "SCV")
    tool = EconTransferWorkersTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[10], resource_tag=999))
    assert result["transferred"] == 0


def test_transfer_bad_worker():
    bot = FakeBot()
    bot.register_unit(200, "MineralField")
    tool = EconTransferWorkersTool(bot)
    result = asyncio.run(tool.execute(worker_tags=[999], resource_tag=200))
    assert result["transferred"] == 0
