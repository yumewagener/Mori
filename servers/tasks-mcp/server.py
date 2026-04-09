"""
Mori Tasks MCP Server

Provides MCP tools for task management backed by SQLite.
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

server = Server("tasks-mcp")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT,
            status      TEXT    NOT NULL DEFAULT 'pending',
            priority    TEXT    NOT NULL DEFAULT 'medium',
            tags        TEXT,
            area        TEXT,
            project_id  INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            area        TEXT,
            status      TEXT    NOT NULL DEFAULT 'active',
            github_url  TEXT,
            local_path  TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)
    await db.commit()


def row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="task_list",
            description="List tasks, optionally filtered by status and/or project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: pending, in_progress, completed, blocked, cancelled",
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "Filter by project ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default 50)",
                        "default": 50,
                    },
                },
            },
        ),
        types.Tool(
            name="task_create",
            description="Create a new task.",
            inputSchema={
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for routing (e.g. coding, research)",
                    },
                    "area": {
                        "type": "string",
                        "description": "Area: personal, trabajo, proyecto, sistema",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority: low, medium, high, urgent (default medium)",
                        "default": "medium",
                    },
                    "project_id": {
                        "type": "integer",
                        "description": "Project ID to associate with",
                    },
                },
            },
        ),
        types.Tool(
            name="task_update_status",
            description="Update the status of a task.",
            inputSchema={
                "type": "object",
                "required": ["task_id", "status"],
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID"},
                    "status": {
                        "type": "string",
                        "description": "New status: pending, in_progress, completed, blocked, cancelled",
                    },
                },
            },
        ),
        types.Tool(
            name="task_get",
            description="Get a single task by ID.",
            inputSchema={
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID"},
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

        if name == "task_list":
            status = arguments.get("status")
            project_id = arguments.get("project_id")
            limit = arguments.get("limit", 50)

            conditions = []
            params: list[Any] = []

            if status:
                conditions.append("status = ?")
                params.append(status)
            if project_id is not None:
                conditions.append("project_id = ?")
                params.append(project_id)

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            query = f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

            tasks = [row_to_dict(r) for r in rows]
            return [types.TextContent(type="text", text=json.dumps(tasks, indent=2))]

        elif name == "task_create":
            title = arguments["title"]
            description = arguments.get("description", "")
            tags = arguments.get("tags", [])
            area = arguments.get("area", "")
            priority = arguments.get("priority", "medium")
            project_id = arguments.get("project_id")

            tags_str = json.dumps(tags) if tags else "[]"
            now = datetime.utcnow().isoformat()

            async with db.execute(
                """
                INSERT INTO tasks (title, description, status, priority, tags, area, project_id, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (title, description, priority, tags_str, area, project_id, now, now),
            ) as cursor:
                task_id = cursor.lastrowid

            await db.commit()

            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()

            return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

        elif name == "task_update_status":
            task_id = arguments["task_id"]
            status = arguments["status"]

            valid_statuses = {"pending", "in_progress", "completed", "blocked", "cancelled"}
            if status not in valid_statuses:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"}),
                    )
                ]

            now = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            await db.commit()

            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return [types.TextContent(type="text", text=json.dumps({"error": f"Task {task_id} not found"}))]

            return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

        elif name == "task_get":
            task_id = arguments["task_id"]

            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return [types.TextContent(type="text", text=json.dumps({"error": f"Task {task_id} not found"}))]

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
