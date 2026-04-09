"""
Agent catalog for mori-orchestrator.

Provides fast lookups into the agents section of the YAML config.
"""

from __future__ import annotations

from typing import Literal, Optional

import structlog

from .config import AgentConfig, MoriConfig

log = structlog.get_logger()

AgentRole = Literal["router", "executor", "reviewer", "validator", "planner"]


class AgentRegistry:
    """Index of configured agents."""

    def __init__(self, config: MoriConfig) -> None:
        self.config = config
        self._index: dict[str, AgentConfig] = {a.id: a for a in config.agents}

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> AgentConfig:
        """
        Return the AgentConfig for *agent_id*.

        Raises KeyError if the agent is not found.
        """
        if agent_id not in self._index:
            raise KeyError(
                f"Agent '{agent_id}' not found. "
                f"Available: {list(self._index.keys())}"
            )
        return self._index[agent_id]

    def get_executors(self) -> list[AgentConfig]:
        """Return all enabled executor agents."""
        return [
            a for a in self.config.agents
            if a.role == "executor" and a.enabled
        ]

    def get_agent_for_role(self, role: AgentRole) -> Optional[AgentConfig]:
        """
        Return the first enabled agent with the given role.

        Returns None if no matching agent is configured.
        """
        for agent in self.config.agents:
            if agent.role == role and agent.enabled:
                return agent
        return None

    def list_agents(self, *, enabled_only: bool = True) -> list[AgentConfig]:
        if enabled_only:
            return [a for a in self.config.agents if a.enabled]
        return list(self.config.agents)

    def get_agents_for_role(self, role: AgentRole) -> list[AgentConfig]:
        """Return all enabled agents with *role*."""
        return [a for a in self.config.agents if a.role == role and a.enabled]
