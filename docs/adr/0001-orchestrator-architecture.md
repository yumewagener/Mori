# ADR-0001: Orchestrator Architecture Decisions

**Date:** 2024-01-15  
**Status:** Accepted  
**Deciders:** Mori Core Team

---

## Context

Mori's orchestrator is the central engine that polls for tasks, selects agents, runs LLM inference, manages tool calling loops, and streams output. Several architectural decisions were made that shape how this component works.

---

## Decision 1: asyncio instead of Celery (or other task queues)

### Options considered

| Option | Description |
|--------|-------------|
| **Celery + Redis** | Mature distributed task queue, used widely in Django apps |
| **asyncio (chosen)** | Python's built-in async event loop |
| **Dramatiq + RabbitMQ** | Alternative to Celery, simpler API |
| **ARQ** | Async task queue built on Redis |

### Decision

Use Python's built-in `asyncio` with `asyncio.gather` for parallel task execution.

### Rationale

**Against Celery:**
- Celery requires a message broker (Redis or RabbitMQ), adding two more services to a system that already has 7.
- Celery's worker model assumes stateless, short-lived tasks. LLM inference tasks are long-lived (minutes) and stateful (streaming output, tool calling loops).
- Celery's distributed tracing and retry semantics don't map well to multi-step pipelines where each step depends on the previous.
- Debugging Celery worker failures is notoriously difficult.

**For asyncio:**
- LLM API calls are I/O-bound (waiting for tokens), making them ideal for async concurrency — no threads or processes needed.
- `asyncio.Semaphore` provides simple, correct parallelism caps (`max_parallel_tasks`, `max_parallel_per_project`).
- A single Python process with async makes streaming output to SQLite straightforward — no cross-process communication needed.
- SQLite with WAL mode handles concurrent async reads/writes from within a single process without contention.
- Lower operational overhead: one container, no broker, no worker pool management.

**Tradeoff accepted:**
- Asyncio does not distribute across multiple machines. Mori is designed for single-machine deployment; horizontal scaling is out of scope for v1.
- A CPU-bound task in the event loop would block everything. This is mitigated by running all CPU-bound work (embedding computation, etc.) in a `ThreadPoolExecutor` via `asyncio.run_in_executor`.

---

## Decision 2: LiteLLM for model abstraction

### Options considered

| Option | Description |
|--------|-------------|
| **LiteLLM (chosen)** | Unified interface to 100+ LLM providers |
| **Direct provider SDKs** | `anthropic`, `openai`, `google-generativeai` packages |
| **Custom adapter pattern** | Write our own provider abstraction |
| **Langchain** | Full agent framework with model abstractions |

### Decision

Use [LiteLLM](https://github.com/BerriAI/litellm) as the sole interface for all model calls.

### Rationale

**Against direct SDKs:**
- Each provider has a different API shape, streaming protocol, tool calling format, and error handling behavior.
- Supporting 3+ providers without an abstraction layer means duplicating retry logic, token counting, cost calculation, and streaming normalization for each.
- Adding a new provider requires code changes to the orchestrator.

**Against custom adapters:**
- Writing and maintaining provider adapters is significant ongoing work, especially as providers update their APIs.
- LiteLLM already handles this for 100+ providers.

**For LiteLLM:**
- Single `litellm.acompletion()` call works for Anthropic, OpenAI, Google, Ollama, Mistral, and more.
- Built-in token counting and cost estimation.
- Handles provider-specific streaming formats transparently.
- Tool calling normalization: a single tool schema works across all providers that support it.
- Fallback model support: `litellm.completion(model=primary, fallbacks=[fallback])`.
- Active maintenance and wide adoption.

**Against Langchain:**
- Langchain is a full framework that imposes opinions on agent architecture, memory, and tool calling that conflict with Mori's YAML-driven config approach.
- Langchain's abstraction overhead is significant; Mori only needs the model-calling layer, not the chain/agent primitives.

**Tradeoff accepted:**
- LiteLLM is an external dependency that adds its own update cycle and potential breaking changes.
- Pinned to a tested version; updates are reviewed before upgrading.

---

## Decision 3: YAML config instead of database config

### Options considered

| Option | Description |
|--------|-------------|
| **YAML file (chosen)** | `~/.mori/config/mori.yaml` mounted into containers |
| **SQLite tables** | Store model/agent/pipeline config in the DB |
| **Environment variables** | All config via env vars |
| **Admin UI editor** | Web UI for editing config stored in DB |

### Decision

All orchestration configuration (models, agents, pipelines, tools, memory) lives in a single YAML file. Only data (tasks, notes, projects, agent runs) lives in SQLite.

### Rationale

**For YAML:**
- Config is versioned with `git`. You can diff, branch, and roll back config changes the same way you manage code.
- YAML is human-readable and editable without a UI or database client.
- The config schema is self-documenting and can be validated with JSON Schema.
- Config changes require a service restart, which is a feature — it prevents partial config updates from causing inconsistent behavior.
- Secrets (API keys) are never in the config; they're referenced by env var name and resolved at runtime.

**Against SQLite config:**
- Mixing config with operational data in the same DB creates schema migration complexity.
- Config stored in a DB is harder to version control and audit.
- A corrupted DB could take down both config and data simultaneously.

**Against env vars for all config:**
- Env vars work for secrets but are unwieldy for complex nested structures (model lists, agent routing rules, pipeline step definitions).
- Docker Compose env files don't support arrays or objects natively.

**Tradeoff accepted:**
- Changes require a restart (handled by `./mori restart orchestrator`).
- No live config reloading in v1. Adding a `SIGHUP` handler for config reload is planned for v2.

---

## Decision 4: Svelte instead of React for the frontend

### Options considered

| Option | Description |
|--------|-------------|
| **Svelte/SvelteKit (chosen)** | Compiler-based frontend framework |
| **React + Vite** | Most popular choice, large ecosystem |
| **Vue 3** | Progressive framework, composition API |
| **HTMX** | Hypermedia-driven, minimal JS |

### Decision

Use SvelteKit for the web UI, compiled to a static build served by the FastAPI app.

### Rationale

**For Svelte:**
- Svelte compiles to vanilla JS — no runtime framework overhead in the browser. This matters for a self-hosted tool where the user may be running on modest hardware.
- Svelte's reactivity model is simpler to reason about for a UI that is primarily driven by SSE streams (task output, status updates).
- SvelteKit's file-based routing and built-in SSE support make the real-time dashboard straightforward to implement.
- Smaller bundle size means faster initial load, important for a tool accessed over a local or tunnel connection.

**Against React:**
- React's ecosystem (Redux, React Query, etc.) is larger but adds complexity for a focused single-user tool.
- React requires a runtime; Svelte components compile away.
- The SSE-driven real-time update pattern is simpler in Svelte's reactive stores than in React's hook model.

**Against HTMX:**
- HTMX is excellent for simple CRUD UIs but becomes awkward for the real-time streaming output display (rendering token-by-token output requires JS event handling that HTMX doesn't handle cleanly).
- Cost dashboard and pipeline visualization benefit from reactive component state.

**Tradeoff accepted:**
- Svelte's ecosystem is smaller than React's. Some libraries may be unavailable.
- Team members more familiar with React have a learning curve; Svelte's model is simpler but different.

---

## Consequences

- The orchestrator is a single-process asyncio application — simple to run, debug, and monitor.
- LiteLLM handles all model I/O, making it easy to add new providers without touching orchestrator logic.
- YAML config is versioned alongside the codebase; `mori.yaml.example` serves as documentation.
- The Svelte UI is compiled to static files at build time, served directly from the FastAPI app with no separate frontend server.
