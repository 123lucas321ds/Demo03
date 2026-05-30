from pathlib import Path

import pytest

from sc2_agent.config.settings import DEFAULT_BURNYSC2_PATH, Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.burnysc2_path == DEFAULT_BURNYSC2_PATH
    assert settings.log_level == "INFO"
    assert settings.history_token_budget == 12_000
    assert settings.max_agent_iterations == 80
    assert settings.subagent_max_iterations == 10


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SC2_AGENT_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("SC2_AGENT_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SC2_AGENT_HISTORY_TOKEN_BUDGET", "9000")

    settings = Settings.from_env()

    assert settings.workspace == tmp_path
    assert settings.log_level == "DEBUG"
    assert settings.history_token_budget == 9000


def test_settings_from_env_rejects_invalid_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SC2_AGENT_HISTORY_TOKEN_BUDGET", "not-an-int")

    with pytest.raises(ValueError, match="SC2_AGENT_HISTORY_TOKEN_BUDGET"):
        Settings.from_env()
