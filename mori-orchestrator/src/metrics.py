"""
Metrics aggregation for mori-orchestrator.

Records execution statistics (cost, tokens, duration) to the
``daily_metrics`` SQLite table and exposes query helpers for dashboards.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import structlog

from .db import Database

log = structlog.get_logger()


def _today() -> str:
    return date.today().isoformat()


class Metrics:
    """
    Thin layer over the database for recording and querying metrics.

    Designed to be called from PipelineEngine / Executor after each
    agent run finishes.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def record_execution(
        self,
        run_id: str,
        cost_usd: float,
        duration_seconds: float,
        model_id: str,
        agent_id: str,
        success: bool = True,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """
        Upsert daily aggregate metrics after one agent run.

        Safe to call even when individual counters are zero (e.g. for
        runs that failed before any tokens were consumed).
        """
        today = _today()
        try:
            await self.db.upsert_daily_metrics(
                date=today,
                model_id=model_id or "unknown",
                agent_id=agent_id or "unknown",
                completed=1 if success else 0,
                failed=0 if success else 1,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
            log.debug(
                "metrics_recorded",
                run_id=run_id,
                date=today,
                model_id=model_id,
                cost_usd=cost_usd,
                duration_seconds=round(duration_seconds, 2),
                success=success,
            )
        except Exception as exc:
            # Metrics errors must never crash the orchestration loop
            log.warning("metrics_record_failed", run_id=run_id, error=str(exc))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_daily_stats(self, target_date: Optional[str] = None) -> dict:
        """
        Return aggregated stats for a given date (defaults to today).

        Returns a dict with keys:
          tasks_completed, tasks_failed, prompt_tokens,
          completion_tokens, cost_usd
        """
        d = target_date or _today()
        row = await self.db.get_daily_stats(d)
        return {
            "date": d,
            "tasks_completed": row.get("tasks_completed") or 0,
            "tasks_failed": row.get("tasks_failed") or 0,
            "prompt_tokens": row.get("prompt_tokens") or 0,
            "completion_tokens": row.get("completion_tokens") or 0,
            "cost_usd": round(row.get("cost_usd") or 0.0, 6),
        }

    async def get_model_stats(
        self, target_date: Optional[str] = None
    ) -> list[dict]:
        """
        Return per-model stats for a given date (or all time if None).

        Each item: {model_id, tasks_completed, cost_usd,
                    prompt_tokens, completion_tokens}
        """
        rows = await self.db.get_model_stats(target_date)
        return [
            {
                "model_id": r["model_id"],
                "tasks_completed": r.get("tasks_completed") or 0,
                "cost_usd": round(r.get("cost_usd") or 0.0, 6),
                "prompt_tokens": r.get("prompt_tokens") or 0,
                "completion_tokens": r.get("completion_tokens") or 0,
            }
            for r in rows
        ]

    async def get_summary(self) -> dict:
        """
        Combined summary: today's stats + all-time per-model breakdown.
        """
        today_stats = await self.get_daily_stats()
        model_stats = await self.get_model_stats()
        return {
            "today": today_stats,
            "by_model": model_stats,
        }
