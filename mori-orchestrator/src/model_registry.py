"""
Model catalog and LiteLLM integration for mori-orchestrator.

Provides:
  - ModelRegistry.get_model(model_id)            → ModelConfig
  - ModelRegistry.build_litellm_kwargs(model)    → dict for litellm.acompletion
  - ModelRegistry.get_fallback(model_id)         → Optional[ModelConfig]
"""

from __future__ import annotations

from typing import Optional

import structlog

from .config import AgentConfig, ModelConfig, MoriConfig

log = structlog.get_logger()


class ModelRegistry:
    """Lookup table for model configs with LiteLLM kwarg builder."""

    def __init__(self, config: MoriConfig) -> None:
        self.config = config
        self._index: dict[str, ModelConfig] = {m.id: m for m in config.models}

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_model(self, model_id: str) -> ModelConfig:
        """
        Return the ModelConfig for *model_id*.

        Raises KeyError if the model is not configured.
        """
        if model_id not in self._index:
            raise KeyError(
                f"Model '{model_id}' not found in config. "
                f"Available: {list(self._index.keys())}"
            )
        return self._index[model_id]

    def get_model_for_agent(self, agent: AgentConfig) -> ModelConfig:
        """Resolve an agent's primary model."""
        return self.get_model(agent.model)

    def get_fallback(self, model_id: str) -> Optional[ModelConfig]:
        """
        Return the fallback model for *model_id* if configured.

        Looks for an AgentConfig whose primary model matches *model_id*
        and has a fallback_model set.  Returns None if no fallback exists.
        """
        # Try to find any agent that uses this model and has a fallback
        for agent in self.config.agents:
            if agent.model == model_id and agent.fallback_model:
                try:
                    return self.get_model(agent.fallback_model)
                except KeyError:
                    log.warning(
                        "fallback_model_not_found",
                        model_id=model_id,
                        fallback_model_id=agent.fallback_model,
                    )
        return None

    def list_models(self) -> list[ModelConfig]:
        return list(self._index.values())

    # ------------------------------------------------------------------
    # LiteLLM kwargs builder
    # ------------------------------------------------------------------

    def build_litellm_kwargs(self, model: ModelConfig) -> dict:
        """
        Build the keyword-argument dict to pass to ``litellm.acompletion``.

        Includes:
          - model      (LiteLLM model string)
          - api_key    (resolved from env, omitted if None)
          - api_base   (for Ollama / custom deployments)
          - max_tokens
        """
        kwargs: dict = {
            "model": model.litellm_model_string,
            "max_tokens": model.max_tokens,
        }

        api_key = model.get_api_key()
        if api_key:
            kwargs["api_key"] = api_key

        if model.base_url:
            kwargs["api_base"] = model.base_url

        # Ollama-specific: point at local server if no explicit base_url
        if model.provider == "ollama" and not model.base_url:
            import os
            ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            kwargs["api_base"] = ollama_url

        log.debug(
            "litellm_kwargs_built",
            model_id=model.id,
            litellm_model=kwargs["model"],
            has_api_key=bool(api_key),
            has_base_url="api_base" in kwargs,
        )
        return kwargs
