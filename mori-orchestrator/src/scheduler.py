"""
scheduler.py — DB-native cron scheduler for Mori.

Polls SQLite every 60 seconds for scheduled_tasks where next_run_at <= now.
Creates a new task in the tasks table based on the template.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import structlog

from .db import Database

log = structlog.get_logger(__name__)


class Scheduler:
    def __init__(self, db: Database):
        self.db = db
        self.running = True

    async def run(self) -> None:
        log.info("scheduler_started")
        while self.running:
            try:
                await self._tick()
            except Exception as e:
                log.error("scheduler_tick_error", error=str(e))
            await asyncio.sleep(60)

    async def _tick(self) -> None:
        due = await self.db.get_due_scheduled_tasks()
        if not due:
            return

        log.info("scheduler_due_tasks", count=len(due))
        for scheduled in due:
            try:
                await self._trigger(scheduled)
                await self.db.advance_scheduled_task(scheduled["id"])
            except Exception as e:
                log.error("scheduler_trigger_error", scheduled_id=scheduled["id"], error=str(e))

    async def _trigger(self, scheduled: dict) -> None:
        """Create a task from a scheduled task template."""
        tags = json.loads(scheduled.get("task_tags") or "[]")
        task = await self.db.create_task(
            title=scheduled["task_title"],
            description=scheduled.get("task_description"),
            tags=tags,
            area=scheduled.get("task_area"),
            priority=scheduled.get("task_priority", "normal"),
            project_id=scheduled.get("task_project_id"),
            pipeline_id=scheduled.get("pipeline_id"),
            agent_id=scheduled.get("agent_id"),
        )
        log.info(
            "scheduled_task_triggered",
            scheduled_id=scheduled["id"],
            task_id=task["id"],
            title=scheduled["task_title"],
        )

    async def shutdown(self) -> None:
        self.running = False
