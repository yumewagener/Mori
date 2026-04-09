"""
backend/routers/notes.py — Notes CRUD + FTS5 search.

Note: the /notes/search route must be registered BEFORE /notes/{id}
so FastAPI doesn't mistake "search" for an ID.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..db import Database
from ..models.note import Note, NoteCreate, NoteList, NoteUpdate

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/notes", tags=["notes"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


# ─────────────── GET /notes/search  (must come before /{id}) ──

@router.get("/search", response_model=NoteList)
async def search_notes(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(_get_db),
) -> NoteList:
    items = await db.search_notes_fts(q, limit=limit)
    return NoteList(items=[Note(**n) for n in items], total=len(items), limit=limit, offset=0)


# ─────────────────────────── GET /notes ──────────────────────

@router.get("", response_model=NoteList)
async def list_notes(
    type: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> NoteList:
    items = await db.get_notes(
        type=type,
        area=area,
        project_id=project_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return NoteList(items=[Note(**n) for n in items], total=len(items), limit=limit, offset=offset)


# ─────────────────────────── POST /notes ─────────────────────

@router.post("", response_model=Note, status_code=201)
async def create_note(
    payload: NoteCreate,
    db: Database = Depends(_get_db),
) -> Note:
    nid = str(uuid4()).replace("-", "").upper()[:26]
    note = await db.create_note(
        id=nid,
        title=payload.title,
        content=payload.content or "",
        type=payload.type or "nota",
        tags=payload.tags or [],
        area=payload.area,
        project_id=payload.project_id,
    )
    log.info("note.created", id=nid, title=payload.title)
    return Note(**note)


# ─────────────────────────── GET /notes/{id} ─────────────────

@router.get("/{note_id}", response_model=Note)
async def get_note(note_id: str, db: Database = Depends(_get_db)) -> Note:
    note = await db.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
    return Note(**note)


# ─────────────────────────── PATCH /notes/{id} ───────────────

@router.patch("/{note_id}", response_model=Note)
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    db: Database = Depends(_get_db),
) -> Note:
    existing = await db.get_note(note_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
    updates = payload.model_dump(exclude_unset=True)
    note = await db.update_note(note_id, **updates)
    log.info("note.updated", id=note_id, fields=list(updates.keys()))
    return Note(**note)


# ─────────────────────────── DELETE /notes/{id} ──────────────

@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: str, db: Database = Depends(_get_db)) -> None:
    deleted = await db.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
    log.info("note.deleted", id=note_id)
