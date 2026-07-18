# Compass — Technical Documentation

Audience: developers / operators. For the plain-language version see
`COMPASS_OVERVIEW.md`.

---

## 1. What it is
Compass is a homeschool operations + curriculum web app for one family per
deployment. Its distinctive idea is a **two-track learning model** — a *Passion
Track* (interest-led projects) blended with a *Foundations Track* (life-skills
and financial literacy) into one weekly plan — on top of a solid records engine
(hour logging with parent approval, grading, WA compliance, exportable records).

It is built as a single Streamlit app backed by SQLite (local) or Postgres
(hosted), packaged in Docker, and deployed one instance per household.

---

## 2. Stack
| Layer | Choice | Notes |
|---|---|---|
| UI / app framework | **Streamlit** (Python) | One file: `tracker/app.py` (~6k lines) |
| Data | **SQLite** locally / **Postgres** hosted | Chosen automatically by `DATABASE_URL` |
| DB access shim | `tracker/db_backend.py` | Uniform `execute(sql, params)` with `?` placeholders; translates to `%s` for Postgres; enforces SSL |
| Charts / map | Plotly | Travel choropleth, dashboard bars |
| Container | **Docker** (`Dockerfile`) | `python:3.12-slim`, Streamlit on `$PORT` |
| Hosting | **Render** (free web) + **Neon** (free Postgres) | One web service + one DB per family |

Key env vars:
- `DATABASE_URL` — set → Postgres (hosted); unset → local SQLite file.
- `PARENT_PASSCODE` — deploy-time parent unlock code on hosted instances.

---

## 3. Architecture & data flow

```
Browser ──HTTP──▶ Render (Docker: Streamlit app) ──SQL──▶ Neon Postgres
   ▲                    │
   └─ Parent / Student ─┘        (local mode: same app ──▶ SQLite file)
```

- **One process, one database, one family.** No multi-tenancy — isolation is
  physical (a separate DB + app per household). This is deliberate: zero
  data-leak risk, near-zero code, right for a handful of families.
- **`get_conn()`** (in `app.py`) runs at startup: opens the DB via
  `db_backend.connect_database()`, creates all tables with
  `CREATE TABLE IF NOT EXISTS`, runs column migrations, and seeds reference
  data (curriculum pools, foundations modules, national parks, quizzes,
  Smithsonian links) once.
- Streamlit reruns the whole script top-to-bottom on every interaction; the DB
  connection is a module-global held under a lock.

### Parent vs Student gate
- **Local:** parent toggle shown only to `st.context.ip_address` == localhost;
  LAN devices get Student view only.
- **Hosted:** everyone is non-local, so parent mode is unlocked by
  `PARENT_PASSCODE` (env) — overridable per household via a `parent_passcode`
  setting (Settings tab). No passcode configured → student-only (safe default).
- The `?view=student` query param forces Student view (the link kids get).

---

## 4. Data model (main tables)
Reference/shared (seeded): `curriculum_materials`, `elective_pool`, `book_pool`,
`fun_project_pool` (quest pool), `foundations_modules`, `national_parks`,
`major_cities`, `settings`.

Per-student: `students`, `log_entries` (hours, with `status`
pending/approved/rejected), `assignments` (grades/quizzes),
`student_fun_projects` (picked quests), `student_foundations_progress`,
`passion_profile` (interests), `weekly_plan_items` (blender output),
`travel_entries`, `health_habits` (daily debrief), `accounts` (site logins +
class codes), `assessments`, `student_electives`, `student_books`,
`link_reports`.

### The core write loop
Every student action creates a **pending** record; only a parent's approval
turns it into counted hours (anti-self-certify):
```
Student marks a block/quest/module done
  └─ add_entry(..., status='pending')  →  log_entries
        └─ Parent → Review & Approve → update_entry_status('approved')
              └─ counts on Dashboard toward the 1,000-hr / 180-day requirement
```
Quests and foundations completions require a "what did you do?" **note** (proof
of work), stored on the item and folded into the log entry description.

---

## 5. The two-track model

**Passion Track** (`fun_project_pool` / `student_fun_projects`): a browsable
pool of real-world projects. An **interest profile** (`passion_profile`, tapped
chips) ranks which quests surface. Matching is whole-word + plural-aware keyword
overlap between the interest words and each quest's title/subject/description
(`_interest_keywords` / `_quest_interest_score`), surfaced as a "Picked for you"
shelf and used by the blender.

**Foundations Track** (`foundations_modules`): a curated, hand-authored library
of life-skills / financial-literacy modules across pillars (Financial Literacy,
Digital Literacy, Career Readiness, Health & Wellness, Life Skills, Civics).
Completing one logs hours like a quest.

**The Blender** (`generate_weekly_plan`): fills a parent-set % of the week's
hours from Passion (interest-ranked) and the rest from not-yet-done Foundations,
into one `weekly_plan_items` list the student sees on "My Plan." Completed items
carry over; only unfinished ones rebuild.

---

## 6. Grade awareness (8th / 9th)
- `WEEKLY_SCHEDULE` / `WEEKLY_SCHEDULE_9TH` and `CURRICULUM_RESOURCES` /
  `CURRICULUM_RESOURCES_9TH` are grade-keyed. `schedule_for_grade(grade)` and
  `resources_for_grade(grade)` route by the student's grade (default 8th).
- `GRADE_SCOPES` holds the 8th/9th scope reference (transcript framing for 9th).
- Every consumer (Today/Week boards, day blocks, quiz suggestion,
  planned-hours, dashboard) reads the student's grade. The parent sets grade in
  the add-student form or Settings.
- Quests are shared across grades; a generic high-school quest set
  (`NINTH_GRADE_QUEST_SEEDS`) enriches the pool.

---

## 7. Records / compliance / export
- WA framing: 11 subject areas, ~1,000 hours / 180 days, Declaration of Intent
  reminder + letter template + district form link, annual assessment tracking.
- **Dashboard** shows approved hours vs. a "planned" target *derived from the
  schedule* (`planned_hours_by_subject(grade)`), so a perfect week reads 100%.
- **Export** produces CSVs plus a print-ready **ESA records packet** (HTML →
  print to PDF) that lists completed Foundations modules with their objectives —
  the "documented educational purpose" ESA reimbursement wants.

---

## 8. Deploy
See `DEPLOY.md` and `docs/SETUP_SECOND_FAMILY.md`. In short: Docker image on
Render (free web) + Neon (free Postgres), `DATABASE_URL` + `PARENT_PASSCODE`
env vars, one instance per family.

---

## 9. Known gaps / next tech tasks
- **Photo persistence (important).** Uploaded photos (graded work, travel) save
  to the container's local disk (`tracker/uploads/`), which is **ephemeral on
  Render** — lost on redeploy. Before relying on photo proof-of-work, move
  uploads to object storage (Cloudflare R2 / Backblaze B2 / Supabase Storage)
  and store only the URL in Postgres.
- **Multi-tenancy.** The instance-per-family model doesn't scale past a handful.
  A shared multi-tenant build (accounts, row-level household isolation, a
  cross-family admin) is the next architecture step when family count grows.
- **District form is hardcoded** (Sumner) — could become a per-household setting.
- **Passcode UI quirk.** The hosted unlock is a form (Enter submits); browser
  automation needs the real keystroke path.

---

## 10. Repo map
```
tracker/app.py          the whole app (UI + data + logic)
tracker/db_backend.py   SQLite/Postgres connection shim
Dockerfile              container image
render.yaml             Render blueprint (free web + external Neon)
requirements.txt        streamlit, pandas, plotly, psycopg2-binary, sqlalchemy
DEPLOY.md               hosting guide
docs/                   these documents
cloud-archive/          earlier Streamlit-Cloud+Supabase attempt (reference)
```
