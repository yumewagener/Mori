-- Mori SQLite Schema v2
-- PRAGMA settings
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;

-- ─────────────────────────────────────────────────────────────
-- projects
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    area        TEXT CHECK(area IN ('personal','empresa','proyecto','sistema','salud','finanzas','otro')),
    status      TEXT NOT NULL DEFAULT 'activo' CHECK(status IN ('activo','pausado','completado','archivado')),
    github_url  TEXT,
    local_path  TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ─────────────────────────────────────────────────────────────
-- tasks
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    status        TEXT NOT NULL DEFAULT 'pendiente'
                       CHECK(status IN ('pendiente','en_progreso','completada','bloqueada','cancelada')),
    priority      TEXT NOT NULL DEFAULT 'normal'
                       CHECK(priority IN ('baja','normal','alta','critica')),
    area          TEXT CHECK(area IN ('personal','empresa','proyecto','sistema','salud','finanzas','otro')),
    tags          TEXT NOT NULL DEFAULT '[]',   -- JSON array
    project_id    TEXT REFERENCES projects(id) ON DELETE SET NULL,
    pipeline_id   TEXT,
    agent_id      TEXT,
    model_id      TEXT,
    run_cost_usd  REAL,
    context_used  INTEGER,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    started_at    TEXT,
    completed_at  TEXT
);

-- ─────────────────────────────────────────────────────────────
-- notes
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'nota'
                     CHECK(type IN ('nota','decision','investigacion','diario','idea')),
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON array
    area        TEXT CHECK(area IN ('personal','empresa','proyecto','sistema','salud','finanzas','otro')),
    project_id  TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ─────────────────────────────────────────────────────────────
-- agent_runs
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_runs (
    id               TEXT PRIMARY KEY,
    task_id          TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id         TEXT,
    model_id         TEXT,
    pipeline_id      TEXT,
    phase            TEXT,
    status           TEXT NOT NULL DEFAULT 'running'
                          CHECK(status IN ('running','completed','failed','cancelled')),
    prompt_tokens    INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_usd         REAL DEFAULT 0.0,
    turns_used       INTEGER DEFAULT 0,
    duration_seconds REAL,
    output           TEXT,
    error            TEXT,
    started_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at      TEXT
);

-- ─────────────────────────────────────────────────────────────
-- run_streams
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_streams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    chunk      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ─────────────────────────────────────────────────────────────
-- memory_chunks
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memory_chunks (
    id          TEXT PRIMARY KEY,
    source_type TEXT NOT NULL
                     CHECK(source_type IN ('note','decision','task_history','diary')),
    source_id   TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   BLOB,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ─────────────────────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tasks_status_created  ON tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id      ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_task_id    ON agent_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_run_streams_run_id    ON run_streams(run_id, id);

-- ─────────────────────────────────────────────────────────────
-- FTS5 virtual tables
-- ─────────────────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, content, tags,
    content='notes', content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    title, description, tags,
    content='tasks', content_rowid='rowid'
);

-- ─────────────────────────────────────────────────────────────
-- FTS triggers – notes
-- ─────────────────────────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content, tags)
    VALUES (new.rowid, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
    INSERT INTO notes_fts(rowid, title, content, tags)
    VALUES (new.rowid, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
END;

-- ─────────────────────────────────────────────────────────────
-- FTS triggers – tasks
-- ─────────────────────────────────────────────────────────────
CREATE TRIGGER IF NOT EXISTS tasks_fts_insert AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, title, description, tags)
    VALUES (new.rowid, new.title, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS tasks_fts_update AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description, tags)
    VALUES ('delete', old.rowid, old.title, old.description, old.tags);
    INSERT INTO tasks_fts(rowid, title, description, tags)
    VALUES (new.rowid, new.title, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS tasks_fts_delete AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description, tags)
    VALUES ('delete', old.rowid, old.title, old.description, old.tags);
END;
