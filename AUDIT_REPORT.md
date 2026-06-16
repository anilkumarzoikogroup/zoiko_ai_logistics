# Audit Report — CORS, Background Tasks & Production Safety

---

## 1. CORS — Who Can Knock on the Door?

**Theory:** CORS is like a nightclub bouncer. A website (say `frontend.com`) tries to call your API (`api.zoiko.com`). The bouncer checks a list: "Is `frontend.com` on the guest list?" If yes, entry allowed. If no, request blocked by the browser.

**We checked four entrances:**

| Entrance (Service) | Bouncer Present? |
|---|---|
| Gateway (port 8000) | ✅ Yes — guest list correct |
| Execution (port 8001) | ✅ Yes — guest list correct |
| API Proxy (port 8080) | ⚠️ Yes, but squinting at names wrong |
| Governance (port 8002) | ❌ No bouncer at all |

**Example — the squinting problem:** The API Proxy reads its guest list from an environment variable. If someone writes `http://site.com, http://other.com` (with a space after the comma), the bouncer sees `" http://other.com"` (space at front). The browser sends `http://other.com` (no space). Bouncer says "names don't match — blocked."

**Example — no bouncer:** Governance has zero CORS setup. Any browser request to it gets silently rejected. If the frontend ever needs data from Governance directly, it fails completely.

**Summary:** Two services fine, one has a typo-level bug, one is missing entirely.

---

## 2. Background Workers — The Night Shift

**Theory:** Some work can't happen during a web request (sending emails, notifying Kafka). You need background workers — like a mailroom clerk who checks the "outgoing" tray every few seconds and processes what's there.

**What we found:**

- **Outbox clerk** — works but runs in only one office (Gateway). If that office closes, mail piles up until it reopens. No backup clerk.
- **Async submit worker** — starts processing a case but if it fails midway, it silently gives up. No second attempt, no alert, no "failed items" bin.

**Example:** A user submits a case. The worker starts. Step 3 of 5 crashes (bad data). Worker logs the error, then... nothing. The case sits in "processing" forever. Nobody knows it failed. No retry happens.

**Summary:** Workers exist but have no safety net — no retries, no backup, no alerts when they fail.

---

## 3. Production Safety — Three Issues

### 3.1 Admin Password in Code

**Theory:** Having the default admin password written in source code is like writing your bank PIN on a sticky note attached to your laptop.

**Example:** An attacker knows the pattern — they try `admin@zoikotech.com` / `Admin@1234` on any Zoiko deployment. It works every time. Full access to every tenant's data.

### 3.2 OTP in Server Logs

**Theory:** When a user requests a password reset, the system sends an OTP via email. It also prints that OTP to the server console/logs.

**Example:** Anyone who has access to the server log files (devops, support staff, or an attacker who breached the server) can see: `"Sending email to user@company.com: Your OTP is 482916"`. They now have the OTP and can reset the user's password.

### 3.3 Errors That Silently Vanish

**Theory:** When the app starts, it tries to set up some database tables. If that fails, the error is caught and... ignored. No log, no alert, no crash. The app starts normally, but the tables don't exist.

**Example:** Deploy happens. Database has a brief connection blip. Table setup fails silently. First user tries to register: "table not found." Debugging takes hours because there's no error trail to follow.

---

## Summary at a Glance

| Issue | What's Wrong | How Bad |
|---|---|---|
| Governance CORS missing | Browser can't talk to this service at all | 🔴 Critical |
| API Proxy CORS whitespace bug | Browser blocked if env var has a space | 🟡 Medium |
| Outbox only runs in Gateway | If Gateway goes down, mail processing stops | 🟡 Medium |
| Async submit has no retry | Failed cases stuck in "processing" forever | 🟡 Medium |
| Admin password in source code | Any attacker can log in as admin | 🔴 Critical |
| OTP printed to logs | Log readers can steal reset codes | 🟠 High |
| Silent error swallowing | Failures happen invisibly — hard to debug | 🟠 High |
