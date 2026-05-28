from __future__ import annotations

import os
from pathlib import Path

import psycopg


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    return db_url


def ensure_migration_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              migration_id TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def list_migration_files() -> list[Path]:
    migrations_dir = Path(__file__).parent / "migrations"
    return sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())


def apply_migrations(db_url: str) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(db_url) as conn:
        ensure_migration_table(conn)
        with conn.cursor() as cur:
            for migration_file in list_migration_files():
                migration_id = migration_file.name
                cur.execute("SELECT 1 FROM schema_migrations WHERE migration_id = %s", (migration_id,))
                if cur.fetchone() is not None:
                    continue
                cur.execute(migration_file.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (migration_id) VALUES (%s)", (migration_id,))
                applied.append(migration_id)
        conn.commit()
    return applied


def main() -> None:
    db_url = get_db_url()
    applied = apply_migrations(db_url)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("No pending migrations")


if __name__ == "__main__":
    main()
