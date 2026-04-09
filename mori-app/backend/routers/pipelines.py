"""
backend/routers/pipelines.py — Read-only pipeline data from mori.yaml + agent_runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..db import Database
from ..models.agent_run import AgentRun, AgentRunList

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

_CONFIG_PATH = os.environ.get("MORI_CONFIG", "/config/mori.yaml")


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _load_config() -> dict:
    path = Path(_CONFIG_PATH)
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


class PipelineSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    steps: list[str] = []


# ─────────────────────────── GET /pipelines ──────────────────

@router.get("", response_model=list[PipelineSummary])
async def list_pipelines() -> list[PipelineSummary]:
    config = _load_config()
    pipelines_raw: dict[str, Any] = config.get("pipelines", {})
    result = []
    for pid, pdata in pipelines_raw.items():
        steps = list(pdata.get("steps", {}).keys()) if isinstance(pdata.get("steps"), dict) else []
        result.append(
            PipelineSummary(
                id=pid,
                name=pdata.get("name", pid),
                description=pdata.get("description"),
                steps=steps,
            )
        )
    return result


# ─────────────────────────── GET /pipelines/runs ─────────────

@router.get("/runs", response_model=AgentRunList)
async def list_pipeline_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> AgentRunList:
    runs = await db.get_agent_runs(limit=limit, offset=offset)
    # filter to runs that have a pipeline_id
    pipeline_runs = [r for r in runs if r.get("pipeline_id")]
    return AgentRunList(items=[AgentRun(**r) for r in pipeline_runs], total=len(pipeline_runs))


# ─────────────────────────── GET /pipelines/{id} ─────────────

@router.get("/{pipeline_id}", response_model=dict)
async def get_pipeline(pipeline_id: str) -> dict:
    config = _load_config()
    pipelines_raw: dict[str, Any] = config.get("pipelines", {})
    if pipeline_id not in pipelines_raw:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    data = dict(pipelines_raw[pipeline_id])
    data["id"] = pipeline_id
    # Remove any sensitive keys
    data.pop("api_key", None)
    data.pop("token", None)
    return data
