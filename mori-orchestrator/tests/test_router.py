"""
Unit tests for src.router — pipeline and agent selection logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.config import (
    AgentConfig,
    MoriConfig,
    OrchestratorConfig,
    PipelineConfig,
    PipelineStep,
    PipelineTrigger,
    RoutingConfig,
)
from src.router import Router, RoutingDecision, SmartRouter


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_pipeline(
    pid: str,
    default: bool = False,
    tags: list[str] | None = None,
    areas: list[str] | None = None,
) -> PipelineConfig:
    trigger = None
    if tags or areas:
        trigger = PipelineTrigger(tags=tags or [], areas=areas or [])
    return PipelineConfig(
        id=pid,
        name=pid,
        default=default,
        trigger=trigger,
        steps=[
            PipelineStep(agent="agent-exec", phase="execute")
        ],
    )


def _make_agent(
    aid: str,
    role: str = "executor",
    enabled: bool = True,
    tags: list[str] | None = None,
    areas: list[str] | None = None,
    keywords: list[str] | None = None,
) -> AgentConfig:
    routing = None
    if tags or areas or keywords:
        routing = RoutingConfig(
            tags=tags or [],
            areas=areas or [],
            keywords=keywords or [],
        )
    return AgentConfig(
        id=aid,
        name=aid,
        model="test-model",
        role=role,  # type: ignore[arg-type]
        enabled=enabled,
        routing=routing,
        system_prompt="You are a test agent.",
    )


def _make_config(
    pipelines: list[PipelineConfig],
    agents: list[AgentConfig] | None = None,
) -> MoriConfig:
    return MoriConfig(
        orchestrator=OrchestratorConfig(),
        models=[],
        agents=agents or [],
        pipelines=pipelines,
    )


# ---------------------------------------------------------------------------
# Pipeline selection tests
# ---------------------------------------------------------------------------


class TestPipelineSelection:
    def test_select_pipeline_by_tags(self) -> None:
        """Tags match should win over default pipeline."""
        p_code = _make_pipeline("pipeline-code", tags=["python", "code"])
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_code, p_default])
        router = Router(config)

        task = {"id": "task-1", "title": "Write a Python script", "tags": ["python"], "area": ""}
        result = router.select_pipeline(task)

        assert result.id == "pipeline-code"

    def test_select_pipeline_by_area(self) -> None:
        """Area match scores +5, enough to beat a default pipeline."""
        p_personal = _make_pipeline("pipeline-personal", areas=["personal"])
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_personal, p_default])
        router = Router(config)

        task = {"id": "task-2", "title": "Plan my week", "tags": [], "area": "personal"}
        result = router.select_pipeline(task)

        assert result.id == "pipeline-personal"

    def test_fallback_to_default_pipeline(self) -> None:
        """No matching trigger → should fall back to default pipeline."""
        p_code = _make_pipeline("pipeline-code", tags=["python"])
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_code, p_default])
        router = Router(config)

        task = {
            "id": "task-3",
            "title": "Meditate for 10 minutes",
            "tags": ["health"],
            "area": "salud",
        }
        result = router.select_pipeline(task)

        assert result.id == "pipeline-default"

    def test_explicit_pipeline_id_wins(self) -> None:
        """Explicit pipeline_id on task overrides all scoring."""
        p_code = _make_pipeline("pipeline-code", tags=["python"])
        p_infra = _make_pipeline("pipeline-infra", tags=["devops"])
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_code, p_infra, p_default])
        router = Router(config)

        task = {
            "id": "task-4",
            "title": "Something",
            "tags": ["python"],
            "area": "",
            "pipeline_id": "pipeline-infra",
        }
        result = router.select_pipeline(task)

        assert result.id == "pipeline-infra"

    def test_first_pipeline_ultimate_fallback(self) -> None:
        """If no default is set, first pipeline is returned."""
        p1 = _make_pipeline("pipeline-first", tags=["alpha"])
        p2 = _make_pipeline("pipeline-second", tags=["beta"])
        config = _make_config([p1, p2])
        router = Router(config)

        task = {"id": "task-5", "title": "Untagged task", "tags": [], "area": ""}
        result = router.select_pipeline(task)

        assert result.id == "pipeline-first"

    def test_tags_score_higher_than_area(self) -> None:
        """Tag match (×10) should beat area-only match (×5)."""
        p_tags = _make_pipeline("pipeline-tags", tags=["devops", "ci"])
        p_area = _make_pipeline("pipeline-area", areas=["sistema"])
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_tags, p_area, p_default])
        router = Router(config)

        task = {
            "id": "task-6",
            "title": "CI pipeline fix",
            "tags": ["devops", "ci"],
            "area": "sistema",
        }
        result = router.select_pipeline(task)

        assert result.id == "pipeline-tags"

    def test_unknown_explicit_pipeline_falls_back(self) -> None:
        """Unknown pipeline_id → fall through to rule/default matching."""
        p_default = _make_pipeline("pipeline-default", default=True)
        config = _make_config([p_default])
        router = Router(config)

        task = {
            "id": "task-7",
            "title": "Something",
            "tags": [],
            "area": "",
            "pipeline_id": "non-existent",
        }
        result = router.select_pipeline(task)

        assert result.id == "pipeline-default"


# ---------------------------------------------------------------------------
# Agent selection tests
# ---------------------------------------------------------------------------


class TestAgentSelection:
    def test_select_agent_by_tags(self) -> None:
        """Tag-matching executor agent should be selected."""
        agent_py = _make_agent("agent-python", tags=["python", "code"])
        agent_infra = _make_agent("agent-infra", tags=["docker", "k8s"])
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_py, agent_infra],
        )
        router = Router(config)

        task = {"id": "t1", "title": "Write Python tests", "tags": ["python"], "area": ""}
        result = router.select_agent(task)

        assert result.id == "agent-python"

    def test_select_agent_by_keywords(self) -> None:
        """Keyword match in task title should influence agent selection."""
        agent_doc = _make_agent("agent-doc", keywords=["documentation", "readme"])
        agent_gen = _make_agent("agent-gen")
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_doc, agent_gen],
        )
        router = Router(config)

        task = {"id": "t2", "title": "Update the README documentation", "tags": [], "area": ""}
        result = router.select_agent(task)

        assert result.id == "agent-doc"

    def test_fallback_to_first_executor(self) -> None:
        """No routing match → first enabled executor is returned."""
        agent_a = _make_agent("agent-a")  # no routing
        agent_b = _make_agent("agent-b", tags=["python"])
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_a, agent_b],
        )
        router = Router(config)

        task = {"id": "t3", "title": "Random task", "tags": [], "area": ""}
        result = router.select_agent(task)

        assert result.id == "agent-a"

    def test_disabled_agents_skipped(self) -> None:
        """Disabled agents should not be selected even if they score highest."""
        agent_disabled = _make_agent("agent-disabled", enabled=False, tags=["python"])
        agent_active = _make_agent("agent-active")
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_disabled, agent_active],
        )
        router = Router(config)

        task = {"id": "t4", "title": "Python work", "tags": ["python"], "area": ""}
        result = router.select_agent(task)

        assert result.id == "agent-active"

    def test_no_executor_raises(self) -> None:
        """ValueError raised when no executor agent is available."""
        agent_reviewer = _make_agent("agent-reviewer", role="reviewer")
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_reviewer],
        )
        router = Router(config)

        task = {"id": "t5", "title": "Some task", "tags": [], "area": ""}
        with pytest.raises(ValueError, match="No executor agent configured"):
            router.select_agent(task)

    def test_area_match_boosts_score(self) -> None:
        """Area match adds +5 to agent score."""
        agent_personal = _make_agent("agent-personal", areas=["personal"])
        agent_generic = _make_agent("agent-generic")
        config = _make_config(
            pipelines=[_make_pipeline("p", default=True)],
            agents=[agent_personal, agent_generic],
        )
        router = Router(config)

        task = {"id": "t6", "title": "Untagged personal task", "tags": [], "area": "personal"}
        result = router.select_agent(task)

        assert result.id == "agent-personal"


# ---------------------------------------------------------------------------
# SmartRouter tests
# ---------------------------------------------------------------------------


class TestSmartRouter:
    def test_routing_decision_dataclass(self) -> None:
        """RoutingDecision dataclass instantiates with correct defaults."""
        decision = RoutingDecision(
            pipeline_id="code_pipeline",
            agent_id="coder",
            reasoning="Test reasoning.",
            confidence=0.9,
            source="rule",
        )
        assert decision.pipeline_id == "code_pipeline"
        assert decision.agent_id == "coder"
        assert decision.confidence == 0.9
        assert decision.source == "rule"
        assert decision.split is False
        assert decision.subtasks == []

    @pytest.mark.asyncio
    async def test_smart_router_uses_rules_when_high_confidence(self) -> None:
        """When rule confidence >= 0.7, SmartRouter returns rule decision without calling LLM."""
        p_code = _make_pipeline("code_pipeline", tags=["python", "code", "dev"])
        p_default = _make_pipeline("pipeline-default", default=True)
        agent_py = _make_agent("coder", tags=["python", "code", "dev"])
        config = _make_config(
            pipelines=[p_code, p_default],
            agents=[agent_py],
        )
        # smart_routing enabled but confidence will be high
        config.orchestrator.smart_routing = True

        router = SmartRouter(config)

        # Task with 3 matching tags → score = 30 → confidence = 0.9
        task = {
            "id": "sr-t1",
            "title": "Write Python code",
            "tags": ["python", "code", "dev"],
            "area": "",
        }

        with patch("src.router.SmartRouter._llm_route", new_callable=AsyncMock) as mock_llm:
            decision = await router.route(task)

        # LLM should NOT have been called
        mock_llm.assert_not_called()
        assert decision.source == "rule"
        assert decision.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_smart_router_returns_rule_decision_with_source_rule(self) -> None:
        """When smart_routing is False, always returns a rule-sourced decision."""
        p_default = _make_pipeline("pipeline-default", default=True)
        agent_gen = _make_agent("agent-gen")
        config = _make_config(
            pipelines=[p_default],
            agents=[agent_gen],
        )
        # smart_routing disabled
        config.orchestrator.smart_routing = False

        router = SmartRouter(config)

        task = {"id": "sr-t2", "title": "Some task", "tags": [], "area": ""}

        with patch("src.router.SmartRouter._llm_route", new_callable=AsyncMock) as mock_llm:
            decision = await router.route(task)

        mock_llm.assert_not_called()
        assert decision.source == "rule"
        assert isinstance(decision, RoutingDecision)

    @pytest.mark.asyncio
    async def test_llm_fallback_on_llm_error(self) -> None:
        """When LLM call fails, SmartRouter returns the rule-based decision as fallback."""
        p_default = _make_pipeline("pipeline-default", default=True)
        agent_gen = _make_agent("agent-gen")
        config = _make_config(
            pipelines=[p_default],
            agents=[agent_gen],
        )
        # Enable smart_routing but confidence will be 0.0 (no tags/areas match)
        config.orchestrator.smart_routing = True
        config.orchestrator.routing_model = "non-existent-model"

        router = SmartRouter(config)

        task = {"id": "sr-t3", "title": "Unmatched task", "tags": [], "area": ""}

        # Mock litellm.acompletion to raise an exception
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = RuntimeError("LLM connection failed")
            decision = await router.route(task)

        # Should fall back to rule-based decision
        assert decision.source == "rule"
        assert isinstance(decision, RoutingDecision)
        assert decision.pipeline_id == "pipeline-default"
