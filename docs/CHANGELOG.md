# Mori Changelog

All notable changes to Mori are documented here.
Format: [version] - date - description

---

## [2.0.0] - 2026-04-09 — Complete rewrite

### Added
- **mori-orchestrator**: async Python engine replacing task-executor.py
  - Parallel task execution (up to 4 simultaneous) with asyncio.TaskGroup
  - 3-level routing: explicit pipeline → rule-based tag/area matching → LLM fallback
  - Full tool-calling loop (up to 20 turns per agent) with LiteLLM
  - Pipeline engine: execute → review → fix with condition gating
  - Standard, code, planning, and research pipelines
- **YAML configuration system**: zero hardcoded models or agents
  - mori.yaml with full model catalog, agent definitions, pipeline config
  - Supports Anthropic, OpenAI, Google, Ollama, and custom providers
  - Per-model capabilities, costs, tool support flags
- **Real-time streaming**: SSE from orchestrator → SQLite → FastAPI → browser
- **FastAPI modular backend**: replaces 75KB monolith
  - 10 REST routers: tasks, projects, notes, pipelines, agents, models, memory, stream, system, scheduled-tasks
  - Bearer token auth via MORI_TOKEN env var
- **Svelte frontend**: 10 routes with dark theme
  - Kanban board with drag-and-drop
  - Real-time execution view with terminal-style streaming
  - Model catalog with cost tracking
  - Agent and pipeline visualizer
- **DB-native scheduler**: cron-based task creation without external cron daemon
  - Full CRUD API at `/api/scheduled-tasks`
  - Toggle enable/disable per scheduled task
  - Automatic `next_run_at` computation via croniter
- **Memory/RAG system**:
  - SQLite FTS5 for full-text search (always available)
  - sqlite-vec + Ollama nomic-embed-text for vector search (optional)
  - Background auto-indexer for notes and decisions
- **Browser automation**: Playwright-based tool for web agents
  - `browser_navigate`, `browser_get_text`, `browser_click`, `browser_fill`, `browser_screenshot`
  - Headless Chromium, controlled by `tools.browser.enabled` in mori.yaml
  - Installed in orchestrator Docker image via `playwright install chromium`
- **Code interpreter**: sandboxed Python execution with configurable timeout
  - `code_execute` tool — enabled when `tools.shell.enabled=true`
  - Captures stdout, stderr, and timeouts gracefully
- **3 MCP servers**: tasks-mcp, notes-mcp, platform-mcp (fully implemented)
- **mori CLI**: install, start, stop, restart, logs, update, backup, upgrade, doctor
  - `upgrade`: git fetch → pull → rebuild images → restart → apply DB migrations
  - `doctor`: checks Docker, config file, .env, data directory, running services, API reachability

### Fixed (from Niwa v1)
- Task status strings now Spanish throughout: `pendiente`, `en_progreso`, `completada`, `bloqueada`, `cancelada`
- Area CHECK constraint: `empresa` (was `empre sa` with space — broken)
- Duplicate `WHEN 'critical' THEN 4` in ORDER BY removed
- agents.json stub replaced by fully functional agents.yaml with routing

### Architecture decisions
- LiteLLM for model abstraction (100+ providers, uniform API)
- asyncio.TaskGroup for parallel execution (no Celery/Redis needed)
- sqlite-vec for vector search (no separate vector DB service)
- SQLite FTS5 for full-text search (built-in, zero deps)
- Svelte 4 for frontend (small bundle, no Virtual DOM, SSE-native)
- croniter for cron expression parsing (no external scheduler daemon)
- Playwright for browser automation (Chromium headless, optional)

---

## [1.x] — Niwa (archived)

Original Niwa project archived. See https://github.com/yumewagener/niwa
