"""
backend/routers/tasks.py — Task CRUD + run listing + cancel.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..db import Database
from ..models.agent_run import AgentRun, AgentRunList
from ..models.task import Task, TaskCreate, TaskList, TaskUpdate

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


# ─────────────────────────── GET /tasks ──────────────────────

@router.get("", response_model=TaskList)
async def list_tasks(
    status: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> TaskList:
    items = await db.get_tasks(
        status=status,
        project_id=project_id,
        area=area,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TaskList(items=[Task(**t) for t in items], total=len(items), limit=limit, offset=offset)


# ─────────────────────────── POST /tasks ─────────────────────

@router.post("", response_model=Task, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: Database = Depends(_get_db),
) -> Task:
    task_id = str(uuid4()).replace("-", "").upper()[:26]  # simple ULID-like
    task = await db.create_task(
        id=task_id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags or [],
        area=payload.area,
        priority=payload.priority or "normal",
        project_id=payload.project_id,
        pipeline_id=payload.pipeline_id,
        agent_id=payload.agent_id,
        model_id=payload.model_id,
    )
    log.info("task.created", id=task_id, title=payload.title)
    return Task(**task)


# ─────────────────────────── GET /tasks/{id} ─────────────────

@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str, db: Database = Depends(_get_db)) -> Task:
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return Task(**task)


# ─────────────────────────── PATCH /tasks/{id} ───────────────

@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: Database = Depends(_get_db),
) -> Task:
    existing = await db.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    updates = payload.model_dump(exclude_unset=True)
    task = await db.update_task(task_id, **updates)
    log.info("task.updated", id=task_id, fields=list(updates.keys()))
    return Task(**task)


# ─────────────────────────── DELETE /tasks/{id} ──────────────

@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: Database = Depends(_get_db)) -> None:
    deleted = await db.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    log.info("task.deleted", id=task_id)


# ─────────────────────────── GET /tasks/{id}/runs ────────────

@router.get("/{task_id}/runs", response_model=AgentRunList)
async def get_task_runs(
    task_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> AgentRunList:
    existing = await db.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    runs = await db.get_agent_runs(task_id=task_id, limit=limit, offset=offset)
    return AgentRunList(items=[AgentRun(**r) for r in runs], total=len(runs))


# ─────────────────────────── POST /tasks/{id}/cancel ─────────

@router.post("/{task_id}/cancel", response_model=Task)
async def cancel_task(task_id: str, db: Database = Depends(_get_db)) -> Task:
    existing = await db.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if existing["status"] not in ("pendiente", "en_progreso"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel task with status '{existing['status']}'",
        )
    task = await db.update_task(task_id, status="cancelada")
    log.info("task.cancelled", id=task_id)
    return Task(**task)
