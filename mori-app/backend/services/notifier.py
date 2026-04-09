"""
backend/services/notifier.py — Optional Telegram / webhook notifications.

Environment variables:
    TELEGRAM_BOT_TOKEN   — Bot API token (e.g. "123456:ABC-...")
    TELEGRAM_CHAT_ID     — Destination chat/group ID
    MORI_WEBHOOK_URL     — Generic webhook URL (POST, JSON body)

If neither variable is set the functions are no-ops.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
_WEBHOOK_URL    = os.environ.get("MORI_WEBHOOK_URL", "")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ─────────────────────────── helpers ─────────────────────────

async def _send_telegram(text: str) -> None:
    if not (_TELEGRAM_TOKEN and _TELEGRAM_CHAT):
        return
    url = _TELEGRAM_API.format(token=_TELEGRAM_TOKEN)
    payload = {
        "chat_id": _TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        log.warning("notifier.telegram_error", error=str(exc))


async def _send_webhook(event: str, data: dict[str, Any]) -> None:
    if not _WEBHOOK_URL:
        return
    body = {"event": event, "data": data}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_WEBHOOK_URL, json=body)
            resp.raise_for_status()
    except Exception as exc:
        log.warning("notifier.webhook_error", error=str(exc))


# ─────────────────────────── public API ──────────────────────

async def send_task_completed(task: dict) -> None:
    """Notify that a task reached status 'completada'."""
    title = task.get("title", "?")
    tid = task.get("id", "?")
    cost = task.get("run_cost_usd")
    cost_str = f"  💵 Cost: ${cost:.4f}" if cost else ""

    text = (
        f"✅ <b>Task completed</b>\n"
        f"  ID: <code>{tid}</code>\n"
        f"  Title: {title}"
        f"{cost_str}"
    )
    await _send_telegram(text)
    await _send_webhook("task.completed", task)
    log.info("notifier.task_completed", id=tid)


async def send_task_failed(task: dict, error: str) -> None:
    """Notify that a task's agent run failed."""
    title = task.get("title", "?")
    tid = task.get("id", "?")

    text = (
        f"❌ <b>Task failed</b>\n"
        f"  ID: <code>{tid}</code>\n"
        f"  Title: {title}\n"
        f"  Error: {error[:300]}"
    )
    await _send_telegram(text)
    await _send_webhook("task.failed", {"task": task, "error": error})
    log.info("notifier.task_failed", id=tid, error=error[:100])


async def send_task_started(task: dict) -> None:
    """Notify that a task has started running."""
    title = task.get("title", "?")
    tid = task.get("id", "?")

    text = (
        f"🚀 <b>Task started</b>\n"
        f"  ID: <code>{tid}</code>\n"
        f"  Title: {title}"
    )
    await _send_telegram(text)
    await _send_webhook("task.started", task)


async def send_generic(event: str, data: dict[str, Any]) -> None:
    """Send an arbitrary event."""
    await _send_webhook(event, data)
