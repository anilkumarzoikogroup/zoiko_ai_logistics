# Audit Report — Database Schema

---

## Stats at a Glance

| What | Count |
|---|---|
| Database migrations | 36 |
| Tables created by migrations | 98 |
| Tables created by app code (not migrations) | 3 |
| Total tables | 101 |
| Tables with security turned on | ~40 |
| Security rules actually written | **0** |

---

## 1. Security Turned On, Rules Missing 🔴 Critical

**Theory:** Imagine a shared office building with 50 companies on different floors. Each floor has its own filing cabinets. The building installed security doors on every floor (RLS enabled). But nobody programmed the door locks — no keycards, no PIN codes. The security doors are permanently locked. Nobody can get in.

**What's happening:** Our database has 40+ tables with `ENABLE ROW LEVEL SECURITY`. This means: "check for a rule before letting anyone read this table." But there are zero rules written. In production (where the app uses a limited-access database user), every SELECT returns nothing. The app shows blank pages.

**Example:** A user logs in, goes to "My Cases." The app runs `SELECT * FROM cases WHERE tenant_id = '...'`. Database says: "RLS is enabled, but there's no policy. Default: block." Returns 0 rows. User sees "No cases found." Admin panics. Everything is fine in dev because dev uses a superuser account that bypasses RLS.

**Why dev is fine vs prod fails:**
- Dev uses the database owner (bypasses RLS entirely)
- Prod uses a limited user (RLS applies → blocks everything)

**Fix:** Write one security rule per table: "Allow access only to rows belonging to your tenant."

---

## 2. Three Tables Not in Migrations 🟠 High

**Theory:** The official blueprints of the building show all rooms. But the building manager built three extra storage closets on their own, without updating the blueprints. If you rebuild from the blueprints, those closets don't exist. You only get them back when the manager shows up and builds them again.

**What's happening:** Three tables (`signup_verification`, `password_reset_otp`, `password_reset_verify`) are created by the application code at startup, not by database migrations. They exist only after the first HTTP request hits the server.

**Example:** A fresh deployment runs all 36 migrations successfully. Health check passes. First user tries to register. The app tries to create these tables — but if the database connection is slow or busy, the creation fails silently (see Audit Report §3.3). User gets "table does not exist." Developers spend hours debugging.

**Fix:** Move these three tables into a proper migration so they exist before the app starts.

---

## 3. Financial Records Can Be Deleted by Accident 🟠 High

**Theory:** Think of a filing system where each case folder is linked to its financial records with a string. The rule says: "If you throw away the case folder, the string pulls the financial records into the trash too." This is fine for shopping carts. It's terrifying for audit records.

**Example:** A developer runs a cleanup script: `DELETE FROM cases WHERE id = 'xyz'`. The database automatically deletes:
1. The case ✅ (intended)
2. All expected recoveries for that case ❌
3. All recovery matches for those recoveries ❌
4. All ledger entries for those matches ❌
5. All write-off records for those entries ❌

Result: ₹4,50,000 of financial audit trail is gone forever. Can never prove the money was recovered.

**Fix:** Change the rule from "delete financial records when case is deleted" to "refuse to delete the case if financial records exist."

---

## 4. Chicken-and-Egg Problem with Finding Revisions 🟡 Medium

**Theory:** Imagine a library where every book has a label saying "This book replaces book #5." Book #5 has a label saying "Replaced by this book." You can't write both labels at the same time because neither book's label makes sense without the other existing first.

**What's happening:** When a "finding" (an AI analysis result) is revised, the new finding says "I replace finding F001" and the old finding says "I am replaced by F002." The database checks: "Does F002 exist?" before allowing F001 to say it's replaced. But you're creating F002 right now — it doesn't exist yet in the database. The operation fails.

**Fix:** Allow the database to check these rules at the end of the transaction, not immediately. That way both labels can be written together.

---

## 5. Missing Indexes — Pages Load Slowly 🟡 Medium

**Theory:** A telephone book has an index (alphabetical order by last name). Without it, to find "Smith" you'd read every single name on every page. An index lets you flip directly to "S."

**What's missing:** Six common lookups have no index:

| What the app needs to find | Like looking up | Without index, reads |
|---|---|---|
| All PENDING cases for my tenant | All "Smith" in a city phonebook | Every single case |
| The AI finding for a case | A person's middle name | Every finding ever made |
| Evidence for a case | Attachments for a specific file | Every evidence record |
| Ledger entries for a case | Bank transactions for one account | Every ledger row |

**Fix:** Add six indexes — like adding alphabetical tabs to a filing cabinet. Queries go from "read everything" to "jump directly to what you need."

---

## 6. Hash Formats  't Match 🟡 Medium

**Theory:** Some employees write dates as `2026-06-16`, others as `June 16, 2026`, others as `16/06/26`. When comparing two documents, you have to convert formats first. If you forget, you miss matches.

**What's happening:** Some tables store hashes (digital fingerprints) as binary (32 bytes), others as text strings (64 characters). Comparing a binary hash to a text hash is like comparing `apples` to `"apples"` — the same thing but in different containers. Joins between these tables can silently fail.

**Fix:** Pick one format and make all tables use it.

---

## 7. Money Columns Use Different Sizes 🟢 Low

**Theory:** One cash register can hold up to ₹99,99,99,99,99,999. Another can only hold ₹99,99,99,99,999. Moving money from the bigger register to the smaller one could overflow it.

**Example:** An invoice of ₹10,00,00,00,00,000 (ten lakh crore) fits in one column but overflows another. Unlikely day-to-day, but possible for enterprise clients.

**Fix:** Make all money columns the same size.

---

## Summary

| Issue | How Bad |
|---|---|
| Security enabled but no rules — production shows empty pages | 🔴 Critical |
| Three tables created by app code, not migrations — breaks fresh deploys | 🟠 High |
| Deleting a case deletes all financial audit records | 🟠 High |
| Chicken-and-egg problem when revising AI findings | 🟡 Medium |
| No indexes on 6 common lookups — pages load slowly | 🟡 Medium |
| Hash fingerprints stored in two different formats | 🟡 Medium |
| Money columns have different size limits | 🟢 Low |
