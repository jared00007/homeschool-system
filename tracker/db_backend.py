import os
import sqlite3
import threading
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

    def _raw_execute(self, sql, params):
        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, params)

    def execute(self, sql, params=None):
        sql = self._owner._adapt_sql(sql)
        # `conn` is one shared, module-level connection for the whole app
        # process, not one per request — Streamlit can run more than one
        # session's script rerun concurrently in the same process, and
        # psycopg2 connections are not safe for two threads to issue
        # commands on at once. Without serializing here, two concurrent
        # queries on the same connection can block forever with no
        # exception raised at all — a silent hang, not a crash (this is
        # exactly what "page goes blank, nothing in the logs" looks like).
        with self._owner._lock:
            try:
                self._raw_execute(sql, params)
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                # The connection itself has gone bad — most likely
                # Supabase's pooler silently closed it server-side after
                # sitting idle (a long-lived process reusing one
                # connection can easily outlast a pooler's idle timeout).
                # A dead socket doesn't fail fast: the next query can hang
                # indefinitely waiting for a response that will never
                # arrive, which is exactly "page goes blank, nothing in
                # the logs" — no exception ever gets the chance to be
                # raised or printed. Reconnect once and retry rather than
                # requiring a manual app restart every time this happens.
                self._owner._reconnect()
                self._cursor = self._owner.conn.cursor()
                self._raw_execute(sql, params)
            except Exception:
                # psycopg2 puts a connection into an "aborted transaction"
                # state after any failed query, where every subsequent
                # command fails too, until a rollback. Roll back here so
                # one bad query can't take down every other page/user for
                # the rest of the process's life.
                self._owner.conn.rollback()
                raise
        # psycopg2's cursor.execute() returns None (per DBAPI2 spec);
        # sqlite3's returns the cursor itself, which the whole app relies
        # on for chaining (conn.execute(...).fetchall()). Return self here
        # so both backends behave the same way to callers. Reading results
        # afterward (.fetchall()/.fetchone()) is safe outside the lock —
        # psycopg2's default cursor buffers the full result client-side
        # during execute(), so fetching doesn't touch the network again.
        return self

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class DbConnection:
    """Small compatibility wrapper that lets the app use either SQLite or Postgres.

    `conn` (the module-level instance of this class in tracker/app.py) is
    shared across the whole app process — one connection object, every
    session, every concurrent script rerun. Neither sqlite3 (in
    check_same_thread=False mode) nor psycopg2 guarantee that's safe for
    two threads to issue commands on at the same time — psycopg2
    especially can just hang forever with no exception. `self._lock`
    serializes every actual query so that risk doesn't exist regardless of
    backend."""

    def __init__(self, backend: str, connection):
        self.backend = backend
        self.conn = connection
        self._lock = threading.Lock()

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
            with self._lock:
                return self.conn.execute(sql, params)
        return self.cursor().execute(sql, params)

    def _reconnect(self):
        """Re-establish the underlying Postgres connection — used when the
        pooled connection has gone stale (closed server-side while idle)
        and the next query would otherwise hang against a dead socket."""
        conn_str = _get_connection_string()
        params = _build_postgres_params(conn_str)
        new_conn = psycopg2.connect(**params)
        new_conn.autocommit = False
        try:
            self.conn.close()
        except Exception:
            pass  # the old connection is already broken; closing it is best-effort
        self.conn = new_conn

    def commit(self):
        with self._lock:
            self.conn.commit()

    def rollback(self):
        with self._lock:
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

    # This app holds one connection open for the entire life of the
    # process (not one per request), which can easily outlast a pooler's
    # idle-connection timeout — Supabase's pgbouncer can silently close a
    # connection server-side after it sits idle. Without these, the next
    # query on that now-dead socket doesn't fail fast: it can hang
    # indefinitely waiting for a response that will never come, with
    # nothing to log because nothing has actually failed yet. TCP
    # keepalives let the OS detect that within ~40s of idling instead of
    # never; connect_timeout bounds how long establishing a *new*
    # connection can take.
    #
    # Deliberately NOT setting statement_timeout via the "options" startup
    # parameter here: that's a session-level GUC, and this connection goes
    # through Supabase's *transaction-mode* pooler (port 6543) — those
    # don't reliably support session-level SET/options the same way a
    # direct connection does, and setting one broke the connection
    # entirely. Not worth the risk for a nice-to-have safety net.
    params.setdefault("connect_timeout", 10)
    params.setdefault("keepalives", 1)
    params.setdefault("keepalives_idle", 20)
    params.setdefault("keepalives_interval", 5)
    params.setdefault("keepalives_count", 4)

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
