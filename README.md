# 🧭 Compass

A homeschool app that follows what a kid is actually *into* — while still
guaranteeing the real-life skills school skips — and quietly keeps the hours and
records a homeschool parent needs for the state.

Built for grades 8–9 (Washington DOI compliance framing). Runs one private
instance per family.

---

## What it does

- **Two-track learning.** A **Passion Track** (interest-led project "adventures"
  that branch through a 4-phase arc — Start · Build · Level Up · Showcase) and a
  **Foundations Track** (life skills — money, cooking, civics), blended into a
  weekly plan at a parent-set ratio.
- **Records that fill themselves in.** Every quest and module is tagged to real
  WA subjects, so finishing the fun stuff logs compliance hours automatically —
  pending parent approval.
- **Parent as certifier.** Kids log work; nothing counts until a parent approves
  it in Review & Approve. Clean records / ESA export when you need it.
- **A home the kid runs toward.** A Home feed, a sprint-board "Today," grades,
  quizzes, a travel log, and a daily debrief.

For the full plain-language tour see [docs/COMPASS_OVERVIEW.md](docs/COMPASS_OVERVIEW.md).

---

## How it runs

| | Local (dev) | Hosted (each family) |
|---|---|---|
| Backend | SQLite file (`tracker/homeschool.db`) | Postgres (free Neon) |
| Host | your Mac | Render (free tier) |
| Parent mode | shown on localhost | unlocked by `PARENT_PASSCODE` |

The app auto-selects the backend: set `DATABASE_URL` and it uses Postgres,
otherwise SQLite. One Render service + one Neon database per family keeps
households fully isolated.

---

## Quickstart (local)

```bash
pip install -r requirements.txt
streamlit run tracker/app.py
```

Or on a Mac, double-click `start-tracker.command` (handles setup + launch).
Your data lives in `tracker/homeschool.db`, created on first run. It's
gitignored — your data never leaves your machine. Back it up by copying that
one file.

## Deploy (hosted)

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for the Render + Neon setup, and
**[docs/SETUP_SECOND_FAMILY.md](docs/SETUP_SECOND_FAMILY.md)** for the
per-family operator checklist.

---

## Repo layout

```
├── tracker/
│   ├── app.py            ← the entire app
│   └── db_backend.py     ← SQLite / Postgres connection layer
├── requirements.txt
├── Dockerfile            ← container image for hosting
├── render.yaml           ← Render blueprint (one service per family)
├── start-tracker.command ← local Mac launcher
├── resources/ curriculum/← static reference content
└── docs/                 ← documentation (index below)
```

## Documentation

| Doc | For |
|---|---|
| [COMPASS_OVERVIEW.md](docs/COMPASS_OVERVIEW.md) | Anyone — what Compass is, plain language |
| [COMPASS_TECHNICAL.md](docs/COMPASS_TECHNICAL.md) | Developers / operators — how it's built |
| [FAMILY_WELCOME_GUIDE.md](docs/FAMILY_WELCOME_GUIDE.md) | A family getting started |
| [DEPLOY.md](docs/DEPLOY.md) | Standing up the hosted app |
| [SETUP_SECOND_FAMILY.md](docs/SETUP_SECOND_FAMILY.md) | Operator checklist for a new family |
| [ANTI_CHEAT_DEVICE_NETWORK_SETUP.md](docs/ANTI_CHEAT_DEVICE_NETWORK_SETUP.md) | Keeping AI out of schoolwork |

---

## Tech

Python · [Streamlit](https://streamlit.io) · SQLite (local) / Postgres (hosted,
via [Neon](https://neon.tech)) · [Render](https://render.com) · Docker.
Single-file app by design — simple to run, simple to reason about.
