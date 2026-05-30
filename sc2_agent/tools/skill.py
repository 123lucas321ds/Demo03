"""Skill tools."""

from __future__ import annotations

from typing import Any

from sc2_agent.skills.loader import SkillLoader, SkillNotFound
from sc2_agent.tools.base import Tool


class SkillLoadTool(Tool):
    read_only = True

    def __init__(self, loader: SkillLoader) -> None:
        self.loader = loader

    @property
    def name(self) -> str:
        return "skill.load"

    @property
    def description(self) -> str:
        return (
            "Load a skill by name to get domain knowledge. "
            "Available skill names are listed in the system prompt's 可用技能 section. "
            "Use this when you need production math, timeline planning guidance, "
            "standard opening templates, diff analysis, or monitor calibration."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1}},
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        try:
            return self.loader.load(kwargs["name"])
        except SkillNotFound as exc:
            return {"ok": False, "code": "SKILL_NOT_FOUND", "error": str(exc)}
        except ValueError as exc:
            return {"ok": False, "code": "INVALID_SKILL_NAME", "error": str(exc)}
