"""
Tests for src/scheduler.py — DB-native cron scheduler.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.scheduler import Scheduler


# ── Helpers ───────────────────────────────────────────────────

def _make_db():
    db = MagicMock()
    db.get_due_scheduled_tasks = AsyncMock(return_value=[])
    db.create_task = AsyncMock(return_value={"id": "task-001", "title": "Test task"})
    db.advance_scheduled_task = AsyncMock()
    return db


def _make_scheduled(
    sid: str = "sched-001",
    title: str = "Weekly report",
    tags: str = '["report"]',
    area: str = "empresa",
    priority: str = "normal",
    description: str = "Generate weekly report",
    project_id: str = None,
    pipeline_id: str = None,
    agent_id: str = None,
) -> dict:
    return {
        "id": sid,
        "task_title": title,
        "task_tags": tags,
        "task_area": area,
        "task_priority": priority,
        "task_description": description,
        "task_project_id": project_id,
        "pipeline_id": pipeline_id,
        "agent_id": agent_id,
        "cron_expression": "0 9 * * 1",
        "name": "Weekly report job",
    }


# ── Test: no due tasks ────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_no_due_tasks():
    """When no tasks are due, create_task is never called."""
    db = _make_db()
    db.get_due_scheduled_tasks = AsyncMock(return_value=[])
    scheduler = Scheduler(db)

    await scheduler._tick()

    db.get_due_scheduled_tasks.assert_called_once()
    db.create_task.assert_not_called()
    db.advance_scheduled_task.assert_not_called()


# ── Test: triggers due task ───────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_triggers_due_task():
    """A due scheduled task creates a task and advances the schedule."""
    db = _make_db()
    scheduled = _make_scheduled()
    db.get_due_scheduled_tasks = AsyncMock(return_value=[scheduled])
    db.create_task = AsyncMock(return_value={"id": "new-task-001", "title": scheduled["task_title"]})

    scheduler = Scheduler(db)
    await scheduler._tick()

    # create_task should have been called with correct args
    db.create_task.assert_called_once_with(
        title=scheduled["task_title"],
        description=scheduled["task_description"],
        tags=["report"],
        area=scheduled["task_area"],
        priority=scheduled["task_priority"],
        project_id=scheduled["task_project_id"],
        pipeline_id=scheduled["pipeline_id"],
        agent_id=scheduled["agent_id"],
    )

    # advance_scheduled_task should have been called
    db.advance_scheduled_task.assert_called_once_with(scheduled["id"])


@pytest.mark.asyncio
async def test_scheduler_triggers_multiple_due_tasks():
    """Multiple due tasks are all triggered."""
    db = _make_db()
    due = [_make_scheduled(sid="s1"), _make_scheduled(sid="s2", title="Daily backup")]
    db.get_due_scheduled_tasks = AsyncMock(return_value=due)
    db.create_task = AsyncMock(side_effect=[
        {"id": "t1", "title": "Weekly report"},
        {"id": "t2", "title": "Daily backup"},
    ])

    scheduler = Scheduler(db)
    await scheduler._tick()

    assert db.create_task.call_count == 2
    assert db.advance_scheduled_task.call_count == 2
    db.advance_scheduled_task.assert_any_call("s1")
    db.advance_scheduled_task.assert_any_call("s2")


# ── Test: trigger error does NOT advance ─────────────────────

@pytest.mark.asyncio
async def test_scheduler_handles_trigger_error():
    """When _trigger raises, advance_scheduled_task is NOT called, scheduler continues."""
    db = _make_db()
    scheduled = _make_scheduled()
    db.get_due_scheduled_tasks = AsyncMock(return_value=[scheduled])
    db.create_task = AsyncMock(side_effect=RuntimeError("DB write failed"))

    scheduler = Scheduler(db)
    # Should not raise
    await scheduler._tick()

    db.create_task.assert_called_once()
    # advance should NOT be called when trigger failed
    db.advance_scheduled_task.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_continues_after_partial_failure():
    """If first task fails to trigger, second task is still processed."""
    db = _make_db()
    due = [
        _make_scheduled(sid="s1", title="Failing task"),
        _make_scheduled(sid="s2", title="Succeeding task"),
    ]
    db.get_due_scheduled_tasks = AsyncMock(return_value=due)
    db.create_task = AsyncMock(side_effect=[
        RuntimeError("First task failed"),
        {"id": "t2", "title": "Succeeding task"},
    ])

    scheduler = Scheduler(db)
    await scheduler._tick()

    assert db.create_task.call_count == 2
    # Only s2 should be advanced (s1 failed to trigger)
    db.advance_scheduled_task.assert_called_once_with("s2")


# ── Test: JSON tags parsing ───────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_parses_empty_tags():
    """Empty tags JSON array is handled correctly."""
    db = _make_db()
    scheduled = _make_scheduled(tags="[]")
    db.get_due_scheduled_tasks = AsyncMock(return_value=[scheduled])
    db.create_task = AsyncMock(return_value={"id": "t1", "title": scheduled["task_title"]})

    scheduler = Scheduler(db)
    await scheduler._tick()

    call_kwargs = db.create_task.call_args.kwargs
    assert call_kwargs["tags"] == []


@pytest.mark.asyncio
async def test_scheduler_parses_none_tags():
    """None task_tags defaults to empty list."""
    db = _make_db()
    scheduled = _make_scheduled(tags=None)
    db.get_due_scheduled_tasks = AsyncMock(return_value=[scheduled])
    db.create_task = AsyncMock(return_value={"id": "t1", "title": scheduled["task_title"]})

    scheduler = Scheduler(db)
    await scheduler._tick()

    call_kwargs = db.create_task.call_args.kwargs
    assert call_kwargs["tags"] == []


# ── Test: shutdown flag ───────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_shutdown_stops_run():
    """Calling shutdown sets running=False which stops the run loop."""
    db = _make_db()
    db.get_due_scheduled_tasks = AsyncMock(return_value=[])

    scheduler = Scheduler(db)
    assert scheduler.running is True

    await scheduler.shutdown()
    assert scheduler.running is False
