"""
Task routing logic for mori-orchestrator.

Three-level routing:
  1. Explicit pipeline_id on the task record → exact match.
  2. Rule-based tag / area scoring against pipeline triggers.
  3. Default pipeline fallback (first pipeline with default=True,
     or the very first pipeline if none is flagged default).

Agent selection follows the same three-level approach but scoped to
agent.role == "executor".

SmartRouter extends this with an optional LLM-based routing path when
rule confidence is low (< 0.7) and config.orchestrator.smart_routing == True.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional

import structlog

from .config import AgentConfig, MoriConfig, PipelineConfig

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Routing decision dataclass
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    pipeline_id: str
    agent_id: str          # agente para los pasos 'auto' del pipeline
    reasoning: str
    confidence: float      # 0.0-1.0
    source: str            # "rule" | "llm"
    split: bool = False
    subtasks: list[dict] = field(default_factory=list)
    # Cada subtarea: {"title": str, "description": str, "tags": list, "area": str, "agent_id": str}


# ---------------------------------------------------------------------------
# Original rule-based Router (kept for compatibility)
# ---------------------------------------------------------------------------


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

    # ------------------------------------------------------------------
    # Internal scoring helpers (used by SmartRouter)
    # ------------------------------------------------------------------

    def _score_pipeline(self, task: dict) -> int:
        """Return the best rule-based score for pipeline matching."""
        task_tags: set[str] = set(task.get("tags") or [])
        task_area: str = task.get("area") or ""

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
        return best_score

    def _score_agent(self, task: dict) -> int:
        """Return the best rule-based score for agent matching."""
        task_tags: set[str] = set(task.get("tags") or [])
        task_area: str = task.get("area") or ""
        task_title: str = (task.get("title") or "").lower()

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
        return best_score


# ---------------------------------------------------------------------------
# SmartRouter — hybrid rule-based + LLM routing
# ---------------------------------------------------------------------------


class SmartRouter:
    """
    Hybrid router: runs rule-based scoring first, then calls the LLM if
    confidence is below the threshold and smart_routing is enabled.
    """

    def __init__(self, config: MoriConfig) -> None:
        self.config = config
        self._rule_router = Router(config)  # el viejo router, para el path rápido

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def route(self, task: dict) -> RoutingDecision:
        """Entry point principal. Híbrido: reglas primero, LLM si baja confianza."""
        decision, confidence = self._rule_based_route(task)

        if not self.config.orchestrator.smart_routing or confidence >= 0.7:
            return decision

        # Low confidence + smart_routing enabled → ask the LLM
        log.info(
            "smart_routing_llm_path",
            task_id=task.get("id"),
            confidence=confidence,
        )
        return await self._llm_route(task, fallback=decision)

    # ------------------------------------------------------------------
    # Rule-based path
    # ------------------------------------------------------------------

    def _rule_based_route(self, task: dict) -> tuple[RoutingDecision, float]:
        """Ejecuta scoring y devuelve (decision, confidence)."""
        pipeline = self._rule_router.select_pipeline(task)
        try:
            agent = self._rule_router.select_agent(task)
            agent_id = agent.id
        except ValueError:
            agent_id = ""

        # Compute combined score to derive confidence
        pipeline_score = self._rule_router._score_pipeline(task)
        agent_score = self._rule_router._score_agent(task)
        score = max(pipeline_score, agent_score)

        if score == 0:
            confidence = 0.0
        elif score < 10:
            confidence = 0.3
        elif score < 20:
            confidence = 0.6
        else:
            confidence = 0.9

        decision = RoutingDecision(
            pipeline_id=pipeline.id,
            agent_id=agent_id,
            reasoning="Seleccionado por reglas de tags y keywords.",
            confidence=confidence,
            source="rule",
        )
        return decision, confidence

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    async def _llm_route(self, task: dict, fallback: RoutingDecision) -> RoutingDecision:
        """Llama al LLM, valida output, devuelve decisión o fallback."""
        try:
            import litellm

            kwargs = self._get_routing_model_kwargs()
            if not kwargs:
                log.warning("no_routing_model_available")
                return fallback

            prompt = self._build_routing_prompt(task)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Eres el router de Mori, un orquestador de IA multi-agente. "
                        "Responde ÚNICAMENTE con JSON válido, sin texto adicional."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

            # Only add response_format for providers that support it
            model_str: str = kwargs.get("model", "")
            provider_supports_json = any(
                p in model_str
                for p in ("gpt-", "claude", "anthropic", "openai", "gemini")
            ) and "ollama" not in model_str

            call_kwargs: dict = {
                **kwargs,
                "messages": messages,
                "timeout": 10,
            }
            if provider_supports_json:
                call_kwargs["response_format"] = {"type": "json_object"}

            response = await asyncio.wait_for(
                litellm.acompletion(**call_kwargs),
                timeout=10,
            )

            raw = response.choices[0].message.content or ""
            data = json.loads(raw)

            # Validate required fields and IDs
            pipeline_id = data.get("pipeline_id", "")
            agent_id = data.get("agent_id", "")

            valid_pipeline_ids = {p.id for p in self.config.pipelines}
            valid_agent_ids = {
                a.id for a in self.config.agents if a.role == "executor" and a.enabled
            }

            if pipeline_id not in valid_pipeline_ids:
                log.warning(
                    "llm_invalid_pipeline_id",
                    pipeline_id=pipeline_id,
                    valid=list(valid_pipeline_ids),
                )
                return fallback

            if agent_id and agent_id not in valid_agent_ids:
                log.warning(
                    "llm_invalid_agent_id",
                    agent_id=agent_id,
                    valid=list(valid_agent_ids),
                )
                # Use fallback agent_id but keep the pipeline
                agent_id = fallback.agent_id

            subtasks = data.get("subtasks", []) or []
            split = bool(data.get("split", False)) and len(subtasks) > 0

            decision = RoutingDecision(
                pipeline_id=pipeline_id,
                agent_id=agent_id or fallback.agent_id,
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
                source="llm",
                split=split,
                subtasks=subtasks if split else [],
            )
            log.info(
                "llm_routing_success",
                task_id=task.get("id"),
                pipeline=decision.pipeline_id,
                agent=decision.agent_id,
                confidence=decision.confidence,
                split=decision.split,
            )
            return decision

        except asyncio.TimeoutError:
            log.warning("llm_routing_timeout", task_id=task.get("id"))
            return fallback
        except (json.JSONDecodeError, KeyError, ValueError, IndexError) as exc:
            log.warning("llm_routing_parse_error", task_id=task.get("id"), error=str(exc))
            return fallback
        except Exception as exc:
            log.warning("llm_routing_error", task_id=task.get("id"), error=str(exc))
            return fallback

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_routing_prompt(self, task: dict) -> str:
        """Construye el prompt con los agentes y pipelines disponibles."""
        # Build agent list (only executor + enabled)
        agent_lines = []
        for agent in self.config.agents:
            if agent.role != "executor" or not agent.enabled:
                continue
            caps = getattr(agent, "capabilities", [])
            routing_tags: list[str] = []
            routing_keywords: list[str] = []
            if agent.routing:
                routing_tags = agent.routing.tags
                routing_keywords = agent.routing.keywords
            # Try to get capabilities from model config
            model_caps: list[str] = []
            for m in self.config.models:
                if m.id == agent.model:
                    model_caps = m.capabilities
                    break
            agent_lines.append(
                f"  - id: {agent.id}, name: {agent.name}, "
                f"capabilities: {model_caps or caps}, "
                f"routing.tags: {routing_tags}, "
                f"routing.keywords: {routing_keywords}"
            )

        agents_str = "\n".join(agent_lines) if agent_lines else "  (none)"

        # Build pipeline list
        pipeline_lines = []
        for p in self.config.pipelines:
            trigger_tags: list[str] = []
            if p.trigger:
                trigger_tags = p.trigger.tags
            pipeline_lines.append(
                f"  - id: {p.id}, name: {p.name}, "
                f"description: {p.description!r}, "
                f"trigger.tags: {trigger_tags}"
            )

        pipelines_str = "\n".join(pipeline_lines) if pipeline_lines else "  (none)"

        prompt = f"""Eres el router de Mori, un orquestador de IA multi-agente.
Tu trabajo: analizar una tarea y decidir el plan óptimo de ejecución.

AGENTES DISPONIBLES (solo role=executor, enabled=true):
{agents_str}

PIPELINES DISPONIBLES:
{pipelines_str}

TAREA:
Título: {task.get('title', '')}
Descripción: {task.get('description', '')}
Tags: {task.get('tags', [])}
Área: {task.get('area', '')}

Analiza la tarea y responde ÚNICAMENTE con JSON válido, sin texto adicional:
{{
  "pipeline_id": "code_pipeline",
  "agent_id": "coder",
  "reasoning": "Esta es una tarea de implementación de código...",
  "confidence": 0.92,
  "split": false,
  "subtasks": []
}}

Reglas:
- pipeline_id y agent_id deben ser IDs exactos de los listados arriba
- Si la tarea es demasiado grande para un solo agente, pon split=true y lista subtareas concretas en subtasks
- Cada subtarea debe tener: title, description, tags (array), area, agent_id
- confidence entre 0.0 y 1.0
- reasoning en español, máximo 2 frases"""

        return prompt

    # ------------------------------------------------------------------
    # LiteLLM model kwargs
    # ------------------------------------------------------------------

    def _get_routing_model_kwargs(self) -> dict:
        """Devuelve los kwargs de LiteLLM para el modelo de routing."""
        routing_model_id = self.config.orchestrator.routing_model

        # Try explicit routing_model first
        if routing_model_id:
            for m in self.config.models:
                if m.id == routing_model_id:
                    kwargs: dict = {"model": m.litellm_model_string}
                    api_key = m.get_api_key()
                    if api_key:
                        kwargs["api_key"] = api_key
                    if m.base_url:
                        kwargs["api_base"] = m.base_url
                    return kwargs
            log.warning("routing_model_not_found", routing_model_id=routing_model_id)

        # Fall back to agent with role=router
        router_agent = self._rule_router.select_agent_by_role("router")
        if router_agent:
            for m in self.config.models:
                if m.id == router_agent.model:
                    kwargs = {"model": m.litellm_model_string}
                    api_key = m.get_api_key()
                    if api_key:
                        kwargs["api_key"] = api_key
                    if m.base_url:
                        kwargs["api_base"] = m.base_url
                    return kwargs

        return {}

    # ------------------------------------------------------------------
    # Compatibility shims (sync, for tests and pipeline_engine)
    # ------------------------------------------------------------------

    def select_pipeline(self, task: dict) -> PipelineConfig:
        """Sync fallback para tests — usa rule-based."""
        return self._rule_router.select_pipeline(task)

    def select_agent(self, task: dict) -> AgentConfig:
        """Sync fallback para tests — usa rule-based."""
        return self._rule_router.select_agent(task)

    def select_agent_by_role(self, role: str) -> Optional[AgentConfig]:
        return self._rule_router.select_agent_by_role(role)
