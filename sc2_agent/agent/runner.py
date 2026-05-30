"""Function-calling Agent runner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from sc2_agent.models import Result
from sc2_agent.tools.base import ToolCall
from sc2_agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Normalized LLM response used by the runner."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def to_assistant_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return message


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call the model."""


@dataclass(frozen=True, slots=True)
class AgentRunSpec:
    initial_messages: list[dict[str, Any]]
    tools: ToolRegistry
    max_iterations: int = 20


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    messages: list[dict[str, Any]]
    final_content: str | None
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: str | None = None
    timings: list[dict[str, Any]] = field(default_factory=list)


class AgentRunner:
    """Run the shared tool-calling loop."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        messages = list(spec.initial_messages)
        initial_count = len(messages)
        tools_used: list[str] = []
        usage: dict[str, int] = {}
        final_content: str | None = None
        stop_reason = "completed"
        error: str | None = None
        committed = False
        aborted = False

        timings: list[dict[str, Any]] = [{}] * initial_count  # placeholder for initial messages
        for _ in range(spec.max_iterations):
            t0 = time.time()
            response = await self._llm.chat(messages=messages, tools=spec.tools.schemas())
            llm_elapsed = round((time.time() - t0) * 1000)
            usage = response.usage or usage
            messages.append(response.to_assistant_message())
            timings.append({"role": "assistant", "elapsed_ms": llm_elapsed, "finish_reason": response.finish_reason})

            if not response.has_tool_calls:
                final_content = response.content
                if response.finish_reason == "error":
                    stop_reason = "error"
                    error = response.content or "LLM returned an error"
                break

            self._publish_pending_messages(spec, response.tool_calls, messages, initial_count)
            t0 = time.time()
            results = await spec.tools.execute_calls(response.tool_calls)
            tool_elapsed = round((time.time() - t0) * 1000)
            per_tool = max(1, round(tool_elapsed / max(1, len(response.tool_calls))))
            for call, result in zip(response.tool_calls, results):
                tools_used.append(call.name)
                messages.append(self._tool_message(call, result))
                timings.append({"role": "tool", "tool_name": call.name, "elapsed_ms": per_tool})
            self._publish_pending_messages(spec, response.tool_calls, messages, initial_count)

            if any(call.name == "ctrl.commit" and result.ok for call, result in zip(response.tool_calls, results)):
                stop_reason = "committed"
                committed = True
                break
            if any(call.name == "ctrl.abort" and result.ok for call, result in zip(response.tool_calls, results)):
                stop_reason = "aborted"
                aborted = True
                break
        else:
            stop_reason = "max_iterations"

        if not committed and not aborted:
            t0 = time.time()
            abort_result = await spec.tools.execute("ctrl.abort", {"reason": stop_reason})
            if abort_result.ok:
                stop_reason = "aborted"
                tools_used.append("ctrl.abort")
                messages.append({
                    "role": "tool",
                    "tool_call_id": "auto_abort",
                    "name": "ctrl.abort",
                    "content": self._serialize_result(abort_result),
                })
                timings.append({"role": "tool", "tool_name": "ctrl.abort", "elapsed_ms": round((time.time() - t0) * 1000)})

        return AgentRunResult(
            messages=messages[initial_count:],
            final_content=final_content,
            tools_used=tools_used,
            usage=usage,
            stop_reason=stop_reason,
            error=error,
            timings=timings[initial_count:],
        )

    def _tool_message(self, call: ToolCall, result: Result) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": self._serialize_result(result),
        }

    @staticmethod
    def _serialize_result(result: Result) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
            "code": result.code,
            "meta": result.meta,
        }

    @staticmethod
    def _publish_pending_messages(
        spec: AgentRunSpec,
        calls: list[ToolCall],
        messages: list[dict[str, Any]],
        initial_count: int,
    ) -> None:
        for call in calls:
            tool = spec.tools.get(call.name)
            controller = getattr(tool, "_controller", None)
            services = getattr(controller, "services", None)
            if services is not None and hasattr(services, "pending_messages"):
                services.pending_messages = lambda messages=messages, initial_count=initial_count: messages[initial_count:]
