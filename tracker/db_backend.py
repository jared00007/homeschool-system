import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


class DbConnection:
    """Small compatibility wrapper that lets the app use either SQLite or Postgres."""

    def __init__(self, backend: str, connection):
        self.backend = backend
        self.conn = connection

    def execute(self, sql, params=()):
        if self.backend == "sqlite":
            return self.conn.execute(sql, params)
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def cursor(self):
        return self.conn.cursor()

    def __getattr__(self, name):
        return getattr(self.conn, name)


def _get_db_backend() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if database_url:
        return "postgres"
    return "sqlite"


def _get_connection_string() -> Optional[str]:
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")


def connect_database(db_path: Path) -> DbConnection:
    backend = _get_db_backend()
    if backend == "postgres":
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed. Install it from requirements.txt.")
        conn = psycopg2.connect(_get_connection_string())
        conn.autocommit = False
        return DbConnection("postgres", conn)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    return DbConnection("sqlite", conn)


def table_columns(conn: DbConnection, table_name: str) -> list:
    if conn.backend == "sqlite":
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]

    cursor = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [row[0] for row in cursor.fetchall()]


def table_exists(conn: DbConnection, table_name: str) -> bool:
    if conn.backend == "sqlite":
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    cursor = conn.execute(
        "SELECT to_regclass(%s)",
        (table_name,),
    )
    return cursor.fetchone()[0] is not None
