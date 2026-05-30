"""LogManager — init loguru sinks, set formats, manage per-game log directories."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger


# Shared format string for JSON sinks. serialize=True wraps it in structured JSON.
_JSON_FMT = (
    "{time:YYYY-MM-DDTHH:mm:ss.SSS!UTC} | "
    "{level} | "
    "{name} | "
    "{message} | "
    "{extra}"
)

# Shared format string for human-readable stderr output.
_CONSOLE_FMT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level:<7}</level> | "
    "<cyan>{name:<20}</cyan> | "
    "<level>{message}</level>"
)


class LogManager:
    """Configure and initialize the logging system. Call setup() once per game."""

    @staticmethod
    def setup(*, log_dir: Path, console_level: str = "INFO") -> None:
        """Initialize loguru sinks.

        - Removes the default loguru handler.
        - Adds a JSON file sink -> app.log (50 MB rotation, 30 day retention).
        - Adds a JSON file sink -> errors.log (ERROR+, 50 MB rotation, 90 day retention).
        - Adds a human-readable stderr sink.
        """
        logger.remove()
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "app.log",
            format=_JSON_FMT,
            level="DEBUG",
            rotation="50 MB",
            retention="30 days",
            compression="gz",
            serialize=True,
            enqueue=True,
        )

        logger.add(
            log_dir / "errors.log",
            format=_JSON_FMT,
            level="ERROR",
            rotation="50 MB",
            retention="90 days",
            compression="gz",
            serialize=True,
            enqueue=True,
        )

        logger.add(
            sys.stderr,
            format=_CONSOLE_FMT,
            level=console_level,
            colorize=True,
            enqueue=True,
        )


def get_logger(name: str) -> Any:
    """Return a loguru logger with module tag bound."""
    return logger.bind(module=name)
