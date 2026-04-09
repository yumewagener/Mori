"""
Stream manager for mori-orchestrator.

Pushes text chunks (from streaming LLM responses) to the run_streams
SQLite table so that an SSE endpoint can pick them up and forward them
to the UI in real time.
"""

from __future__ import annotations

import structlog

from .db import Database

log = structlog.get_logger()


class StreamManager:
    """
    Thin wrapper that persists streaming chunks to the database.

    Each call to :meth:`push` appends a row to ``run_streams``.
    The SSE server polls ``run_streams`` using :meth:`Database.get_stream_chunks`
    and forwards rows to connected clients.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def push(self, run_id: str, chunk: str) -> None:
        """
        Persist a streaming text chunk for *run_id*.

        Silently swallows DB errors so that a streaming failure never
        kills the execution loop.
        """
        if not chunk:
            return
        try:
            await self.db.append_stream_chunk(run_id, chunk)
        except Exception as exc:
            log.warning(
                "stream_push_failed",
                run_id=run_id,
                chunk_len=len(chunk),
                error=str(exc),
            )

    async def push_event(self, run_id: str, event_type: str, data: str) -> None:
        """
        Persist a structured event chunk formatted as ``[EVENT:type] data``.

        Useful for signalling phase transitions, tool calls, or errors.
        """
        formatted = f"[EVENT:{event_type}] {data}"
        await self.push(run_id, formatted)

    async def push_tool_result(
        self, run_id: str, tool_name: str, result: str, truncate: int = 500
    ) -> None:
        """Convenience helper to stream a tool result summary."""
        summary = result[:truncate] + ("…" if len(result) > truncate else "")
        await self.push(run_id, f"✓ {tool_name}: {summary}")
