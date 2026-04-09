# ADR-0002: Mori / Niwa Separation

**Date:** 2024-01-15  
**Status:** Accepted  
**Deciders:** Mori Core Team

---

## Context

Mori grew out of Niwa v1, a personal productivity system built around a task manager, notes, and a basic Claude integration. As the AI orchestration requirements grew more complex — multi-model routing, pipeline execution, MCP servers, streaming UI — it became clear that the Niwa codebase needed to be either significantly extended or cleanly separated.

This ADR documents the decision to treat Mori as a standalone platform rather than a Niwa module or plugin.

---

## Background: What was Niwa v1?

Niwa v1 was a self-hosted personal knowledge + task management system with:
- SQLite-backed tasks, notes, decisions, and projects
- A FastAPI REST API
- A minimal Svelte UI
- A basic Claude integration that could execute single tasks
- Single-model, single-agent, no streaming, no pipelines

Niwa v1's AI integration was a bolt-on: one API endpoint that sent a task to Claude and returned the result synchronously.

---

## The Separation Problem

As AI orchestration requirements grew, we faced a fundamental tension:

**Option A: Extend Niwa in place**
Add multi-model support, pipeline engine, MCP servers, streaming, and orchestrator directly to the Niwa codebase.

**Option B: Build Mori as a separate platform**
Start fresh with orchestration as a first-class concern, while retaining Niwa's data model (tasks, notes, projects).

---

## Decision

Build Mori as a separate, standalone platform. The Niwa codebase is not extended; instead:

1. **Mori inherits the Niwa data model** — the SQLite schema for tasks, notes, projects, and decisions is preserved and extended. This allows data migration from Niwa v1 to Mori.
2. **Mori replaces Niwa's API** — the FastAPI app is rewritten with orchestration-first API design.
3. **Mori replaces Niwa's UI** — the Svelte UI is redesigned for real-time streaming and pipeline visualization.
4. **No Niwa dependency** — Mori does not import or depend on any Niwa code. The data model compatibility is maintained through schema compatibility, not code sharing.

---

## Rationale

### Against extending Niwa in place

**Architectural mismatch.** Niwa v1 was designed around synchronous request/response. Adding asyncio orchestration, SSE streaming, and multi-step pipelines to a synchronous architecture requires rewriting most of the core anyway — the result would be a hybrid that's harder to reason about than a clean rewrite.

**Config philosophy conflict.** Niwa stored all configuration (including AI settings) in the database via an admin UI. Mori uses YAML files as the configuration source of truth (see ADR-0001). Retrofitting YAML-first config into Niwa's DB-config architecture would require replacing large portions of the existing admin system.

**Testing and stability.** Niwa v1 is a working production system for some users. Making deep architectural changes risks breaking it. A clean separation allows Mori to evolve rapidly without compromising Niwa v1 users.

**Scope creep prevention.** If Mori is "Niwa with AI," every new Mori feature becomes a question of "should this also be in Niwa?" Treating them as separate systems eliminates this ambiguity.

### For a clean separation

**Cleaner boundaries.** Mori's scope is clearly defined: it is an AI orchestrator with a task/notes/project data model. It is not a general-purpose personal productivity system with optional AI.

**Independent evolution.** Niwa v1 can continue to be maintained for users who don't need AI orchestration. Mori can evolve its architecture without backward compatibility constraints.

**Data migration path.** Because Mori's SQLite schema is a superset of Niwa v1's schema, migration is possible with a simple SQL script. This preserves user data while moving to the new platform.

**Naming clarity.** "Niwa" (Japanese: garden) was a fitting name for a personal productivity system. "Mori" (Japanese: forest) suggests a more complex, interconnected system — appropriate for an orchestrator that routes work across multiple AI models.

---

## What Mori Retains from Niwa

| Aspect | Niwa v1 | Mori |
|--------|---------|------|
| Data model | tasks, notes, decisions, projects | Same + agent_runs, pipelines |
| SQLite storage | ✓ | ✓ |
| FastAPI backend | ✓ | ✓ (rewritten) |
| Svelte frontend | ✓ | ✓ (redesigned) |
| Caddy reverse proxy | ✓ | ✓ |
| Bearer token auth | ✓ | ✓ |

## What Mori Does Not Retain

| Aspect | Niwa v1 | Mori |
|--------|---------|------|
| DB-stored AI config | ✓ | ✗ (YAML only) |
| Admin UI for config | ✓ | ✗ |
| Synchronous AI calls | ✓ | ✗ (async only) |
| Single-model only | ✓ | ✗ (multi-model) |
| No MCP | ✓ | ✗ (MCP-first) |
| No pipeline engine | ✓ | ✗ |

---

## Migration from Niwa v1

For users migrating from Niwa v1 to Mori:

```bash
# 1. Export Niwa v1 database
cp ~/.niwa/data/niwa.sqlite3 /tmp/niwa-backup.sqlite3

# 2. Install Mori
./mori install

# 3. Copy the existing database (schema is compatible)
cp /tmp/niwa-backup.sqlite3 ~/.mori/data/mori.sqlite3

# 4. Run migration script to add new Mori columns
./mori migrate
```

The migration script adds the `agent_runs` table and any new columns to existing tables with sensible defaults. Existing tasks, notes, projects, and decisions are preserved without modification.

---

## Consequences

- Mori and Niwa v1 can coexist on the same machine (different ports, different home directories).
- Mori's development is not constrained by Niwa v1 backward compatibility.
- Users of Niwa v1 have a clear migration path.
- The Niwa v1 codebase enters maintenance-only mode; no new features.
- Documentation, issues, and releases are managed in the Mori repository independently.
