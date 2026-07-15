import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional
import urllib.parse

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None

try:
    from sqlalchemy import create_engine
except Exception:  # pragma: no cover - optional dependency
    create_engine = None


def _adapt_sql(sql: str) -> str:
    """Translate this app's SQLite-flavored SQL (written once, throughout
    tracker/app.py, using "?" placeholders) to Postgres syntax."""
    if not isinstance(sql, str):
        return sql
    adapted = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    adapted = adapted.replace("AUTOINCREMENT", "")
    # psycopg2 requires "%s", not "?". Escape any literal "%" first (e.g.
    # in a LIKE pattern) so it isn't misread as a new placeholder, then
    # swap every "?" for "%s". (Verified no query in this app has a
    # literal "?" character outside of a placeholder position, and none
    # use LIKE/"%" wildcards — safe as a blind two-pass replace.)
    adapted = adapted.replace("%", "%%")
    adapted = adapted.replace("?", "%s")
    return adapted


class _PooledCursor:
    """A cursor-shaped object that checks out a fresh connection from the
    SQLAlchemy pool only when .execute() actually runs, and returns it to
    the pool immediately afterward — never holds one open and idle.

    This is the fix for everything that went wrong tonight holding one
    psycopg2 connection open for the app's entire process lifetime:
    - pool_pre_ping validates the connection is actually alive before
      handing it out, transparently reconnecting if Supabase's pooler
      closed it server-side while idle (previously: a silent hang).
    - The pool itself is thread-safe by design — concurrent script
      reruns each get their own checked-out connection (previously: a
      hand-rolled lock, easy to get wrong).
    - Nothing is held open between calls, so nothing can accumulate an
      open transaction across a long-idle period (previously: the actual
      root cause — autocommit=False plus a connection kept for the
      process's whole life meant every read left a transaction open,
      which pinned a backend connection and exhausted Supabase's pool).

    Matches both calling conventions used in this codebase: chained
    (`conn.execute(sql, params).fetchall()`) and pandas' own
    (`conn.cursor()` now, `.execute(...)` later, `.description`/
    `.fetchall()` after that) — the checkout only happens inside
    execute(), so both work identically.
    """

    def __init__(self, engine):
        self._engine = engine
        self._cursor = None

    def execute(self, sql, params=None):
        sql = _adapt_sql(sql)
        conn = self._engine.raw_connection()
        try:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
        except Exception:
            conn.rollback()
            conn.close()
            raise
        else:
            # The DBAPI cursor buffers its full result set client-side
            # during execute() (true for both psycopg2's default cursor
            # and sqlite3) — closing/returning the connection now is safe;
            # .fetchall()/.fetchone() afterward just reads that buffer,
            # no further network round-trip. The engine runs in autocommit
            # mode (set at creation), so writes are already durable too.
            self._cursor = cur
            conn.close()  # returns the connection to the pool
        return self

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class DbConnection:
    """Compatibility wrapper so tracker/app.py's existing code — "?"
    placeholders, conn.execute(...).fetchall() chaining, conn.commit()
    after writes — works completely unchanged, while the actual
    connection handling underneath differs by backend:

    - SQLite: one plain sqlite3.Connection held for the process's life.
      This has never been the source of any problem — it's a local file,
      no pooling/staleness concerns — so it's untouched.
    - Postgres: a SQLAlchemy engine with a real connection pool
      (pool_pre_ping validates liveness before every checkout). No
      connection is held between calls; see _PooledCursor.
    """

    def __init__(self, backend: str, connection):
        self.backend = backend
        self.conn = connection  # sqlite3.Connection, or a SQLAlchemy Engine for postgres
        self._lock = threading.Lock()

    def execute(self, sql, params=()):
        if self.backend == "sqlite":
            with self._lock:
                return self.conn.execute(sql, params)
        return _PooledCursor(self.conn).execute(sql, params)

    def commit(self):
        if self.backend == "sqlite":
            with self._lock:
                self.conn.commit()
        # Postgres path: each _PooledCursor.execute() call already runs
        # against an autocommit connection and returns it to the pool
        # immediately — there is no "current" connection left to commit
        # by the time app.py calls this separately. Safe no-op.

    def rollback(self):
        if self.backend == "sqlite":
            with self._lock:
                self.conn.rollback()
        # Postgres: see commit() — nothing to roll back after the fact;
        # _PooledCursor.execute() already rolls back its own connection
        # immediately on failure, before returning it to the pool.

    def close(self):
        if self.backend == "sqlite":
            self.conn.close()
        else:
            self.conn.dispose()  # closes every pooled connection

    def cursor(self):
        if self.backend == "sqlite":
            return self.conn.cursor()
        return _PooledCursor(self.conn)

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
    if create_engine is None:
        raise RuntimeError(
            "DATABASE_URL is set but sqlalchemy is not installed — install "
            "it from requirements.txt (sqlalchemy)."
        )

    params = _build_postgres_params(conn_str)
    url = (
        f"postgresql+psycopg2://{urllib.parse.quote(params.get('user', ''))}:"
        f"{urllib.parse.quote(params.get('password', ''))}@"
        f"{params.get('host')}:{params.get('port', 5432)}/{params.get('dbname', 'postgres')}"
    )

    connect_args = {
        "sslmode": params.get("sslmode", "require"),
        "connect_timeout": 10,
        # This app used to hold one connection open for its entire
        # process lifetime; a long-idle connection can outlast Supabase's
        # pooler idle timeout, and TCP keepalives let a genuinely dead
        # socket get noticed within ~40s rather than never. Kept as a
        # second layer of defense even though the pool itself (below) no
        # longer holds any one connection open between calls.
        "keepalives": 1,
        "keepalives_idle": 20,
        "keepalives_interval": 5,
        "keepalives_count": 4,
    }

    try:
        engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,   # validate a connection is alive before handing it out; reconnect if not
            pool_size=3,          # this is one low-traffic family app, not a high-concurrency service
            max_overflow=2,
            pool_recycle=280,     # proactively recycle before any pooler-side idle timeout, belt-and-suspenders with pre-ping
            isolation_level="AUTOCOMMIT",
        )
        # Fail fast here if the connection is genuinely bad (wrong host,
        # bad password, pooler unreachable) rather than deferring the
        # first real error to whatever page happens to run the first
        # query.
        test_conn = engine.raw_connection()
        test_conn.close()
    except Exception as exc:
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

    print(f"Connected to Postgres at {params.get('host')}:{params.get('port')} "
          f"(pooled via SQLAlchemy, pool_pre_ping enabled)")
    return DbConnection("postgres", engine)


def table_columns(conn: DbConnection, table_name: str) -> list:
    if conn.backend == "sqlite":
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]

    cursor = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
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

    cursor = conn.execute("SELECT to_regclass(?)", (table_name,))
    return cursor.fetchone()[0] is not None
