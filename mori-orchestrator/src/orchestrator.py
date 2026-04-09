"""
Main orchestration loop for mori-orchestrator.

Polls the database for pending tasks, dispatches them to the pipeline
engine under a global concurrency semaphore, and handles graceful shutdown.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog

from .config import MoriConfig
from .db import Database
from .memory import Memory
from .router import SmartRouter
from .scheduler import Scheduler

if TYPE_CHECKING:
    from .pipeline_engine import PipelineEngine
    from .router import RoutingDecision

log = structlog.get_logger()


class Orchestrator:
    def __init__(self, config: MoriConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.router = SmartRouter(config)
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
        scheduler = Scheduler(self.db)
        memory = Memory(self.config, self.db)
        semaphore = asyncio.Semaphore(self.config.orchestrator.max_parallel_tasks)

        log.info(
            "orchestrator_loop_started",
            poll_seconds=self.config.orchestrator.poll_seconds,
        )

        # Run scheduler, background indexer, and main poll loop concurrently
        async with asyncio.TaskGroup() as tg:
            tg.create_task(scheduler.run())
            tg.create_task(memory.run_background_indexer())
            tg.create_task(self._poll_loop(semaphore))

    async def _poll_loop(self, semaphore: asyncio.Semaphore) -> None:
        """Main task-polling loop."""
        poll_seconds = self.config.orchestrator.poll_seconds
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
        """Select pipeline via SmartRouter and hand off to the pipeline engine."""
        task_id = task["id"]
        log.info(
            "task_started",
            task_id=task_id,
            title=task.get("title"),
            area=task.get("area"),
            tags=task.get("tags"),
        )

        decision = await self.router.route(task)

        log.info(
            "routing_decision",
            task_id=task_id,
            pipeline=decision.pipeline_id,
            agent=decision.agent_id,
            confidence=decision.confidence,
            source=decision.source,
            reasoning=decision.reasoning,
            split=decision.split,
        )

        if decision.split and decision.subtasks:
            await self._run_split_task(task, decision)
            return

        # Lookup pipeline from the decision
        pipeline = next(
            (p for p in self.config.pipelines if p.id == decision.pipeline_id), None
        )
        if pipeline is None:
            # fallback al primer pipeline
            pipeline = self.config.pipelines[0]

        engine = self._get_pipeline_engine()
        # Pasa el agent_id al engine para que lo use en pasos 'auto'
        await engine.run(task, pipeline, preferred_agent_id=decision.agent_id)

        log.info("task_dispatched", task_id=task_id, pipeline=pipeline.id)

    # ------------------------------------------------------------------
    # Split task handling
    # ------------------------------------------------------------------

    async def _run_split_task(self, parent_task: dict, decision: "RoutingDecision") -> None:
        """Crea subtareas, las ejecuta en paralelo y completa la tarea padre."""
        subtask_records = []
        for st in decision.subtasks:
            subtask_id = str(uuid.uuid4())
            subtask = await self.db.create_task({
                "id": subtask_id,
                "title": st["title"],
                "description": st.get("description", ""),
                "tags": st.get("tags", []),
                "area": st.get("area", parent_task.get("area", "")),
                "project_id": parent_task.get("project_id"),
                "parent_task_id": parent_task["id"],
                "priority": parent_task.get("priority", "normal"),
            })
            subtask_records.append(subtask)

        log.info(
            "split_task_created",
            parent_task_id=parent_task["id"],
            subtask_count=len(subtask_records),
        )

        # Ejecutar subtareas en paralelo
        semaphore = asyncio.Semaphore(self.config.orchestrator.max_parallel_tasks)
        async with asyncio.TaskGroup() as tg:
            for subtask in subtask_records:
                tg.create_task(self._run_task_safe(subtask, semaphore))

        # Marcar tarea padre como completada
        await self.db.complete_task(
            parent_task["id"],
            f"Dividida en {len(subtask_records)} subtareas y completadas.",
        )

    # ------------------------------------------------------------------
    # Immediate task execution (for chat trigger)
    # ------------------------------------------------------------------

    async def execute_task_by_id(self, task_id: str) -> None:
        """Execute a task immediately, bypassing the poll delay.

        Used by the HTTP /trigger endpoint for real-time chat responses.
        Retries up to 10 times with 300ms delay to handle SQLite WAL
        visibility race between the app and orchestrator containers.
        """
        try:
            task = None
            for attempt in range(10):
                task = await self.db.get_task(task_id)
                if task is not None:
                    break
                await asyncio.sleep(0.3)
            if task is None:
                log.warning("trigger_task_not_found", task_id=task_id)
                return
            if task.get("status") != "pendiente":
                log.warning(
                    "trigger_task_not_pending",
                    task_id=task_id,
                    status=task.get("status"),
                )
                return
            log.info("trigger_task_immediate", task_id=task_id)
            await self._run_task(task)
        except Exception as exc:
            log.error("trigger_task_error", task_id=task_id, error=str(exc), exc_info=True)
            try:
                await self.db.fail_task(task_id, str(exc))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        log.info("shutdown_requested")
        self.running = False
