"""
backend/routers/projects.py — Project CRUD + task listing.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..db import Database
from ..models.project import Project, ProjectCreate, ProjectList, ProjectUpdate
from ..models.task import Task, TaskList

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


@router.get("", response_model=ProjectList)
async def list_projects(
    status: Optional[str] = Query(None),
    area: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> ProjectList:
    items = await db.get_projects(status=status, area=area, limit=limit, offset=offset)
    return ProjectList(
        items=[Project(**p) for p in items],
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=Project, status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: Database = Depends(_get_db),
) -> Project:
    pid = str(uuid4()).replace("-", "").upper()[:26]
    project = await db.create_project(
        id=pid,
        name=payload.name,
        description=payload.description,
        area=payload.area,
        status=payload.status or "activo",
        github_url=payload.github_url,
        local_path=payload.local_path,
    )
    log.info("project.created", id=pid, name=payload.name)
    return Project(**project)


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, db: Database = Depends(_get_db)) -> Project:
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Project(**project)


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Database = Depends(_get_db),
) -> Project:
    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    updates = payload.model_dump(exclude_unset=True)
    project = await db.update_project(project_id, **updates)
    log.info("project.updated", id=project_id, fields=list(updates.keys()))
    return Project(**project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: Database = Depends(_get_db)) -> None:
    deleted = await db.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    log.info("project.deleted", id=project_id)


@router.get("/{project_id}/tasks", response_model=TaskList)
async def get_project_tasks(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> TaskList:
    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    tasks = await db.get_project_tasks(project_id, limit=limit, offset=offset)
    return TaskList(
        items=[Task(**t) for t in tasks],
        total=len(tasks),
        limit=limit,
        offset=offset,
    )
