# Compass — Pre-Rollout Code Review & QA Report

**Date:** 2026-07-18
**Scope:** Full review of `tracker/app.py` (~7,200 LOC) + `tracker/db_backend.py`,
plus the hosted deployment config (`Dockerfile`, `render.yaml`).
**Context:** Shipping to a second live household (9th grade) for the 2026–2027
school year. Goal: bullet-proof for real daily use, single family per instance.

---

## Verdict

**Ship-ready after the fixes in this review.** Core business logic (hour
logging, approval, subject-split, the weekly blender, records/export) is
correct and was verified end-to-end. Two significant issues were found and
fixed: one **critical** access-control bug on hosted deployments and one
**high** database-connection leak. Everything else is either fixed, an
accepted design choice, or a documented limitation.

All fixes are committed on branch `compass-v2`. **Each Render service must be
redeployed** to pick them up.

---

## How it was tested

This was not a read-only skim. The app was exercised three ways:

1. **Full render sweep** — all 30 views (14 student + 16 parent) rendered
   under three database states, scanning for exceptions and "nan" leaks:
   - real data,
   - a **NULL-stress DB** (every optional column nulled + NULL-heavy rows
     inserted into the empty display tables),
   - an **empty / brand-new-student DB**.
   Result: **30/30 clean in all three states.**

2. **Write-path suite** — the actual mutation functions were driven against a
   throwaway DB and the resulting rows inspected:
   - schedule block → pending → parent approve → status flips ✓
   - quest completion splits hours evenly across **valid** WA subjects
     (3.0h → two 1.5h rows), is **idempotent** (no double-logging), and an
     invalid subject tag falls back to "Occupational Education" so compliance
     hours are never silently dropped ✓
   - foundations-module completion logs pending hours, idempotent ✓
   - assignment / quiz / travel / feedback inserts land correctly ✓
   - **2-student data isolation**: student B sees none of student A's entries,
     travel, assignments ✓
   - **weekly blender**: 60/40 ratio at a 10h target produced exactly 6.0h
     passion / 4.0h foundations ✓

3. **Helper edge-cases** — 17 unit checks on the NaN-safe helpers
   (`cell`/`num`/`letter_grade`/`format_elapsed`/`fmt_date`) under
   NaN/None/garbage input, plus the photo-storage round-trip (real image,
   non-image, corrupt image, bad references). All pass.

4. **Seed-data audit** — every subject tag in the quest pool and foundations
   modules was checked against `WA_SUBJECTS`; **all valid** (no mis-attributed
   compliance hours).

---

## Findings

### 🔴 CRITICAL — Parent mode could unlock with no passcode on hosted  — FIXED

The Parent/Student gate decided "is this the family's own Mac?" from
`st.context.ip_address`. Behind Render's proxy that value can come back as
`None` or a loopback address, which the code treated as "local" and showed an
**unlocked Parent toggle to anyone — including the student — with no passcode.**
That defeats the entire access model (a kid could approve their own hours, edit
curriculum, read everything).

**Fix:** the "local" shortcut is now only trusted on the local SQLite backend.
Any hosted deploy (Postgres backend) always falls through to the passcode gate,
regardless of what IP the proxy reports. Fail-safe unchanged: no passcode
configured = student-only.

> **Operator action:** make sure `PARENT_PASSCODE` is set on every Render
> service. With this fix, a hosted instance with no passcode is student-only
> (safe), so a missing passcode now locks *you* out rather than letting the kid
> in — set it.

### 🟠 HIGH — Database connection leak on every interaction  — FIXED

`get_conn()` ran at module scope, and Streamlit re-executes the whole script on
every click. With no caching, a **new SQLAlchemy engine + pool (and a fresh
Postgres connection) was created on every single interaction**, accumulating
connections against Neon's free-tier limit until the app would hang or error.
(The code comments show this class of problem — "exhausted the pool" — had bitten
before.)

**Fix:** `get_conn()` is now `@st.cache_resource` — one connection pool per
process, shared across all reruns and sessions. `pool_pre_ping` (already
configured) transparently reconnects after Neon idle-closes the socket during
the free tier's sleep/wake, so this also makes cold-starts more robust.

### 🟡 LOW — `int(badge_earned)` could crash a travel insert  — FIXED

A `None` passed as the travel "badge earned" flag would raise. All current
callers pass a bool, but it's now `int(bool(...))` defensively.

### Earlier in this review cycle (all FIXED, verified)

- **Grading view crash** on any assignment with a NULL score/max_score
  (object-dtype broke `.round()`) — now coerces numerically, treats 0-max as
  N/A, grades show "—".
- **~20 latent NaN-truthy bugs** of the form `x or default` (NaN is truthy, so
  it returned NaN, not the default): `est_hours` math, `.split()` on NULL DB
  text (would have *crashed* — floats have no `.split`), and cosmetic "nan"
  leaks including in the ESA records packet ("nan/nan (nan%)" → "—").
- **Divide-by-zero / empty-DataFrame** guards on quiz scoring, park lookups,
  and progress bars.
- Dead `UPLOADS_BASE` constant removed after the photo→Postgres migration.

---

## Accepted design choices / known limitations (not bugs)

These are intentional for a single-family testing tool and are called out for
transparency, not as action items.

| # | Item | Why it's acceptable | Note |
|---|------|--------------------|------|
| 1 | **Site passwords stored & shown in plaintext** on the kid's *My Logins* tab | Kids need to log into Khan/CommonLit/etc. themselves; documented in the family guide | Don't reuse an important password for a learning-site account |
| 2 | **Feedback reader is instance-global** (shows all students' testing feedback) | It's a temporary testing tool; single family | Remove before any real multi-family use |
| 3 | **Siblings share the student picker in student mode** — a kid could switch to a sibling's view | Same household, parent-managed | If a private journal matters, consider per-kid locking later |
| 4 | **Passcode has no rate-limiting / not constant-time** | Threat model is one kid guessing on a family instance, not the internet | Fine at this scale |
| 5 | **One instance per family** (no shared multi-tenant DB) | This *is* the isolation model — physically separate DBs | Multi-tenant is a separate, larger build |
| 6 | **Free-tier cold start ~30–60s** after 15 min idle | Zero-cost hosting trade-off; documented for families | Upgrade Render to `starter` ($7/mo) to stay always-on |

---

## Pre-launch checklist (operator)

- [ ] **Redeploy every Render service** so the fixes above are live.
- [ ] Confirm `PARENT_PASSCODE` **and** `DATABASE_URL` are set on each service.
- [ ] Open each instance's parent link, unlock with the passcode, confirm the
      Parent toggle does **not** appear without it (verifies the critical fix).
- [ ] Add the student, set their grade, and generate their first week.
- [ ] Do one full loop on a phone: kid marks a block done → parent approves →
      hours show on the Dashboard.
- [ ] Send each family their student link + passcode.

---

## Bottom line

The parts that matter for a homeschool compliance record — hours, subject
attribution, approval, and the records/ESA export — are **correct and tested**.
The two real risks (an open parent door on hosting, and a connection leak that
would take the app down under normal use) are **fixed**. With a redeploy and the
checklist above, this is ready for the school year.
