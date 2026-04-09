"""
Unit tests for src.config — YAML loading and Pydantic v2 validation.
"""

from __future__ import annotations

import os
import textwrap
import tempfile

import pytest

from src.config import (
    AgentConfig,
    MemoryConfig,
    MoriConfig,
    ModelConfig,
    OrchestratorConfig,
    PipelineConfig,
    PipelineStep,
    PipelineTrigger,
    RoutingConfig,
    ToolsConfig,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(content: str) -> str:
    """Write *content* to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    tmp.write(textwrap.dedent(content))
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Default / empty config
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_empty_yaml_loads_defaults(self) -> None:
        path = _write_yaml("{}")
        try:
            config = load_config(path)
        finally:
            os.unlink(path)

        assert isinstance(config, MoriConfig)
        assert config.orchestrator.poll_seconds == 15
        assert config.orchestrator.max_parallel_tasks == 4
        assert config.orchestrator.stream_output is True
        assert config.models == []
        assert config.agents == []
        assert config.pipelines == []

    def test_orchestrator_defaults(self) -> None:
        cfg = OrchestratorConfig()
        assert cfg.poll_seconds == 15
        assert cfg.max_parallel_tasks == 4
        assert cfg.max_parallel_per_project == 2
        assert cfg.heartbeat_seconds == 30
        assert cfg.timeout_default_seconds == 1800
        assert cfg.retry_on_failure == 1
        assert cfg.stream_output is True

    def test_memory_defaults(self) -> None:
        mem = MemoryConfig()
        assert mem.enabled is True
        assert mem.top_k == 5
        assert "notes" in mem.sources
        assert "task_history" in mem.sources

    def test_tools_defaults(self) -> None:
        tools = ToolsConfig()
        assert tools.web_search.enabled is False
        assert tools.shell.enabled is False
        assert tools.browser.enabled is False


# ---------------------------------------------------------------------------
# Full YAML loading
# ---------------------------------------------------------------------------


FULL_YAML = """\
orchestrator:
  poll_seconds: 10
  max_parallel_tasks: 6
  stream_output: false

models:
  - id: claude-opus
    provider: anthropic
    model: claude-opus-4-5
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 16384
    supports_tools: true
    cost_per_1k_input: 15.0
    cost_per_1k_output: 75.0
    capabilities:
      - coding
      - reasoning

  - id: llama-local
    provider: ollama
    model: llama3.1:8b
    max_tokens: 8192
    supports_tools: false

agents:
  - id: agent-executor
    name: Executor
    model: claude-opus
    fallback_model: llama-local
    role: executor
    enabled: true
    system_prompt: "You are a capable agent."
    tools:
      - web_search
      - shell
    routing:
      tags:
        - python
        - backend
      areas:
        - proyecto
      keywords:
        - refactor
        - implement

  - id: agent-reviewer
    name: Reviewer
    model: claude-opus
    role: reviewer
    enabled: true
    system_prompt: "Review the work and respond with APROBADO or NECESITA_CAMBIOS."

pipelines:
  - id: pipeline-code
    name: Code Pipeline
    description: For coding tasks
    default: false
    trigger:
      tags:
        - python
        - backend
      areas:
        - proyecto
    steps:
      - agent: agent-executor
        phase: execute
        condition: always
        max_iterations: 3
      - agent: agent-reviewer
        phase: review
        condition: on_success
        optional: true
        max_iterations: 1

  - id: pipeline-default
    name: Default Pipeline
    default: true
    steps:
      - agent: agent-executor
        phase: execute
        condition: always

memory:
  enabled: true
  top_k: 8
  sources:
    - notes
    - task_history

tools:
  web_search:
    enabled: true
    searxng_url: http://searxng:8888
  shell:
    enabled: true
    allowed_commands:
      - git
      - pytest
      - cargo

notifications:
  telegram:
    enabled: true
    on_events:
      - task_completed
      - task_failed
"""


class TestFullYamlLoading:
    def setup_method(self) -> None:
        self.path = _write_yaml(FULL_YAML)
        self.config = load_config(self.path)

    def teardown_method(self) -> None:
        os.unlink(self.path)

    def test_orchestrator_overrides(self) -> None:
        assert self.config.orchestrator.poll_seconds == 10
        assert self.config.orchestrator.max_parallel_tasks == 6
        assert self.config.orchestrator.stream_output is False

    def test_models_loaded(self) -> None:
        assert len(self.config.models) == 2
        claude = self.config.models[0]
        assert claude.id == "claude-opus"
        assert claude.provider == "anthropic"
        assert claude.model == "claude-opus-4-5"
        assert claude.max_tokens == 16384
        assert claude.cost_per_1k_input == 15.0
        assert claude.cost_per_1k_output == 75.0
        assert "coding" in claude.capabilities

    def test_ollama_model(self) -> None:
        llama = self.config.models[1]
        assert llama.provider == "ollama"
        assert llama.litellm_model_string == "ollama/llama3.1:8b"
        assert llama.supports_tools is False

    def test_anthropic_model_string(self) -> None:
        claude = self.config.models[0]
        assert claude.litellm_model_string == "claude-opus-4-5"

    def test_model_api_key_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        claude = self.config.models[0]
        assert claude.get_api_key() == "sk-test-key"

    def test_model_api_key_missing_env(self) -> None:
        """get_api_key returns None if env var is not set."""
        claude = self.config.models[0]
        # Ensure it's not in the environment
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert claude.get_api_key() is None

    def test_agents_loaded(self) -> None:
        assert len(self.config.agents) == 2
        exec_agent = self.config.agents[0]
        assert exec_agent.id == "agent-executor"
        assert exec_agent.role == "executor"
        assert exec_agent.fallback_model == "llama-local"
        assert "web_search" in exec_agent.tools

    def test_agent_routing(self) -> None:
        exec_agent = self.config.agents[0]
        assert exec_agent.routing is not None
        assert "python" in exec_agent.routing.tags
        assert "proyecto" in exec_agent.routing.areas
        assert "refactor" in exec_agent.routing.keywords

    def test_pipelines_loaded(self) -> None:
        assert len(self.config.pipelines) == 2
        code_pipeline = self.config.pipelines[0]
        assert code_pipeline.id == "pipeline-code"
        assert code_pipeline.default is False
        assert code_pipeline.trigger is not None
        assert "python" in code_pipeline.trigger.tags

    def test_pipeline_steps(self) -> None:
        code_pipeline = self.config.pipelines[0]
        assert len(code_pipeline.steps) == 2
        step0 = code_pipeline.steps[0]
        assert step0.agent == "agent-executor"
        assert step0.phase == "execute"
        assert step0.condition == "always"
        assert step0.max_iterations == 3

        step1 = code_pipeline.steps[1]
        assert step1.agent == "agent-reviewer"
        assert step1.condition == "on_success"
        assert step1.optional is True

    def test_default_pipeline(self) -> None:
        defaults = [p for p in self.config.pipelines if p.default]
        assert len(defaults) == 1
        assert defaults[0].id == "pipeline-default"

    def test_memory_config(self) -> None:
        assert self.config.memory.enabled is True
        assert self.config.memory.top_k == 8
        assert "notes" in self.config.memory.sources
        assert "task_history" in self.config.memory.sources

    def test_tools_web_search(self) -> None:
        ws = self.config.tools.web_search
        assert ws.enabled is True
        assert ws.searxng_url == "http://searxng:8888"

    def test_tools_shell(self) -> None:
        sh = self.config.tools.shell
        assert sh.enabled is True
        assert "git" in sh.allowed_commands
        assert "cargo" in sh.allowed_commands

    def test_notifications_telegram(self) -> None:
        tg = self.config.notifications.telegram
        assert tg.enabled is True
        assert "task_completed" in tg.on_events
        assert "task_failed" in tg.on_events


# ---------------------------------------------------------------------------
# Validation / error cases
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_invalid_provider_raises(self) -> None:
        with pytest.raises(Exception):
            ModelConfig(
                id="bad",
                provider="unsupported_provider",  # type: ignore[arg-type]
                model="x",
            )

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(Exception):
            AgentConfig(
                id="bad-agent",
                name="Bad Agent",
                model="some-model",
                role="invalid_role",  # type: ignore[arg-type]
            )

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(Exception):
            ModelConfig(provider="anthropic", model="claude")  # type: ignore[call-arg]  # missing id

    def test_google_model_string(self) -> None:
        m = ModelConfig(
            id="gemini",
            provider="google",
            model="gemini-1.5-pro",
        )
        assert m.litellm_model_string == "gemini/gemini-1.5-pro"

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_config("/tmp/this_does_not_exist_mori_1234567890.yaml")
