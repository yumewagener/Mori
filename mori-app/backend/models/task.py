from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


AreaType = Literal["personal", "empresa", "proyecto", "sistema", "salud", "finanzas", "otro"]
StatusType = Literal["pendiente", "en_progreso", "completada", "bloqueada", "cancelada"]
PriorityType = Literal["baja", "normal", "alta", "critica"]


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    tags: Optional[list[str]] = Field(default_factory=list)
    area: Optional[AreaType] = None
    priority: Optional[PriorityType] = "normal"
    project_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[StatusType] = None
    tags: Optional[list[str]] = None
    area: Optional[AreaType] = None
    priority: Optional[PriorityType] = None
    pipeline_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    run_cost_usd: Optional[float] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    area: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    run_cost_usd: Optional[float] = None
    context_used: Optional[int] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskList(BaseModel):
    items: list[Task]
    total: int
    limit: int
    offset: int
