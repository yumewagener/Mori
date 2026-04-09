from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel

RunStatus = Literal["running", "completed", "failed", "cancelled"]


class AgentRun(BaseModel):
    id: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    phase: Optional[str] = None
    status: RunStatus
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    turns_used: int = 0
    duration_seconds: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None


class AgentRunList(BaseModel):
    items: list[AgentRun]
    total: int


class AgentStats(BaseModel):
    agent_id: str
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    success_rate: float = 0.0
    avg_cost_usd: Optional[float] = None
    total_cost_usd: Optional[float] = None
    avg_turns: Optional[float] = None
    avg_duration_seconds: Optional[float] = None


class ModelStats(BaseModel):
    model_id: str
    total_runs: int = 0
    total_prompt_tokens: Optional[int] = None
    total_completion_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    avg_response_time: Optional[float] = None
