"""
backend/db.py — Async SQLite wrapper for Mori.

Uses aiosqlite with Row factory.  All IDs are TEXT (ULIDs).
Tags are stored as JSON strings, deserialized to list[str] on reads.
Timestamps are ISO 8601 TEXT in UTC.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

log = structlog.get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


def _deserialize_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_tags(tags: list[str] | None) -> str:
    return json.dumps(tags or [])


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    # ─────────────────────────── lifecycle ────────────────────────────

    async def initialize(self) -> None:
        """Open connection and apply schema if tables are absent."""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._apply_schema()
        log.info("database.initialized", path=self._path)

    async def _apply_schema(self) -> None:
        async with self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ) as cur:
            exists = await cur.fetchone()
        if not exists:
            schema = _SCHEMA_PATH.read_text()
            # aiosqlite executescript doesn't support async directly; use execute_many via script
            await self._conn.executescript(schema)
            await self._conn.commit()
            log.info("database.schema_applied")
        else:
            # Apply chat tables for existing databases (idempotent)
            await self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id         TEXT PRIMARY KEY,
                    title      TEXT NOT NULL DEFAULT 'Nueva conversaci\u00f3n',
                    model_id   TEXT,
                    agent_id   TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id         TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role       TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content    TEXT NOT NULL DEFAULT '',
                    run_id     TEXT,
                    task_id    TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
            """)
            await self._conn.commit()
            log.info("database.chat_tables_ensured")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            log.info("database.closed")

    # ─────────────────────────── helpers ──────────────────────────────

    async def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        async with self._conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self._conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════════════
    # TASKS
    # ══════════════════════════════════════════════════════════════════

    async def get_tasks(
        self,
        *,
        status: str | None = None,
        project_id: str | None = None,
        area: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if search:
            sql = """
                SELECT t.* FROM tasks t
                JOIN tasks_fts ON tasks_fts.rowid = t.rowid
                WHERE tasks_fts MATCH ?
            """
            params: list[Any] = [search]
            conditions: list[str] = []
        else:
            sql = "SELECT * FROM tasks WHERE 1=1"
            params = []
            conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if area:
            conditions.append("area = ?")
            params.append(area)

        if conditions:
            if search:
                sql += " AND " + " AND ".join(conditions)
            else:
                sql += " AND " + " AND ".join(conditions)

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self._fetchall(sql, tuple(params))
        for r in rows:
            r["tags"] = _deserialize_tags(r.get("tags"))
        return rows

    async def get_task(self, task_id: str) -> dict | None:
        row = await self._fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if row:
            row["tags"] = _deserialize_tags(row.get("tags"))
        return row

    async def create_task(
        self,
        *,
        id: str,
        title: str,
        description: str | None = None,
        tags: list[str] | None = None,
        area: str | None = None,
        priority: str = "normal",
        project_id: str | None = None,
        pipeline_id: str | None = None,
        agent_id: str | None = None,
        model_id: str | None = None,
    ) -> dict:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO tasks
                (id, title, description, tags, area, priority,
                 project_id, pipeline_id, agent_id, model_id, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                id, title, description, _serialize_tags(tags), area, priority,
                project_id, pipeline_id, agent_id, model_id, now, now,
            ),
        )
        await self._conn.commit()
        return await self.get_task(id)  # type: ignore[return-value]

    async def update_task(self, task_id: str, **kwargs: Any) -> dict | None:
        if not kwargs:
            return await self.get_task(task_id)

        if "tags" in kwargs:
            kwargs["tags"] = _serialize_tags(kwargs["tags"])
        kwargs["updated_at"] = _now()

        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [task_id]
        await self._conn.execute(
            f"UPDATE tasks SET {sets} WHERE id = ?", tuple(values)
        )
        await self._conn.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        cur = await self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    # ══════════════════════════════════════════════════════════════════
    # PROJECTS
    # ══════════════════════════════════════════════════════════════════

    async def get_projects(
        self,
        *,
        status: str | None = None,
        area: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM projects WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if area:
            sql += " AND area = ?"
            params.append(area)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self._fetchall(sql, tuple(params))

    async def get_project(self, project_id: str) -> dict | None:
        return await self._fetchone("SELECT * FROM projects WHERE id = ?", (project_id,))

    async def create_project(
        self,
        *,
        id: str,
        name: str,
        description: str | None = None,
        area: str | None = None,
        status: str = "activo",
        github_url: str | None = None,
        local_path: str | None = None,
    ) -> dict:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO projects (id, name, description, area, status, github_url, local_path, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (id, name, description, area, status, github_url, local_path, now, now),
        )
        await self._conn.commit()
        return await self.get_project(id)  # type: ignore[return-value]

    async def update_project(self, project_id: str, **kwargs: Any) -> dict | None:
        if not kwargs:
            return await self.get_project(project_id)
        kwargs["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [project_id]
        await self._conn.execute(
            f"UPDATE projects SET {sets} WHERE id = ?", tuple(values)
        )
        await self._conn.commit()
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def get_project_tasks(
        self, project_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        )
        for r in rows:
            r["tags"] = _deserialize_tags(r.get("tags"))
        return rows

    # ══════════════════════════════════════════════════════════════════
    # NOTES
    # ══════════════════════════════════════════════════════════════════

    async def get_notes(
        self,
        *,
        type: str | None = None,
        area: str | None = None,
        project_id: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if search:
            sql = """
                SELECT n.* FROM notes n
                JOIN notes_fts ON notes_fts.rowid = n.rowid
                WHERE notes_fts MATCH ?
            """
            params: list[Any] = [search]
        else:
            sql = "SELECT * FROM notes WHERE 1=1"
            params = []

        conditions: list[str] = []
        if type:
            conditions.append("type = ?")
            params.append(type)
        if area:
            conditions.append("area = ?")
            params.append(area)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        if conditions:
            sql += " AND " + " AND ".join(conditions)

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self._fetchall(sql, tuple(params))
        for r in rows:
            r["tags"] = _deserialize_tags(r.get("tags"))
        return rows

    async def get_note(self, note_id: str) -> dict | None:
        row = await self._fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))
        if row:
            row["tags"] = _deserialize_tags(row.get("tags"))
        return row

    async def create_note(
        self,
        *,
        id: str,
        title: str,
        content: str = "",
        type: str = "nota",
        tags: list[str] | None = None,
        area: str | None = None,
        project_id: str | None = None,
    ) -> dict:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO notes (id, title, content, type, tags, area, project_id, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (id, title, content, type, _serialize_tags(tags), area, project_id, now, now),
        )
        await self._conn.commit()
        return await self.get_note(id)  # type: ignore[return-value]

    async def update_note(self, note_id: str, **kwargs: Any) -> dict | None:
        if not kwargs:
            return await self.get_note(note_id)
        if "tags" in kwargs:
            kwargs["tags"] = _serialize_tags(kwargs["tags"])
        kwargs["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [note_id]
        await self._conn.execute(
            f"UPDATE notes SET {sets} WHERE id = ?", tuple(values)
        )
        await self._conn.commit()
        return await self.get_note(note_id)

    async def delete_note(self, note_id: str) -> bool:
        cur = await self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    async def search_notes_fts(self, query: str, limit: int = 20) -> list[dict]:
        rows = await self._fetchall(
            """
            SELECT n.* FROM notes n
            JOIN notes_fts ON notes_fts.rowid = n.rowid
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )
        for r in rows:
            r["tags"] = _deserialize_tags(r.get("tags"))
        return rows

    # ══════════════════════════════════════════════════════════════════
    # AGENT RUNS
    # ══════════════════════════════════════════════════════════════════

    async def get_agent_runs(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM agent_runs WHERE 1=1"
        params: list[Any] = []
        if task_id:
            sql += " AND task_id = ?"
            params.append(task_id)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        sql += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self._fetchall(sql, tuple(params))

    async def get_agent_run(self, run_id: str) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM agent_runs WHERE id = ?", (run_id,)
        )

    async def get_agent_stats(self, agent_id: str) -> dict:
        row = await self._fetchone(
            """
            SELECT
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                AVG(cost_usd) AS avg_cost_usd,
                SUM(cost_usd) AS total_cost_usd,
                AVG(turns_used) AS avg_turns,
                AVG(duration_seconds) AS avg_duration_seconds
            FROM agent_runs WHERE agent_id = ?
            """,
            (agent_id,),
        )
        if not row:
            return {}
        total = row["total_runs"] or 0
        completed = row["completed_runs"] or 0
        return {
            "total_runs": total,
            "completed_runs": completed,
            "failed_runs": row["failed_runs"] or 0,
            "success_rate": round(completed / total, 4) if total else 0.0,
            "avg_cost_usd": row["avg_cost_usd"],
            "total_cost_usd": row["total_cost_usd"],
            "avg_turns": row["avg_turns"],
            "avg_duration_seconds": row["avg_duration_seconds"],
        }

    async def get_model_stats(self, model_id: str) -> dict:
        row = await self._fetchone(
            """
            SELECT
                COUNT(*) AS total_runs,
                SUM(prompt_tokens) AS total_prompt_tokens,
                SUM(completion_tokens) AS total_completion_tokens,
                SUM(cost_usd) AS total_cost_usd,
                AVG(duration_seconds) AS avg_response_time
            FROM agent_runs WHERE model_id = ?
            """,
            (model_id,),
        )
        return dict(row) if row else {}

    # ══════════════════════════════════════════════════════════════════
    # STREAM CHUNKS
    # ══════════════════════════════════════════════════════════════════

    async def get_stream_chunks(
        self, run_id: str, *, after_id: int = 0
    ) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM run_streams WHERE run_id = ? AND id > ? ORDER BY id ASC",
            (run_id, after_id),
        )

    async def append_stream_chunk(self, run_id: str, chunk: str) -> dict:
        now = _now()
        cur = await self._conn.execute(
            "INSERT INTO run_streams (run_id, chunk, created_at) VALUES (?,?,?)",
            (run_id, chunk, now),
        )
        await self._conn.commit()
        return {"id": cur.lastrowid, "run_id": run_id, "chunk": chunk, "created_at": now}

    # ══════════════════════════════════════════════════════════════════
    # MEMORY CHUNKS
    # ══════════════════════════════════════════════════════════════════

    async def get_memory_chunks(
        self,
        *,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT id, source_type, source_id, content, created_at, updated_at FROM memory_chunks WHERE 1=1"
        params: list[Any] = []
        if source_type:
            sql += " AND source_type = ?"
            params.append(source_type)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self._fetchall(sql, tuple(params))

    async def delete_memory_chunk(self, chunk_id: str) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM memory_chunks WHERE id = ?", (chunk_id,)
        )
        await self._conn.commit()
        return cur.rowcount > 0

    # ══════════════════════════════════════════════════════════════════
    # SCHEDULED TASKS
    # ══════════════════════════════════════════════════════════════════

    async def get_scheduled_tasks(self) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM scheduled_tasks ORDER BY created_at DESC"
            )
            return [dict(r) for r in rows]

    async def create_scheduled_task(
        self,
        name: str,
        cron_expression: str,
        task_title: str,
        task_description: str | None = None,
        task_tags: list[str] | None = None,
        task_area: str | None = None,
        task_priority: str = "normal",
        task_project_id: str | None = None,
        pipeline_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        from croniter import croniter
        import uuid
        now = _now()
        task_id = str(uuid.uuid4())
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        next_run = cron.get_next(datetime).isoformat()
        tags_json = json.dumps(task_tags or [])
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO scheduled_tasks
                   (id, name, cron_expression, task_title, task_description, task_tags,
                    task_area, task_priority, task_project_id, pipeline_id, agent_id,
                    enabled, next_run_at, run_count, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,0,?,?)
                """,
                (
                    task_id, name, cron_expression, task_title, task_description,
                    tags_json, task_area, task_priority, task_project_id,
                    pipeline_id, agent_id, next_run, now, now,
                ),
            )
            await db.commit()
            row = await db.execute_fetchone(
                "SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)
            )
            return dict(row) if row else {}

    async def update_scheduled_task(self, task_id: str, **kwargs: Any) -> dict:
        kwargs["updated_at"] = _now()
        if "cron_expression" in kwargs:
            from croniter import croniter
            cron = croniter(kwargs["cron_expression"], datetime.now(timezone.utc))
            kwargs["next_run_at"] = cron.get_next(datetime).isoformat()
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"UPDATE scheduled_tasks SET {cols} WHERE id=?", vals
            )
            await db.commit()
            row = await db.execute_fetchone(
                "SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)
            )
            return dict(row) if row else {}

    async def delete_scheduled_task(self, task_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM scheduled_tasks WHERE id=?", (task_id,)
            )
            await db.commit()

    # ════════════════════════════════════════════════════════════════
    # SYSTEM STATS
    # ════════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════════
    # CHAT SESSIONS
    # ══════════════════════════════════════════════════════════════════

    async def create_chat_session(
        self,
        session_id: str,
        title: str = "Nueva conversación",
        model_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO chat_sessions (id, title, model_id, agent_id, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (session_id, title, model_id, agent_id, now, now),
        )
        await self._conn.commit()
        return await self.get_chat_session(session_id)  # type: ignore[return-value]

    async def get_chat_sessions(self) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM chat_sessions ORDER BY updated_at DESC"
        )

    async def get_chat_session(self, session_id: str) -> dict | None:
        return await self._fetchone(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        )

    async def update_chat_session_title(self, session_id: str, title: str) -> None:
        now = _now()
        await self._conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )
        await self._conn.commit()

    async def delete_chat_session(self, session_id: str) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
        )
        await self._conn.commit()
        return cur.rowcount > 0

    # ══════════════════════════════════════════════════════════════════
    # CHAT MESSAGES
    # ══════════════════════════════════════════════════════════════════

    async def create_chat_message(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str = "",
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, content, run_id, task_id, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (message_id, session_id, role, content, run_id, task_id, now),
        )
        # Also update session updated_at
        await self._conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await self._conn.commit()
        return await self._fetchone(  # type: ignore[return-value]
            "SELECT * FROM chat_messages WHERE id = ?", (message_id,)
        )

    async def get_chat_messages(self, session_id: str) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )

    async def update_chat_message_content(self, message_id: str, content: str) -> None:
        await self._conn.execute(
            "UPDATE chat_messages SET content = ? WHERE id = ?",
            (content, message_id),
        )
        await self._conn.commit()

    # ══════════════════════════════════════════════════════════════════
    # SYSTEM STATS
    # ══════════════════════════════════════════════════════════════════

    async def get_daily_stats(self) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tasks_today = await self._fetchone(
            "SELECT COUNT(*) as cnt FROM tasks WHERE created_at LIKE ?",
            (f"{today}%",),
        )
        completed_today = await self._fetchone(
            "SELECT COUNT(*) as cnt FROM tasks WHERE completed_at LIKE ? AND status='completada'",
            (f"{today}%",),
        )
        cost_today = await self._fetchone(
            "SELECT COALESCE(SUM(cost_usd),0) as total FROM agent_runs WHERE started_at LIKE ?",
            (f"{today}%",),
        )
        total_tasks = await self._fetchone("SELECT COUNT(*) as cnt FROM tasks", ())
        return {
            "date": today,
            "tasks_created_today": tasks_today["cnt"] if tasks_today else 0,
            "tasks_completed_today": completed_today["cnt"] if completed_today else 0,
            "cost_today_usd": cost_today["total"] if cost_today else 0.0,
            "total_tasks": total_tasks["cnt"] if total_tasks else 0,
        }
