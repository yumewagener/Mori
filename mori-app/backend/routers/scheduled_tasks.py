"""
routers/scheduled_tasks.py — CRUD for scheduled tasks.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["scheduled-tasks"])


# ── Pydantic models ────────────────────────────────────────────

class ScheduledTaskCreate(BaseModel):
    name: str
    cron_expression: str           # e.g. "0 9 * * 1" = Mondays at 9am UTC
    task_title: str
    task_description: Optional[str] = None
    task_tags: list[str] = []
    task_area: Optional[str] = None
    task_priority: str = "normal"
    task_project_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    agent_id: Optional[str] = None

class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    task_title: Optional[str] = None
    task_description: Optional[str] = None
    enabled: Optional[bool] = None

# ── Routes ─────────────────────────────────────────────────────

@router.get("/scheduled-tasks")
async def list_scheduled_tasks(db=Depends(lambda: None)):  # db injected via app.state
    from ..main import app
    return await app.state.db.get_scheduled_tasks()

@router.post("/scheduled-tasks", status_code=201)
async def create_scheduled_task(data: ScheduledTaskCreate):
    from ..main import app
    try:
        return await app.state.db.create_scheduled_task(
            name=data.name,
            cron_expression=data.cron_expression,
            task_title=data.task_title,
            task_description=data.task_description,
            task_tags=data.task_tags,
            task_area=data.task_area,
            task_priority=data.task_priority,
            task_project_id=data.task_project_id,
            pipeline_id=data.pipeline_id,
            agent_id=data.agent_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/scheduled-tasks/{task_id}")
async def get_scheduled_task(task_id: str):
    from ..main import app
    tasks = await app.state.db.get_scheduled_tasks()
    for t in tasks:
        if t["id"] == task_id:
            return t
    raise HTTPException(status_code=404, detail="Not found")

@router.patch("/scheduled-tasks/{task_id}")
async def update_scheduled_task(task_id: str, data: ScheduledTaskUpdate):
    from ..main import app
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    return await app.state.db.update_scheduled_task(task_id, **updates)

@router.delete("/scheduled-tasks/{task_id}", status_code=204)
async def delete_scheduled_task(task_id: str):
    from ..main import app
    await app.state.db.delete_scheduled_task(task_id)

@router.post("/scheduled-tasks/{task_id}/toggle")
async def toggle_scheduled_task(task_id: str):
    """Enable/disable a scheduled task."""
    from ..main import app
    tasks = await app.state.db.get_scheduled_tasks()
    for t in tasks:
        if t["id"] == task_id:
            new_enabled = not bool(t["enabled"])
            return await app.state.db.update_scheduled_task(task_id, enabled=new_enabled)
    raise HTTPException(status_code=404, detail="Not found")
