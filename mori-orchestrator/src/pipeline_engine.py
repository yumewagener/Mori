"""
Pipeline execution engine for mori-orchestrator.

Runs each step of a pipeline in order, evaluating conditions, resolving
agents, retrieving memory context, and recording every agent run.

Reviewer output is parsed for APROBADO / NECESITA_CAMBIOS / RECHAZADO
keywords to determine the next step's condition.
"""

from __future__ import annotations

import structlog

from .config import AgentConfig, MoriConfig, PipelineConfig, PipelineStep
from .db import Database
from .memory import Memory
from .metrics import Metrics
from .router import Router, SmartRouter

log = structlog.get_logger()


class PipelineEngine:
    """
    Executes a pipeline step-by-step for a given task.

    Executor and supporting objects are lazy-initialised to break
    circular import chains.
    """

    def __init__(self, config: MoriConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.router = SmartRouter(config)
        self.memory = Memory(config, db)
        self.metrics = Metrics(db)
        self._executor = None  # lazy

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(
        self,
        task: dict,
        pipeline: PipelineConfig,
        preferred_agent_id: str | None = None,
    ) -> dict:
        """
        Execute all steps in *pipeline* for *task*.

        When *preferred_agent_id* is set, steps with agent="auto" will use
        that agent instead of the default rule-based selection.

        Returns a dict::

            {
                "success": bool,
                "result": AgentResult | None,
                "pipeline_id": str,
            }
        """
        task_id: str = task["id"]
        log.info(
            "pipeline_started",
            task_id=task_id,
            pipeline_id=pipeline.id,
            steps=len(pipeline.steps),
        )

        last_result = None
        last_status = "success"  # "success" | "needs_changes" | "failed"

        for step_idx, step in enumerate(pipeline.steps):
            # ---- Condition gate -----------------------------------
            should_run = self._should_run_step(step, last_status)
            if not should_run:
                if step.optional:
                    log.debug(
                        "step_skipped_optional",
                        task_id=task_id,
                        phase=step.phase,
                        condition=step.condition,
                        last_status=last_status,
                    )
                    continue
                else:
                    log.info(
                        "pipeline_halted",
                        task_id=task_id,
                        phase=step.phase,
                        reason=f"condition={step.condition} not met, last_status={last_status}",
                    )
                    break

            # ---- Resolve agent ------------------------------------
            try:
                agent = self._resolve_agent(step, task, preferred_agent_id=preferred_agent_id)
            except ValueError as exc:
                log.error("agent_resolution_failed", task_id=task_id, error=str(exc))
                await self.db.fail_task(task_id, str(exc))
                return {"success": False, "result": None, "pipeline_id": pipeline.id}

            log.info(
                "step_started",
                task_id=task_id,
                step=step_idx + 1,
                phase=step.phase,
                agent=agent.id,
                model=agent.model,
            )

            # ---- Create run record --------------------------------
            run_id = await self.db.create_agent_run(
                task_id=task_id,
                agent_id=agent.id,
                model_id=agent.model,
                pipeline_id=pipeline.id,
                phase=step.phase,
            )

            # ---- Retrieve memory context -------------------------
            context = ""
            if self.config.memory.enabled:
                try:
                    context = await self.memory.retrieve(task)
                except Exception as exc:
                    log.warning("memory_retrieve_failed", run_id=run_id, error=str(exc))

            # ---- Execute ----------------------------------------
            executor = self._get_executor()
            result = await executor.execute(
                task=task,
                agent=agent,
                context=context,
                run_id=run_id,
                max_turns=step.max_iterations * 10,  # turns ≈ iterations × turns_per_iter
            )

            # ---- Persist run record ------------------------------
            await self.db.finish_agent_run(
                run_id=run_id,
                output=result.content,
                status="completed" if result.success else "failed",
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                turns_used=result.turns_used,
            )

            # ---- Record metrics ----------------------------------
            await self.metrics.record_execution(
                run_id=run_id,
                cost_usd=result.cost_usd,
                duration_seconds=result.duration_seconds,
                model_id=agent.model,
                agent_id=agent.id,
                success=result.success,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )

            log.info(
                "step_finished",
                task_id=task_id,
                phase=step.phase,
                agent=agent.id,
                success=result.success,
                turns_used=result.turns_used,
                cost_usd=round(result.cost_usd, 6),
            )

            # ---- Evaluate reviewer output -----------------------
            if agent.role == "reviewer":
                last_status = self._parse_reviewer_output(result.content)
                log.info(
                    "reviewer_verdict",
                    task_id=task_id,
                    phase=step.phase,
                    verdict=last_status,
                )
            else:
                last_status = "success" if result.success else "failed"

            last_result = result

        # ---- Finalise task -----------------------------------------
        if last_result and last_result.success and last_status in ("success",):
            await self.db.finish_task(
                task_id=task_id,
                result=last_result.content,
                cost_usd=last_result.cost_usd,
                agent_id=None,
                model_id=None,
            )
            log.info(
                "pipeline_completed",
                task_id=task_id,
                pipeline_id=pipeline.id,
                cost_usd=round(last_result.cost_usd, 6),
            )
            return {
                "success": True,
                "result": last_result,
                "pipeline_id": pipeline.id,
            }
        else:
            error_msg = (
                f"Pipeline '{pipeline.id}' ended with status '{last_status}'"
                + (f": {last_result.error}" if last_result and last_result.error else "")
            )
            await self.db.fail_task(task_id, error_msg)
            log.warning(
                "pipeline_failed",
                task_id=task_id,
                pipeline_id=pipeline.id,
                last_status=last_status,
            )
            return {
                "success": False,
                "result": last_result,
                "pipeline_id": pipeline.id,
            }

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    def _should_run_step(self, step: PipelineStep, last_status: str) -> bool:
        cond = step.condition or "always"
        if cond == "always":
            return True
        if cond == "on_success":
            return last_status == "success"
        if cond == "needs_changes":
            return last_status == "needs_changes"
        return True

    def _resolve_agent(
        self,
        step: PipelineStep,
        task: dict,
        preferred_agent_id: str | None = None,
    ) -> AgentConfig:
        if step.agent == "auto":
            # Use preferred_agent_id if provided and valid
            if preferred_agent_id:
                for agent in self.config.agents:
                    if agent.id == preferred_agent_id and agent.enabled:
                        return agent
            return self.router.select_agent(task)
        for agent in self.config.agents:
            if agent.id == step.agent:
                if not agent.enabled:
                    raise ValueError(f"Agent '{step.agent}' is disabled")
                return agent
        raise ValueError(f"Agent '{step.agent}' not found in config")

    # ------------------------------------------------------------------
    # Reviewer output parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_reviewer_output(content: str) -> str:
        """
        Parse reviewer verdict from output text.

        Returns "success", "needs_changes", or "failed".
        """
        upper = content.upper()
        if "APROBADO" in upper:
            return "success"
        if "NECESITA_CAMBIOS" in upper or "NECESITA CAMBIOS" in upper:
            return "needs_changes"
        if "RECHAZADO" in upper:
            return "failed"
        # Ambiguous — treat as success to keep moving
        return "success"

    # ------------------------------------------------------------------
    # Lazy executor initialisation
    # ------------------------------------------------------------------

    def _get_executor(self):
        if self._executor is None:
            from .executor import Executor
            from .stream import StreamManager
            from .tool_manager import ToolManager

            self._executor = Executor(
                config=self.config,
                db=self.db,
                tool_manager=ToolManager(self.config),
                stream=StreamManager(self.db),
            )
        return self._executor
