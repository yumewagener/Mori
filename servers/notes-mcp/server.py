"""
Mori Notes MCP Server

Provides MCP tools for notes and decisions backed by SQLite with FTS5 search.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

import aiosqlite
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

DB_PATH = os.environ.get("MORI_DB_PATH", "/data/mori.sqlite3")

server = Server("notes-mcp")


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            content     TEXT    NOT NULL DEFAULT '',
            type        TEXT    NOT NULL DEFAULT 'note',
            tags        TEXT,
            area        TEXT,
            project_id  INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            title,
            content,
            tags,
            content=notes,
            content_rowid=id
        );

        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
            INSERT INTO notes_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
            INSERT INTO notes_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
            INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
        END;
    """)
    await db.commit()


def row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="note_list",
            description="List notes with optional filtering by type, area, or full-text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Filter by type: note, decision, log, reference",
                    },
                    "area": {
                        "type": "string",
                        "description": "Filter by area: personal, trabajo, proyecto, sistema",
                    },
                    "search": {
                        "type": "string",
                        "description": "Full-text search query (searches title, content, tags)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
        types.Tool(
            name="note_create",
            description="Create a new note.",
            inputSchema={
                "type": "object",
                "required": ["title", "content"],
                "properties": {
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Note content (Markdown)"},
                    "type": {
                        "type": "string",
                        "description": "Note type: note, decision, log, reference (default note)",
                        "default": "note",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization",
                    },
                    "area": {
                        "type": "string",
                        "description": "Area: personal, trabajo, proyecto, sistema",
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "Associated project ID",
                    },
                },
            },
        ),
        types.Tool(
            name="note_get",
            description="Get a single note by ID.",
            inputSchema={
                "type": "object",
                "required": ["note_id"],
                "properties": {
                    "note_id": {"type": "integer", "description": "Note ID"},
                },
            },
        ),
        types.Tool(
            name="note_update",
            description="Update an existing note.",
            inputSchema={
                "type": "object",
                "required": ["note_id"],
                "properties": {
                    "note_id": {"type": "integer", "description": "Note ID"},
                    "title": {"type": "string", "description": "New title"},
                    "content": {"type": "string", "description": "New content"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (replaces existing)",
                    },
                },
            },
        ),
        types.Tool(
            name="decision_create",
            description="Create a decision record (a note with type='decision').",
            inputSchema={
                "type": "object",
                "required": ["title", "content"],
                "properties": {
                    "title": {"type": "string", "description": "Decision title / question"},
                    "content": {
                        "type": "string",
                        "description": "Decision rationale, options considered, and outcome",
                    },
                    "area": {
                        "type": "string",
                        "description": "Area: personal, trabajo, proyecto, sistema",
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "Associated project ID",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_schema(db)

        if name == "note_list":
            note_type = arguments.get("type")
            area = arguments.get("area")
            search = arguments.get("search")
            limit = arguments.get("limit", 20)

            if search:
                # FTS5 search
                conditions = ["notes.id = notes_fts.rowid", "notes_fts MATCH ?"]
                params: list[Any] = [search]
                if note_type:
                    conditions.append("notes.type = ?")
                    params.append(note_type)
                if area:
                    conditions.append("notes.area = ?")
                    params.append(area)

                query = f"""
                    SELECT notes.* FROM notes, notes_fts
                    WHERE {' AND '.join(conditions)}
                    ORDER BY rank
                    LIMIT ?
                """
                params.append(limit)
            else:
                conditions = []
                params = []
                if note_type:
                    conditions.append("type = ?")
                    params.append(note_type)
                if area:
                    conditions.append("area = ?")
                    params.append(area)

                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                query = f"SELECT * FROM notes {where} ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

            notes = [row_to_dict(r) for r in rows]
            return [types.TextContent(type="text", text=json.dumps(notes, indent=2))]

        elif name in ("note_create", "decision_create"):
            title = arguments["title"]
            content = arguments["content"]
            note_type = "decision" if name == "decision_create" else arguments.get("type", "note")
            tags = arguments.get("tags", [])
            area = arguments.get("area", "")
            project_id = arguments.get("project_id")

            tags_str = json.dumps(tags) if tags else "[]"
            now = datetime.utcnow().isoformat()

            async with db.execute(
                """
                INSERT INTO notes (title, content, type, tags, area, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, content, note_type, tags_str, area, project_id, now, now),
            ) as cursor:
                note_id = cursor.lastrowid

            await db.commit()

            async with db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)) as cursor:
                row = await cursor.fetchone()

            return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

        elif name == "note_get":
            note_id = arguments["note_id"]

            async with db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return [types.TextContent(type="text", text=json.dumps({"error": f"Note {note_id} not found"}))]

            return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

        elif name == "note_update":
            note_id = arguments["note_id"]

            # Fetch existing
            async with db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return [types.TextContent(type="text", text=json.dumps({"error": f"Note {note_id} not found"}))]

            existing = row_to_dict(row)
            title = arguments.get("title", existing["title"])
            content = arguments.get("content", existing["content"])
            tags = arguments.get("tags", json.loads(existing.get("tags") or "[]"))
            tags_str = json.dumps(tags)
            now = datetime.utcnow().isoformat()

            await db.execute(
                "UPDATE notes SET title = ?, content = ?, tags = ?, updated_at = ? WHERE id = ?",
                (title, content, tags_str, now, note_id),
            )
            await db.commit()

            async with db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)) as cursor:
                row = await cursor.fetchone()

            return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
