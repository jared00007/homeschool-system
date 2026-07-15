# Homeschool One-Stop — app.py Product Knowledge

Reference doc for an LLM picking up work on this codebase. It describes what
the app does, how it's built, the full data model, and the conventions that
have to be followed to extend it safely. This is NOT the user-facing README
(`README.md` at repo root) — that's short and friendly for the parent. This
doc is exhaustive and technical, for a coding assistant.

## 1. What this is

A single-file **Streamlit + SQLite** app that runs one WA-state homeschool
family's entire operation: daily schedule, curriculum links, hour/day
compliance tracking (1,000 hrs / 180 days), parent-approval workflow,
grading, health check-ins, a full travel-log/journal system, and WA DOI
legal-compliance tracking (RCW 28A.200.010 annual assessment requirement).

- Built for one specific student (currently: an 8th grader, WA state).
- Runs entirely local. `Nothing leaves your machine` is a stated design
  principle in the app's own docstring — no cloud, no accounts, no network
  calls except the curriculum resource links the student clicks out to.
- Single entry point: `tracker/app.py` (~4,200 lines). No other Python
  files, no package structure — everything (schema, queries, rendering) is
  in this one file, top to bottom.

Run with `streamlit run app.py` from `tracker/`, or double-click
`start-tracker.command` at repo root (handles venv/deps setup).

## 2. File layout

```
homeschool-system/
├── README.md                    ← human-facing (parent) doc
├── APP_KNOWLEDGE.md             ← this file
├── start-tracker.command        ← double-click launcher
├── enhancements                 ← plain-text running list of feature
│                                   requests (---ideas---/---adds---/
│                                   ---removal---/---work done---)
├── tracker/
│   ├── app.py                   ← the entire app
│   ├── requirements.txt         ← streamlit>=1.35, pandas>=2.0, plotly>=5.20
│   ├── homeschool.db            ← SQLite DB, created on first run
│   ├── uploads/
│   │   ├── journal/             ← travel entry photos
│   │   └── grading/             ← photos of handwritten graded work
│   └── venv/
├── curriculum/
│   └── 8th-grade-curriculum-map.md
└── resources/
    └── links.md
```

No ORM. Every table is raw SQL via a single module-level `conn =
sqlite3.connect(...)` (thread-unsafe flag `check_same_thread=False` is set
since Streamlit can run callbacks off the main thread). All reads go through
`pd.read_sql(...)`, all writes are `conn.execute(...); conn.commit()`.

## 3. Modes & auth

Two modes, switched via a sidebar radio (`🎒 Student` / `🔑 Parent`):

- **Student mode** (default, no password): today's schedule with links,
  "Done ✔" buttons that create **pending** log entries, quizzes, travel log,
  health check-in, grades (read-only), logins (read-only), broken-link
  reporting, curriculum proposals.
- **Parent mode** (password-gated): everything above plus approve/reject
  pending hours, grading, dashboards, exports, admin panels for every
  content pool (electives, books, fun projects, parks, cities), settings.

Password: SHA-256 + per-install random salt (`secrets.token_hex(16)`),
stored in the `settings` table as `pw_hash`/`pw_salt`. First Parent-mode
visit prompts to *create* the password; after that it's required to unlock,
with an explicit "Lock parent mode" button.

**⚠️ Testing bypass currently active**: `st.session_state.parent_authed`
defaults to `True` at boot (see `app.py` around the `# TESTING:` comment
near `st.set_page_config`). This must be flipped back to `False` before any
real use — currently anyone can open Parent mode with zero password prompt.

**Two different security models coexist by design, do not conflate them:**
- The parent password is hashed+salted (real, if lightweight, security).
- External-site credentials in the `accounts` table (Khan Academy logins,
  etc.) are stored **plain text**, on purpose — the student needs to read
  them to log in himself. The UI shows an explicit warning caption about
  this. Don't "fix" this by hashing it; that would break the feature.

## 4. Data model (SQLite, `tracker/homeschool.db`)

All migrations happen in `get_conn()` at the top of the file: a fresh
`CREATE TABLE IF NOT EXISTS` for every table, followed by `PRAGMA
table_info(...)` + `ALTER TABLE ... ADD COLUMN` guards for columns added
after a table's original ship date. **Every new column must be added in
both places** — the CREATE (for fresh installs) and a guarded ALTER (for
this family's already-seeded DB) — or existing installs silently break.

| Table | Purpose | Key columns |
|---|---|---|
| `students` | One row per kid (app supports multiple, only one is in real use) | name, grade, school_year |
| `log_entries` | Hour/day compliance log — both student "Done ✔" taps (status=`pending`) and parent Manual Log entries (status=`approved`) | entry_date, subject, hours, day_type, status, **submitted_at** |
| `assignments` | Grades — quiz auto-submissions AND parent-entered grades, same table | assign_date, subject, title, score, max_score, notes, photo_path, **submitted_at** |
| `assessments` | Annual WA-required standardized test / certificated-evaluator record | assessment_date, assessment_type, evaluator, result, notes |
| `settings` | Key/value store | pw_hash, pw_salt, elective deadlines, school-year start/end dates |
| `student_electives` | Which electives the student picked this year (max `MAX_ELECTIVES`=2) | elective_name, selected_date |
| `student_books` | Reading list state | title, author, status (planned/reading/finished), selected_date, finished_date, **finished_at** |
| `accounts` | External-site logins (⚠️ plain text password, by design) | service_name, url, username, password, status |
| `elective_pool` / `book_pool` / `fun_project_pool` | Parent-managed catalogs of *available* options (admin CRUD via `render_pool_admin`) | — |
| `proposals` | Student-submitted "I want to add X to the pool" requests | prop_type, title, status (pending/approved/rejected), parent_note, submitted_date, **submitted_at**, reviewed_date |
| `student_fun_projects` | Student's picked fun/enrichment projects | status (planned/finished), selected_date, finished_date, **finished_at** |
| `health_habits` | Daily wellness check-in — separate from hour-compliance | log_date (UNIQUE w/ student_id), exercise/water/sleep/nutrition (0/1), journal, day_rating, mood_rating (1-5), lesson_hard (0/1), lesson_hard_notes |
| `holidays` | Date ranges shown as "no school" on the Calendar | start_date, end_date, label |
| `parent_checkins` | Free-form parent journal about the homeschool experience | checkin_date, notes |
| `national_parks` | Reference pool of all 63 NPS national parks (seeded once) | name, state, lat, lon, booklet_url, region (one of `NPS_REGIONS`) |
| `major_cities` | Reference pool — every state capital + a few extra | name, state, lat, lon |
| `travel_entries` | **Unified** table for every kind of travel log entry — park visit, state visit, city visit, or freeform journal entry. One entry tags *at most one* of state/park/city (see §6) | entry_date, title, content, photo_path, tag_state, tag_park_id, tag_city_id, badge_earned, **submitted_at** |
| `link_reports` | Student-submitted "this link is broken" reports for parent review | url, description, status (pending/fixed/dismissed), parent_note, resolved_date, **submitted_at** |

Bolded columns (`submitted_at` / `finished_at`) are auto-captured full
datetimes (`datetime.now().isoformat(timespec="seconds")`), written
server-side at the moment of insert/status-change, **not user-editable**,
and distinct from the adjacent user-facing date field (which the student/
parent can pick/backdate). Added across every "student submits or marks
done" table per an explicit ask — see §8.

## 5. Date handling — read this before touching any date

- **Storage is always ISO** (`YYYY-MM-DD`, or full ISO datetime for the
  `submitted_at`/`finished_at` columns). Never change this — sorting,
  `WHERE` comparisons, and set operations throughout the file assume ISO
  string ordering.
- **Display is always `MM-DD-YYYY`.** A helper `fmt_date(d)` (near the top
  of the file, before `letter_grade`) converts any ISO string / `date`
  object / `None` / `NaN` to `MM-DD-YYYY` for display. **Every place a date
  is shown to the user must go through `fmt_date()`** — dataframes, markdown,
  captions, CSV exports. Every `st.date_input(...)` widget must be given
  `format="MM-DD-YYYY"`.
- Exception, deliberately not converted: the Calendar tab's own
  navigational chrome (month headers like "July 2026", weekday grid labels,
  "Tuesday, July 14" day headers) stays in natural human-readable form —
  that's calendar-browsing UI, not a data-record date, and forcing
  MM-DD-YYYY into it would hurt readability without matching what was
  actually asked for.

## 6. Travel Log — architecture and history (important, easy to get wrong)

This subsystem went through several redesigns in one session; the *current*
shape is the one described here — don't reintroduce the earlier ones.

- **One table, one form, one list.** `travel_entries` holds every kind of
  entry. `render_travel_entry_form()` renders a **Type** selectbox — 🏔️
  National Park visit / 🗺️ State visit / 🏙️ City visit / 📓 Journal entry —
  and the form fields *change* based on the selected type:
  - Park: park picker + date + 🏅 Junior Ranger badge checkbox + notes.
    **No state/city field** — the park's state is implied via a JOIN to
    `national_parks`, never duplicated into `tag_state`.
  - State: state picker (excludes states already covered by a logged
    park/city visit, via `get_all_visited_states()`, with a caption listing
    what's already covered) + date + notes. **No park/city field.**
  - City: city picker + date + notes. **No state/park field.**
  - Journal: free title + date + content, **no location tag at all** — the
    catch-all type for anything that isn't specifically a park/state/city
    visit. Each type includes a one-line geography/writing prompt caption
    above its notes field (e.g. "What region of the country is this in?"),
    and every type supports an optional photo upload.
  - This is intentionally **not** a single form where you can tag
    state+park+city simultaneously on one entry — that was tried and
    explicitly reverted per user feedback ("if park is chosen, don't
    include state or city for this type").
  - 🏅 badge checkbox for Park type used a "reset counter in the widget key"
    trick at one point to make it appear/disappear conditionally when it
    lived in a single unified form; that whole mechanism is gone now that
    each type is its own static field set — don't reintroduce it unless the
    form goes back to a single-type-does-everything shape.
- **One combined list** (`render_travel_entries_list`) shows every entry as
  a card — title, date, whatever tags/badge/photo it has, Remove button. The
  four old separate containers (National Parks / States Visited / Major
  Cities / Travel Journal) were explicitly removed as duplicative — do not
  re-add per-type list containers.
- A small separate **Junior Ranger booklet lookup** expander (park picker →
  link to that park's real booklet URL) sits above the form — it's a
  reference tool, not a log entry, and was deliberately kept separate.
- `get_all_visited_states(student_id)` derives the visited-states set from
  `travel_entries` directly (`tag_state` ∪ park's state ∪ city's state) —
  there is no separate "states visited" table anymore.
- **Migration history**: this table used to be four separate tables
  (`student_park_visits`, `student_city_visits`, `student_state_visits`,
  `travel_journal`). They were consolidated into `travel_entries` in one
  migration pass. `get_conn()` handles: renaming a pre-existing
  `travel_journal` to `travel_entries` (guarded to run **before** the fresh
  `CREATE TABLE IF NOT EXISTS travel_entries`, otherwise the empty new table
  shadows the rename and old data is orphaned — this was a real bug, caught
  and fixed), then dropping the three legacy per-type tables.
- Map (`render_travel_map`): Plotly `Scattergeo` choropleth of US states
  (2-color: visited/not, from the dataviz palette) plus emoji markers for
  parks (🏔️, colored by NPS region via `get_region_color_map()`, using the
  dataviz skill's validated 8-hue categorical palette) and cities (📍, fixed
  blue). Emoji markers are built as a colored circle trace (carries
  legend/hover) layered under a text-mode trace with the emoji (no legend/
  hover of its own) — Plotly `Scattergeo` has no native per-point image
  support, so this is the workaround; don't try to swap in per-marker PNG
  logos without re-deriving that constraint.
- `NPS_REGIONS` (12 entries) is NPS's real DOI Unified Regions structure,
  verified live against nps.gov, not guessed. Region-to-color mapping is
  computed **dynamically per family** (`get_region_color_map`) rather than a
  fixed table, specifically so a family whose home region sorts late in the
  canonical list doesn't get a muted/last-resort color for their own most-
  visited region.

## 7. Feature tour by tab

### Student mode tabs
(`🚀 Day 1 & Day 2 Checklist`, `🎯 Electives & Books`, `📅 Today`, `📆
Calendar`, `🗓 My Week`, `📋 8th Grade Scope`, `🎉 Make It Fun`, `🗺️ Travel
Log`, `📝 Quizzes`, `🔑 My Logins`, `🏆 My Grades`)

- **Day 1/2 Checklist**: onboarding — orientation tasks, account setup
  status, links unlock on a delay (`day2_unlock` date) so day 2 material
  doesn't show day 1.
- **Electives & Books**: pick up to `MAX_ELECTIVES` electives (locks after a
  parent-set deadline) and a current book; can also submit a **proposal**
  for a new elective/book/fun-project not in the pool, for parent review.
- **Today**: the day's schedule blocks (`WEEKLY_SCHEDULE`) with curriculum
  links and "Done ✔" buttons → creates a `pending` `log_entries` row. Also
  hosts the daily **Health Check-in** card (exercise/water/sleep/nutrition
  toggles, day/mood rating emoji scale, "was today's lesson hard?" Y/N +
  optional notes, journal text) and the quiz-suggestion nudge.
- **Calendar**: month grid, holiday/break shading, key legal dates
  (`KEY_DATES` — Declaration of Intent, assessment window), quiz/fun-project
  markers.
- **My Week**: read-only full weekly schedule with links.
- **8th Grade Scope**: static reference of the typical 8th-grade scope —
  informational only, WA has no state-mandated grade-level standards for
  home-based students; explicitly not tracked/graded.
- **Make It Fun**: fun/enrichment project picker (`fun_project_pool`),
  separate from core academics; students can propose new ones.
- **Travel Log**: see §6.
- **Quizzes**: `QUIZ_BANK` — subject → topic → 5 multiple-choice questions,
  currently covering Mathematics, Science, Social Studies, History, Reading,
  Writing, Health (17 topics total). Auto-graded on submit, writes straight
  to `assignments` (title prefixed `"Quiz: "`), with a minimum-time floor
  (`QUIZ_SEC_PER_QUESTION` × question count) to discourage rushing.
- **My Logins**: read-only table of `accounts` with status=`created`, plus
  the **broken-link report** form (submits to `link_reports`) and the
  student's own report-status list.
- **My Grades**: read-only per-subject average/letter grade
  (`grade_summary()`).

### Parent mode tabs
(`🚀 Launch Checklist`, `🕓 Review & Approve`, `📝 Manual Log`, `🎓 Grading`,
`📊 Dashboard`, `📚 Curriculum`, `📋 8th Grade Scope`, `🎉 Make It Fun`,
`🗺️ Travel Log`, `🔑 Accounts`, `✅ Assessments`, `⬇️ Export`, `⚙️ Settings`)

- **Launch Checklist**: first-run setup — school year dates, curriculum
  picks, account creation progress, etc.
- **Review & Approve**: every `pending` `log_entries` row, with hours
  adjustable before Approve/Reject.
- **Manual Log**: parent-entered hours (auto-approved), plus the full
  editable log table.
- **Grading**: record a grade (subject/title/score/notes + optional photo
  for handwritten work), a curated list of free printable-worksheet
  resources (Math-Drills, CommonCoreSheets, HomeschoolMath, EnglishLinx,
  K12Reader, ReadWorks), per-subject grade summary, full graded-work table
  with a photo gallery expander.
- **Dashboard**: hours/days vs `REQUIRED_HOURS`=1000 / `REQUIRED_DAYS`=180,
  planned-vs-actual for the current week (`PLANNED_HOURS`), hours-by-subject
  chart, health-habits weekly summary.
- **Curriculum**: pool-admin panels (add/edit/delete) for electives, books,
  fun projects — uses the generic `render_pool_admin()` pattern (see §9) —
  plus the **proposal review** queue (approve auto-adds to the relevant
  pool; reject just closes it out with a note).
- **8th Grade Scope**: same reference view as student mode.
- **Make It Fun**: fun-project pool admin.
- **Travel Log**: same shared `render_travel_log()` as student mode (see
  §6), plus national-park and major-city pool admin panels.
- **Accounts**: the checklist of every curriculum-linked service that needs
  a login (`ACCOUNT_SERVICES` — 14 services incl. Khan Academy, CommonLit,
  ReadWorks, CK-12, Duolingo, Code.org, etc.), a custom-account add form,
  and the **broken-link report review** section (mark fixed/dismiss/delete,
  with an optional parent note).
- **Assessments**: log the annual WA-required standardized test /
  certificated-evaluator result (RCW 28A.200.010); overdue/upcoming
  reminders computed from the school-year end date.
- **Export**: CSV downloads of approved hours, grades, assessments — dates
  reformatted to MM-DD-YYYY, `student_id` column dropped. Framed as the
  annual compliance packet / future transcript source.
- **Settings**: change parent password.

## 8. Conventions to follow when extending this app

- **Migration discipline** (§4): every new column in both the CREATE and a
  guarded ALTER, every new table needs a fresh `CREATE TABLE IF NOT EXISTS`.
- **Date discipline** (§5): ISO storage, `MM-DD-YYYY` display via
  `fmt_date()`, `format="MM-DD-YYYY"` on every `st.date_input`.
- **Auto-timestamp on student submissions/completions**: any new
  student-submits or student-marks-done flow should get its own
  `submitted_at`/`finished_at` column, auto-populated with
  `datetime.now().isoformat(timespec="seconds")` at the DB layer, not
  user-editable, not currently surfaced in the UI (pure audit capture) —
  match the existing pattern in `add_entry`, `add_assignment`,
  `add_travel_entry`, `add_link_report`, `add_proposal`,
  `update_fun_project_status`, `update_book_status`.
- **Generic pool-admin pattern** — `render_pool_admin(subheader, caption,
  df, id_col, fields, add_fn, update_fn, delete_fn, key_prefix,
  expander_label_fn=None)` is a reusable add/edit/delete admin UI. `fields`
  is a list of `(column, label, widget_type)` where `widget_type` is
  `"text"`, `"textarea"`, or a list (renders as `st.selectbox`). Used for
  elective/book/fun-project/national-park/major-city pools. Reuse this
  rather than hand-rolling another admin CRUD panel.
- **Photo upload pattern**: `st.file_uploader` → `save_uploaded_photo(
  uploaded_file, student_id, subdir="journal")` writes to `UPLOADS_BASE /
  subdir / "{student_id}_{epoch_ms}.{ext}"` and returns a path *relative to
  the app folder* (what gets stored in the DB as `photo_path`). Current
  subdirs: `"journal"` (travel entries) and `"grading"` (graded-work
  photos). Always pair with cleanup: the corresponding `delete_*` function
  must `unlink()` the file (guarded with `.exists()` or
  `missing_ok=True`) before/alongside the DB row delete.
- **Two security models, don't conflate**: parent password is hashed
  (`hashlib.sha256` + `secrets.token_hex(16)` salt); external-site
  `accounts` passwords are plain text on purpose, with an on-screen warning.
- **Color palette**: any new chart/map element should pull from the
  dataviz skill's validated palette (`MAP_CITY_COLOR`, `MAP_REGION_PALETTE`,
  status colors, etc.), not ad-hoc hex — load the `dataviz` skill before
  adding chart color logic.
- **No comments explaining WHAT code does** — this file's existing comment
  style is sparse, used only for non-obvious WHY (e.g. the migration-order
  bug note in `get_conn()`, the NPS region-color rationale). Match that
  density; don't add narrative comments.

## 9. Testing this app

There is no formal test suite. Verification throughout development has been
via:

1. **Syntax**: `python3 -m py_compile app.py`.
2. **Boot check**: `python3 -c "import app"` from `tracker/` with the venv
   active — this executes `get_conn()` at import time (module-level `conn =
   get_conn()`), so it's the fastest way to confirm migrations run clean
   and check the resulting schema via `sqlite3 homeschool.db "PRAGMA
   table_info(...)"` / `.tables`.
3. **`streamlit.testing.v1.AppTest`** — the primary interaction-level
   verification tool. Pattern:
   ```python
   from streamlit.testing.v1 import AppTest
   at = AppTest.from_file("app.py")
   at.run(timeout=30)
   assert not at.exception  # empty ElementList() == no error
   ```
   Gotchas learned the hard way:
   - The mode radio is `at.sidebar.radio[0]`, not `at.radio[0]`.
   - `radio.set_value(...)` needs the *exact* option string including emoji
     (e.g. `"🔑 Parent"`, not `"Parent"`).
   - Widget indices drift whenever a new widget is inserted earlier in
     render order — re-query `list(tab.selectbox)` / filter by `.label` or
     `.key` before each interaction rather than assuming positional index.
   - A widget's `st.session_state[key]` **cannot be written after that
     widgets's already been instantiated in the same script run** — trying
     to "reset" a widget's value post-submit this way raises
     `StreamlitAPIException`. The fix is a reset-counter baked into the
     widget's `key` (mint a fresh widget next run instead of mutating the
     old one's state).
   - `st.date_input`'s `format` parameter accepts `"YYYY/MM/DD"`,
     `"DD/MM/YYYY"`, or `"MM/DD/YYYY"`, and separators may be swapped for
     `.` or `-` (i.e. `"MM-DD-YYYY"` is valid) — confirmed against the
     installed Streamlit 1.50 via `help(st.date_input)`.
4. **Always clean up test data written to the real `homeschool.db`** after
   an `AppTest` run — this is the family's actual local database, not a
   fixture. `DELETE FROM <table> WHERE <whatever uniquely identifies the
   test row>` after every verification pass. A backlog of ~16 stray test
   rows (fake park/state/city visits) was found and cleaned up mid-session
   from exactly this kind of leftover.

## 10. Notable constants (for quick reference, values may drift — check source)

- `WA_SUBJECTS` — the 11 WA-recognized subject areas tracked for coverage.
- `REQUIRED_HOURS = 1000`, `REQUIRED_DAYS = 180` — WA compliance targets.
- `MAX_ELECTIVES = 2`.
- `WEEKLY_SCHEDULE` — dict of weekday → list of `(subject, start_time,
  end_time)` blocks; this **is** the curriculum schedule.
- `PLANNED_HOURS` — target hours per subject per week, used for the
  planned-vs-actual dashboard chart.
- `ACCOUNT_SERVICES` — the 14 curriculum-linked services needing logins.
- `QUIZ_BANK` — subject → topic → question list (17 topics currently).
- `NPS_REGIONS` — NPS's 12 official DOI Unified Regions.
- `MAP_*` constants — dataviz-palette-derived colors for the travel map.
- `ACCOUNT_SERVICES`, `DEFAULT_ELECTIVE_POOL`, `DEFAULT_BOOK_POOL`,
  `DEFAULT_FUN_PROJECTS`, `DEFAULT_NATIONAL_PARKS`, `DEFAULT_MAJOR_CITIES`
  — seed data, inserted once on first run if the corresponding pool table
  is empty.

## 11. Known open items (as of this doc)

- Parent-mode password bypass is still active for testing (§3) — must be
  turned off before real use.
- `submitted_at`/`finished_at` timestamp columns exist and populate
  correctly but aren't surfaced anywhere in the UI yet (pure backend
  capture) — a natural follow-up would be showing them in the parent
  review queues.
- Check the `enhancements` file at repo root for the live backlog of
  requested-but-not-yet-built features (`---adds---` section) and a log of
  what's already shipped (`---work done---`).
