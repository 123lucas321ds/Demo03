"""Dispatch tools — spawn SubAgents for observation and planning."""

from __future__ import annotations

from typing import Any

from sc2_agent.agent.subagent import SubAgent, SubAgentResult
from sc2_agent.tools.base import Tool
from sc2_agent.tools.registry import ToolRegistry


class DispatchObserveTool(Tool):
    """Spawn an observation SubAgent to gather game state information."""

    read_only = True

    OBS_SYSTEM_PROMPT = """\
你是 SC2 观测专家。主 Agent 会给你一个观测任务，你需要选择合适的观测工具来收集信息。

工具使用原则：
- 先用 obs.resources / obs.structures / obs.enemy_visible 建立全局认知
- 如果任务要求细节，用 obs.unit(tag=N) 或 query.find_units(...) 深入
- 如果任务提到历史对比，用 hist.snapshot / hist.compare
- 根据任务复杂度决定返回摘要还是全量——简单任务给摘要，深入任务给细节
- 最终以 markdown 格式返回结构化的观测报告"""

    def __init__(self, registry: ToolRegistry, llm: Any) -> None:
        self._registry = registry
        self._llm = llm

    @property
    def name(self) -> str:
        return "dispatch.observe"

    @property
    def description(self) -> str:
        return "Spawn an observation sub-agent. Provide a natural language task describing what to observe."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What to observe. E.g. '全局局势概览', '右侧敌方单位详情', '对比上次快照'",
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        task: str = kwargs["task"]
        sub_tools = self._registry.filter(namespaces={"obs", "query", "hist"})
        sub = SubAgent(
            llm=self._llm,
            tools=sub_tools,
            system_prompt=self.OBS_SYSTEM_PROMPT,
            max_iterations=8,
        )
        result: SubAgentResult = await sub.run(task)
        return {
            "ok": result.ok,
            "content": result.content,
            "tools_used": result.tools_used,
            "stop_reason": result.stop_reason,
        }


class DispatchPlanTool(Tool):
    """Spawn a planning SubAgent to generate and validate a build timeline."""

    read_only = True

    PLAN_SYSTEM_PROMPT = """\
你是 SC2 规划专家。主 Agent 会给你初始状态和建造目标，你需要生成一份经过模拟验证的时间线。

工作流程：
1. 先用 plan.build_time 查询每个目标的耗时和成本
2. 用 plan.simulate 逐步验证资源约束
3. 对模拟失败的命令，调整 at_time（用二分搜索逼近临界点，不依赖 LLM 猜测）
4. at_time = max(当前时间, 前置完成时间, 生产者空闲时间, 资源足够时间)
5. 最多模拟 5 轮，达不到就标记失败原因

输出格式（JSON）：
{
  "ok": true/false,
  "commands": [
    {"tool_name": "build.train", "arguments": {"unit_type": "SCV", ...}, "at_time": 0.0},
    ...
  ],
  "verification": {"rounds": N, "passed": true/false, "failure_reason": "..."},
  "notes": "时间线摘要描述"
}"""

    def __init__(self, registry: ToolRegistry, llm: Any) -> None:
        self._registry = registry
        self._llm = llm

    @property
    def name(self) -> str:
        return "dispatch.plan"

    @property
    def description(self) -> str:
        return "Spawn a planning sub-agent. Provide initial state, template name, and horizon."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Planning task with context. E.g. '基于 terran_1rax_expand 模板规划 90s 时间线'",
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        task: str = kwargs["task"]
        sub_tools = self._registry.filter(namespaces={"plan"})
        sub = SubAgent(
            llm=self._llm,
            tools=sub_tools,
            system_prompt=self.PLAN_SYSTEM_PROMPT,
            max_iterations=8,
        )
        result: SubAgentResult = await sub.run(task)
        return {
            "ok": result.ok,
            "content": result.content,
            "tools_used": result.tools_used,
            "stop_reason": result.stop_reason,
        }
