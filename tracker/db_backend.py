import os
import sqlite3
from pathlib import Path
from typing import Optional
import urllib.parse
import socket

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


class _AdaptingCursor:
    """Wraps a real Postgres cursor so the ?-to-%s translation and the
    rollback-on-error safety net apply no matter how the cursor's
    .execute() gets called — including by code we don't control.

    This matters because pandas' pd.read_sql(sql, conn, params=...) does
    NOT go through DbConnection.execute(): it calls conn.cursor() and then
    .execute() directly on the raw cursor, bypassing any translation logic
    that only lived in DbConnection.execute(). Since DbConnection.cursor()
    is what pandas actually calls, putting the adaptation here instead
    catches every caller uniformly."""

    def __init__(self, cursor, owner: "DbConnection"):
        self._cursor = cursor
        self._owner = owner

    def execute(self, sql, params=None):
        sql = self._owner._adapt_sql(sql)
        try:
            if params is None:
                return self._cursor.execute(sql)
            return self._cursor.execute(sql, params)
        except Exception:
            # `conn` is one shared, module-level connection for the whole
            # app process (not per-request) — psycopg2 puts a connection
            # into an "aborted transaction" state after any failed query,
            # where every subsequent command fails too, until a rollback.
            # Roll back here so one bad query can't take down every other
            # page/user for the rest of the process's life.
            self._owner.conn.rollback()
            raise

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


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
        # The whole app is written against SQLite's "?" placeholder style;
        # psycopg2 requires "%s". Escape any literal "%" first (e.g. in a
        # LIKE pattern) so it isn't misread as a new placeholder, then swap
        # every "?" for "%s". (Verified no query in this app has a literal
        # "?" character outside of a placeholder position, and none use
        # LIKE/"%" wildcards — safe to do this as a blind two-pass replace.)
        adapted = adapted.replace("%", "%%")
        adapted = adapted.replace("?", "%s")
        return adapted

    def execute(self, sql, params=()):
        if self.backend == "sqlite":
            return self.conn.execute(sql, params)
        return self.cursor().execute(sql, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def cursor(self):
        real_cursor = self.conn.cursor()
        if self.backend == "postgres":
            return _AdaptingCursor(real_cursor, self)
        return real_cursor

    def __getattr__(self, name):
        return getattr(self.conn, name)


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
    conn_str = _get_connection_string()
    if not conn_str:
        # No cloud DB configured at all — SQLite is the intended backend,
        # not a fallback from a failure.
        print("No DATABASE_URL/SUPABASE_DB_URL configured — using local SQLite.")
        return _connect_sqlite(db_path)

    if psycopg2 is None:
        raise RuntimeError(
            "DATABASE_URL is set but psycopg2 is not installed — install it "
            "from requirements.txt (psycopg2-binary)."
        )

    params = _build_postgres_params(conn_str)

    try:
        if params.get("host"):
            addrs = socket.getaddrinfo(params["host"], params.get("port") or 5432)
            print(f"DNS resolution for {params['host']}: {addrs[:3]}")
    except Exception as dns_exc:
        print(f"DNS resolution failed for {params.get('host')}: {dns_exc}")

    try:
        conn = psycopg2.connect(**params)
    except Exception as exc:
        # A connection string WAS configured — a failure here is a real
        # setup problem, not "no cloud DB configured." Raise loudly instead
        # of silently substituting local SQLite: that fallback used to make
        # the app look like it "just works" while quietly not using the
        # configured database (and, on most hosts, against an empty/
        # ephemeral local file) — exactly the failure mode that's hard to
        # notice until data you expect to see just isn't there.
        raise RuntimeError(
            f"Could not connect to the configured Postgres database "
            f"(host={params.get('host')!r}, port={params.get('port')!r}, "
            f"dbname={params.get('dbname')!r}): {exc}\n\n"
            "Common Supabase-specific causes:\n"
            "- Using the 'direct connection' string (port 5432, a "
            "db.<ref>.supabase.co host) from a host without outbound IPv6 "
            "— Supabase's direct connection is IPv6-only; use the Session "
            "or Transaction Pooler connection string instead (host like "
            "aws-0-<region>.pooler.supabase.com, username "
            "postgres.<project-ref>, port 6543 or 5432).\n"
            "- A password with special characters that needs URL-encoding "
            "in the connection string.\n"
            "- sslmode or firewall/network restrictions on the host running "
            "this app."
        ) from exc

    conn.autocommit = False
    print(f"Connected to Postgres at {params.get('host')}:{params.get('port')}")
    return DbConnection("postgres", conn)


def table_columns(conn: DbConnection, table_name: str) -> list:
    if conn.backend == "sqlite":
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]

    # Note: "?" here, not "%s" — DbConnection.execute()'s _adapt_sql() step
    # converts "?" to "%s" for the postgres backend. Writing "%s" directly
    # in a caller would get double-escaped by that same step (it escapes
    # literal "%" to "%%" before translating placeholders).
    cursor = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = ?
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
        "SELECT to_regclass(?)",
        (table_name,),
    )
    return cursor.fetchone()[0] is not None
