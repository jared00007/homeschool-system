# How we moved this app to the cloud — plain-language version

## What we did

Your homeschool app used to live only on your Mac — the schedule, hours,
grades, everything was stored in one file on your computer. We moved the
data to a cloud database (a service called Supabase) and the app itself to
a cloud host (Streamlit Community Cloud), so now it's reachable from a
web address instead of only working when you're sitting at that specific
computer.

Nothing about how the app *looks or works* changed — same tabs, same
buttons, same features. What changed is *where the data lives* and *how
you get to the app*.

## Why

The app tied to one Mac meant: only usable at home, on that machine, and
if that computer ever had a problem, so did years of homeschool records.
Moving the data to a proper cloud database and putting the app on a public
web address fixes both — it's reachable from any device, and the data
lives somewhere professionally maintained and backed up, not just on one
laptop.

## The pieces, in plain terms

- **GitHub** — think of this as the app's source code living in a shared,
  versioned filing cabinet. It's what the hosting service actually reads
  from to run the app.
- **Supabase** — the actual database, now living on a server somewhere
  instead of on your Mac. This is where every hour logged, every grade,
  every travel entry actually gets stored.
- **Streamlit Community Cloud** — the service that keeps the app itself
  running and gives it a real web address anyone with the link can open.

## What actually happened getting this working (the honest version)

This wasn't a flip-a-switch move — getting a local-only app talking to a
real cloud database took several rounds of "deploy it, see what breaks,
fix that specific thing." None of it was wasted effort; each round found
something real. In order:

1. **The app could talk to the cloud database, but wasn't actually saying
   anything to it correctly.** Think of it like the app and the cloud
   database spoke two dialects of the same language — most words matched,
   but a handful didn't, so a lot of what the app tried to say came out
   as gibberish. We built a translator that sits between them so the app
   never has to think about which dialect it's speaking.

2. **When the cloud connection failed, the app was quietly pretending
   everything was fine** by falling back to a temporary, empty local
   database instead of telling anyone something was wrong. That's exactly
   backwards for troubleshooting — we changed it so a real connection
   problem now shows a clear error explaining what went wrong, instead of
   hiding it.

3. **The app needed to work two different ways** — one for when you
   double-click the launcher on your Mac, and a different one for how the
   cloud service starts it up. It took a couple of tries to find a version
   that worked both ways at once (the first attempt fixed one and broke
   the other).

4. **Supabase gives you two different addresses for the database, and we
   were using the wrong one.** One only works from certain networks; the
   other works from anywhere. Once we switched to the right one, the
   connection itself started working.

5. **The password ran into a copy-paste snag.** Supabase's website shows
   you a template with placeholder brackets around where your password
   goes, and some of that placeholder text accidentally stayed mixed in
   with the real password. We reset it to a fresh, simple password (just
   letters and numbers, nothing that could get mangled) and that cleared
   it up.

6. **Moving your existing data over needed one more safeguard** so that
   new entries you add going forward don't accidentally clash with the
   older data that got copied in. That's now handled automatically as
   part of the one-time data-copy step.
7. **The translator from step 1 turned out to have a gap** — found the
   morning after everything else shipped, when the live app actually
   crashed loading your accounts page. One particular way the app fetches
   data was quietly skipping the translator entirely, so some pages worked
   and others didn't. Fixed the same day, and moved the fix to a spot in
   the code that nothing can accidentally skip going forward.

## A security fix worth knowing about

While reviewing everything, we found that the "Parent mode" password lock
had been left in a testing mode where it didn't actually require a
password — that was fine while the app only ran on your own Mac, but once
it had a real public web address, it meant *anyone* with the link could
open Parent mode with no password at all. That's fixed now — the next
time you (or anyone) opens Parent mode, it'll ask you to set a password,
same as it's supposed to.

## What to expect now

- The app works the same as before — same tabs, same features.
- Data now lives in the cloud database, not just on your Mac.
- You (or your son) can reach it from any device via the app's web
  address, not just the computer it used to run on.
- Running it locally via the double-click launcher still works too, and
  still uses a local copy of the data by default — the two aren't mixed
  together automatically. If you want your Mac and the cloud version
  looking at the exact same data, that's a small extra setup step
  described in `CLOUD_DEPLOYMENT.md`.
- One thing not yet moved to the cloud: **photos** uploaded in the app
  (travel journal pictures, photos of graded handwritten work). Those
  still only live on whichever computer they were uploaded from, and on
  the cloud host specifically they won't survive a restart yet. That's a
  known next step, not something broken — see `PRODUCT.md` for what's
  planned.

## Where to look next

- `CLOUD_DEPLOYMENT.md` — step-by-step setup and troubleshooting if
  something about the cloud connection ever needs revisiting.
- `PRODUCT.md` — the running list of what the app does today and what's
  planned next.
- `LEARNING_GUIDE_TECHNICAL.md` — the same story as this doc, but written
  for a developer picking up the code.
