# How we moved this app to the cloud — technical version

This is the real story of the SQLite → Postgres/Supabase cloud migration
for this app: what we built, what broke, and why each fix was needed. If
you're picking up this codebase, read this before touching
`tracker/db_backend.py` or the deployment setup — most of what looks like
odd/defensive code in there exists because of something specific in this
list, not by accident.

## Starting point

A single-file Streamlit app (`tracker/app.py`, ~4,200 lines) with all data
in a local SQLite file (`tracker/homeschool.db`), launched by double-clicking
`start-tracker.command`. Every query in the app was written directly
against SQLite: `?` placeholders, `PRAGMA table_info(...)` for schema
introspection, `sqlite_master` for table existence checks, `INTEGER PRIMARY
KEY AUTOINCREMENT` for IDs.

## Goal

Make the app reachable from any device, not tied to one Mac, without a
rewrite. Chosen stack:
- **GitHub** — source control + what the host deploys from
- **Supabase** — managed Postgres, generous free tier
- **Streamlit Community Cloud** — free hosting for the Streamlit app itself

## The design: one connection abstraction, not a rewrite

Rather than porting the whole app to an ORM or rewriting every query, we
added one module, `tracker/db_backend.py`, exposing a `DbConnection` class
that wraps either a `sqlite3.Connection` or a `psycopg2` connection behind
the same interface (`.execute()`, `.commit()`, `.cursor()`, etc.). The rest
of `app.py` calls `conn.execute(sql, params)` exactly as before — it has no
idea which database is actually behind it.

The two things that differ between SQLite and Postgres syntax get adapted
automatically, in one place, `DbConnection._adapt_sql()`:
```python
adapted = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
adapted = adapted.replace("AUTOINCREMENT", "")
adapted = adapted.replace("%", "%%")   # escape literal % first...
adapted = adapted.replace("?", "%s")   # ...then translate placeholders
```
This only runs for the Postgres backend; SQLite queries pass through
`self.conn.execute()` untouched.

Two schema-introspection calls don't have Postgres equivalents at all
(`PRAGMA table_info`, `sqlite_master`), so `db_backend.py` also exposes
`table_columns()` and `table_exists()` — backend-aware functions that do
the SQLite thing on SQLite and query `information_schema.columns` /
`to_regclass()` on Postgres. `tracker/app.py`'s migration code (in
`get_conn()`) calls these instead of raw PRAGMA.

Which database gets used is decided by one function,
`connect_database()`: if `DATABASE_URL` (or `SUPABASE_DB_URL`) is set in
the environment or Streamlit secrets, connect to Postgres; otherwise, local
SQLite. That's the whole decision tree — no configuration flags, no modes
to choose.

## What broke, in the order we found it

**1. Silent fallback masked real connection failures.** The first version
of `connect_database()` wrapped the Postgres connection attempt in a
broad `try/except` that fell back to SQLite on *any* failure, only
`print()`-logging the error. This meant a broken `DATABASE_URL` produced
an app that looked like it "just worked" while quietly running against an
empty local database — the worst possible failure mode for debugging.
Fixed: fall back to SQLite only when no connection string is configured at
all (that's the intended default, not a failure); if a connection string
*is* configured and fails, raise a `RuntimeError` with the host/port/dbname
and the real underlying error.

**2. Every query needed `?` → `%s` translation, and nothing did it.**
`get_conn()`'s migration code alone has ~15 parameterized queries, and the
rest of the app has around 100 more, all written with SQLite's `?`
placeholder. psycopg2 requires `%s`. This is the `_adapt_sql()` translation
described above — the single highest-leverage fix, since without it,
*every* write and most reads would fail against Postgres even with a
perfect connection.

**3. `db_backend.py`'s own helper queries used `%s` directly — which then
got double-escaped.** `table_columns()`/`table_exists()` were originally
written with native `%s` placeholders (since their author knew they'd run
against Postgres). Once `_adapt_sql()` started escaping literal `%` to
`%%` before translating `?` to `%s`, those hand-written `%s` occurrences
got mangled into `%%s`. Fixed by normalizing those two functions to use
`?` too, so there's exactly one placeholder convention in the whole
codebase and one place that translates it.

**4. Two entry points need two different Python import styles.** The repo
has:
- `start-tracker.command` → `cd tracker/ && streamlit run app.py`, which
  runs `tracker/app.py` as the main script. Python/Streamlit adds the
  *script's own directory* to `sys.path` in this case, so `from
  db_backend import ...` (same-directory) works, but `from
  tracker.db_backend import ...` doesn't (no parent `tracker` package
  visible from inside `tracker/`).
- Streamlit Cloud, whose main module is the repo-root `app.py` — a shim
  that does `sys.path.insert(0, repo_root)` then `from tracker.app import
  *`. This imports `tracker/app.py` as the *submodule* `tracker.app`,
  which does **not** auto-add its own directory to `sys.path` — only the
  repo root (inserted explicitly) is on the path, so `from
  tracker.db_backend import ...` works and plain `from db_backend import
  ...` throws `ModuleNotFoundError`.

  One fix looked right, broke the other entry point, twice, before landing
  on the actual fix:
  ```python
  try:
      from db_backend import connect_database, table_columns, table_exists
  except ImportError:
      from tracker.db_backend import connect_database, table_columns, table_exists
  ```
  Verified by literally simulating both import contexts locally (`python3
  -c "import app"` from inside `tracker/`, and the same from the repo root
  importing the shim) before trusting either "fix."

**5. Supabase's Direct connection string is IPv6-only.** `db.<project-ref
>.supabase.co:5432` only resolves over IPv6. Streamlit Community Cloud (like
most PaaS hosts) has no outbound IPv6, so this connection fails from there
— but works fine testing from a home network with IPv6, which is exactly
the kind of thing that passes locally and fails in production. Fix: use
Supabase's **Session pooler** or **Transaction pooler** connection string
instead (`aws-<n>-<region>.pooler.supabase.com`, username
`postgres.<project-ref>`, port 6543 or 5432) — IPv4-compatible.

**6. Streamlit Cloud's Secrets box needs TOML, not a bare string.** Pasting
just `postgresql://...` into the Secrets textarea fails with "Invalid
format: please enter valid TOML" — it needs `DATABASE_URL =
"postgresql://..."` (key, `=`, quoted value).

**7. A malformed password broke authentication.** Supabase's dashboard
shows the connection string template with the password as a literal
placeholder (e.g. `[YOUR-PASSWORD]`). When the real password got swapped
in, leftover bracket/template characters and part of the old direct-connection
host ended up embedded in the password field, producing a string that
`urllib.parse` happily parsed (host/port/dbname were all fine) but which
authenticated with garbage. Diagnosed by parsing the actual connection
string with `urllib.parse.urlparse()` and inspecting the *shape* of the
parsed password (length, leading `[`, embedded `@`) without needing to
print the real secret. Fixed by resetting the database password to a
random alphanumeric-only string (no characters that need URL-encoding) and
copying a fresh connection string straight from the dashboard instead of
hand-editing one.

**8. Migrated rows would collide with new ones.** `migrate_to_cloud.py`
copies each row's original SQLite `id` across (needed to keep foreign-key
references intact between tables). Postgres's `BIGSERIAL` sequence for
each table has no idea those IDs are now taken, so the first row the *live
app* inserts afterward (which lets the sequence assign an ID) could
collide with an already-migrated row and fail with a duplicate-key error.
Fixed by advancing each table's sequence past `MAX(id)` right after that
table's rows are migrated:
```sql
SELECT setval(pg_get_serial_sequence(%s, 'id'),
       (SELECT COALESCE(MAX(id), 1) FROM <table>))
```

## What the code review turned up once things were working

Getting the connection working end-to-end surfaced the motivation to
actually review the rest of the code, which found:

**9. The parent-mode password lock was still bypassed.**
`st.session_state.parent_authed` defaulted to `True` with a `# TESTING`
comment — leftover from local development, where it's harmless. Once this
became a public Streamlit Cloud URL, it meant *anyone* who opened the link
had unrestricted Parent-mode access (approve hours, see/edit grades,
change the password) with zero prompt. Fixed to default to `False`; first
Parent-mode visit now correctly prompts to create the password.

**10. A single failed query could take down the whole app.** `conn` is one
shared, module-level `DbConnection` — one Python process serving every
user/session, not a fresh connection per request. Postgres's failure
model: after any failed query, the connection enters an "aborted
transaction" state where *every subsequent command fails too*, until a
`ROLLBACK`. Nothing in `app.py` ever called `rollback()`. In practice this
meant one bad query (a constraint violation, for instance) could
effectively break the app for every user until the process restarted.
Fixed centrally, in `DbConnection.execute()`:
```python
try:
    cursor.execute(sql, params)
except Exception:
    self.conn.rollback()
    raise
```

**11. Dead code and repo bloat.** An unused function
(`set_park_booklet_url`, fully superseded by `update_national_park`) and an
unused `Tuple` import got removed. Separately — unrelated to the cloud
migration, but found in the same pass — the entire `tracker/venv/` Python
virtual environment (~8,750 files, including compiled binaries) had been
committed to git at some point. Untracked and gitignored; this alone cut
the tracked repo from ~8,780 files to ~30.

## Verifying it without a live Postgres instance available

Most of this was fixed and verified without direct access to run a real
Postgres server in the dev sandbox:
- SQLite-path regressions were caught with `streamlit.testing.v1.AppTest`
  (`at.run(); assert not at.exception`) after every change — the same
  harness used throughout this app's development.
- The Postgres-path *logic* (placeholder translation, connection-string
  parsing, the loud-failure behavior) was verified with isolated Python
  calls against `db_backend.py`'s functions directly — feeding known SQL
  strings through `_adapt_sql()` and checking the output, and feeding a
  deliberately-bad connection string (a nonexistent hostname) through
  `connect_database()` and confirming it raised the expected `RuntimeError`
  with a real DNS-resolution error embedded, rather than silently falling
  back.
- The actual live connection to Supabase was only confirmed once deployed,
  via the on-page status banner (added specifically because Streamlit
  Cloud's log viewer wasn't reliably showing this app's `print()` output
  from import time — logs are not a reliable signal for this, the on-page
  status is).

## Current state / what's still local-only

- **Photo uploads** (`tracker/uploads/`) are still local-disk-only. On
  Streamlit Community Cloud specifically, the filesystem is ephemeral —
  uploaded photos won't survive a redeploy there yet. Moving these to
  Supabase Storage is the natural next step (tracked in `PRODUCT.md`).
- `migrate_to_cloud.py` is a one-time/manual tool, run locally by a human
  with `DATABASE_URL` set — it is not something the live app ever
  executes itself.
- No automated test suite exists; verification is the `AppTest`-script
  pattern described above, run ad hoc, not checked into CI.

See `APP_KNOWLEDGE.md` for the full technical reference (data model, every
tab's feature set, coding conventions) and `PRODUCT.md` for the roadmap.
