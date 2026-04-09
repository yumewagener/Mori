from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

AreaType = Literal["personal", "empresa", "proyecto", "sistema", "salud", "finanzas", "otro"]
NoteType = Literal["nota", "decision", "investigacion", "diario", "idea"]


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: Optional[str] = ""
    type: Optional[NoteType] = "nota"
    tags: Optional[list[str]] = Field(default_factory=list)
    area: Optional[AreaType] = None
    project_id: Optional[str] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    content: Optional[str] = None
    type: Optional[NoteType] = None
    tags: Optional[list[str]] = None
    area: Optional[AreaType] = None
    project_id: Optional[str] = None


class Note(BaseModel):
    id: str
    title: str
    content: str
    type: str
    tags: list[str] = Field(default_factory=list)
    area: Optional[str] = None
    project_id: Optional[str] = None
    created_at: str
    updated_at: str


class NoteList(BaseModel):
    items: list[Note]
    total: int
    limit: int
    offset: int
