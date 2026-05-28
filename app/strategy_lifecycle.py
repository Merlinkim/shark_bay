from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


class StrategyLifecycleRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        strategy_id = payload.get("strategy_id") or str(uuid.uuid4())
        row = {
            "strategy_id": strategy_id,
            "title": payload["title"],
            "description": payload["description"],
            "current_status": "idea",
            "created_by_agent": payload["created_by_agent"],
            "created_at": now,
            "updated_at": now,
        }
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_strategy_proposals (
                      strategy_id, title, description, current_status,
                      created_by_agent, created_at, updated_at
                    ) VALUES (
                      %(strategy_id)s, %(title)s, %(description)s, %(current_status)s,
                      %(created_by_agent)s, %(created_at)s, %(updated_at)s
                    )
                    RETURNING *
                    """,
                    row,
                )
                proposal = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO research_strategy_status_history (
                      strategy_id, from_status, to_status, reason, changed_by_agent, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (strategy_id, None, "idea", "proposal_created", payload["created_by_agent"], now),
                )
                return proposal

    def get_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM research_strategy_proposals WHERE strategy_id=%s", (strategy_id,))
                return cur.fetchone()

    def patch_status(self, strategy_id: str, to_status: str, reason: str, changed_by_agent: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_status FROM research_strategy_proposals WHERE strategy_id=%s", (strategy_id,))
                current = cur.fetchone()
                if not current:
                    return None
                from_status = current["current_status"]
                cur.execute(
                    """
                    UPDATE research_strategy_proposals
                    SET current_status=%s, updated_at=%s
                    WHERE strategy_id=%s
                    RETURNING *
                    """,
                    (to_status, now, strategy_id),
                )
                updated = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO research_strategy_status_history (
                      strategy_id, from_status, to_status, reason, changed_by_agent, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (strategy_id, from_status, to_status, reason, changed_by_agent, now),
                )
                return updated

    def get_history(self, strategy_id: str) -> list[dict[str, Any]]:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT strategy_id, from_status, to_status, reason, changed_by_agent, created_at
                    FROM research_strategy_status_history
                    WHERE strategy_id=%s
                    ORDER BY created_at ASC
                    """,
                    (strategy_id,),
                )
                return cur.fetchall()
