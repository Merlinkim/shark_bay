from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg


@dataclass(frozen=True)
class ExperimentRunRecord:
    strategy_id: str
    run_id: str
    job_id: str
    config_hash: str
    dataset_fingerprint: str
    risk_config_hash: str
    execution_config_hash: str
    git_commit_hash: str | None
    summary_metrics: dict[str, Any]
    result_reference: str | None


class ExperimentRegistryRepository:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def create_from_backtest(self, record: ExperimentRunRecord) -> str:
        experiment_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with psycopg.connect(self.db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO experiments (id, strategy_id, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    (experiment_id, record.strategy_id, created_at),
                )
                cur.execute(
                    """
                    INSERT INTO experiment_runs (
                      id, experiment_id, run_id, job_id, config_hash, dataset_fingerprint,
                      risk_config_hash, execution_config_hash, git_commit_hash,
                      summary_metrics, result_reference, created_at
                    )
                    VALUES (
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s,
                      %s::jsonb, %s, %s
                    )
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        record.run_id,
                        record.job_id,
                        record.config_hash,
                        record.dataset_fingerprint,
                        record.risk_config_hash,
                        record.execution_config_hash,
                        record.git_commit_hash,
                        json.dumps(record.summary_metrics),
                        record.result_reference,
                        created_at,
                    ),
                )

                metric_rows = [
                    (str(uuid.uuid4()), experiment_id, record.run_id, name, float(value), created_at)
                    for name, value in record.summary_metrics.items()
                    if isinstance(value, (int, float))
                ]
                if metric_rows:
                    cur.executemany(
                        """
                        INSERT INTO experiment_metrics (
                          id, experiment_id, run_id, metric_name, metric_value, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        metric_rows,
                    )

                if record.result_reference:
                    cur.execute(
                        """
                        INSERT INTO experiment_artifacts (
                          id, experiment_id, run_id, artifact_type, artifact_reference, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (str(uuid.uuid4()), experiment_id, record.run_id, "backtest_result", record.result_reference, created_at),
                    )
            conn.commit()
        return experiment_id
