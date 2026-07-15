# Cloud deployment guide

This is the single, current, accurate guide for the cloud-hosted version of
this app. (Three earlier drafts of this doc — `README_CLOUD.md`,
`DEPLOYMENT_CHECKLIST.md`, `CLOUD_MIGRATION_PLAN.md` — are archived in
`local-only/` for history; don't follow them, they're superseded.)

The stack:
- **GitHub** — source control, and what Streamlit Cloud deploys from
- **Supabase** — managed Postgres database
- **Streamlit Community Cloud** — hosts the running app

## How it actually works

- The repo has **two entry points** that both end up running
  `tracker/app.py`:
  - Locally, `start-tracker.command` runs `streamlit run app.py` from
    inside `tracker/` directly.
  - On Streamlit Cloud, the main module is the repo-root `app.py`, which
    is a tiny shim: it adds the repo root to `sys.path` and does
    `from tracker.app import *`.
  - `tracker/app.py` imports `db_backend` with a try/except that tries
    the same-directory form first, then falls back to the
    package-qualified `tracker.db_backend` — this is what makes both
    entry points work with the same source file. Don't "simplify" this to
    a single import style; it'll break one of the two paths.
- `tracker/db_backend.py` is the only thing that knows whether it's
  talking to SQLite or Postgres. `get_conn()` in `tracker/app.py` calls
  `connect_database()`, which checks for `DATABASE_URL` (or
  `SUPABASE_DB_URL`) and:
  - **Not set** → connects to the local `tracker/homeschool.db` SQLite
    file. This is the normal, intended local-dev path, not a fallback.
  - **Set** → connects to Postgres. If that connection fails, it **raises
    a clear error** (host/port/dbname + the real psycopg2 error) instead
    of silently falling back to SQLite. An earlier version of this code
    fell back silently on failure, which made a broken cloud deployment
    look like it "just worked" while quietly using an empty local
    database — that behavior is gone on purpose.
- Every query in `tracker/app.py` is written once, using SQLite's `?`
  placeholder style. For the Postgres path, `db_backend.py` translates
  `?` → `%s` and adapts `INTEGER PRIMARY KEY AUTOINCREMENT` →
  `BIGSERIAL PRIMARY KEY` automatically, so the app code itself never
  needs to know which backend it's talking to.
- The app shows its actual connected backend on-page (a green box near
  the top: *"✅ Connected to the cloud Postgres database (host)"*). This
  exists because Streamlit Cloud's log viewer doesn't reliably surface
  this app's `print()` output from module-import time — the on-page
  status is the reliable way to confirm what's actually connected,
  don't rely on the logs alone for this.

## Setting it up from scratch

### 1. Create the database
1. Create a Supabase project at supabase.com.
2. Settings → Database → **Reset database password** if you don't already
   have one you like. Pick something with **only letters and digits** —
   avoid `$ * % @ . : / [ ]` — so it never needs URL-encoding when it ends
   up inside a connection string.
3. Settings → Database → Connection string → select **Session pooler** or
   **Transaction pooler** (not "Direct connection" — see the callout
   below). Copy the string.

### ⚠️ Pooler vs. Direct connection — pick Pooler

Supabase gives you two connection string options:
- **Direct connection** (`db.<project-ref>.supabase.co`, port 5432) — this
  host is **IPv6-only**. Most hosted platforms, including Streamlit
  Community Cloud, don't have outbound IPv6, so this connection fails to
  resolve from there. It only works from a network with IPv6 (many home
  networks do, which is why this can look fine when testing locally and
  then fail once deployed).
- **Session pooler** or **Transaction pooler** (host like
  `aws-<n>-<region>.pooler.supabase.com`, username
  `postgres.<project-ref>`, port `5432` or `6543`) — IPv4-compatible,
  works from any host. **Use one of these.**

### 2. Set the connection string

**In Streamlit Cloud** (this is what the live deployment reads): your app
→ Settings → **Secrets**. This box requires **TOML syntax**, not a bare
URL — the value needs a key name and quotes:

```toml
DATABASE_URL = "postgresql://postgres.<project-ref>:<password>@aws-<n>-<region>.pooler.supabase.com:6543/postgres"
```

Save, and it redeploys automatically (takes about a minute; use "Reboot
app" if it doesn't pick it up).

**For local testing against the same cloud database** (optional — local
runs use SQLite by default and that's normally what you want): copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
the same value. That file is gitignored — it never gets pushed, and Streamlit
Cloud's secrets are configured separately in its own dashboard, not read
from this repo.

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
(from the repo root — this is the single `requirements.txt` both the cloud
deployment and the local launcher use.)

### 4. Migrate your existing local data
If you already have real data in `tracker/homeschool.db`, copy it into the
new Postgres database:

```bash
DATABASE_URL="<your pooler connection string>" python3 tracker/migrate_to_cloud.py
```

Run this from the repo root. It preserves the original row IDs (so
cross-table references stay intact) and advances each table's Postgres
sequence past the highest migrated ID afterward, so the live app's next
new row won't collide with one just migrated.

This only needs to be run once. Running it again is safe for tables that
were empty, but will error on tables that already have the migrated rows
(primary key conflict) — it doesn't currently do upserts.

### 5. Deploy
1. Push the repo to GitHub (`git push origin main`).
2. Streamlit Community Cloud → create an app pointing at the repo,
   branch `main`, main file `app.py` (repo root).
3. Set the `DATABASE_URL` secret (step 2 above) if you haven't already.
4. Deploy, then open the app and confirm the green "Connected to the cloud
   Postgres database" box appears near the top.

## Troubleshooting

**Green box doesn't appear at all, no error either** — `DATABASE_URL`
isn't being read as set. Check the exact key name in Streamlit Cloud's
Secrets box (`DATABASE_URL`, spelled exactly, with `= "..."` and quotes)
and that you hit Save.

**Yellow warning box** ("connected to local SQLite instead") — this
shouldn't be possible given the current code (a failed Postgres connection
raises instead of falling back). If you see this, something regressed —
worth investigating as a real bug, not just retrying.

**App crashes on boot with a traceback mentioning `ModuleNotFoundError`** —
almost certainly the dual-import-path issue described above got broken
again. Check `tracker/app.py`'s `db_backend` import still has the
try/except fallback.

**App crashes with a Postgres `RuntimeError`** — read the message, it
includes the host/port/dbname it tried and the real underlying error:
- *"could not translate host name"* → DNS failure, almost always means
  you're using the Direct connection string (IPv6-only) instead of a
  Pooler string.
- An authentication error → wrong password, or the password has special
  characters that got mangled/not-encoded when pasted into the connection
  string. Easiest fix: reset the database password to letters+digits only
  and get a fresh connection string from the Supabase dashboard (don't
  hand-edit the string yourself).
- Streamlit's Secrets box rejects the paste with *"Invalid format: please
  enter valid TOML"* → you pasted the bare connection string without the
  `DATABASE_URL = "..."` wrapper.

**Data doesn't show up even though it connects** — you likely haven't run
the migration script yet (step 4) — a fresh Postgres database only has the
seed/reference catalogs (national parks, elective pool, etc.), not your
actual logged hours/grades/students.

## Notes
- Local SQLite still works with zero configuration if `DATABASE_URL` isn't
  set — that's the normal local-dev path, not a degraded fallback.
- Photo uploads (`tracker/uploads/`) are still local-disk-only. On
  Streamlit Cloud specifically, the filesystem is ephemeral, so uploaded
  photos won't survive a redeploy/restart there yet — moving these to
  Supabase Storage is a real follow-up, not yet done (see `PRODUCT.md`
  roadmap).
