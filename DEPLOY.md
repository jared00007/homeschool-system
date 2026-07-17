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

The current `render.yaml` is the **free** setup: a free Render web service +
an external **free Neon Postgres** you paste in. ~$0 per household.

### Per household (repeat for each family)

1. **Free database (Neon).** Go to neon.tech → sign up (free) → **New
   Project** (name it e.g. `compass-<family>`). Copy the **pooled** connection
   string it shows — looks like
   `postgresql://<user>:<pass>@ep-xxx-pooler.<region>.aws.neon.tech/<db>?sslmode=require`.
   The app requires SSL, and Neon strings already include `sslmode=require`.
2. **Free web (Render).** Render → **New +** → **Blueprint** → pick the repo,
   branch `compass-v2`. It reads `render.yaml` and creates one free web
   service (no paid database — that's the change from the old blueprint).
3. Set the two env vars on the service:
   - `DATABASE_URL` = the Neon string from step 1.
   - `PARENT_PASSCODE` = this family's parent unlock code.
4. Deploy. On first visit the app creates its tables in the Neon DB and seeds
   Foundations/Smithsonian/quests. **Verified working against real Postgres.**
5. Give the family: their Render URL, their passcode, and the student link
   `https://<their-url>/?view=student`.

Each family = its own Neon project + its own Render service = fully isolated,
~$0. Free tiers sleep/suspend when idle (Render web ~15 min, Neon after a
while) — the first visit after a quiet stretch takes ~30–60s to wake, then
it's normal. Fine for testing; bump the Render web to `starter` ($7/mo) for
always-on, or keep Neon and pay only if you outgrow the free tier.

### Bringing local data across (optional)

`cloud-archive/migrate_to_cloud.py` copies a local SQLite DB into Postgres —
point its `DATABASE_URL` at the Neon string. A fresh hosted DB works fine and
just starts empty, which is what you want for a new family anyway.

## Railway / Fly.io

Same idea, no blueprint file needed: both build the `Dockerfile` directly.
Provision (or point at) a Postgres, set `DATABASE_URL` and `PARENT_PASSCODE`
in the service env, deploy.

## Local Docker smoke test

```
docker build -t compass .
docker run -p 8501:8501 -e PARENT_PASSCODE=test compass
# open http://localhost:8501 — with no DATABASE_URL it runs on an in-container
# SQLite file (ephemeral), which is fine for a build check.
```

## Two households (prod testing) — one instance per family

Compass is single-tenant, so **each household gets its own instance with its
own database**. This is the recommended path for the current "my house + one
other house" testing: data isolation is physical (separate Postgres per
family — House B literally cannot see House A's kid), and it needs zero new
code. Graduate to real multi-tenant signup later, when there are more families
than instances are worth managing.

Do the Render steps above **once per household**, changing three things each
time so the two don't collide:

| | House A | House B |
|---|---|---|
| Web service `name` | `compass-a` | `compass-b` |
| Database `name` | `compass-a-db` | `compass-b-db` |
| `PARENT_PASSCODE` | A's code | B's code |

Two ways to create the second one:
- **Simplest:** in Render, **New + → Web Service → Docker**, point at the same
  GitHub repo, add a Postgres from **New + → Postgres**, and set that service's
  `DATABASE_URL` + `PARENT_PASSCODE` by hand. (Blueprints key on the names in
  `render.yaml`, so a second blueprint from the same file would clash — the
  manual route avoids that.)
- Or keep a copy of `render.yaml` per household with the names above and deploy
  each as its own blueprint.

Each family then self-serves inside their own instance:
1. Parent opens the URL, unlocks with the passcode you set, and adds their
   student(s) — **setting each kid's grade (8th/9th) in the add form or in
   Settings**.
2. The parent hands their kid the **student link**: `https://<their-url>/?view=student`.
3. The parent can change their own passcode any time in **Parent → Settings**
   (that overrides the deploy-time `PARENT_PASSCODE`).

**What to give the other household:** just their URL, their parent passcode,
and the `/?view=student` link for the kid. Nothing else.

## Notes / next step

The `PARENT_PASSCODE` gate is a household unlock, **not** real multi-user auth —
don't treat it as such, and don't put more than one family on a single
instance. Real per-family accounts (signup, login, row-level isolation) and
billing are the next build when the instance-per-family model stops scaling.
