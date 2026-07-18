# Setting up a new family (operator checklist)

This is the step-by-step for **you (the operator)** to stand up a fresh,
isolated Compass instance for another household. Each family = its own free
database + its own free web app + its own passcode. Nothing is shared between
families, so their data is completely private from each other.

Time: ~10 minutes. Cost: **$0** on the free tiers.

---

## Before you start
- The code lives on GitHub: `jared00007/homeschool-system`, branch **`compass-v2`**.
- Everything (8th + 9th grade, all upgrades) is already on that branch — a
  fresh deploy gets it all automatically.
- You'll create accounts on two free services: **Neon** (database) and
  **Render** (web hosting). If you already have accounts, just log in.

---

## Step 1 — Create their database (Neon)
1. Go to **neon.tech** and sign in.
2. **New Project.**
   - Name: `compass-<family-name>` (e.g. `compass-smith`). A *separate* project
     per family is what keeps their data isolated.
   - Postgres version: default is fine.
   - **Neon Auth: OFF** (we don't use it).
3. On the "Connect" screen, make sure **Connection string** is selected, click
   **👁 Show password**, then **Copy snippet**.
4. Paste that connection string somewhere safe for a minute — it's the one
   secret you'll need in Step 2. It looks like:
   `postgresql://...@ep-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require`

> ⚠️ Treat this string like a password — it grants full access to their
> database. Never commit it to GitHub or paste it into a chat.

---

## Step 2 — Create their web app (Render)
Use the **manual web-service** route (a second *blueprint* would collide with
your first family's service name).

1. Render → **New + → Web Service.**
2. Connect the repo `jared00007/homeschool-system`, branch **`compass-v2`**.
3. Settings:
   - **Runtime / Language:** Docker (it auto-detects the `Dockerfile`).
   - **Instance type:** **Free**.
   - **Region:** pick one near you (ideally the same region as the Neon project).
4. Under **Environment / Environment Variables**, add two:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from Step 1 |
   | `PARENT_PASSCODE` | a passcode **unique to this family** (not the same as yours) |
5. Click **Create Web Service.** It builds the image (~3–5 min) and goes
   **Live** with a URL like `compass-xxxx.onrender.com`.

---

## Step 3 — Configure it as the parent
1. Open their URL. In the sidebar, expand **🔑 Parent access**, enter the
   passcode you set, and **Unlock**.
2. **➕ Add a student.** Enter the name, **set the grade (8th or 9th)**, and the
   school year (e.g. `2026-2027`).
   - Setting the grade to **9th** is what turns on all the 9th-grade content
     (Algebra, Biology, World History, high-school quests, the 9th scope).
3. (Optional but recommended) walk through **⚙️ Settings**, **📚 Curriculum**
   (pick electives / books), and set the **🎛️ Plan Blender** mix.

---

## Step 4 — Hand it off to the family
Give them exactly three things:
| Item | Value |
|---|---|
| **Parent URL** | `https://compass-xxxx.onrender.com/` |
| **Parent passcode** | the one you set in Step 2 |
| **Student link** | `https://compass-xxxx.onrender.com/?view=student` |

Also send them the **Family Welcome Guide** (`docs/FAMILY_WELCOME_GUIDE.md`, or
the shared link version) — it walks them through everything with no jargon.

---

## Verifying it worked
- The web service in Render shows **Live** with a green dot.
- Open the URL → you see the 🧭 Compass header and "add a student" (or the
  student's name once added).
- In Neon → **Tables**, you should see ~26 tables (accounts, foundations_modules,
  students, log_entries, …). That confirms the app connected to *their* Neon DB.
- Set a student to 9th and open **Today** → the Math block should read
  **"Khan Academy — Algebra 1"** (proof the 9th-grade code is live).

---

## Keeping instances updated
When you push new code to `compass-v2`, each family's Render service needs a
redeploy to pick it up:
- Render → the service → **Manual Deploy → Deploy latest commit.**
- (Or turn on **Auto-Deploy** in the service settings so it redeploys on every
  push automatically.)

Data is safe across redeploys because it lives in Neon, not the container.

---

## Free-tier behavior (set expectations)
- **Cold start:** after ~15 min idle, the first visit takes ~30–60s to wake the
  web service + database, then it's fast. Fine for testing.
- **Always-on:** upgrade the Render web service to **Starter ($7/mo)** to remove
  cold starts.
- **Storage:** Neon free is 0.5 GB. Text data (hours, notes, grades) is tiny and
  fine for years. **Photos** are the exception — see the note in
  `docs/COMPASS_TECHNICAL.md` (photos currently need the object-storage upgrade
  before heavy use).

---

## Cost summary
| | Per family | Two families |
|---|---|---|
| Neon database (free) | $0 | $0 |
| Render web (free) | $0 | $0 |
| **Total** | **$0** | **$0** |

Upgrade levers if you outgrow free: Render Starter web ($7/mo/family) for
always-on; paid Neon only if you exceed 0.5 GB (unlikely on text alone).
