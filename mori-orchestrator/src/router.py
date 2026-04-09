"""
Task routing logic for mori-orchestrator.

Three-level routing:
  1. Explicit pipeline_id on the task record → exact match.
  2. Rule-based tag / area scoring against pipeline triggers.
  3. Default pipeline fallback (first pipeline with default=True,
     or the very first pipeline if none is flagged default).

Agent selection follows the same three-level approach but scoped to
agent.role == "executor".
"""

from __future__ import annotations

import structlog

from .config import AgentConfig, MoriConfig, PipelineConfig

log = structlog.get_logger()


class Router:
    def __init__(self, config: MoriConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Pipeline selection
    # ------------------------------------------------------------------

    def select_pipeline(self, task: dict) -> PipelineConfig:
        """
        Choose the most appropriate pipeline for *task*.

        Priority:
          1. task["pipeline_id"] explicit override
          2. Highest-scoring trigger match (tags × 10 + area × 5)
          3. Default pipeline
        """
        if not self.config.pipelines:
            raise ValueError("No pipelines configured — add at least one pipeline to mori.yaml")

        # --- Level 1: explicit ---
        explicit_id: str | None = task.get("pipeline_id")
        if explicit_id:
            for p in self.config.pipelines:
                if p.id == explicit_id:
                    log.debug("pipeline_explicit", task_id=task.get("id"), pipeline=explicit_id)
                    return p
            log.warning(
                "pipeline_id_not_found",
                task_id=task.get("id"),
                pipeline_id=explicit_id,
            )

        # --- Level 2: rule-based ---
        task_tags: set[str] = set(task.get("tags") or [])
        task_area: str = task.get("area") or ""

        best_pipeline: PipelineConfig | None = None
        best_score: int = 0

        for pipeline in self.config.pipelines:
            if pipeline.default:
                continue
            if not pipeline.trigger:
                continue

            score = 0
            trigger_tags = set(pipeline.trigger.tags)
            if task_tags and trigger_tags:
                score += len(task_tags & trigger_tags) * 10
            if task_area and task_area in (pipeline.trigger.areas or []):
                score += 5

            if score > best_score:
                best_score = score
                best_pipeline = pipeline

        if best_pipeline and best_score > 0:
            log.debug(
                "pipeline_rule_match",
                task_id=task.get("id"),
                pipeline=best_pipeline.id,
                score=best_score,
            )
            return best_pipeline

        # --- Level 3: default / first ---
        for p in self.config.pipelines:
            if p.default:
                log.debug("pipeline_default", task_id=task.get("id"), pipeline=p.id)
                return p

        log.debug(
            "pipeline_first_fallback",
            task_id=task.get("id"),
            pipeline=self.config.pipelines[0].id,
        )
        return self.config.pipelines[0]

    # ------------------------------------------------------------------
    # Agent selection
    # ------------------------------------------------------------------

    def select_agent(self, task: dict) -> AgentConfig:
        """
        Choose the best executor agent for *task*.

        Scoring:
          - Matching tag:   +10 per tag
          - Matching area:  +5
          - Matching keyword in title: +3 per keyword

        Falls back to the first enabled executor if no scored match found.
        """
        task_tags: set[str] = set(task.get("tags") or [])
        task_area: str = task.get("area") or ""
        task_title: str = (task.get("title") or "").lower()

        best_agent: AgentConfig | None = None
        best_score: int = 0

        for agent in self.config.agents:
            if agent.role != "executor" or not agent.enabled:
                continue
            if not agent.routing:
                continue

            score = 0
            agent_tags = set(agent.routing.tags)
            if task_tags and agent_tags:
                score += len(task_tags & agent_tags) * 10
            if task_area and task_area in (agent.routing.areas or []):
                score += 5
            for kw in agent.routing.keywords:
                if kw.lower() in task_title:
                    score += 3

            if score > best_score:
                best_score = score
                best_agent = agent

        if best_agent:
            log.debug(
                "agent_rule_match",
                task_id=task.get("id"),
                agent=best_agent.id,
                score=best_score,
            )
            return best_agent

        # Fallback: first enabled executor (no routing rules required)
        for agent in self.config.agents:
            if agent.role == "executor" and agent.enabled:
                log.debug(
                    "agent_first_fallback",
                    task_id=task.get("id"),
                    agent=agent.id,
                )
                return agent

        raise ValueError(
            "No executor agent configured — add at least one agent with role='executor' to mori.yaml"
        )

    def select_agent_by_role(self, role: str) -> AgentConfig | None:
        """Return the first enabled agent with the given role, or None."""
        for agent in self.config.agents:
            if agent.role == role and agent.enabled:
                return agent
        return None
