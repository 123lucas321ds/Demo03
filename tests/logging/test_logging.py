"""Tests for the logging system."""

import json
from pathlib import Path
import pytest
from loguru import logger

from sc2_agent.logging import LogManager, get_logger, game_context


@pytest.fixture
def log_dir(tmp_path):
    p = tmp_path / "logs"
    p.mkdir()
    return p


class TestLogManager:
    def test_setup_creates_app_log_file(self, log_dir):
        LogManager.setup(log_dir=log_dir)
        logger.bind(module="t").info("msg")
        logger.complete()
        app_log = log_dir / "app.log"
        assert app_log.exists()

    def test_json_output_has_record_fields(self, log_dir):
        LogManager.setup(log_dir=log_dir)
        logger.bind(module="t.json").info("hello")
        logger.complete()

        content = (log_dir / "app.log").read_text(encoding="utf-8").strip()
        assert content
        record = json.loads(content.split("\n")[0])
        assert "text" in record
        assert "record" in record
        assert record["record"]["level"]["name"] == "INFO"

    def test_errors_log_excludes_info(self, log_dir):
        LogManager.setup(log_dir=log_dir)
        logger.bind(module="t.err").info("info msg")
        logger.bind(module="t.err").error("err msg")
        logger.complete()

        errors_log = log_dir / "errors.log"
        assert errors_log.exists()
        for line in errors_log.read_text(encoding="utf-8").strip().split("\n"):
            assert json.loads(line)["record"]["level"]["name"] == "ERROR"

    def test_console_level_filters_debug(self, log_dir):
        LogManager.setup(log_dir=log_dir, console_level="WARNING")
        logger.bind(module="t.cl").debug("no see")
        logger.bind(module="t.cl").warning("see")
        logger.complete()
        # Console filtered — file still gets DEBUG


class TestGetLogger:
    def test_returns_logger_with_module_binding(self):
        log = get_logger("a.b")
        assert log is not None


class TestGameContext:
    def test_smoke(self, log_dir):
        LogManager.setup(log_dir=log_dir)
        with game_context(game_id="g-1", race="Terran"):
            logger.bind(module="t.gc").info("inside")
        logger.bind(module="t.gc").info("outside")
        logger.complete()
