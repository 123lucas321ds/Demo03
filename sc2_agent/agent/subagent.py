"""Sub-Agent — isolated AgentRunner for review, diff, and calibration tasks.

Adapted from nanobot's subagent pattern:
- Reuses the same AgentRunner class
- Fresh message list (system prompt + task only, no history)
- Minimized ToolRegistry (read-only observation tools, no ctrl/timer/spawn)
- Runs synchronously in the stop-the-world model
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sc2_agent.agent.runner import AgentRunner, AgentRunSpec, LLMClient
from sc2_agent.tools.registry import ToolRegistry


@dataclass
class SubAgentResult:
    """Structured result from a Sub-Agent run."""

    ok: bool
    content: str | None = None
    tools_used: list[str] = field(default_factory=list)
    stop_reason: str = "completed"
    error: str | None = None


class SubAgent:
    """Run an isolated AgentRunner for a focused sub-task.

    The Sub-Agent has:
    - No access to ctrl.* / timer.* / cmd.* / build.* / econ.* / squad.*
    - No access to skill.load or spawn (no recursive sub-agents)
    - A fresh message list (system prompt + task, no session history)
    - A low max_iterations limit (default 10)
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 8,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._runner = AgentRunner(llm=llm)

    async def run(self, task: str) -> SubAgentResult:
        """Execute the Sub-Agent for a single task.

        Parameters
        ----------
        task:
            The user message describing what the Sub-Agent should do.

        Returns
        -------
        SubAgentResult
            Structured result with the agent's final content or error.
        """
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": task},
            ],
            tools=self._tools,
            max_iterations=self._max_iterations,
        )
        result = await self._runner.run(spec)

        if result.stop_reason == "error" or result.error:
            return SubAgentResult(
                ok=False,
                content=result.final_content,
                tools_used=result.tools_used,
                stop_reason=result.stop_reason,
                error=result.error,
            )

        return SubAgentResult(
            ok=True,
            content=result.final_content,
            tools_used=result.tools_used,
            stop_reason=result.stop_reason,
        )


def make_review_subagent_tools(
    obs_provider: Any,
    memory_store: Any,
    event_store: Any | None = None,
    snapshot_recorder: Any | None = None,
) -> ToolRegistry:
    """Build the minimal ToolRegistry for a review Sub-Agent.

    Allowed tools:
    - obs.* — read current game state
    - query.* — search/filter entities
    - hist.snapshot / hist.trend / hist.compare — historical data
    - query.tech_requirement

    NOT allowed:
    - ctrl.* — cannot commit or abort
    - timer.* — cannot schedule
    - cmd.* / build.* / econ.* / squad.* — cannot act on game world
    - skill.load — cannot load skills
    - spawn — cannot create sub-agents (no recursion)
    """
    from sc2_agent.tools.obs import (
        ObsResourcesTool, ObsUnitsTool, ObsStructuresTool,
        ObsGameTimeTool, ObsMapTool, ObsBasesTool,
        ObsEnemyVisibleTool, ObsUpgradesTool,
    )
    from sc2_agent.tools.query import (
        QueryFindUnitsTool, QueryFindEnemyTool, QueryFindStructuresTool,
        QueryIdleProducersTool, QueryCanAffordTool, QueryTechRequirementTool,
        QueryInRegionTool, QueryExpansionsTool,
    )

    registry = ToolRegistry()
    registry.register(ObsResourcesTool(obs_provider))
    registry.register(ObsUnitsTool(obs_provider))
    registry.register(ObsStructuresTool(obs_provider))
    registry.register(ObsGameTimeTool(obs_provider))
    registry.register(ObsMapTool(obs_provider))
    registry.register(ObsBasesTool(obs_provider))
    registry.register(ObsEnemyVisibleTool(obs_provider))
    registry.register(ObsUpgradesTool(obs_provider))

    registry.register(QueryFindUnitsTool(obs_provider))
    registry.register(QueryFindEnemyTool(obs_provider))
    registry.register(QueryFindStructuresTool(obs_provider))
    registry.register(QueryIdleProducersTool(obs_provider))
    registry.register(QueryCanAffordTool(obs_provider))
    registry.register(QueryTechRequirementTool(obs_provider))
    registry.register(QueryInRegionTool(obs_provider))
    registry.register(QueryExpansionsTool(obs_provider))

    return registry


def build_review_system_prompt(game_state_md: str) -> str:
    """Build the system prompt for a review Sub-Agent."""
    return f"""你是 SC2 决策审查器。
你的任务是审查主 Agent 制定的命令时间线。

## 审查维度
1. **对抗合理性**：命令是否考虑了已知的敌方单位和可能的威胁？
2. **资源合理性**：命令消耗是否在预测资源范围内？
3. **战略一致性**：命令是否服务于当前战略判断和优先级？
4. **时间线合理性**：命令的时间安排是否可行，是否存在冲突？

## 当前局势
{game_state_md}

## 规则
- 只使用 obs.* 和 query.* 工具获取信息，禁止使用 cmd/build/econ/timer/ctrl 工具。
- 审查结果必须是结构化 JSON，包含 verdict (PASS/WARN/REVISE)、issues 数组和 suggestions 数组。
- 如果发现问题，给出具体的修复建议。
- 用中文输出。"""
