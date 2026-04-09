# Mori Architecture

## System Diagram

```
                        ┌─────────────────────────────────────────────┐
                        │                   HOST                       │
                        │                                              │
                        │   Browser / MCP Client / Claude Desktop      │
                        └──────────┬──────────────┬───────────────────┘
                                   │              │
                            :18811 │        :18810│ :18812
                                   ▼              ▼
                        ┌──────────────┐   ┌──────────────────────────┐
                        │    Caddy     │   │      MCP Gateways         │
                        │  :80 → :18811│   │ streaming :18810          │
                        │  (Auth + TLS)│   │ SSE       :18812          │
                        └──────┬───────┘   └───────┬──────────────────┘
                               │                    │
                        mori-net (bridge)            │
                               │                    │
              ┌────────────────┼────────────────────┤
              │                │                    │
              ▼                ▼                    ▼
      ┌───────────────┐ ┌─────────────┐   ┌─────────────────────┐
      │  mori-app     │ │ orchestrator│   │   MCP Servers        │
      │  FastAPI :8080│ │ asyncio:9000│   │  tasks-mcp  (stdio) │
      │  Web UI       │ │  Pipeline   │   │  notes-mcp  (stdio) │
      │  REST API     │ │  Engine     │   │  platform-mcp(stdio)│
      └───────┬───────┘ └──────┬──────┘   └──────────┬──────────┘
              │                │                      │
              └────────────────┴──────────────────────┘
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                    ▼           ▼           ▼
           ┌──────────────┐  ┌─────┐  ┌──────────┐
           │ SQLite DB    │  │ socket  │  Ollama   │
           │ mori.sqlite3 │  │ proxy│  │ :11434    │
           │ (WAL mode)   │  └─────┘  │ (optional)│
           └──────────────┘           └──────────┘

socket-net (internal bridge — no external access):
    socket-proxy ←→ platform-mcp, orchestrator
```

## Component Descriptions

### Caddy (`:18811`)
The public-facing reverse proxy. Handles:
- Bearer token authentication for all endpoints
- Routing: `/mcp/*` → MCP streaming gateway, `/sse/*` → MCP SSE gateway, `/api/*` and `/` → mori-app
- TLS termination when a domain is configured
- JSON access logging to stdout

### MCP Gateway — streaming (`:18810`) and SSE (`:18812`)
Two instances of `docker/mcp-gateway` exposing the three MCP servers (tasks, notes, platform) over HTTP streaming and SSE transports respectively. This allows any MCP-compatible client (Claude Desktop, Cursor, custom agents) to connect directly on the local network without going through Caddy.

Config lives at `~/.mori/config/mcp-gateway.json`.

### mori-app (internal `:8080`)
FastAPI application providing:
- REST API for the web UI (tasks, notes, projects, agent runs, cost dashboard)
- Server-Sent Events endpoint (`/api/stream`) for real-time task output
- Serves the compiled Svelte frontend
- Validates `MORI_TOKEN` on every request

### mori-orchestrator (internal `:9000`)
The core execution engine. Responsibilities:
- Polls SQLite for `pending` tasks every `poll_seconds`
- Selects the appropriate agent based on tags, area, and keywords (configurable routing rules)
- Loads the pipeline definition and executes each step sequentially or in parallel
- Manages the agent loop: calls the model via LiteLLM, handles tool calls, streams output back to the DB
- Enforces timeouts, retries, and iteration limits
- Writes agent run records and cost data to SQLite after each step

### tasks-mcp
MCP server exposing task CRUD tools (`task_list`, `task_create`, `task_update_status`, `task_get`) over stdio. Connected to the shared SQLite database.

### notes-mcp
MCP server exposing note and decision tools (`note_list`, `note_create`, `note_get`, `note_update`, `decision_create`) with FTS5 full-text search. Connected to the shared SQLite database.

### platform-mcp
MCP server exposing project management and Docker control tools (`project_list`, `project_create`, `container_logs`, `container_restart`, `pipeline_status`). Connects to Docker via `socket-proxy` to avoid mounting the Docker socket directly.

### socket-proxy
`tecnativa/docker-socket-proxy` running on the internal `socket-net` network. Exposes only the read/write operations needed for container inspection and restart. Prevents agents from accessing destructive Docker API endpoints.

### Ollama (optional, `--profile local-models`)
Local model inference server. Activated with `./mori ollama`. Exposed on `127.0.0.1:11434`. Supports GPU acceleration when NVIDIA drivers are present.

### SearXNG (optional, `--profile web-search`)
Self-hosted meta-search engine. Activated alongside the `web_search` tool in `mori.yaml`. Exposed on `127.0.0.1:8888`.

---

## Data Flow: Task Execution

```
1. User creates task via Web UI or API
        │
        ▼
2. Task written to tasks table (status=pending)
        │
        ▼
3. Orchestrator polls tasks table (every poll_seconds)
        │
        ▼
4. Orchestrator selects pipeline based on task tags
        │
        ▼
5. Orchestrator builds context:
   ├── Loads relevant notes via FTS5 search (memory.top_k results)
   ├── Loads task history for the project
   └── Injects as system prompt prefix
        │
        ▼
6. Pipeline step 1: execute
   ├── Selects agent (auto-routing or explicit)
   ├── Calls model via LiteLLM (streams tokens to DB)
   ├── Handles tool calls in a loop until done
   └── Writes result to agent_runs table
        │
        ▼
7. Pipeline step 2: review (if configured)
   ├── Reviewer agent evaluates output
   └── Returns APROBADO / NECESITA_CAMBIOS / RECHAZADO
        │
        ▼
8. If NECESITA_CAMBIOS: return to step 6 (up to max_iterations)
        │
        ▼
9. Task status updated to completed (or failed)
        │
        ▼
10. Notification sent (Telegram/webhook, if configured)
```

---

## Database Schema Overview

### `tasks`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Task title |
| description | TEXT | Full description |
| status | TEXT | pending / in_progress / completed / blocked / cancelled |
| priority | TEXT | low / medium / high / urgent |
| tags | TEXT | JSON array of strings |
| area | TEXT | personal / trabajo / proyecto / sistema |
| project_id | INTEGER FK | Optional project association |
| created_at | TEXT | ISO 8601 timestamp |
| updated_at | TEXT | ISO 8601 timestamp |

### `notes`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Note title |
| content | TEXT | Markdown content |
| type | TEXT | note / decision / log / reference |
| tags | TEXT | JSON array of strings |
| area | TEXT | Area classification |
| project_id | INTEGER FK | Optional project association |
| created_at | TEXT | ISO 8601 timestamp |
| updated_at | TEXT | ISO 8601 timestamp |

### `notes_fts` (virtual FTS5 table)
Mirrors `notes(title, content, tags)` for full-text search with automatic triggers.

### `projects`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Project name |
| description | TEXT | Description |
| area | TEXT | Area classification |
| status | TEXT | active / archived / paused |
| github_url | TEXT | Repository URL |
| local_path | TEXT | Local filesystem path |
| created_at | TEXT | ISO 8601 timestamp |
| updated_at | TEXT | ISO 8601 timestamp |

### `agent_runs`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| task_id | INTEGER FK | Associated task |
| agent_id | TEXT | Agent identifier |
| pipeline_id | TEXT | Pipeline identifier |
| phase | TEXT | execute / review / fix / plan |
| status | TEXT | running / completed / failed |
| model_id | TEXT | Model used |
| input_tokens | INTEGER | Tokens consumed (input) |
| output_tokens | INTEGER | Tokens consumed (output) |
| cost_usd | REAL | Calculated cost |
| started_at | TEXT | ISO 8601 timestamp |
| finished_at | TEXT | ISO 8601 timestamp |
| error | TEXT | Error message if failed |

---

## Network Topology

### `mori-net` (bridge)
All services join this network. Services can reach each other by service name:
- `caddy` → `app:8080`, `mcp-gateway:3000`, `mcp-gateway-sse:3000`
- `orchestrator` → `mcp-gateway:3000`, `app:8080`
- `mcp-gateway` → `tasks-mcp`, `notes-mcp`, `platform-mcp`
- `tasks-mcp`, `notes-mcp`, `platform-mcp` → SQLite volume (no network needed)

### `socket-net` (internal bridge)
Only `socket-proxy` and `platform-mcp` join this network. The `internal: true` flag prevents any container on this network from reaching the internet or `mori-net`. Docker socket access is strictly limited to `socket-proxy`.

---

## Config System

All runtime behavior is controlled by `~/.mori/config/mori.yaml`, mounted read-only into `app` and `orchestrator` containers. Changes take effect on container restart.

The config is validated on startup. Unknown keys are warned but not fatal. Required fields (model API key envs, pipeline step agents) that reference undefined IDs will cause a startup error with a clear message.

Environment variables from `~/.mori/.env` are loaded by Docker Compose and injected into containers. API keys are never written to the config file — they are referenced by env var name (`api_key_env: ANTHROPIC_API_KEY`) and resolved at runtime.
