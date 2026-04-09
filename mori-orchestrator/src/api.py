"""HTTP API del orchestrator — trigger de ejecución inmediata para chat."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from pydantic import BaseModel

api = FastAPI(title="mori-orchestrator-internal")

# El orquestador se inyecta en startup desde main.py
_orchestrator = None


class TriggerRequest(BaseModel):
    task_id: str


@api.post("/trigger")
async def trigger_task(req: TriggerRequest):
    """Dispara ejecución inmediata de una tarea (para chat)."""
    if _orchestrator is None:
        return {"error": "orchestrator not ready"}
    # Encola la tarea para ejecución inmediata saltándose el poll delay
    asyncio.create_task(_orchestrator.execute_task_by_id(req.task_id))
    return {"status": "triggered", "task_id": req.task_id}


@api.get("/health")
async def health():
    return {"status": "ok", "orchestrator_ready": _orchestrator is not None}
