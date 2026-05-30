"""Runtime settings for the SC2 Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BURNYSC2_PATH = Path(r"D:\Anaconda\anaconda\envs\LLM\Lib\site-packages\sc2")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Small dependency-free settings object for Phase 0.

    A pydantic-settings implementation can replace this once dependency
    management is introduced. Keeping Phase 0 dependency-free makes the basic
    skeleton easy to test on a clean workspace.
    """

    workspace: Path = Path.cwd()
    burnysc2_path: Path = DEFAULT_BURNYSC2_PATH
    log_level: str = "INFO"
    history_token_budget: int = 12_000
    max_agent_iterations: int = 20
    subagent_max_iterations: int = 10
    snapshot_decision_keep: int = 5
    snapshot_recent_keep: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables."""

        workspace = Path(os.getenv("SC2_AGENT_WORKSPACE", str(Path.cwd())))
        burnysc2_path = Path(os.getenv("SC2_AGENT_BURNYSC2_PATH", str(DEFAULT_BURNYSC2_PATH)))
        return cls(
            workspace=workspace,
            burnysc2_path=burnysc2_path,
            log_level=os.getenv("SC2_AGENT_LOG_LEVEL", "INFO"),
            history_token_budget=_env_int("SC2_AGENT_HISTORY_TOKEN_BUDGET", 12_000),
            max_agent_iterations=_env_int("SC2_AGENT_MAX_AGENT_ITERATIONS", 20),
            subagent_max_iterations=_env_int("SC2_AGENT_SUBAGENT_MAX_ITERATIONS", 10),
            snapshot_decision_keep=_env_int("SC2_AGENT_SNAPSHOT_DECISION_KEEP", 5),
            snapshot_recent_keep=_env_int("SC2_AGENT_SNAPSHOT_RECENT_KEEP", 5),
        )
