from __future__ import annotations

import asyncio

from sc2_agent.skills.loader import SkillLoader
from sc2_agent.tools.registry import ToolRegistry
from sc2_agent.tools.skill import SkillLoadTool


def test_skill_loader_prefers_workspace_skill(tmp_path) -> None:
    workspace_skill = tmp_path / "skills" / "macro" / "SKILL.md"
    builtin_skill = tmp_path / "builtin" / "macro" / "SKILL.md"
    workspace_skill.parent.mkdir(parents=True)
    builtin_skill.parent.mkdir(parents=True)
    workspace_skill.write_text("workspace skill", encoding="utf-8")
    builtin_skill.write_text("builtin skill", encoding="utf-8")

    loaded = SkillLoader(tmp_path, builtin_roots=(tmp_path / "builtin",)).load("macro")

    assert loaded["name"] == "macro"
    assert loaded["path"] == str(workspace_skill)
    assert loaded["content"] == "workspace skill"


def test_skill_load_tool_returns_failure_for_missing_skill(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(SkillLoadTool(SkillLoader(tmp_path)))

    result = asyncio.run(registry.execute("skill.load", {"name": "missing"}))

    assert not result.ok
    assert result.code == "SKILL_NOT_FOUND"


def test_skill_load_tool_rejects_path_traversal(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(SkillLoadTool(SkillLoader(tmp_path)))

    result = asyncio.run(registry.execute("skill.load", {"name": "../secret"}))

    assert not result.ok
    assert result.code == "INVALID_SKILL_NAME"
