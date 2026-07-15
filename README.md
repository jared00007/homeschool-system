# Homeschool One-Stop — 8th Grade (Washington DOI)

One app for everything: your son's daily schedule with links,
hour logging with parent approval, grading, and WA compliance tracking.
It now supports a simple cloud-backed deployment while still working locally.

## Folder structure

```
homeschool-system/
├── README.md
├── start-tracker.command       ← double-click to launch (handles setup too)
├── tracker/
│   ├── app.py                  ← the entire app
│   └── requirements.txt
├── curriculum/
│   └── 8th-grade-curriculum-map.md   ← reference copy of the yearly plan
└── resources/
    └── links.md                ← curriculum + WA legal links reference
```

## Launch

Double-click `start-tracker.command`. First run installs dependencies
automatically (takes a minute or two), then the app opens in your browser
at localhost:8501. Every run after that is instant.

(If macOS blocks it: System Settings → Privacy & Security → "Open Anyway",
or run `xattr -d com.apple.quarantine start-tracker.command` in Terminal.)

## How it works

**Two modes, switched in the sidebar:**

### 🎒 Student mode (default — no password)
- **Today tab:** the day's schedule blocks with times, direct links to each
  resource, and a "Done ✔" button per block
- Pressing Done creates a PENDING entry — it does NOT count toward
  compliance hours until a parent approves it
- **My Week tab:** the full weekly schedule with links
- **My Grades tab:** read-only view of his grade averages per subject

### 🔑 Parent mode (password protected)
First time you open Parent mode, you create the password. After that it's
required to unlock. "Lock parent mode" button re-locks it when you walk away.

- **Review & Approve:** every block your son marked done shows here — adjust
  the hours if needed, then Approve (counts) or Reject (sends it back)
- **Manual Log:** add entries directly (field trips, co-op days, catch-up) —
  these are auto-approved since you entered them
- **Grading:** record scores for assignments/quizzes/tests; automatic
  per-subject averages and letter grades (student sees these in his mode)
- **Dashboard:** approved hours vs the 1,000-hour / 180-day WA requirement,
  planned-vs-actual for the current week, hours by subject
- **Coverage:** the 11 WA-required subject areas at a glance
- **Assessments:** log the annual standardized test / evaluator result
- **Export:** CSVs of hours, grades, and assessments — your compliance
  packet and future transcript source data
- **Settings:** change the parent password

## The legal side (don't forget)

- **Sept 15** (or within 2 weeks of term start): file the Declaration of
  Intent with your school district — see resources/links.md for OSPI
- Withdraw him in writing from his prior school if applicable
- **Spring:** one annual assessment; log it in the Assessments tab
- **End of year:** export the CSVs and archive them as that year's packet

## Changing the plan

Schedule times, curriculum links, and weekly hour targets are plain-text
constants near the top of `tracker/app.py` (WEEKLY_SCHEDULE,
CURRICULUM_RESOURCES, PLANNED_HOURS). Edit and relaunch.

## Backup

Everything — hours, grades, assessments, the password — lives in
`tracker/homeschool.db` (created on first run). Copy that one file to
back the whole system up.

## A note on the password

This keeps honest kids honest — it stops your son from approving his own
hours or editing grades through the app. It is not bank-grade security:
anyone with full access to the Mac could open the database file directly.
For this use case (one family, one machine), that's the right trade-off.
