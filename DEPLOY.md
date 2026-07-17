# Deploying Compass (hosted)

Local is unchanged — keep using `start-tracker.command`. This is only for
putting Compass on the web so any family/device can reach it, which the
strategy doc's multi-family direction needs and the local-only app can't do.

## How it works

- `tracker/db_backend.py` already speaks both SQLite and Postgres. With no
  `DATABASE_URL` it uses the local `homeschool.db`; set `DATABASE_URL` and it
  transparently switches to Postgres. Nothing in the app code changes.
- On a host every visitor is "non-local", so the localhost parent/student
  trick can't tell a parent from a kid. Parent mode is unlocked with a
  passcode from the `PARENT_PASSCODE` env var. No passcode set = student-only
  (safe default).

## Render (recommended — real logs + shell, unlike Streamlit Community Cloud)

1. Push this repo to GitHub.
2. Render → **New +** → **Blueprint** → pick the repo. It reads `render.yaml`
   and creates the web service + a managed Postgres, wiring `DATABASE_URL`
   automatically.
3. In the service's **Environment**, set `PARENT_PASSCODE` to something only
   you know.
4. First deploy: the app creates its own tables on boot (same `get_conn()`
   that runs locally) and seeds Foundations/Smithsonian/etc.
5. To bring your existing local data across, run
   `cloud-archive/migrate_to_cloud.py` with `DATABASE_URL` pointed at the
   Render database (see that file's header). Optional — a fresh hosted DB
   works fine, it just starts empty.

## Railway / Fly.io

Same idea, no blueprint file needed: both build the `Dockerfile` directly.
Provision a Postgres add-on, set `DATABASE_URL` and `PARENT_PASSCODE` in the
service env, deploy.

## Local Docker smoke test

```
docker build -t compass .
docker run -p 8501:8501 -e PARENT_PASSCODE=test compass
# open http://localhost:8501 — with no DATABASE_URL it runs on an in-container
# SQLite file (ephemeral), which is fine for a build check.
```

## Notes / next step

Single-tenant for now: one hosted instance = one family's data. Real
per-family accounts (signup, login, data isolation) and billing are the next
build, per the plan's deferred list. The `PARENT_PASSCODE` gate is the
stand-in until then — do not treat it as real multi-user auth.
