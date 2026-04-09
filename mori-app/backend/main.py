"""
backend/main.py — Mori API entry point.

Dev mode: if MORI_TOKEN is not set, all requests are allowed.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import Database
from .routers import agents, chat, memory, models, notes, pipelines, projects, scheduled_tasks, stream, system, tasks

log = structlog.get_logger(__name__)

security = HTTPBearer(auto_error=False)


# ─────────────────────────── auth ────────────────────────────

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> HTTPAuthorizationCredentials | None:
    token = os.environ.get("MORI_TOKEN", "")
    if token:
        if not credentials or credentials.credentials != token:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials


# ─────────────────────────── DB dep ──────────────────────────

def get_db() -> Database:
    return app.state.db


# ─────────────────────────── lifespan ────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.environ.get("MORI_DB_PATH", "/data/mori.sqlite3")
    log.info("startup", db_path=db_path)
    app.state.db = Database(db_path)
    await app.state.db.initialize()
    yield
    await app.state.db.close()
    log.info("shutdown")


# ─────────────────────────── app ─────────────────────────────

app = FastAPI(
    title="Mori API",
    version="2.0.0",
    description="Local multi-model AI orchestrator — REST backend",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────── routers ─────────────────────────

_AUTH = [Depends(verify_token)]

app.include_router(tasks.router,     prefix="/api", dependencies=_AUTH)
app.include_router(projects.router,  prefix="/api", dependencies=_AUTH)
app.include_router(notes.router,     prefix="/api", dependencies=_AUTH)
app.include_router(pipelines.router, prefix="/api", dependencies=_AUTH)
app.include_router(agents.router,    prefix="/api", dependencies=_AUTH)
app.include_router(models.router,    prefix="/api", dependencies=_AUTH)
app.include_router(memory.router,    prefix="/api", dependencies=_AUTH)
app.include_router(stream.router,    prefix="/api", dependencies=_AUTH)
app.include_router(system.router,          prefix="/api")  # /health has no auth
app.include_router(scheduled_tasks.router, prefix="/api", dependencies=_AUTH)
app.include_router(chat.router,            prefix="/api", dependencies=_AUTH)


@app.get("/api", tags=["root"])
async def root() -> dict:
    return {"name": "mori", "version": "2.0.0", "status": "running"}


# ─────────────────────────── static SPA ──────────────────────

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # Serve compiled Svelte assets
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Serve index.html for all non-API routes (SPA client-side routing)."""
        index = _FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"error": "Frontend not built. Run: cd mori-app/frontend && npm run build"}
