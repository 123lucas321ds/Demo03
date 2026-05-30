"""Project-specific exceptions."""

from __future__ import annotations


class SC2AgentError(Exception):
    """Base exception for SC2 Agent errors."""


class InvalidRuntimeTransition(SC2AgentError):
    """Raised when the stop-the-world runtime state transition is invalid."""


class ConfigurationError(SC2AgentError):
    """Raised for invalid runtime configuration."""
