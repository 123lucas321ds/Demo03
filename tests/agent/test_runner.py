from __future__ import annotations

import asyncio
from typing import Any

from sc2_agent.agent.runner import AgentRunSpec, AgentRunner, LLMResponse
from sc2_agent.models import Result
from sc2_agent.tools.base import Tool, ToolCall
from sc2_agent.tools.registry import ToolRegistry


class FakeLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls.append(list(messages))
        return self.responses.pop(0)


class EchoTool(Tool):
    read_only = True

    @property
    def name(self) -> str:
        return "obs.echo"

    @property
    def description(self) -> str:
        return "echo"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    async def execute(self, **kwargs: Any) -> str:
        return kwargs["text"]


class AbortTool(Tool):
    read_only = False

    @property
    def name(self) -> str:
        return "ctrl.abort"

    @property
    def description(self) -> str:
        return "abort"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}

    async def execute(self, **kwargs: Any) -> str:
        return f"aborted:{kwargs['reason']}"


class CommitTool(Tool):
    read_only = False

    @property
    def name(self) -> str:
        return "ctrl.commit"

    @property
    def description(self) -> str:
        return "commit"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"staging_hash": {"type": "string"}}, "required": ["staging_hash"]}

    async def execute(self, **kwargs: Any) -> str:
        return f"committed:{kwargs['staging_hash']}"


class PendingServices:
    def __init__(self) -> None:
        self.pending_messages = None


class PendingController:
    def __init__(self) -> None:
        self.services = PendingServices()
        self.captured: list[dict[str, Any]] = []

    async def commit(self, staging_hash: str) -> Result:
        assert self.services.pending_messages is not None
        self.captured = self.services.pending_messages()
        return Result.success({"staging_hash": staging_hash})


class ControllerBackedCommitTool(Tool):
    read_only = False

    def __init__(self, controller: PendingController) -> None:
        self._controller = controller

    @property
    def name(self) -> str:
        return "ctrl.commit"

    @property
    def description(self) -> str:
        return "commit"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"staging_hash": {"type": "string"}}, "required": ["staging_hash"]}

    async def execute(self, **kwargs: Any) -> Result:
        return await self._controller.commit(kwargs["staging_hash"])


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(AbortTool())
    registry.register(CommitTool())
    return registry


def test_runner_executes_tool_then_final_response() -> None:
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(id="call_1", name="obs.echo", arguments={"text": "hello"})]),
        LLMResponse(content="done"),
    ])
    runner = AgentRunner(llm)

    result = asyncio.run(runner.run(AgentRunSpec(
        initial_messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "wake"}],
        tools=_registry(),
    )))

    assert result.stop_reason == "aborted"
    assert result.final_content == "done"
    assert result.tools_used == ["obs.echo", "ctrl.abort"]
    tool_messages = [message for message in result.messages if message.get("role") == "tool"]
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert tool_messages[0]["content"]["ok"] is True
    assert tool_messages[0]["content"]["data"] == "hello"
    assert tool_messages[-1]["name"] == "ctrl.abort"


def test_runner_auto_aborts_when_final_response_has_no_commit() -> None:
    llm = FakeLLM([LLMResponse(content="I am done without committing")])

    result = asyncio.run(AgentRunner(llm).run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "think"}],
        tools=_registry(),
    )))

    assert result.stop_reason == "aborted"
    assert result.final_content == "I am done without committing"
    assert result.tools_used == ["ctrl.abort"]
    assert result.messages[-1]["name"] == "ctrl.abort"
    assert result.messages[-1]["content"]["data"] == "aborted:completed"


def test_runner_stops_after_commit() -> None:
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(id="commit_1", name="ctrl.commit", arguments={"staging_hash": "abc"})]),
        LLMResponse(content="should not be consumed"),
    ])

    result = asyncio.run(AgentRunner(llm).run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "commit"}],
        tools=_registry(),
    )))

    assert result.stop_reason == "committed"
    assert result.tools_used == ["ctrl.commit"]
    assert len(llm.calls) == 1


def test_runner_publishes_pending_incremental_messages_before_commit_executes() -> None:
    controller = PendingController()
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(AbortTool())
    registry.register(ControllerBackedCommitTool(controller))
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(id="call_1", name="obs.echo", arguments={"text": "hello"})]),
        LLMResponse(tool_calls=[ToolCall(id="commit_1", name="ctrl.commit", arguments={"staging_hash": "abc"})]),
    ])

    result = asyncio.run(AgentRunner(llm).run(AgentRunSpec(
        initial_messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "wake"}],
        tools=registry,
    )))

    assert result.stop_reason == "committed"
    assert [message["role"] for message in controller.captured] == ["assistant", "tool", "assistant"]
    assert controller.captured[-1]["tool_calls"][0]["function"]["name"] == "ctrl.commit"
    assert all(message.get("tool_call_id") != "commit_1" for message in controller.captured)
    assert result.messages[:3] == controller.captured


def test_runner_auto_aborts_on_max_iterations() -> None:
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(id="call_1", name="obs.echo", arguments={"text": "again"})]),
    ])

    result = asyncio.run(AgentRunner(llm).run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "loop"}],
        tools=_registry(),
        max_iterations=1,
    )))

    assert result.stop_reason == "aborted"
    assert "ctrl.abort" in result.tools_used
    assert result.messages[-1]["name"] == "ctrl.abort"
