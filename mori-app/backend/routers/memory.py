"""
backend/routers/memory.py — Memory chunks + FTS search across notes and tasks.
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..db import Database
from ..models.note import Note, NoteList

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


class MemoryChunk(BaseModel):
    id: str
    source_type: str
    source_id: str
    content: str
    created_at: str
    updated_at: str


class MemoryChunkList(BaseModel):
    items: list[MemoryChunk]
    total: int


class SearchResult(BaseModel):
    notes: list[Note]
    tasks: list[dict]


# ─────────────────────────── GET /memory/search ──────────────

@router.get("/search", response_model=SearchResult)
async def search_memory(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(_get_db),
) -> SearchResult:
    notes = await db.search_notes_fts(q, limit=limit)
    tasks = await db.get_tasks(search=q, limit=limit)
    return SearchResult(
        notes=[Note(**n) for n in notes],
        tasks=tasks,
    )


# ─────────────────────────── GET /memory/chunks ──────────────

@router.get("/chunks", response_model=MemoryChunkList)
async def list_memory_chunks(
    source_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> MemoryChunkList:
    chunks = await db.get_memory_chunks(source_type=source_type, limit=limit, offset=offset)
    return MemoryChunkList(items=[MemoryChunk(**c) for c in chunks], total=len(chunks))


# ─────────────────────────── DELETE /memory/chunks/{id} ──────

@router.delete("/chunks/{chunk_id}", status_code=204)
async def delete_memory_chunk(
    chunk_id: str,
    db: Database = Depends(_get_db),
) -> None:
    deleted = await db.delete_memory_chunk(chunk_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory chunk '{chunk_id}' not found")
    log.info("memory_chunk.deleted", id=chunk_id)
