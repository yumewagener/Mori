"""
Pydantic v2 configuration models and YAML loader for mori-orchestrator.
All settings are sourced from a single YAML file whose path is provided
at startup (env MORI_CONFIG, default /config/mori.yaml).
"""

from __future__ import annotations

import os
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Orchestrator-level settings
# ---------------------------------------------------------------------------


class OrchestratorConfig(BaseModel):
    poll_seconds: int = 15
    max_parallel_tasks: int = 4
    max_parallel_per_project: int = 2
    heartbeat_seconds: int = 30
    timeout_default_seconds: int = 1800
    retry_on_failure: int = 1
    stream_output: bool = True
    smart_routing: bool = False        # usa LLM para routing cuando confianza es baja
    routing_model: Optional[str] = None  # model_id para routing (si None, usa agente role=router)


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    id: str
    provider: Literal["anthropic", "openai", "google", "ollama", "custom", "claude-cli"]
    model: str
    api_key_env: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 8192
    capabilities: list[str] = []
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    supports_tools: bool = True
    cli_path: str = "claude"          # path to claude binary
    allowed_tools: list[str] = ["Read", "Edit", "Bash", "WebSearch", "ListDirectory"]
    max_turns: int = 20

    def get_api_key(self) -> Optional[str]:
        """Resolve API key from environment."""
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return None

    @property
    def is_cli_provider(self) -> bool:
        return self.provider == "claude-cli"

    @property
    def litellm_model_string(self) -> str:
        """Return the model identifier string that LiteLLM understands."""
        if self.provider == "ollama":
            return f"ollama/{self.model}"
        elif self.provider == "anthropic":
            return self.model
        elif self.provider == "openai":
            return self.model
        elif self.provider == "google":
            return f"gemini/{self.model}"
        # custom or unknown — pass through as-is
        return self.model


# ---------------------------------------------------------------------------
# Routing rules (for agents and pipelines)
# ---------------------------------------------------------------------------


class RoutingConfig(BaseModel):
    tags: list[str] = []
    areas: list[str] = []
    keywords: list[str] = []


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    id: str
    name: str
    model: str
    fallback_model: Optional[str] = None
    role: Literal["router", "executor", "reviewer", "validator", "planner"]
    enabled: bool = True
    routing: Optional[RoutingConfig] = None
    system_prompt: str = ""
    tools: list[str] = []
    working_directory: bool = False
    timeout_seconds: int = 1800


# ---------------------------------------------------------------------------
# Pipeline definitions
# ---------------------------------------------------------------------------


class PipelineStep(BaseModel):
    agent: str
    phase: str
    condition: Optional[Literal["on_success", "needs_changes", "always"]] = "always"
    optional: bool = False
    parallel: bool = False
    max_iterations: int = 1


class PipelineTrigger(BaseModel):
    tags: list[str] = []
    areas: list[str] = []


class PipelineConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    default: bool = False
    trigger: Optional[PipelineTrigger] = None
    steps: list[PipelineStep] = []


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class MemoryConfig(BaseModel):
    enabled: bool = True
    embedding_model: str = "nomic-embed-text"
    fallback: Literal["tfidf", "none"] = "tfidf"
    top_k: int = 5
    sources: list[str] = ["notes", "decisions", "task_history"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class WebSearchConfig(BaseModel):
    enabled: bool = False
    provider: str = "searxng"
    searxng_url: str = "http://localhost:8888"


class ShellConfig(BaseModel):
    enabled: bool = False
    allowed_commands: list[str] = ["git", "pytest", "npm", "cargo", "make"]
    working_directory_only: bool = True


class BrowserConfig(BaseModel):
    enabled: bool = False
    headless: bool = True


class ToolsConfig(BaseModel):
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    shell: ShellConfig = Field(default_factory=ShellConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token_env: str = "MORI_TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "MORI_TELEGRAM_CHAT_ID"
    on_events: list[str] = ["task_completed", "task_failed", "pipeline_blocked"]


class WebhookConfig(BaseModel):
    enabled: bool = False
    url_env: str = "MORI_WEBHOOK_URL"


class NotificationsConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class MoriConfig(BaseModel):
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    models: list[ModelConfig] = []
    agents: list[AgentConfig] = []
    pipelines: list[PipelineConfig] = []
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(path: str) -> MoriConfig:
    """Load and validate config from a YAML file."""
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return MoriConfig(**data)
