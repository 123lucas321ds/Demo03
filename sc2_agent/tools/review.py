"""Review tools for hard validation before commit."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from sc2_agent.models import Result
from sc2_agent.planning.simulator import PlanSimulator, SimulationState
from sc2_agent.timer.models import TimerCommand
from sc2_agent.timer.staging import TimerStaging
from sc2_agent.tools.base import Tool

if TYPE_CHECKING:
    from sc2_agent.agent.subagent import SubAgent


@dataclass(frozen=True, slots=True)
class LogicReview:
    verdict: str = "PASS"
    issues: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "issues": list(self.issues), "suggestions": list(self.suggestions)}


class DeterministicLogicReviewer:
    """Small local reviewer used as fallback when no LLM Sub-Agent is available."""

    def review(
        self,
        *,
        staging_hash: str,
        commands: list[TimerCommand],
        game_state: dict[str, Any] | None = None,
    ) -> LogicReview:
        issues: list[dict[str, Any]] = []
        if not commands:
            issues.append({
                "code": "NO_COMMANDS",
                "severity": "warn",
                "message": "staging contains no timer commands",
            })
        verdict = "WARN" if issues else "PASS"
        return LogicReview(verdict=verdict, issues=issues)


class SubAgentLogicReviewer:
    """Logic reviewer that spawns a review Sub-Agent with LLM."""

    def __init__(self, subagent: SubAgent) -> None:
        self._subagent = subagent

    async def review(
        self,
        *,
        staging_hash: str,
        commands: list[TimerCommand],
        game_state: dict[str, Any] | None = None,
    ) -> LogicReview:
        task = self._build_task(staging_hash, commands, game_state)
        result = await self._subagent.run(task)

        if not result.ok:
            return LogicReview(
                verdict="WARN",
                issues=[{
                    "code": "LOGIC_REVIEW_ERROR",
                    "severity": "warn",
                    "message": f"Sub-Agent review failed: {result.error or 'unknown error'}",
                }],
                suggestions=["Re-run review.logic or proceed with caution"],
            )

        return self._parse_response(result.content)

    def _build_task(
        self,
        staging_hash: str,
        commands: list[TimerCommand],
        game_state: dict[str, Any] | None,
    ) -> str:
        lines = [
            f"审查 staging_hash={staging_hash} 的命令时间线。",
            "",
            "## 待审查的命令",
        ]
        for cmd in commands:
            lines.append(
                f"- [{cmd.at_time:.1f}s] {cmd.tool_name} "
                f"({json.dumps(cmd.arguments, ensure_ascii=False)})"
            )
        if not commands:
            lines.append("(空 — 无命令)")
        lines.append("")
        lines.append("请返回 JSON 格式的审查结果。")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(content: str | None) -> LogicReview:
        if not content:
            return LogicReview(verdict="WARN", issues=[{
                "code": "EMPTY_RESPONSE",
                "severity": "warn",
                "message": "Sub-Agent returned empty response",
            }])
        try:
            # Try to extract JSON from the response
            text = content.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            data = json.loads(text)
            return LogicReview(
                verdict=data.get("verdict", "WARN"),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
            )
        except (json.JSONDecodeError, IndexError):
            return LogicReview(
                verdict="WARN",
                issues=[{
                    "code": "PARSE_FAILED",
                    "severity": "warn",
                    "message": "Failed to parse Sub-Agent response as JSON",
                }],
            )


class ReviewParamsTool(Tool):
    """Validate command parameters that should never reach commit if malformed."""

    def __init__(self, bot: Any = None) -> None:
        self._bot = bot

    @property
    def name(self) -> str:
        return "review.params"

    @property
    def description(self) -> str:
        return "Review hard parameter errors such as missing tags and invalid coordinates."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "arguments": {"type": "object"},
                "map_width": {"type": "number", "minimum": 1},
                "map_height": {"type": "number", "minimum": 1},
            },
            "required": ["tool_name", "arguments"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        tool_name = kwargs["tool_name"]
        arguments = kwargs["arguments"]
        map_width = float(kwargs.get("map_width", 256))
        map_height = float(kwargs.get("map_height", 256))
        errors: list[dict[str, Any]] = []

        if self._requires_producer_tag(tool_name, arguments) and not self._has_producer_tag(arguments):
            errors.append({"code": "TAG_MISSING", "message": "command requires producer tag"})

        for x_key, y_key in (("x", "y"), ("target_x", "target_y")):
            if x_key in arguments or y_key in arguments:
                x = arguments.get(x_key)
                y = arguments.get(y_key)
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    errors.append({"code": "COORDINATE_INVALID", "message": f"{x_key}/{y_key} must be numbers"})
                elif x < 0 or y < 0 or x > map_width or y > map_height:
                    errors.append({"code": "COORDINATE_OUT_OF_BOUNDS", "message": f"{x_key}/{y_key} outside map bounds"})

        # Validate that referenced tags actually exist in current game state
        if self._bot is not None:
            for key in ("structure_tag", "worker_tag", "producer_id", "target_tag"):
                tag = arguments.get(key)
                if tag is not None and self._bot.find_by_tag(tag) is None:
                    errors.append({
                        "code": "TAG_NOT_FOUND",
                        "message": f"{key}={tag} does not exist in current game state",
                    })

        return {"ok": not errors, "errors": errors}

    @staticmethod
    def _requires_producer_tag(tool_name: str, arguments: dict[str, Any]) -> bool:
        if any(key in arguments for key in ("unit_type", "structure_type", "building_type")):
            return True
        return any(part in tool_name for part in ("train", "build"))

    @staticmethod
    def _has_producer_tag(arguments: dict[str, Any]) -> bool:
        return any(arguments.get(key) is not None for key in ("producer_id", "structure_tag", "worker_tag"))


class ReviewPlanTool(Tool):
    """Review staged timer commands against the deterministic simulator."""

    read_only = False

    def __init__(
        self,
        *,
        staging: TimerStaging,
        initial_state_provider: Callable[[], SimulationState],
        active_timers_provider: Callable[[], list[TimerCommand]] | None = None,
        logic_reviewer: DeterministicLogicReviewer | SubAgentLogicReviewer | None = None,
        simulator: PlanSimulator | None = None,
        build_order_provider: Callable[[], dict] | None = None,
    ) -> None:
        self.staging = staging
        self.initial_state_provider = initial_state_provider
        self.active_timers_provider = active_timers_provider or (lambda: [])
        self.logic_reviewer = logic_reviewer or DeterministicLogicReviewer()
        self.simulator = simulator or PlanSimulator()
        self.build_order_provider = build_order_provider

    @property
    def name(self) -> str:
        return "review.plan"

    @property
    def description(self) -> str:
        return "Review the current timer staging with plan.simulate and bind the reviewed staging_hash."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "staging_hash": {"type": "string", "minLength": 1},
                "horizon": {"type": ["number", "null"]},
            },
            "required": ["staging_hash"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        staging_hash = kwargs["staging_hash"]
        current_hash = self.staging.hash()
        if staging_hash != current_hash:
            return Result.failure(
                "STAGING_HASH_MISMATCH",
                "review.plan staging_hash does not match current staging",
                expected=current_hash,
                actual=staging_hash,
            )

        result = self.simulator.simulate(
            initial_state=self.initial_state_provider(),
            commands=list(self.staging.commands),
            active_timers=self.active_timers_provider(),
            horizon=kwargs.get("horizon"),
        )
        if result.first_failure:
            return Result.failure(
                "PLAN_REVIEW_FAILED",
                result.first_failure.message,
                failure=result.first_failure.to_dict(),
            )

        # Build review context with game state and optional build order template
        game_state = self.initial_state_provider()
        review_context: dict[str, Any] = {"game_state": game_state}

        if self.build_order_provider:
            template = self.build_order_provider()
            if template:
                review_context["build_order"] = template

        logic_review = self.logic_reviewer.review(
            staging_hash=staging_hash,
            commands=list(self.staging.commands),
            game_state=review_context,
        )
        import inspect
        if inspect.isawaitable(logic_review):
            logic_review = await logic_review

        if any(issue.get("severity") == "error" for issue in logic_review.issues):
            return Result.failure("LOGIC_REVIEW_FAILED", "logic review returned error issues", logic_review=logic_review.to_dict())

        self.staging.mark_reviewed(staging_hash)
        return Result.success(
            {
                "status": "reviewed",
                "staging_hash": staging_hash,
                "points": [point.to_dict() for point in result.points],
                "assumptions": result.assumptions,
                "logic_review": logic_review.to_dict(),
            }
        )


class ReviewLogicTool(Tool):
    read_only = True

    def __init__(self, staging: TimerStaging, reviewer: DeterministicLogicReviewer | SubAgentLogicReviewer | None = None) -> None:
        self.staging = staging
        self.reviewer = reviewer or DeterministicLogicReviewer()

    @property
    def name(self) -> str:
        return "review.logic"

    @property
    def description(self) -> str:
        return "Run strategic logic review for the current staging hash."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"staging_hash": {"type": "string", "minLength": 1}},
            "required": ["staging_hash"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        staging_hash = kwargs["staging_hash"]
        current_hash = self.staging.hash()
        if staging_hash != current_hash:
            return Result.failure(
                "STAGING_HASH_MISMATCH",
                "review.logic staging_hash does not match current staging",
                expected=current_hash,
                actual=staging_hash,
            )
        result = self.reviewer.review(staging_hash=staging_hash, commands=list(self.staging.commands))
        import inspect
        if inspect.isawaitable(result):
            result = await result

        data = result.to_dict()
        for issue in data.get("issues", []):
            if issue.get("code") in ("LOGIC_REVIEW_ERROR", "PARSE_FAILED", "EMPTY_RESPONSE"):
                return Result.failure(
                    "LOGIC_REVIEW_ERROR",
                    f"SubAgent review failed: {issue.get('message', 'unknown')}",
                    logic_review=data,
                )
        return data
