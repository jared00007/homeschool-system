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
    # Prefer an explicit connection string from environment or Streamlit secrets
    if _get_connection_string():
        return "postgres"
    return "sqlite"


def _get_connection_string() -> Optional[str]:
    # Check environment variables first
    val = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if val:
        return val

    # If running inside Streamlit, secrets are available via streamlit.secrets
    try:
        import streamlit as st

        # st.secrets behaves like a dict
        val = st.secrets.get("DATABASE_URL") or st.secrets.get("SUPABASE_DB_URL")
        if val:
            return val
    except Exception:
        # Not running under Streamlit or secrets not available
        pass

    # If found, ensure any special characters in username/password are percent-encoded
    if val and (val.startswith("postgresql://") or val.startswith("postgres://")):
        try:
            parsed = urllib.parse.urlparse(val)
            if parsed.username:
                user = urllib.parse.quote(parsed.username, safe='')
                pwd = urllib.parse.quote(parsed.password or '', safe='')
                host = parsed.hostname or ''
                port = f":{parsed.port}" if parsed.port else ''
                # Rebuild netloc with encoded credentials
                netloc = f"{user}:{pwd}@{host}{port}"
                rebuilt = urllib.parse.urlunparse((parsed.scheme, netloc, parsed.path or '', parsed.params or '', parsed.query or '', parsed.fragment or ''))
                return rebuilt
        except Exception:
            # If parsing fails, return the raw value and let psycopg2 raise a useful error
            return val

    return val


def connect_database(db_path: Path) -> DbConnection:
    backend = _get_db_backend()
    if backend == "postgres":
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed. Install it from requirements.txt.")
        # Build connection parameters and pass as kwargs to psycopg2.connect
        conn_str = _get_connection_string()
        if not conn_str:
            raise RuntimeError("DATABASE_URL not set for postgres backend")

        try:
            parsed = urllib.parse.urlparse(conn_str)
            params = {}
            if parsed.username:
                params['user'] = urllib.parse.unquote(parsed.username)
            if parsed.password:
                params['password'] = urllib.parse.unquote(parsed.password)
            if parsed.hostname:
                params['host'] = parsed.hostname
            if parsed.port:
                params['port'] = parsed.port
            # path is database name (leading slash)
            dbname = (parsed.path or '').lstrip('/')
            if dbname:
                params['dbname'] = dbname
            # include query params like sslmode
            query = urllib.parse.parse_qs(parsed.query)
            for k, v in query.items():
                # take first value
                params[k] = v[0]

            # Ensure SSL is required by default for cloud Postgres hosts
            if 'sslmode' not in params:
                params['sslmode'] = 'require'

            # Diagnostic: attempt to resolve the host and print outcome to logs
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
            # Re-raise with the original exception so Streamlit logs show the detail
            raise

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
