"""
backend/routers/agents.py — Agent listing from mori.yaml + run stats.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..db import Database
from ..models.agent_run import AgentRun, AgentRunList, AgentStats

router = APIRouter(prefix="/agents", tags=["agents"])

_CONFIG_PATH = os.environ.get("MORI_CONFIG", "/config/mori.yaml")


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _load_config() -> dict:
    path = Path(_CONFIG_PATH)
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


class AgentSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    model: str | None = None
    pipeline: str | None = None


# ─────────────────────────── GET /agents ─────────────────────

@router.get("", response_model=list[AgentSummary])
async def list_agents() -> list[AgentSummary]:
    config = _load_config()
    agents_raw: dict[str, Any] = config.get("agents", {})
    result = []
    for aid, adata in agents_raw.items():
        result.append(
            AgentSummary(
                id=aid,
                name=adata.get("name", aid),
                description=adata.get("description"),
                model=adata.get("model"),
                pipeline=adata.get("pipeline"),
            )
        )
    return result


# ─────────────────────────── GET /agents/{id}/runs ───────────

@router.get("/{agent_id}/runs", response_model=AgentRunList)
async def get_agent_runs(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(_get_db),
) -> AgentRunList:
    runs = await db.get_agent_runs(agent_id=agent_id, limit=limit, offset=offset)
    return AgentRunList(items=[AgentRun(**r) for r in runs], total=len(runs))


# ─────────────────────────── GET /agents/{id}/stats ──────────

@router.get("/{agent_id}/stats", response_model=AgentStats)
async def get_agent_stats(
    agent_id: str,
    db: Database = Depends(_get_db),
) -> AgentStats:
    stats = await db.get_agent_stats(agent_id)
    return AgentStats(agent_id=agent_id, **stats)
