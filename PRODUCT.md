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

The product is now being migrated to a simple cloud-backed architecture so it
can run from a hosted environment while keeping the same core workflow.

Design principles that shape every feature decision here:
- **Nothing leaves this machine.** No cloud, no accounts, no third-party
  API calls except the curriculum links the student clicks out to.
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
  button. *(Currently bypassed for testing — see §5, Known Gaps.)*

## 3. Recently shipped (most recent first)

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
- Surface the new `submitted_at`/`finished_at` timestamps somewhere in the
  UI — e.g. next to items in the parent Review & Approve queue, or on
  graded/finished work — now that the data exists.
- Turn off the parent-mode password bypass before any real use (see §5).
- Tie travel entries into hour-logging (explicitly deferred earlier —
  "let's not include hours to tie in yet" — revisit once the writing-prompt
  pattern proves out).
- A lightweight per-entry-type filter on the Travel Log's combined list,
  once entry volume grows enough that a flat chronological list gets long.
- Expand the worksheet/printable-resource list beyond Grading (e.g. a
  similar resource list for the 8th Grade Scope reference tab).

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

- **Parent-mode password bypass is active for testing** —
  `st.session_state.parent_authed` defaults to `True` at boot. Must be
  flipped back to `False` before real use; currently anyone can open
  Parent mode with no password prompt.
- `submitted_at`/`finished_at` fields exist and populate correctly but
  aren't shown anywhere yet (see Roadmap above).
- No automated test suite — verification has been manual (`AppTest`
  scripts run ad hoc during development, not checked into the repo). See
  `APP_KNOWLEDGE.md` §9 for the testing approach used so far.
- Multi-student support exists at the schema level (`students` table) but
  is untested in practice — the app has only ever been used with one real
  student.

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
