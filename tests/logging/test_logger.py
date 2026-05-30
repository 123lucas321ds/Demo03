"""Tests for the backward-compatible logger wrapper."""

import pytest

from sc2_agent.logging.logger import configure_logging, get_logger


def test_configure_logging_does_not_crash():
    configure_logging("DEBUG")
    logger = get_logger("sc2_agent.test")
    logger.debug("should not crash")


def test_configure_logging_idempotent():
    configure_logging("INFO")
    configure_logging("DEBUG")  # second call should be no-op
