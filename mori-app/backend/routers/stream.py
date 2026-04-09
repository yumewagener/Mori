"""
backend/routers/stream.py — SSE streaming endpoint for agent run output.

GET /runs/{run_id}/stream

Streams run_streams chunks as Server-Sent Events.
Polls DB every 100ms for new chunks; stops when run is no longer 'running'
or client disconnects.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from ..db import Database

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["stream"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    db: Database = Depends(_get_db),
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict, None]:
        last_id = 0
        idle_ticks = 0
        max_idle = 600  # 60 s of no new chunks after run completes before giving up

        while True:
            # Respect client disconnect
            if await request.is_disconnected():
                log.info("stream.client_disconnected", run_id=run_id)
                break

            chunks = await db.get_stream_chunks(run_id, after_id=last_id)
            for chunk in chunks:
                yield {"data": chunk["chunk"], "id": str(chunk["id"])}
                last_id = chunk["id"]
                idle_ticks = 0

            if not chunks:
                # Check if run is still active
                run = await db.get_agent_run(run_id)
                if run and run.get("status") not in ("running",):
                    idle_ticks += 1
                    if idle_ticks >= max_idle:
                        # Signal end-of-stream
                        yield {"data": "[DONE]", "event": "done"}
                        break
                elif run is None:
                    # Run doesn't exist; send error and stop
                    yield {"data": f"Run '{run_id}' not found", "event": "error"}
                    break

            await asyncio.sleep(0.1)

    return EventSourceResponse(event_generator())
