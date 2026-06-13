"""Research holdout enforcement (Engine v2, Task 9).

The holdout boundary is configured via the RESEARCH_HOLDOUT_START environment
variable (ISO-8601 UTC datetime, e.g. "2025-06-01T00:00:00+00:00"). All research
reads of candle data are clamped to strictly before this boundary unless the
caller explicitly requests holdout access, which requires RESEARCH_HOLDOUT_UNLOCK=1
and is recorded in the holdout_access_log table.

Candle WRITES (ingestion, backfill) are unaffected: enforcement applies only to
research read paths.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg


class HoldoutViolationError(RuntimeError):
    """Raised when a research request crosses the holdout boundary."""


def holdout_start() -> datetime | None:
    raw = os.getenv("RESEARCH_HOLDOUT_START")
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def holdout_unlocked() -> bool:
    return os.getenv("RESEARCH_HOLDOUT_UNLOCK", "0") == "1"


def clamp_research_end(end_time: datetime | None) -> datetime | None:
    """Clamp a research query upper bound to strictly before the holdout start.

    Returns the effective end_time. If no boundary is configured, returns the
    input unchanged.
    """
    boundary = holdout_start()
    if boundary is None:
        return end_time
    if end_time is None or end_time >= boundary:
        return boundary
    return end_time


def assert_range_outside_holdout(start_time: datetime | None, end_time: datetime | None) -> None:
    """Reject (rather than silently clamp) ranges that cross the boundary.

    Used by the backtest job path so that a campaign requesting holdout data
    fails loudly instead of quietly evaluating on truncated data.
    """
    boundary = holdout_start()
    if boundary is None:
        return
    if end_time is None or end_time >= boundary:
        raise HoldoutViolationError(
            f"Requested range end ({end_time}) reaches into the research holdout "
            f"(boundary {boundary.isoformat()}). Restrict end_time to before the boundary."
        )
    if start_time is not None and start_time >= boundary:
        raise HoldoutViolationError(
            f"Requested range start ({start_time}) is inside the research holdout "
            f"(boundary {boundary.isoformat()})."
        )


def log_holdout_access(db_url: str, *, accessor: str, purpose: str, range_start: datetime | None, range_end: datetime | None) -> None:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO holdout_access_log (accessor, purpose, range_start, range_end, accessed_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (accessor, purpose, range_start, range_end),
            )
        conn.commit()
