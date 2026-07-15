import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple
import urllib.parse
import socket

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


class DbConnection:
    """Small compatibility wrapper that lets the app use either SQLite or Postgres."""

    def __init__(self, backend: str, connection):
        self.backend = backend
        self.conn = connection

    def _adapt_sql(self, sql: str) -> str:
        if self.backend != "postgres" or not isinstance(sql, str):
            return sql
        adapted = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        adapted = adapted.replace("AUTOINCREMENT", "")
        return adapted

    def execute(self, sql, params=()):
        if self.backend == "sqlite":
            return self.conn.execute(sql, params)
        sql = self._adapt_sql(sql)
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
    # Prefer an explicit connection string from environment or Streamlit secrets
    if _get_connection_string():
        return "postgres"
    return "sqlite"


def _get_connection_string() -> Optional[str]:
    # Check environment variables first, then Streamlit secrets.
    val = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")

    try:
        import streamlit as st

        secret_val = st.secrets.get("DATABASE_URL") or st.secrets.get("SUPABASE_DB_URL")
        if secret_val:
            val = secret_val
    except Exception:
        # Not running under Streamlit or secrets not available
        pass

    return val


def _build_postgres_params(conn_str: str) -> dict:
    parsed = urllib.parse.urlparse(conn_str)
    params = {}

    if parsed.username:
        params["user"] = urllib.parse.unquote(parsed.username)
    if parsed.password is not None:
        params["password"] = urllib.parse.unquote(parsed.password)
    if parsed.hostname:
        params["host"] = parsed.hostname
    if parsed.port:
        params["port"] = parsed.port

    dbname = (parsed.path or "").lstrip("/")
    if dbname:
        params["dbname"] = dbname

    query = urllib.parse.parse_qs(parsed.query)
    for key, values in query.items():
        params[key] = values[0]

    if "sslmode" not in params:
        params["sslmode"] = "require"

    return params


def _connect_sqlite(db_path: Path) -> DbConnection:
    db_path = Path(db_path or "/tmp/homeschool.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return DbConnection("sqlite", conn)


def connect_database(db_path: Path) -> DbConnection:
    backend = _get_db_backend()
    print(f"Database backend selected: {backend}")
    if backend == "postgres":
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed. Install it from requirements.txt.")
        # Build connection parameters and pass as kwargs to psycopg2.connect
        conn_str = _get_connection_string()
        if not conn_str:
            raise RuntimeError("DATABASE_URL not set for postgres backend")

        try:
            params = _build_postgres_params(conn_str)

            try:
                if params.get('host'):
                    addrs = socket.getaddrinfo(params['host'], params.get('port') or 5432)
                    print(f"DNS resolution for {params['host']}: {addrs[:3]}")
            except Exception as dns_exc:
                print(f"DNS resolution failed for {params.get('host')}: {dns_exc}")

            conn = psycopg2.connect(**params)
            conn.autocommit = False
            return DbConnection("postgres", conn)
        except Exception as exc:
            print(f"Postgres connection failed; falling back to SQLite at {db_path}: {exc}")
            return _connect_sqlite(db_path)

    return _connect_sqlite(db_path)


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
