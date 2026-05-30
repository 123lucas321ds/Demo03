from __future__ import annotations

from sc2_agent.agent.prompt_builder import PromptBuilder


def test_build_system_prompt_has_four_sections() -> None:
    builder = PromptBuilder()
    prompt = builder.build_system_prompt(
        game_state_md="# Current Situation\n(empty)\n",
        tool_summary="obs.*, query.*, cmd.*, build.*, ctrl.*",
        skill_summary="No skills loaded.",
    )
    assert "星际争霸2人族指挥官" in prompt
    assert "当前局势" in prompt
    assert "可用工具" in prompt
    assert "obs.*" in prompt
    assert "可用技能" in prompt


def test_build_system_prompt_without_skills() -> None:
    builder = PromptBuilder()
    prompt = builder.build_system_prompt(
        game_state_md="...",
        tool_summary="obs.*, ctrl.*",
    )
    assert "星际争霸2人族指挥官" in prompt
    assert "当前局势" in prompt
    assert "可用工具" in prompt
    assert "可用技能" not in prompt  # skills omitted when empty


def test_build_wake_message() -> None:
    builder = PromptBuilder()
    msg = builder.build_wake_message(
        game_time=45.0,
        wake_id=1,
        reason="game_start",
        trigger_source="startup",
    )
    assert "game_time=45.0s" in msg
    assert "wake_id=1" in msg
    assert "game_start" in msg
