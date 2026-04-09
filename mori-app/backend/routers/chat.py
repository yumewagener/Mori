"""
backend/routers/chat.py — Chat sessions and real-time messaging.

Endpoints:
  GET    /chat/sessions                        — list all sessions
  POST   /chat/sessions                        — create session
  GET    /chat/sessions/{session_id}           — session detail
  DELETE /chat/sessions/{session_id}           — delete session + messages
  GET    /chat/sessions/{session_id}/messages  — list messages
  POST   /chat/sessions/{session_id}/send      — send message + trigger orchestrator
"""

from __future__ import annotations

import os
from typing import Optional
from uuid import uuid4

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..db import Database

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:9000")


# ─────────────────────────── helpers ──────────────────────────

def _get_db(request: Request) -> Database:
    return request.app.state.db


def _new_id() -> str:
    return str(uuid4()).replace("-", "").upper()[:26]


# ─────────────────────────── request / response models ────────

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "Nueva conversación"
    model_id: Optional[str] = None
    agent_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str
    model_id: Optional[str] = None
    agent_id: Optional[str] = None


# ─────────────────────────── GET /chat/sessions ───────────────

@router.get("/sessions")
async def list_sessions(request: Request):
    db = _get_db(request)
    sessions = await db.get_chat_sessions()
    return sessions


# ─────────────────────────── POST /chat/sessions ──────────────

@router.post("/sessions", status_code=201)
async def create_session(payload: CreateSessionRequest, request: Request):
    db = _get_db(request)
    session_id = _new_id()
    session = await db.create_chat_session(
        session_id=session_id,
        title=payload.title or "Nueva conversación",
        model_id=payload.model_id,
        agent_id=payload.agent_id,
    )
    log.info("chat.session.created", session_id=session_id)
    return session


# ─────────────────────────── GET /chat/sessions/{id} ──────────

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    db = _get_db(request)
    session = await db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


# ─────────────────────────── DELETE /chat/sessions/{id} ───────

@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    db = _get_db(request)
    deleted = await db.delete_chat_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


# ─────────────────────────── GET /chat/sessions/{id}/messages ─

@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, request: Request):
    db = _get_db(request)
    session = await db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    messages = await db.get_chat_messages(session_id)
    return messages


# ─────────────────────────── POST /chat/sessions/{id}/send ────

@router.post("/sessions/{session_id}/send")
async def send_message(
    session_id: str,
    payload: SendMessageRequest,
    request: Request,
):
    db = _get_db(request)

    # Ensure session exists
    session = await db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    # 1. Create user message
    user_msg_id = _new_id()
    user_message = await db.create_chat_message(
        message_id=user_msg_id,
        session_id=session_id,
        role="user",
        content=content,
    )

    # Auto-title the session from the first message
    if session.get("title") == "Nueva conversación":
        auto_title = content[:60].strip()
        await db.update_chat_session_title(session_id, auto_title)

    # 2. Create internal task
    task_id = _new_id()
    task_title = content[:60].strip()
    model_id = payload.model_id or session.get("model_id")
    agent_id = payload.agent_id or session.get("agent_id")

    task = await db.create_task(
        id=task_id,
        title=task_title,
        description=content,
        tags=["chat"],
        agent_id=agent_id,
        model_id=model_id,
    )

    # 3. Create run_id and agent_run
    run_id = _new_id()
    now = _get_now()
    await db._conn.execute(
        """
        INSERT INTO agent_runs
            (id, task_id, agent_id, model_id, status, started_at)
        VALUES (?,?,?,?,?,?)
        """,
        (run_id, task_id, agent_id, model_id, "running", now),
    )
    await db._conn.commit()

    # 4. Create assistant message (empty, will be filled via SSE streaming)
    assistant_msg_id = _new_id()
    assistant_message = await db.create_chat_message(
        message_id=assistant_msg_id,
        session_id=session_id,
        role="assistant",
        content="",
        run_id=run_id,
        task_id=task_id,
    )

    # 5. Trigger immediate orchestrator execution (best-effort)
    await _trigger_orchestrator(task_id)

    log.info(
        "chat.message.sent",
        session_id=session_id,
        task_id=task_id,
        run_id=run_id,
    )

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "run_id": run_id,
        "task_id": task_id,
    }


# ─────────────────────────── helpers ──────────────────────────

def _get_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _trigger_orchestrator(task_id: str) -> None:
    """Fire-and-forget: ask the orchestrator to run the task immediately."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/trigger",
                json={"task_id": task_id},
            )
            if resp.status_code == 200:
                log.info("chat.trigger.sent", task_id=task_id)
            else:
                log.warning(
                    "chat.trigger.bad_status",
                    task_id=task_id,
                    status=resp.status_code,
                )
    except Exception as exc:
        # Orchestrator may not be running in dev — poll loop will pick it up
        log.warning("chat.trigger.failed", task_id=task_id, error=str(exc))
