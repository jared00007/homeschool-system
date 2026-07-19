# Keeping AI Out of Schoolwork — Device & Network Setup

**For:** the homeschool parent/operator.
**Time:** ~45–60 min, one time. Then it runs itself for the school year.
**What this does:** actually *blocks* AI chatbots on the kid's devices and your
home network — as opposed to the in-app signals, which only *flag* cheating
after it happens. This is the lock. Build it first.

> **Why this layer and not just the app?** Compass runs in a browser tab, and a
> browser tab can't police the *other* tab or the phone in a pocket. Blocking has
> to happen at the device and network level — the two places you fully control
> because you own the hardware. Do this once and casual cheating mostly just
> stops; the app's job then shrinks to catching the determined edge cases.

---

## The 2-layer model (do both — they cover each other's gaps)

| Layer | Covers | Gap it leaves | Closed by |
|---|---|---|---|
| **Device** (Screen Time / Family Link) | That one device, **everywhere** — home wifi *and* cellular | A different, unmanaged device | You managing every device the kid uses |
| **Network** (NextDNS) | **Every** device on your home wifi, even guests | Cellular data; DoH browser bypass | Device layer + the DoH note below |

Device layer = the kid's own laptop & phone, everywhere. Network layer = a
backstop for anything else that touches your wifi. You want both.

---

## Layer 1 — Device (Apple Screen Time)

*For Mac / iPad / iPhone. Google users skip to Layer 1-B.*

1. On the kid's device: **Settings → Screen Time → turn on.**
2. **Set a Screen Time passcode the kid does NOT know** (different from the
   device unlock code). Use "Lock Screen Time Settings." This is what stops them
   undoing everything below.
   - Best practice: make the kid's device a **child Apple ID in Family Sharing**,
     so you manage it from *your* phone and they can't touch the controls.
3. **Content & Privacy Restrictions → turn on.**
4. **Content Restrictions → Web Content:**
   - **Strict (recommended for school hours):** choose **"Allowed Websites Only"**
     and add just the sites they need (Khan Academy, CommonLit, Google Docs,
     Compass, etc.). Everything else — including every AI site — is blocked by
     default. This is the strongest option and the easiest to maintain.
   - **Looser:** keep "Limit Adult Websites" and add each AI domain (list below)
     to the **"Never Allow"** list. Works, but you're playing whack-a-mole as new
     tools launch.
5. **Block new browser installs.** Content & Privacy → App Store → don't allow
   installing apps (or require your approval). Otherwise they install Firefox and
   walk around Safari's rules.
6. **Downtime** (optional): schedule non-school apps off during school hours.

### Layer 1-B — Device (Google Family Link, for Android / Chromebook / Chrome)

1. Install **Family Link**, link the kid's Google account as a child account.
2. **Controls → Content restrictions → Google Chrome → "Only allow approved
   sites"** (strict) *or* **"Try to block explicit sites" + Manage sites →
   Blocked** and add the AI domains.
3. **Controls → Apps →** require your approval for new installs (stops them
   installing another browser).
4. Set a **school-hours schedule** under screen-time limits.

**Effort:** 20–30 min per device. **Undo-proof:** yes, behind your passcode.

---

## Layer 2 — Network (NextDNS — free)

This blocks AI on **every device on your wifi**, as a backstop.

1. Make a free account at **nextdns.io** → you get a config with an ID.
2. **Security tab:** turn on the threat-intelligence feeds.
3. **Denylist tab:** paste the AI domains (list below).
4. **Point your devices (or whole router) at NextDNS:**
   - **Easiest & strongest:** install the **NextDNS app / configuration profile**
     on each device. This forces *all* DNS — including browsers' encrypted DNS —
     through NextDNS, so it can't be walked around. (On iOS it installs a
     configuration profile; lock its removal in Screen Time → Content & Privacy →
     don't allow changes to VPN/DNS.)
   - **Whole-house:** set your **router's DNS** to the NextDNS servers. Covers
     everything at once, but see the DoH note below.

### ⚠️ The one gotcha: browser "Secure DNS" (DoH)

Modern Chrome/Safari can send DNS **encrypted straight past your router**, which
would skip a router-only NextDNS. Two fixes, either works:
- Use the **NextDNS device profile** (above) — it captures DoH too. *Preferred.*
- Or turn off "Secure DNS" in the browser and lock settings via the device layer.

**Effort:** 30–45 min one time.

---

## The AI blocklist (copy-paste into Screen Time "Never Allow" or NextDNS denylist)

```
chatgpt.com
chat.openai.com
openai.com
claude.ai
gemini.google.com
bard.google.com
copilot.microsoft.com
bing.com/chat
perplexity.ai
character.ai
poe.com
you.com
deepseek.com
chat.deepseek.com
huggingface.co
pi.ai
meta.ai
grok.com
x.ai
chatsonic.com
jasper.ai
quillbot.com
caktus.ai
```

> This list needs a refresh every couple of months — new tools launch. The
> "Allowed Websites Only" approach (Layer 1, strict) sidesteps this entirely,
> which is why it's the recommended one.
>
> Note a few dual-use ones: `quillbot.com`/`caktus.ai` are essay-writers worth
> blocking; leave `huggingface.co` off if the kid legitimately uses it for a
> coding elective.

---

## Prove it works (5-minute test)

On the kid's device, **during school hours**, try to open `chatgpt.com` and
`gemini.google.com`. Both should fail to load. Then try on their **phone on wifi**
(network layer) and their **phone on cellular** (device layer). If cellular still
loads AI, your device-layer rules on that phone aren't on — fix that; cellular is
device-layer's job.

---

## Known bypasses — accept these up front

No setup is airtight. The realistic holes:
- A **second, unmanaged device** on cellular (a friend's phone, an old tablet).
- **Screenshots** of a problem sent to another device.
- A **VPN** (block VPN app installs at the device layer).

The goal isn't a perfect wall — it's to make the honest path easier than the
dishonest one, and to make the remaining attempts *visible*. That's where the
in-app integrity signals come in as the second half.

---

## The part no setting can do

The strongest anti-cheat is the conversation: *why* the work matters, and that
using AI to skip the thinking mostly cheats **them**, not you. Tell the kid the
blocks exist and why — a visible, explained boundary lands better than a secret
one they discover and treat as a game to beat. Pair the lock with the reason for
it.
