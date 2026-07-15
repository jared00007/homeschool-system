# local-only/ — not part of the cloud app

Everything in this folder is **not used by the running Streamlit Cloud
deployment**. It's kept (not deleted) because it still has some value —
historical reference, an alternate local dev path, or just something that
seemed worth not throwing away — but none of it is on the import/dependency
path that `app.py` (root shim) → `tracker/app.py` → `tracker/db_backend.py`
actually runs.

What's here and why:

| File/folder | What it is | Why it's here, not deleted |
|---|---|---|
| `app.py.bak_20260714_134832` | A full backup of `tracker/app.py` from partway through development (2026-07-14, before most of the current features existed) | Point-in-time snapshot in case anything from that stage is ever worth diffing against. Very stale now — not a reference for current behavior. |
| `homeschool-parks-app.textClipping` | A macOS Finder "text clipping" file — created by dragging selected text onto the Desktop | Landed in the project folder by accident at some point; not real project content. Kept rather than deleted on the chance it held a note that mattered. |
| `calendar/weekly-schedule.html` | A standalone static HTML weekly-schedule page, built independently of the Streamlit app | Predates (or was an early parallel prototype to) the app's own "My Week" tab, which now does this natively with live data. Not linked from anywhere in the app. |
| `.devcontainer/devcontainer.json` | GitHub Codespaces / VS Code Dev Containers config | A legitimate alternate way to get a running dev environment (cloud IDE instead of a local venv), but Streamlit Community Cloud doesn't read this file at all — it's irrelevant to the actual production deployment. Move it back to the repo root if you want to use Codespaces. |
| `README_CLOUD.md`, `DEPLOYMENT_CHECKLIST.md`, `CLOUD_MIGRATION_PLAN.md` | Three earlier drafts of cloud-deployment instructions | All superseded by the single, accurate, up-to-date `CLOUD_DEPLOYMENT.md` at the repo root (which reflects everything actually learned getting this working — the pooler-vs-direct-connection gotcha, the placeholder/PRAGMA/import bugs, etc.). Kept for history, not for reference — follow the root doc instead. |
| `tracker-requirements.txt` | The old `tracker/requirements.txt` | Identical content to the repo-root `requirements.txt`, which is what both the cloud deployment and `start-tracker.command` now read from. Having two copies of the same file risked them silently drifting apart. |

## Why this folder exists at all

The repo root and `tracker/` are meant to contain **only what the cloud app
actually needs**: `app.py` (the Streamlit Cloud entry shim), `requirements.txt`,
`tracker/app.py`, `tracker/db_backend.py`, and the docs that describe the
product. Everything else that had accumulated in the project folder —
one-off artifacts, superseded drafts, an alternate dev-environment config —
is collected here instead of scattered through the main tree or silently
deleted.
