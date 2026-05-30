"""Structured context for loguru — bind / unbind game-scoped fields."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from loguru import logger


def bind_context(**kwargs: Any) -> None:
    """Bind structured fields to the global loguru logger.

    All subsequent logger.xxx() calls will include these fields in extra.
    """
    global logger
    logger = logger.bind(**kwargs)  # type: ignore[assignment]


@contextmanager
def game_context(game_id: str, **kwargs: Any):
    """Context manager that binds game-scoped fields for one game.

    Usage::

        with game_context(game_id="2026-05-29_14-30", race="Terran"):
            logger.info("Game started")
            # All log calls inside this block automatically
            # carry game_id="2026-05-29_14-30" and race="Terran"
    """
    global logger
    previous = logger
    bind_context(game_id=game_id, **kwargs)
    try:
        yield
    finally:
        logger = previous  # type: ignore[assignment]
