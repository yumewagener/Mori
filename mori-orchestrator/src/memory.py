"""
Memory / context retrieval for mori-orchestrator.

Uses SQLite FTS5 to find relevant notes and past tasks that provide
context to the executing agent.  Falls back gracefully if FTS fails.
"""

from __future__ import annotations

import structlog

from .config import MemoryConfig, MoriConfig
from .db import Database

log = structlog.get_logger()


class Memory:
    """
    Retrieves relevant context chunks from the local knowledge base.

    Sources:
      - notes        → notes table (FTS5)
      - task_history → tasks table (FTS5, status = completada/bloqueada)
      - decisions    → (future: separate decisions table, not yet implemented)
    """

    def __init__(self, config: MoriConfig, db: Database) -> None:
        self.config = config
        self.db = db

    @property
    def memory_cfg(self) -> MemoryConfig:
        return self.config.memory

    async def retrieve(self, task: dict) -> str:
        """
        Build a context string for *task* by searching enabled memory sources.

        Returns an empty string if memory is disabled or no matches found.
        """
        if not self.memory_cfg.enabled:
            return ""

        # Build search query from task fields
        parts = [task.get("title") or ""]
        if task.get("description"):
            # Use first 200 chars of description to avoid overly long FTS queries
            parts.append(task["description"][:200])
        tags = task.get("tags") or []
        if tags and isinstance(tags, list):
            parts.append(" ".join(tags))

        query = " ".join(p for p in parts if p).strip()
        if not query:
            return ""

        chunks: list[str] = []
        top_k = self.memory_cfg.top_k

        # --- Notes ---
        if "notes" in self.memory_cfg.sources:
            chunks.extend(await self._retrieve_notes(query, top_k))

        # --- Task history ---
        if "task_history" in self.memory_cfg.sources:
            chunks.extend(await self._retrieve_task_history(query, max(3, top_k // 2)))

        # --- Decisions (placeholder — extend when decisions table exists) ---
        # if "decisions" in self.memory_cfg.sources:
        #     chunks.extend(await self._retrieve_decisions(query))

        if not chunks:
            return ""

        trimmed = chunks[:top_k]
        log.debug(
            "memory_retrieved",
            task_id=task.get("id"),
            chunks=len(trimmed),
        )
        return "\n".join(trimmed)

    # ------------------------------------------------------------------
    # Source handlers
    # ------------------------------------------------------------------

    async def _retrieve_notes(self, query: str, limit: int) -> list[str]:
        try:
            notes = await self.db.search_notes_fts(query, limit=limit)
        except Exception as exc:
            log.warning("memory_notes_error", error=str(exc))
            return []

        results: list[str] = []
        for note in notes:
            date_str = (note.get("updated_at") or "")[:10]
            content_preview = (note.get("content") or "")[:300]
            title = note.get("title") or "(sin título)"
            results.append(f"[Nota - {date_str}] {title}: {content_preview}")

        return results

    async def _retrieve_task_history(self, query: str, limit: int) -> list[str]:
        try:
            tasks = await self.db.search_similar_tasks(query, limit=limit)
        except Exception as exc:
            log.warning("memory_task_history_error", error=str(exc))
            return []

        results: list[str] = []
        for t in tasks:
            date_str = (t.get("updated_at") or "")[:10]
            title = t.get("title") or "(sin título)"
            status = t.get("status") or "?"
            results.append(f"[Tarea similar - {date_str}] {title} → {status}")

        return results

    # ------------------------------------------------------------------
    # Write helpers (for future use)
    # ------------------------------------------------------------------

    async def store_decision(
        self,
        project_id: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> None:
        """
        Placeholder for persisting decisions/notes produced by the agent.
        Currently a no-op — extend by inserting into a decisions table.
        """
        log.debug(
            "decision_store_called",
            project_id=project_id,
            title=title,
            note="decisions table not yet implemented",
        )
