# Passion Track → "Choose Your Adventure" — Build Plan

**Status:** design locked, ready to build.
**Prototypes:** the interactive board + the map-style options (Artifacts, shared
separately). This doc is how the prototype becomes real Compass code.

---

## What we're building

The Passion Track stops being a flat list of matched quests and becomes a
**branching adventure**:

- The student picks a **World** (a themed category — Maker's Forge, Story
  Studio, Field & Lab, Hustle HQ).
- They land on a **node** = one real, detailed assignment (a mission, a
  "what's expected" checklist, and a "turn in" deliverable).
- Finishing a node offers **2–3 branches** — and *each branch is tagged to a
  different school subject*, so the student's own choices spread the week
  across subjects.
- Their path draws a **board-game trail**; a **finale** tallies every subject
  they covered ("look what you learned without opening a textbook").

**Why it fits Compass:** completion still routes through the existing hour-split
engine, so following what's fun *is* what fills the compliance record. Nothing
about the records/approval/export half changes.

### Design decisions (locked)
- Model: Choose-Your-Adventure. Mechanic: Branching Cards. Map: board-game trail.
- Four worlds to start; schema supports **any** number of worlds, nodes, and
  branch depth, so growth is content, not code.
- Each node is a **detailed assignment**: mission + expectations checklist +
  deliverable + time estimate.
- **Expectations are tickable checkboxes** the student checks off; the parent
  sees how many were completed. (Recommended over a static rubric — it's self-
  tracking and reuses the proof-of-work idea.)

---

## Data model

Reuse the existing quest tables — do **not** invent a parallel system. The
quest pool already has almost every field a node needs.

### 1. Extend `fun_project_pool` (the node library)

Current columns: `id, title, subject, description, subjects, steps, mess_level,
est_hours, icon`. The mapping is close already:

| Node concept | Column | Change |
|---|---|---|
| Assignment title | `title` | reuse |
| Subjects (drives hour split) | `subjects` | reuse |
| The mission | `description` | reuse |
| "What's expected" checklist | `steps` | reuse (already newline-separated, already rendered) |
| Time estimate | `est_hours` | reuse |
| Card icon | `icon` | reuse |

Add three columns (all nullable, additive — safe on both SQLite and Postgres):

```sql
ALTER TABLE fun_project_pool ADD COLUMN world TEXT;         -- "Maker's Forge"
ALTER TABLE fun_project_pool ADD COLUMN deliverable TEXT;   -- the "turn in" line
ALTER TABLE fun_project_pool ADD COLUMN branches TEXT;      -- JSON: the forks
```

`branches` is a small JSON array describing the forks out of this node:

```json
[
  {"label": "Double the distance", "teaser": "Re-engineer for 2× range", "to": "f1"},
  {"label": "Slow-mo cinema",      "teaser": "Film + explain the launch", "to": "f2"},
  {"label": "Siege story",         "teaser": "Write the battle it fought", "to": "f3"}
]
```

`to` is a stable node key. Add a `node_key TEXT` column too (e.g. `"f0"`) so
branches can reference nodes independent of the autoincrement `id` — this makes
the seed data portable and editable.

```sql
ALTER TABLE fun_project_pool ADD COLUMN node_key TEXT;      -- "f0", stable ref
```

A node with `branches = "[]"` (or null) is a **leaf** — finishing it ends that
arm of the adventure.

### 2. Track each student's path — extend `student_fun_projects`

This table already tracks a student picking + finishing a quest, with the
idempotent `hours_logged` flag the hour-split relies on. Add:

```sql
ALTER TABLE student_fun_projects ADD COLUMN world TEXT;
ALTER TABLE student_fun_projects ADD COLUMN node_key TEXT;
ALTER TABLE student_fun_projects ADD COLUMN step_index INTEGER;  -- position in the trail (0,1,2…)
ALTER TABLE student_fun_projects ADD COLUMN expects_done TEXT;   -- JSON: which checkboxes are ticked
```

A student's trail in a world = their `student_fun_projects` rows for that
`world`, ordered by `step_index`. The "current node" is the highest
`step_index` that isn't finished. Choosing a branch inserts the next row.

### 3. No new hours logic

Completion continues to call the existing:

```python
finish_fun_project(project_id, student_id, title, subjects_str, est_hours, note)
```

`subjects_str` comes straight off the node, so the branch the kid chose is what
determines the subject split. This is the whole trick and it already works
(verified in the pre-rollout review: even-split across valid WA subjects,
idempotent, invalid-tag fallback to Occupational Education).

---

## Views

### Student — `render_adventure(student_id, school_year)`

Replaces/augments the current `render_fun_projects_picker`. Layout matches the
prototype:

1. **World picker** — buttons from `SELECT DISTINCT world FROM fun_project_pool`.
2. **The board** — SVG board-game trail of the student's path in that world
   (rendered via `components.html`, same pattern the ESA packet already uses).
   Numbered stops, "you are here" ring, finale flag.
3. **The current node's brief** — reuse the comic card look; show:
   - mission (`description`), subject tags (`subjects`),
   - the expectations checklist as real `st.checkbox`es, persisted to
     `expects_done`,
   - the deliverable (`deliverable`) and time (`est_hours`).
4. **Finish + branch** — a "✅ I finished this — here's my proof" note box
   (routes to `finish_fun_project`), then the branch buttons from `branches`.
   Picking one inserts the next `student_fun_projects` row at `step_index+1`.
5. **Finale** — when a leaf node is finished, show the subject tally
   (distinct subjects across the path) and a badge.

Reuse: `render_quest_card` (app.py) for the card, `finish_fun_project`,
`add_entry` (via finish), `setting_get/set`, the `QUEST_*` styling constants.

### Parent — authoring, `render_adventure_admin()`

Extend the existing `render_fun_project_pool_admin` pattern (bespoke CRUD):
- Add `world`, `deliverable`, `node_key`, and a simple **branch editor**
  (pick 0–3 existing nodes in the same world as the forks).
- `subjects` stays a multiselect against `WA_SUBJECTS` — this is what makes the
  branch count toward the right subject.

### Parent — the "metro" path view (Phase D, optional)

The parent-facing read of a kid's finished path as the clean metro-style
diagram from the map prototype: one colored line per world, stations = finished
nodes, interchanges labelled with the subjects crossed. Pure visualization over
`student_fun_projects` — no new data. Doubles as a compliance story ("here's
what one passion actually covered").

---

## Kid-proposed branches (optional, later)

The `proposals` table already lets a student suggest electives/books for parent
review. Extend it with a `prop_type = "adventure_branch"` so a kid can pitch
"I want to take this toward music" — the parent approves it into `branches`.
Keeps the student steering without letting them author unreviewed work.

---

## Phasing

| Phase | Scope | Notes |
|---|---|---|
| **A. Schema + seed** | Add the columns; author the 4 worlds' ~24 nodes as seed data (mission/expectations/deliverable/subjects/branches) | Seed-if-empty guard, same style as existing seeds |
| **B. Student board** | `render_adventure` — world picker, board SVG, node brief with checkboxes, finish→`finish_fun_project`, branch advance, finale tally | The shippable slice; reuses the hour engine |
| **C. Parent authoring** | `render_adventure_admin` with the branch editor | So content isn't code-locked |
| **D. Polish** | Metro parent view, kid-proposed branches, more worlds/depth | Optional |

Phases A+B are the first real, usable version.

---

## Safety / testing (same bar as the pre-rollout review)

- All schema changes are **additive nullable columns** + `CREATE TABLE IF NOT
  EXISTS` — safe to deploy over the live DB, both backends.
- Test against an **isolated copy** of the DB with the AppTest harness: seed →
  render every world → walk a full path → confirm `finish_fun_project` logs the
  right subject split → confirm the finale tally matches the path's subjects.
- Re-run the 30-view render sweep + write-path suite before shipping.
- Never touch a family's live DB during testing.

---

## Effort estimate (rough)

- Phase A (schema + seed content): small code, **most of the work is writing
  good adventures** — the ~24 already drafted in the prototype port directly.
- Phase B (student board + finish/branch wiring): the real engineering, but
  ~70% is reuse (`render_quest_card`, `finish_fun_project`, the SVG board from
  the prototype).
- Phase C (authoring UI): moderate, follows an existing admin pattern.
- Phase D: optional polish.

The risk is low because the hard part — logging correct compliance hours from a
completion — is untouched, already built, and already verified.
