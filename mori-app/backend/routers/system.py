"""
backend/routers/system.py — Health check, daily stats, and safe config view.

/health is intentionally unauthenticated (registered without auth deps in main.py).
/system/stats and /system/config are under the same router but the router itself
is included without auth deps — add them in main.py if needed.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..db import Database

router = APIRouter(tags=["system"])

_CONFIG_PATH = os.environ.get("MORI_CONFIG", "/config/mori.yaml")

_SENSITIVE_KEYS = {
    "api_key", "api_keys", "token", "secret", "password",
    "openai_api_key", "anthropic_api_key", "telegram_token",
}


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _strip_secrets(obj: object) -> object:
    """Recursively remove sensitive keys from a config dict."""
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in _SENSITIVE_KEYS else _strip_secrets(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_strip_secrets(i) for i in obj]
    return obj


class HealthResponse(BaseModel):
    status: str
    db: str
    version: str = "2.0.0"
    orchestrator: str = "unknown"


# ─────────────────────────── GET /health ─────────────────────

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    db_status = "disconnected"
    try:
        db: Database = _get_db(request)
        # Quick connectivity probe
        await db._fetchone("SELECT 1", ())
        db_status = "connected"
    except Exception:
        pass

    config = _load_config()
    orchestrator = config.get("orchestrator", {}).get("status", "unknown")

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        db=db_status,
        orchestrator=orchestrator,
    )


# ─────────────────────────── GET /system/stats ───────────────

@router.get("/system/stats")
async def system_stats(request: Request) -> dict:
    db: Database = _get_db(request)
    return await db.get_daily_stats()


# ─────────────────────────── GET /system/config ──────────────

@router.get("/system/config")
async def system_config() -> dict:
    config = _load_config()
    safe = _strip_secrets(config)
    return safe  # type: ignore[return-value]


def _load_config() -> dict:
    path = Path(_CONFIG_PATH)
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}
