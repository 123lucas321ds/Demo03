"""Tests for the LLM adapter (openai-native, no SC2 project dependency)."""

import json
import asyncio
from unittest import mock

import pytest

from sc2_agent.llm.adapter import SC2LLMAdapter, _resolve_api_key


class TestConstruction:
    def test_empty_specs_raises(self):
        with pytest.raises(ValueError):
            SC2LLMAdapter(client_specs=[])

    def test_picks_sticky_spec_by_name(self):
        adapter = SC2LLMAdapter(
            client_specs=[
                {"name": "other", "api_key": "k1", "base_url": "http://a", "model": "m1"},
                {"name": "deepseek_chat", "api_key": "k2", "base_url": "http://b", "model": "m2"},
            ],
            sticky_client_name="deepseek_chat",
        )
        assert adapter._model == "m2"

    def test_falls_back_to_first_spec(self):
        adapter = SC2LLMAdapter(
            client_specs=[
                {"name": "first", "api_key": "k1", "base_url": "http://a", "model": "m1"},
            ],
            sticky_client_name="nonexistent",
        )
        assert adapter._model == "m1"

    def test_resolves_env_api_key(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "secret123")
        result = _resolve_api_key("env:TEST_KEY")
        assert result == "secret123"


class TestNormalizeMsg:
    def test_system_message_passthrough(self):
        result = SC2LLMAdapter._normalize_msg({"role": "system", "content": "hello"})
        assert result == {"role": "system", "content": "hello"}

    def test_assistant_with_tool_calls(self):
        result = SC2LLMAdapter._normalize_msg({
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "obs.resources", "arguments": "{}"},
            }],
        })
        assert result["tool_calls"][0]["function"]["arguments"] == "{}"

    def test_dict_arguments_serialized(self):
        result = SC2LLMAdapter._normalize_msg({
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "c2",
                "function": {"name": "cmd.move", "arguments": {"x": 1, "y": 2}},
            }],
        })
        assert '"x": 1' in result["tool_calls"][0]["function"]["arguments"]

    def test_tool_message_with_dict_content(self):
        result = SC2LLMAdapter._normalize_msg({
            "role": "tool", "tool_call_id": "c3", "content": {"ok": True},
        })
        assert json.loads(result["content"]) == {"ok": True}


class TestConvertTools:
    def test_empty_list(self):
        assert SC2LLMAdapter._convert_tools([]) == []

    def test_converts_to_openai_format(self):
        tools = [{"function": {"name": "obs.resources", "description": "d", "parameters": {"type": "object"}}}]
        result = SC2LLMAdapter._convert_tools(tools)
        assert result[0]["type"] == "function"

    def test_default_parameters(self):
        tools = [{"function": {"name": "t"}}]
        result = SC2LLMAdapter._convert_tools(tools)
        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_skips_non_dict(self):
        result = SC2LLMAdapter._convert_tools(["not_a_dict", {"function": {"name": "t"}}])
        assert len(result) == 1


class TestChat:
    def test_chat_returns_text_response(self):
        adapter = SC2LLMAdapter(
            client_specs=[{"name": "t", "api_key": "k", "base_url": "http://x", "model": "m"}],
        )
        fake = mock.MagicMock()
        fake.chat.completions.create.return_value = mock.MagicMock(
            choices=[mock.MagicMock(
                finish_reason="stop",
                message=mock.MagicMock(content="hello", tool_calls=None),
            )],
            usage=mock.MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        adapter._openai_client = fake
        async def go():
            resp = await adapter.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
            assert resp.content == "hello"
            assert resp.tool_calls == []
            assert resp.usage["total_tokens"] == 15
        asyncio.run(go())

    def test_chat_returns_tool_calls(self):
        adapter = SC2LLMAdapter(
            client_specs=[{"name": "t", "api_key": "k", "base_url": "http://x", "model": "m"}],
        )
        fake = mock.MagicMock()
        tc = mock.MagicMock(id="c1", function=mock.MagicMock(name="o.r", arguments="{}"))
        fake.chat.completions.create.return_value = mock.MagicMock(
            choices=[mock.MagicMock(
                finish_reason="tool_calls",
                message=mock.MagicMock(content=None, tool_calls=[tc]),
            )],
            usage=None,
        )
        adapter._openai_client = fake
        async def go():
            resp = await adapter.chat(messages=[{"role": "user", "content": "go"}], tools=[])
            assert len(resp.tool_calls) == 1
        asyncio.run(go())

    def test_chat_handles_api_error(self):
        adapter = SC2LLMAdapter(
            client_specs=[{"name": "t", "api_key": "k", "base_url": "http://x", "model": "m"}],
        )
        fake = mock.MagicMock()
        fake.chat.completions.create.side_effect = RuntimeError("boom")
        adapter._openai_client = fake
        async def go():
            resp = await adapter.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
            assert resp.finish_reason == "error"
        asyncio.run(go())
