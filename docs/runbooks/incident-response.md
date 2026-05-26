# Runbook: Incident Response

**Audience:** On-call SRE  
**Last updated:** 2025-10-01

---

## P0 — Double Execution (Money Moved Twice)

**Symptoms:** Two execution envelopes for the same token_id.

**Immediate action:**
1. Check Redis: `REDIS-CLI GET zoiko:token:<token_id>` — should return `CONSUMED`.
   If missing, Redis may have been flushed.
2. Check DB: `SELECT status FROM governance_tokens WHERE id = '<token_id>'`
   If `CONSUMED`, the second execution was blocked by DB gate.
3. If two DISPATCHED envelopes exist, escalate to Finance immediately.

**Root cause:** Redis outage between Gate 3 check and token DB update.
The DB `status=CONSUMED` update is the authoritative guard. If both executions
completed, the second one bypassed gate 3.

**Prevention:** Ensure Redis is HA (Redis Sentinel or Cluster in prod). The DB
`status` field is the final backstop.

---

## P1 — Phase 2 API Returning 500

**Symptoms:** All API calls return 500 with `{"error": "INTERNAL_ERROR"}`.

**Steps:**
1. `curl http://localhost:8000/health` — if 500, service is broken at startup.
2. Check logs: `journalctl -u phase2-api --since "5 min ago"` or Docker logs.
3. Common cause: DB_URL wrong or PostgreSQL unreachable.
   Test: `psql $DB_URL -c "SELECT 1"`
4. Common cause: `import paths` path issues. Restart with `PYTHONIOENCODING=utf-8`.

---

## P1 — OPA 503 Storms

**Symptoms:** All API requests return 503 `{"error": "OPA_UNAVAILABLE"}`.

**Steps:**
1. `curl http://$OPA_URL/v1/health` — should return `{"status":"ok"}`.
2. If OPA is down, restart: `docker restart zoiko-opa` or `kubectl rollout restart`.
3. Do NOT set `OPA_URL=""` to bypass — this sets fail-open mode.
4. Check OPA policy loaded: `curl http://$OPA_URL/v1/data/zoiko/freight/allow`
   Should return `{"result": true}` for a valid request.

---

## P2 — Token TTL Expired Before Execution

**Symptoms:** Phase 4 returns 422 `"Gate 2 (not_expired) failed: Token expired Xs ago"`.

**Steps:**
1. Governance tokens expire in 15 minutes after issuance.
2. The analyst or system must re-run Phase 3 to issue a fresh token.
3. Check the case state is still `EXECUTION_READY` before re-issuing.
4. If repeated expiry: increase `TOKEN_TTL_MINUTES` env var (max 60 recommended).

---

## P2 — Merkle Root Mismatch in ACR Verification

**Symptoms:** `verifier.py` exits 1 with "Merkle root mismatch".

**Steps:**
1. Download the ACR bundle: `GET /v1/cases/<case_id>/acr`
2. Run: `python phase-4/services/audit_acr_svc/verifier.py acr.json`
3. Step 2 of verification checks that the recomputed Merkle root matches the signed root.
4. A mismatch means an artifact was tampered with AFTER the ACR was issued.
5. This is a security incident — escalate immediately to InfoSec.

---

## Useful Queries

```sql
-- Cases stuck in APPROVAL_PENDING > 48h
SELECT id, state, opened_at FROM cases
WHERE state = 'APPROVAL_PENDING'
  AND opened_at < NOW() - INTERVAL '48 hours';

-- Unconsumed tokens expiring soon
SELECT id, expires_at FROM governance_tokens
WHERE status = 'ACTIVE'
  AND expires_at < NOW() + INTERVAL '5 minutes';

-- WORM index growth rate
SELECT DATE(created_at), COUNT(*) FROM audit_worm_index
GROUP BY DATE(created_at) ORDER BY 1 DESC LIMIT 7;

-- Outbox relay backlog
SELECT COUNT(*) FROM outbox WHERE published = FALSE;
```
