"""LLM Adapter — wraps openai SDK for Demo03's LLMClient Protocol."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import openai

from sc2_agent.agent.runner import LLMClient, LLMResponse
from sc2_agent.tools.base import ToolCall

_logger = logging.getLogger(__name__)


def _resolve_api_key(value: str) -> str:
    """Resolve ``env:VAR_NAME`` entries to their environment value."""
    if value.startswith("env:"):
        env_name = value[4:]
        result = os.getenv(env_name, "")
        if not result:
            _logger.warning("Env var %s is not set or empty", env_name)
        return result
    return value


@dataclass
class SC2LLMAdapter:
    """OpenAI-compatible LLM adapter satisfying Demo03's LLMClient Protocol."""

    client_specs: list[dict[str, Any]]
    request_timeout_seconds: float = 80.0
    sticky_client_name: str = "deepseek_chat"

    _openai_client: Any = field(init=False, repr=False)
    _model: str = field(init=False)

    def __post_init__(self) -> None:
        spec = self._find_sticky_spec()
        self._model = str(spec.get("model", ""))
        self._openai_client = openai.OpenAI(
            api_key=_resolve_api_key(spec.get("api_key", "")),
            base_url=str(spec.get("base_url", "")).strip(),
            timeout=self.request_timeout_seconds,
        )

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Call the LLM and return a normalized response."""
        try:
            result = await asyncio.to_thread(
                self._openai_client.chat.completions.create,
                model=self._model,
                messages=[self._normalize_msg(m) for m in messages],
                tools=self._convert_tools(tools) if tools else None,
            )
        except Exception as exc:
            _logger.error("LLM API call failed: %s", exc)
            return LLMResponse(
                content=None, tool_calls=[], usage={}, finish_reason="error",
            )

        choice = result.choices[0]
        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=SC2LLMAdapter._unsanitize_name(tc.function.name),
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                )
                for tc in msg.tool_calls
            ]
        usage = {}
        if result.usage:
            usage = {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
            }

        return LLMResponse(
            content=msg.content, tool_calls=tool_calls, usage=usage,
            finish_reason=choice.finish_reason,
        )

    # --- private ---

    def _find_sticky_spec(self) -> dict[str, Any]:
        if not self.client_specs:
            raise ValueError(f"No client specs available (sticky={self.sticky_client_name!r})")
        for spec in self.client_specs:
            if isinstance(spec, dict) and spec.get("name") == self.sticky_client_name:
                return spec
        return self.client_specs[0]

    @staticmethod
    def _normalize_msg(msg: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {"role": msg["role"]}
        if msg.get("content") is not None:
            normalized["content"] = (
                str(msg["content"])
                if not isinstance(msg["content"], str)
                else msg["content"]
            )
        if msg.get("tool_calls"):
            normalized["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": (
                            tc["function"]["arguments"]
                            if isinstance(tc["function"]["arguments"], str)
                            else json.dumps(tc["function"]["arguments"])
                        ),
                    },
                }
                for tc in msg["tool_calls"]
            ]
        if msg["role"] == "tool":
            normalized["tool_call_id"] = msg["tool_call_id"]
            content = msg["content"]
            normalized["content"] = (
                content if isinstance(content, str) else json.dumps(content)
            )
        return normalized

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Replace the first dot with double-underscore for LLM API compatibility.

        ``query.find_units`` → ``query__find_units``
        The double-underscore is unambiguous — the LLM won't invent it.
        """
        return name.replace(".", "__", 1)

    @staticmethod
    def _unsanitize_name(name: str) -> str:
        """Restore namespace dot from double-underscore.

        ``query__find_units`` → ``query.find_units``
        If the LLM used a single underscore, try to recover common patterns.
        """
        if "__" in name:
            return name.replace("__", ".", 1)
        # Fallback: LLM may have used single underscore for namespace separator.
        # Known namespace prefixes help disambiguate.
        _KNOWN_NS = {"obs", "query", "cmd", "build", "econ", "squad", "timer", "plan", "review", "hist", "ctrl", "skill"}
        for ns in _KNOWN_NS:
            if name.startswith(ns + "_"):
                return ns + "." + name[len(ns)+1:]
        return name

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": SC2LLMAdapter._sanitize_name(t["function"]["name"]),
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"].get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
            if isinstance(t, dict)
        ]
