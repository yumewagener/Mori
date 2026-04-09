from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

AreaType = Literal["personal", "empresa", "proyecto", "sistema", "salud", "finanzas", "otro"]
ProjectStatus = Literal["activo", "pausado", "completado", "archivado"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    area: Optional[AreaType] = None
    status: Optional[ProjectStatus] = "activo"
    github_url: Optional[str] = None
    local_path: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    area: Optional[AreaType] = None
    status: Optional[ProjectStatus] = None
    github_url: Optional[str] = None
    local_path: Optional[str] = None


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    status: str
    github_url: Optional[str] = None
    local_path: Optional[str] = None
    created_at: str
    updated_at: str


class ProjectList(BaseModel):
    items: list[Project]
    total: int
    limit: int
    offset: int
