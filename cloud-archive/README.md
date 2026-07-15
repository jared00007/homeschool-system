# cloud-archive/ — everything from the Streamlit Cloud + Supabase attempt

The app now runs **local-only**, on the family Mac, shared over the home
WiFi network to other devices (see the root `README.md`). Nothing in this
folder is used by the running app — `tracker/app.py` never imports or
reads anything here.

It's kept, not deleted, because a lot of real debugging work went into
getting the cloud version this far, and it's the starting point if cloud
hosting is ever worth revisiting.

## Why it's archived instead of finished

The backend was proven correct through extensive testing — clean local
runs, zero database errors, zero server-side exceptions, even while
reproducing the exact failure sequence live. But the deployed app on
Streamlit Community Cloud never rendered reliably in the browser, and the
cause was never pinned down: the backend logs showed no crash at all
during the failures, which points at something in that specific hosting
platform's environment (its Python 3.14 runtime, its resource limits, or
something else not visible from outside it) rather than in this code.
Rather than keep guessing blind against a platform with no shell access
and limited logs, we moved to local-only, which is simpler and has
worked in every test.

## What's here

| File | What it is |
|---|---|
| `CLOUD_DEPLOYMENT.md` | The most complete, accurate write-up of the cloud architecture and every bug found and fixed along the way (SQL placeholder translation, schema introspection, dual-entry-point imports, connection pooling/autocommit, the pandas cursor bypass, etc.) — read this first if picking cloud back up |
| `migrate_to_cloud.py` | One-time script that copied the local SQLite data into Postgres |
| `app.py.cloud-entry-shim` | The root-level `app.py` Streamlit Cloud required as its entry point (`sys.path` shim into `tracker/app.py`) — local mode doesn't need this, `start-tracker.command` runs `tracker/app.py` directly |
| `.devcontainer/devcontainer.json` | GitHub Codespaces / VS Code Dev Containers config, for cloud-IDE development |
| `secrets.toml.example` | Template showing the `DATABASE_URL` / `SUPABASE_DB_URL` format Streamlit secrets expected |
| `CLOUD_MIGRATION_PLAN.md`, `DEPLOYMENT_CHECKLIST.md`, `README_CLOUD.md` | Earlier planning drafts, superseded by `CLOUD_DEPLOYMENT.md` — kept for history only |
| `tracker-requirements.txt` | An old duplicate of the repo-root `requirements.txt` from before that was consolidated to one file |

## If you pick this back up

`tracker/db_backend.py` still has the Postgres/SQLAlchemy connection code
(`connect_database()` transparently uses Postgres if `DATABASE_URL` or
`SUPABASE_DB_URL` is set, SQLite otherwise) — that was left in place since
it's harmless when unused. You'd need to re-add `psycopg2-binary` and
`sqlalchemy` to the root `requirements.txt`, restore `app.py.cloud-entry-shim`
to the repo root as `app.py`, and pick a host. Streamlit Community Cloud is
one option but was the source of the unresolved rendering failures here;
worth trying a host with real log/shell access instead (Render, Railway,
Fly.io) so the next debugging session isn't flying blind.
