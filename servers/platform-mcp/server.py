"""
Mori Platform MCP Server

Provides MCP tools for project management and Docker container control.
Uses DOCKER_HOST env var to connect to socket-proxy for safe container access.
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime
from typing import Any

import aiosqlite
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

DB_PATH = os.environ.get("MORI_DB_PATH", "/data/mori.sqlite3")
DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://socket-proxy:2375")

server = Server("platform-mcp")


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            area        TEXT,
            status      TEXT    NOT NULL DEFAULT 'active',
            github_url  TEXT,
            local_path  TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER,
            agent_id     TEXT    NOT NULL,
            pipeline_id  TEXT,
            phase        TEXT,
            status       TEXT    NOT NULL DEFAULT 'running',
            model_id     TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd     REAL    DEFAULT 0.0,
            started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            finished_at  TEXT,
            error        TEXT
        );
    """)
    await db.commit()


def row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row)


def run_docker(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a docker CLI command via the configured DOCKER_HOST."""
    env = os.environ.copy()
    env["DOCKER_HOST"] = DOCKER_HOST
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except FileNotFoundError:
        return False, "Docker CLI not found"
    except Exception as e:
        return False, str(e)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="project_list",
            description="List projects, optionally filtered by status and/or area.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: active, archived, paused",
                    },
                    "area": {
                        "type": "string",
                        "description": "Filter by area: personal, trabajo, proyecto, sistema",
                    },
                },
            },
        ),
        types.Tool(
            name="project_create",
            description="Create a new project.",
            inputSchema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "Project name"},
                    "description": {"type": "string", "description": "Project description"},
                    "area": {
                        "type": "string",
                        "description": "Area: personal, trabajo, proyecto, sistema",
                    },
                    "github_url": {
                        "type": "string",
                        "description": "GitHub repository URL",
                    },
                    "local_path": {
                        "type": "string",
                        "description": "Local filesystem path to the project",
                    },
                },
            },
        ),
        types.Tool(
            name="container_logs",
            description="Get recent logs from a Docker container.",
            inputSchema={
                "type": "object",
                "required": ["container_name"],
                "properties": {
                    "container_name": {
                        "type": "string",
                        "description": "Container name or ID",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to return (default 100)",
                        "default": 100,
                    },
                },
            },
        ),
        types.Tool(
            name="container_restart",
            description="Restart a Docker container.",
            inputSchema={
                "type": "object",
                "required": ["container_name"],
                "properties": {
                    "container_name": {
                        "type": "string",
                        "description": "Container name or ID to restart",
                    },
                },
            },
        ),
        types.Tool(
            name="pipeline_status",
            description="Get recent pipeline runs and their statuses.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent runs to return (default 20)",
                        "default": 20,
                    },
                    "task_id": {
                        "type": "integer",
                        "description": "Filter by task ID",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status: running, completed, failed",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:

    if name in ("project_list", "project_create", "pipeline_status"):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await ensure_schema(db)

            if name == "project_list":
                status = arguments.get("status")
                area = arguments.get("area")

                conditions = []
                params: list[Any] = []
                if status:
                    conditions.append("status = ?")
                    params.append(status)
                if area:
                    conditions.append("area = ?")
                    params.append(area)

                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                query = f"SELECT * FROM projects {where} ORDER BY updated_at DESC"

                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()

                projects = [row_to_dict(r) for r in rows]
                return [types.TextContent(type="text", text=json.dumps(projects, indent=2))]

            elif name == "project_create":
                project_name = arguments["name"]
                description = arguments.get("description", "")
                area = arguments.get("area", "")
                github_url = arguments.get("github_url", "")
                local_path = arguments.get("local_path", "")
                now = datetime.utcnow().isoformat()

                async with db.execute(
                    """
                    INSERT INTO projects (name, description, area, status, github_url, local_path, created_at, updated_at)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
                    """,
                    (project_name, description, area, github_url, local_path, now, now),
                ) as cursor:
                    project_id = cursor.lastrowid

                await db.commit()

                async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
                    row = await cursor.fetchone()

                return [types.TextContent(type="text", text=json.dumps(row_to_dict(row), indent=2))]

            elif name == "pipeline_status":
                limit = arguments.get("limit", 20)
                task_id = arguments.get("task_id")
                status = arguments.get("status")

                conditions = []
                params = []
                if task_id is not None:
                    conditions.append("task_id = ?")
                    params.append(task_id)
                if status:
                    conditions.append("status = ?")
                    params.append(status)

                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                query = f"SELECT * FROM agent_runs {where} ORDER BY started_at DESC LIMIT ?"
                params.append(limit)

                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()

                runs = [row_to_dict(r) for r in rows]
                return [types.TextContent(type="text", text=json.dumps(runs, indent=2))]

    elif name == "container_logs":
        container_name = arguments["container_name"]
        lines = arguments.get("lines", 100)

        ok, output = run_docker(["logs", "--tail", str(lines), container_name])
        result = {
            "container": container_name,
            "lines": lines,
            "ok": ok,
            "output": output,
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "container_restart":
        container_name = arguments["container_name"]
        ok, output = run_docker(["restart", container_name])
        result = {
            "container": container_name,
            "ok": ok,
            "output": output,
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    return [types.TextContent(type="text", text=json.dumps({"error": "Unreachable"}))]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
