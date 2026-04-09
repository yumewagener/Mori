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


# ─────────────────────────── conversation context builder ────

_MAX_WORDS = 3000      # aprox. 4000 tokens
_RECENT_KEEP = 8       # mensajes recientes verbatim
_COMPRESS_LEN = 150    # chars por mensaje en resumen comprimido


def _build_chat_context(history: list[dict], current_message: str) -> str:
    """
    Construye el prompt con historial de conversación.
    Estrategia de compresión: mensajes recientes verbatim,
    mensajes antiguos resumidos a extractos cortos.
    """
    # Excluir mensajes sin contenido (asistente vacío mientras streaming)
    history = [m for m in history if m.get("content", "").strip()]

    if not history:
        return current_message

    recent = history[-_RECENT_KEEP:]
    old = history[:-_RECENT_KEEP] if len(history) > _RECENT_KEEP else []

    parts: list[str] = []

    if old:
        compressed = []
        for m in old:
            role = "Usuario" if m["role"] == "user" else "Asistente"
            text = m["content"][:_COMPRESS_LEN]
            if len(m["content"]) > _COMPRESS_LEN:
                text += "…"
            compressed.append(f"{role}: {text}")
        parts.append("[Contexto anterior - comprimido]\n" + "\n".join(compressed))

    conv_lines = []
    for m in recent:
        role = "Usuario" if m["role"] == "user" else "Asistente"
        conv_lines.append(f"{role}: {m['content']}")
    parts.append("[Conversacion reciente]\n" + "\n".join(conv_lines))

    parts.append("[Mensaje actual]\n" + current_message)

    sep = "\n\n"
    context = sep.join(parts)

    # Si sigue siendo muy largo, quitar el bloque comprimido
    if len(context.split()) > _MAX_WORDS:
        parts_short = [p for p in parts if not p.startswith("[Contexto anterior")]
        context = "[Historial anterior omitido - demasiado largo]\n\n" + sep.join(parts_short)

    return context


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

    # Build conversation context with compression
    history_msgs = await db.get_chat_messages(session_id)
    # Exclude the user message just created and future empty assistant msg
    history_msgs = [m for m in history_msgs if m["id"] != user_msg_id]
    task_description = _build_chat_context(history_msgs, content)

    task = await db.create_task(
        id=task_id,
        title=task_title,
        description=task_description,
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
