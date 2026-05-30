"""Backward-compatible wrapper over loguru.

The old API (configure_logging / get_logger) delegates to loguru via LogManager.
New code should import directly from sc2_agent.logging.
"""

from __future__ import annotations

from pathlib import Path

from sc2_agent.logging import LogManager, get_logger

_initialized = False


def configure_logging(level: str = "INFO") -> None:
    """Configure process-wide logging (backward compat).

    If LogManager.setup() has not been called yet, initializes with
    console-only output to a default log directory.
    """
    global _initialized
    if _initialized:
        return
    LogManager.setup(
        log_dir=Path.cwd() / "storage" / "_default" / "logs",
        console_level=level,
    )
    _initialized = True
