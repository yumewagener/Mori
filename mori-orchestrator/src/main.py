"""
mori-orchestrator entry point.
Loads YAML config, initialises the database, and starts the main polling loop.
"""

import asyncio
import os
import signal

import structlog

from .config import load_config
from .db import Database
from .orchestrator import Orchestrator

log = structlog.get_logger()


async def main() -> None:
    # ---------- config ---------------------------------------------------
    config_path = os.environ.get("MORI_CONFIG", "/config/mori.yaml")
    config = load_config(config_path)

    # ---------- database -------------------------------------------------
    db_path = os.environ.get("MORI_DB_PATH", "/data/mori.sqlite3")
    db = Database(db_path)
    await db.initialize()

    # ---------- orchestrator ---------------------------------------------
    orchestrator = Orchestrator(config, db)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(orchestrator.shutdown())
        )

    log.info(
        "mori-orchestrator starting",
        version="2.0.0",
        config=config_path,
        db=db_path,
        max_parallel_tasks=config.orchestrator.max_parallel_tasks,
        poll_seconds=config.orchestrator.poll_seconds,
    )

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
