from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS research_reviews (
  id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  experiment_run_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  verdict TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  overfit_risk TEXT NOT NULL,
  summary TEXT NOT NULL,
  failure_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  required_changes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  recommendation_to_arthur TEXT NOT NULL,
  created_by_agent TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_reviews_strategy_id ON research_reviews (strategy_id);
CREATE INDEX IF NOT EXISTS idx_research_reviews_experiment_run_id ON research_reviews (experiment_run_id);
CREATE INDEX IF NOT EXISTS idx_research_reviews_run_id ON research_reviews (run_id);
CREATE INDEX IF NOT EXISTS idx_research_reviews_job_id ON research_reviews (job_id);
CREATE INDEX IF NOT EXISTS idx_research_reviews_verdict ON research_reviews (verdict);
"""


class ResearchReviewRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def ensure_schema(self) -> None:
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        review_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        row = {
            "id": review_id,
            "strategy_id": payload["strategy_id"],
            "experiment_run_id": payload["experiment_run_id"],
            "run_id": payload["run_id"],
            "job_id": payload["job_id"],
            "verdict": payload["verdict"],
            "risk_level": payload["risk_level"],
            "overfit_risk": payload["overfit_risk"],
            "summary": payload["summary"],
            "failure_reasons_json": json.dumps(payload.get("failure_reasons", [])),
            "required_changes_json": json.dumps(payload.get("required_changes", [])),
            "recommendation_to_arthur": payload.get("recommendation_to_arthur", ""),
            "created_by_agent": payload["created_by_agent"],
            "created_at": created_at,
        }
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_reviews (
                      id, strategy_id, experiment_run_id, run_id, job_id,
                      verdict, risk_level, overfit_risk, summary,
                      failure_reasons_json, required_changes_json,
                      recommendation_to_arthur, created_by_agent, created_at
                    ) VALUES (
                      %(id)s, %(strategy_id)s, %(experiment_run_id)s, %(run_id)s, %(job_id)s,
                      %(verdict)s, %(risk_level)s, %(overfit_risk)s, %(summary)s,
                      %(failure_reasons_json)s::jsonb, %(required_changes_json)s::jsonb,
                      %(recommendation_to_arthur)s, %(created_by_agent)s, %(created_at)s
                    )
                    RETURNING *
                    """,
                    row,
                )
                return cur.fetchone()

    def get(self, review_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM research_reviews WHERE id=%s", (review_id,))
                return cur.fetchone()

    def list(self, strategy_id: str | None = None, experiment_run_id: str | None = None, verdict: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id=%s")
            values.append(strategy_id)
        if experiment_run_id:
            clauses.append("experiment_run_id=%s")
            values.append(experiment_run_id)
        if verdict:
            clauses.append("verdict=%s")
            values.append(verdict)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM research_reviews {where} ORDER BY created_at DESC LIMIT %s", tuple(values))
                return cur.fetchall()
