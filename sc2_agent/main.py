"""SC2 Agent entry point — starts a StarCraft II game with SC2AgentBot."""

from __future__ import annotations

import os
import sys
from datetime import datetime

import sc2.maps
from sc2.data import Difficulty, Race
from sc2.main import run_game
from sc2.player import Bot, Computer

from sc2_agent.bot import SC2AgentBot
from sc2_agent.config.settings import Settings
from sc2_agent.logging.logger import configure_logging, get_logger


def main() -> int:
    settings = Settings.from_env()
    run_dir = settings.workspace / "storage" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SC2_AGENT_WORKSPACE"] = str(run_dir)
    configure_logging(settings.log_level)
    logger = get_logger(__name__)

    logger.info("Starting SC2 game: Terran(SC2AgentBot) vs Random(VeryEasy)")
    try:
        result = run_game(
            sc2.maps.get("Simple64"),
            [
                Bot(Race.Terran, SC2AgentBot()),
                Computer(Race.Random, Difficulty.VeryEasy),
            ],
            realtime=False,
        )
        logger.info("Game result: %s", result)
    except Exception as e:
        logger.exception("Game crashed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
