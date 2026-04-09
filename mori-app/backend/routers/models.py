"""
backend/routers/models.py — Model listing from mori.yaml + usage stats.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from ..db import Database
from ..models.agent_run import ModelStats

router = APIRouter(prefix="/models", tags=["models"])

_CONFIG_PATH = os.environ.get("MORI_CONFIG", "/config/mori.yaml")


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _load_config() -> dict:
    path = Path(_CONFIG_PATH)
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


class ModelSummary(BaseModel):
    id: str
    name: str
    provider: str | None = None
    context_window: int | None = None
    description: str | None = None


# ─────────────────────────── GET /models ─────────────────────

@router.get("", response_model=list[ModelSummary])
async def list_models() -> list[ModelSummary]:
    config = _load_config()
    models_raw: dict[str, Any] = config.get("models", {})
    result = []
    for mid, mdata in models_raw.items():
        result.append(
            ModelSummary(
                id=mid,
                name=mdata.get("name", mid),
                provider=mdata.get("provider"),
                context_window=mdata.get("context_window"),
                description=mdata.get("description"),
            )
        )
    return result


# ─────────────────────────── GET /models/{id}/stats ──────────

@router.get("/{model_id}/stats", response_model=ModelStats)
async def get_model_stats(
    model_id: str,
    db: Database = Depends(_get_db),
) -> ModelStats:
    stats = await db.get_model_stats(model_id)
    return ModelStats(model_id=model_id, **stats)
