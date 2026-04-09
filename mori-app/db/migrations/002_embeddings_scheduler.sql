-- Migration 002: add embeddings support + scheduler
-- Apply with: sqlite3 mori.sqlite3 < 002_embeddings_scheduler.sql

-- Ensure memory_chunks has embedding column (may already exist in fresh installs)
-- Using IF NOT EXISTS pattern via trigger workaround isn't needed since schema.sql handles it

-- Scheduled tasks table
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    task_title TEXT NOT NULL,
    task_description TEXT,
    task_tags TEXT DEFAULT '[]',
    task_area TEXT,
    task_priority TEXT DEFAULT 'normal',
    task_project_id TEXT,
    pipeline_id TEXT,
    agent_id TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT NOT NULL,
    run_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run ON scheduled_tasks(next_run_at, enabled);

-- Add embedding_model column to memory_chunks for tracking which model generated it
ALTER TABLE memory_chunks ADD COLUMN embedding_model TEXT;
ALTER TABLE memory_chunks ADD COLUMN token_count INTEGER;
