# Homeschool One-Stop — Product Doc (living document)

This is the product-level companion to `APP_KNOWLEDGE.md` (which is the
technical/architecture reference). This doc tracks **what the product does,
what's being considered next, and where it's headed** — meant to be updated
as features ship, not written once and forgotten.

**How this doc relates to the `enhancements` file**: `enhancements` (repo
root) is the raw, informal intake — quick notes jotted down as ideas come up,
organized loosely into `---ideas---` / `---adds---` / `---removal---` /
`---work done---`. This doc is the organized, standing view built from that
intake: current state in one place, backlog turned into an actual roadmap.
**When a feature ships, update both**: move the line in `enhancements` from
`---adds---` to `---work done---`, and update the relevant sections below.

---

## 1. Product overview

A single-family homeschool operations app for a WA-state 8th grader.
One Streamlit app (`tracker/app.py`) replaces what would otherwise be a
spreadsheet + a folder of bookmarks + a paper log: daily schedule and
curriculum links, hour/day compliance tracking toward WA's 1,000-hour/
180-day requirement, a parent-approval workflow so a kid can't self-certify
his own hours, grading, health check-ins, a travel/geography journal, and
the legal side (Declaration of Intent reminders, annual assessment tracking,
exportable compliance packet).

**Now cloud-hosted.** As of this section, the product runs two ways:
locally (double-click launcher, local SQLite file, the original design),
and as a public Streamlit Community Cloud deployment backed by a Supabase
Postgres database, reachable from any device via a web address. Both are
the same codebase — `tracker/db_backend.py` picks whichever database is
configured; the app itself doesn't know or care which one it's talking to.
See `CLOUD_DEPLOYMENT.md` for setup/troubleshooting and
`LEARNING_GUIDE_TECHNICAL.md` / `LEARNING_GUIDE_SIMPLE.md` for the full
story of how that migration actually went.

Design principles that shape every feature decision here:
- **Local-first, cloud-optional.** The app was built local-only ("nothing
  leaves this machine") and that's still the zero-config default — no
  `DATABASE_URL` set, no cloud involved. The cloud deployment is an
  explicit opt-in on top of the same code, not a replacement for the local
  mode.
- **The student can log things; only the parent can certify them.** Almost
  every student-facing action creates a record a parent reviews, rather
  than something that silently counts.
- **Simple over flexible.** This is built for exactly one family's actual
  workflow, not a general-purpose product — features get built narrow and
  concrete rather than configurable, unless asked otherwise.

## 2. Current feature set

### Daily schedule & hour compliance
- Fixed weekly schedule (subject blocks with times) drives the Today/My
  Week/Calendar views.
- Student taps "Done ✔" on a block → creates a **pending** hour-log entry.
- Parent reviews every pending entry, can adjust hours, then Approve
  (counts toward compliance) or Reject (sends it back).
- Parent can also add hours directly via Manual Log (auto-approved) for
  field trips, co-op days, catch-up work.
- Dashboard: hours/days vs the 1,000-hr/180-day requirement, planned-vs-
  actual for the current week by subject, hours-by-subject chart.

### Grading
- Parent records scores for assignments/quizzes/tests; automatic
  per-subject averages and letter grades.
- Optional photo upload on a grade record, for handwritten/non-digital
  work — paired with a curated list of free printable-worksheet sites
  (Math-Drills, CommonCoreSheets, HomeschoolMath, EnglishLinx, K12Reader,
  ReadWorks).
- Quizzes (in-app, 17 topics across 7 subjects, multiple-choice, auto-
  graded) write straight into the same grade table.
- Student sees a read-only per-subject grade summary.

### Curriculum & content pools
- Electives (pick up to 2, deadline-locked after a parent-set date), a
  reading list, and "fun/enrichment projects" — each backed by a
  parent-managed pool (add/edit/delete) that the student picks from.
- Student can **propose** a new elective/book/project not in the pool;
  parent reviews and either approves (auto-adds to the pool) or rejects
  with a note.
- Static reference view of the typical 8th-grade scope (informational only
  — WA has no state-mandated standards for home-based students).

### Health & wellness check-in
- Daily, separate from academic hour-logging: exercise/water/sleep/
  nutrition toggles, a day-rating and mood-rating emoji scale, a "was
  today's lesson hard?" Y/N + optional notes, and a free-text journal line.
- Parent Dashboard shows a weekly summary.

### Travel Log & geography/writing tie-in
- One unified log for national park visits, state visits, city visits, and
  freeform journal entries — each type asks only for its own relevant
  fields (see `APP_KNOWLEDGE.md` §6 for the exact shape).
- Every entry type supports an optional photo and a one-line
  geography/writing prompt to nudge a real sentence out of the "notes"
  field, not just a location tag.
- National Park entries can mark a Junior Ranger badge earned; a separate
  reference tool looks up a park's real Junior Ranger booklet link.
- A combined map (Plotly `Scattergeo`) shows visited states (2-color
  choropleth), parks (🏔️, colored by NPS region), and cities (📍).
- States/parks/cities are seeded reference pools (63 NPS parks, every
  state capital + a few extras) that a parent can edit via admin panels.

### Accounts & logins
- Checklist of every curriculum-linked service needing a login (14
  services), plus custom accounts (library card, district portal, etc.).
- Credentials stored plain-text on purpose (student needs to read them to
  log in) with an explicit on-screen warning.
- Student can report a broken/dead link from anywhere in the app; parent
  reviews and marks fixed/dismissed with an optional note.

### Legal / WA DOI compliance
- Key-date reminders: Declaration of Intent deadline, annual assessment
  window.
- Assessments tab logs the annual standardized-test or certificated-
  evaluator result required under RCW 28A.200.010.
- Export tab: CSVs of approved hours, grades, and assessments — the actual
  compliance packet / future transcript source data.

### Auth
- Student mode: no password, always available.
- Parent mode: password-gated (hashed+salted), with an explicit lock
  button. Real by default — a prior testing bypass that defaulted this
  open has been fixed (was a live issue once the app got a public URL).

### Deployment (cloud + local)
- Runs locally (SQLite, zero config) or as a public Streamlit Community
  Cloud deployment backed by Supabase Postgres — same code, one
  environment variable (`DATABASE_URL`) decides which.
- A migration script (`tracker/migrate_to_cloud.py`) does a one-time copy
  of existing local data into the cloud database, preserving IDs and
  correctly advancing Postgres's auto-increment sequences afterward so new
  rows don't collide with migrated ones.
- The app shows its actual connected database (and host) directly on-page
  — not just whether cloud config is present, but whether the connection
  actually succeeded.

## 3. Recently shipped (most recent first)

- **Cloud deployment**: the app now runs on Streamlit Community Cloud
  against a Supabase Postgres database, in addition to local SQLite.
  Involved building a backend-agnostic connection layer
  (`tracker/db_backend.py`), fixing a silent connection-failure fallback
  that was masking real errors, translating SQLite-style query
  placeholders to Postgres's for the ~120 queries in the app, replacing
  raw `PRAGMA`/`sqlite_master` schema-introspection calls with
  backend-aware equivalents, resolving a two-entry-point import conflict
  between the local launcher and the Cloud deployment shim, and (found the
  morning after deploying) fixing a gap where `pandas.read_sql()` was
  quietly bypassing the placeholder translation for most of the app's read
  queries. Full story: `LEARNING_GUIDE_TECHNICAL.md` (dev version) /
  `LEARNING_GUIDE_SIMPLE.md` (plain-language version).
- **Full code review pass**: fixed a live security issue (parent-mode
  password lock was defaulting to unlocked — harmless locally, a real
  problem on a public URL), a Postgres correctness bug (a single failed
  query could silently break the app for every user until restart, now
  fixed with automatic rollback), and removed dead code.
- **Repo cleanup**: an entire Python virtual environment (~8,750 files)
  had been committed to git by accident — removed from tracking. Non-
  runtime files (a stale backup, an orphaned prototype, superseded docs)
  moved into a clearly labeled `local-only/` folder instead of cluttering
  the main tree.
- Auto-captured `submitted_at`/`finished_at` datetime stamps on every
  table where the student submits something or marks it done (hour log,
  quizzes/grades, travel entries, link reports, proposals, finished books/
  projects) — backend only, not yet surfaced in the UI.
- App-wide date display standardized to MM-DD-YYYY (storage stays ISO).
- Travel Log consolidated from four separate per-type tables/forms/lists
  into one unified table, one type-conditional form, one combined list.
- Geography/writing prompt captions added to each travel entry type.
- Broken-link reporting (student submits, parent reviews/resolves).
- "Was today's lesson hard?" Y/N + notes added to the daily check-in.
- Photo upload for handwritten graded work + free worksheet-site list.
- Researched Khan Academy API feasibility: no public API exists (program
  discontinued) — not pursued.

Full raw history: `enhancements` file, `---work done---` section.

## 4. Roadmap

### Near-term (from the live backlog — see `enhancements` `---ideas---`)
- **Parent-assigned main project** — a bigger, ongoing project a parent
  hands the student (vs. the student picking from a fun-project pool).
  Needs: is this one persistent project or something that rotates? Does it
  need its own tracking UI or does it fit into the existing fun-project
  pattern?
- **Social/situational awareness content** — the student struggles with
  some social basics; parent wants curriculum content addressing this.
  Needs scoping: is this a new curriculum resource link (like the existing
  `ACCOUNT_SERVICES` ties), a new quiz topic, or something more like a
  dedicated lesson/reading section?

### Plausible next enhancements (not yet requested, worth considering)
- **Move photo uploads to Supabase Storage.** Travel journal photos and
  graded-work photos are still local-disk-only; on the Streamlit Cloud
  deployment specifically, the filesystem is ephemeral, so uploads there
  won't survive a redeploy/restart. This is the most concrete gap left by
  the cloud migration.
- Surface the new `submitted_at`/`finished_at` timestamps somewhere in the
  UI — e.g. next to items in the parent Review & Approve queue, or on
  graded/finished work — now that the data exists.
- Tie travel entries into hour-logging (explicitly deferred earlier —
  "let's not include hours to tie in yet" — revisit once the writing-prompt
  pattern proves out).
- A lightweight per-entry-type filter on the Travel Log's combined list,
  once entry volume grows enough that a flat chronological list gets long.
- Expand the worksheet/printable-resource list beyond Grading (e.g. a
  similar resource list for the 8th Grade Scope reference tab).
- A real automated test suite. Verification so far has been `AppTest`
  scripts run by hand during development, not checked into the repo or
  run in CI — fine for a single-family app iterated on this closely, but
  the first thing that would need to exist before anyone else touches
  this code without the same context.

### Exploratory / long-horizon ideas
- Multi-year view — the app currently centers on "school_year" as a loose
  string field; a proper year-over-year history/transcript view doesn't
  exist yet.
- A simple transcript-generation pass over the Export CSVs, since the
  compliance packet already exists as raw data.
- Revisit whether any curriculum links have gone dead (same mechanism as
  the student-facing broken-link reporter, run periodically by a parent
  instead of relying on the student to notice).

## 5. Known gaps / not yet solved

- **Photo uploads don't survive on the cloud deployment.** Still written
  to local disk (`tracker/uploads/`); Streamlit Community Cloud's
  filesystem is ephemeral, so anything uploaded there is gone on the next
  restart/redeploy. Not an issue for local use. See Roadmap (Supabase
  Storage) for the fix.
- `submitted_at`/`finished_at` fields exist and populate correctly but
  aren't shown anywhere yet (see Roadmap above).
- No automated test suite — verification has been manual (`AppTest`
  scripts run ad hoc during development, not checked into the repo). See
  `APP_KNOWLEDGE.md` §9 for the testing approach used so far.
- Multi-student support exists at the schema level (`students` table) but
  is untested in practice — the app has only ever been used with one real
  student.
- `migrate_to_cloud.py` copies data one-way, local → cloud, and doesn't
  support re-running safely once data already exists on the cloud side
  (it'll hit primary-key conflicts on tables that aren't empty). Fine for
  the one-time initial migration; would need real upsert logic to become
  a repeatable sync.

## 6. Keeping this doc current

Update this file whenever a feature ships or the roadmap shifts:
1. Move the corresponding line in `enhancements` from `---adds---` to
   `---work done---` (with a short "-> what actually got built" note, the
   existing convention in that file).
2. Add a line to §3 (Recently shipped) here.
3. If it fulfilled something in §4 (Roadmap), remove it from there.
4. If the change affects architecture/conventions (new table, new pattern,
   new gotcha), update `APP_KNOWLEDGE.md` too — that file is the technical
   reference and can drift out of sync with the code just as easily as
   this one can.
