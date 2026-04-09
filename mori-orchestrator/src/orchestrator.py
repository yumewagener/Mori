"""
Main orchestration loop for mori-orchestrator.

Polls the database for pending tasks, dispatches them to the pipeline
engine under a global concurrency semaphore, and handles graceful shutdown.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from .config import MoriConfig
from .db import Database
from .router import Router

if TYPE_CHECKING:
    from .pipeline_engine import PipelineEngine

log = structlog.get_logger()


class Orchestrator:
    def __init__(self, config: MoriConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.router = Router(config)
        self.running = True
        # Per-project semaphores to limit parallelism per project
        self._project_semaphores: dict[str, asyncio.Semaphore] = {}
        # Lazily created pipeline engine to avoid circular imports at module load
        self._pipeline_engine: "PipelineEngine | None" = None

    # ------------------------------------------------------------------
    # Pipeline engine — lazy init
    # ------------------------------------------------------------------

    def _get_pipeline_engine(self) -> "PipelineEngine":
        if self._pipeline_engine is None:
            from .pipeline_engine import PipelineEngine
            self._pipeline_engine = PipelineEngine(self.config, self.db)
        return self._pipeline_engine

    # ------------------------------------------------------------------
    # Per-project semaphore
    # ------------------------------------------------------------------

    def _project_semaphore(self, project_id: str) -> asyncio.Semaphore:
        if project_id not in self._project_semaphores:
            self._project_semaphores[project_id] = asyncio.Semaphore(
                self.config.orchestrator.max_parallel_per_project
            )
        return self._project_semaphores[project_id]

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Poll for pending tasks and dispatch them concurrently."""
        semaphore = asyncio.Semaphore(self.config.orchestrator.max_parallel_tasks)
        poll_seconds = self.config.orchestrator.poll_seconds

        log.info("orchestrator_loop_started", poll_seconds=poll_seconds)

        while self.running:
            try:
                tasks = await self.db.claim_pending_tasks(
                    limit=self.config.orchestrator.max_parallel_tasks
                )
            except Exception as exc:
                log.error("poll_error", error=str(exc))
                await asyncio.sleep(poll_seconds)
                continue

            if not tasks:
                await asyncio.sleep(poll_seconds)
                continue

            log.info("tasks_claimed", count=len(tasks))

            # Dispatch all claimed tasks concurrently
            async with asyncio.TaskGroup() as tg:
                for task in tasks:
                    tg.create_task(self._run_task_safe(task, semaphore))

    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    async def _run_task_safe(
        self, task: dict, semaphore: asyncio.Semaphore
    ) -> None:
        """Wrapper that catches any exception and marks the task failed."""
        task_id = task["id"]
        project_id = task.get("project_id", "_global")
        proj_sem = self._project_semaphore(project_id)

        try:
            async with semaphore:
                async with proj_sem:
                    await self._run_task(task)
        except asyncio.CancelledError:
            log.warning("task_cancelled", task_id=task_id)
            await self.db.fail_task(task_id, "Task cancelled during shutdown")
        except Exception as exc:
            log.error("task_error", task_id=task_id, error=str(exc), exc_info=True)
            await self.db.fail_task(task_id, str(exc))

    async def _run_task(self, task: dict) -> None:
        """Select pipeline and hand off to the pipeline engine."""
        task_id = task["id"]
        log.info(
            "task_started",
            task_id=task_id,
            title=task.get("title"),
            area=task.get("area"),
            tags=task.get("tags"),
        )

        pipeline = self.router.select_pipeline(task)
        log.info(
            "pipeline_selected",
            task_id=task_id,
            pipeline_id=pipeline.id,
            pipeline_name=pipeline.name,
        )

        engine = self._get_pipeline_engine()
        await engine.run(task, pipeline)

        log.info("task_dispatched", task_id=task_id, pipeline=pipeline.id)

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        log.info("shutdown_requested")
        self.running = False
