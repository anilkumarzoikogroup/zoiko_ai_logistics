# Runbook: Freight Overcharge Recovery (SC-001)

**Audience:** On-call engineers, analysts  
**Scope:** End-to-end SC-001 scenario (BlueDart bills ₹12,500, contract ₹8,000, ₹4,500 recovered)

---

## Prerequisites

- PostgreSQL running at `DB_URL` (default: `postgresql://postgres:1234@localhost/zoiko`)
- Phase 2 API running on port 8000
- Phase 3 API running on port 8002 (optional — Phase 2 submit runs inline)
- Phase 4 API running on port 8001
- Active tenant in `tenants` table (`seed_dummy_data.py` if fresh DB)

---

## Step 1 — Submit invoice (Phase 2)

```powershell
$env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
$env:ZOIKO_DEV_MODE = "true"
$env:PYTHONIOENCODING = "utf-8"
cd phase-2; py demo_phase2.py
```

Expected output:
```
[Phase 2] Case opened: <case_id> state=FINDING_GENERATED
```

Note the `case_id` for subsequent steps.

---

## Step 2 — Evidence + token (Phase 3)

```powershell
cd phase-3; py demo_phase3.py
```

Expected output:
```
[Phase 3] Token issued: <token_id> expires_at=<15min TTL>
```

---

## Step 3 — Execute recovery (Phase 4)

```powershell
cd backend\execution; py scripts\demo_phase4.py
```

Expected output:
```
[Phase 4] Execution: DISPATCHED  USD 220.00 credited
[Phase 4] Reconciliation: MATCHED
[Phase 4] ACR issued: <acr_id>  Merkle root: <64-char hex>
```

---

## Step 4 — Verify ACR offline

```bash
python phase-4/services/audit_acr_svc/verifier.py <path-to-acr.json>
# or via the convenience wrapper:
bash verify.sh acr.json
```

Exit code 0 = PASS, exit code 1 = FAIL. The verifier checks:
1. All 8 artifact hashes are SHA-256 hex strings
2. Merkle root recomputation matches the signed root
3. Ed25519 signature over `SHA-256(b"zoiko/v1/acr" + JCS(payload))` verifies

---

## Common Issues

### "No active tenant in DB"
```powershell
cd phase-0; py scripts/seed_dummy_data.py
```

### "Token expired" at Phase 4
The governance token has a 15-minute TTL. Re-run Phase 3 demo to issue a fresh token.

### "Gate 1 (signature_valid) failed"
KMS key not provisioned for this tenant. Run `KeyHierarchy().provision_tenant(tid, slug)` or
check that `ZOIKO_DEV_MODE=true` (dev KMS uses software backend).

### "Gate 3 (not_consumed) failed: Token already consumed (Redis)"
This is the replay-protection gate working correctly. The token was already consumed.
Issue a new token via Phase 3.

### "Gate 6 (sanctions) failed"
Actor or carrier is on the blocked list. Check `SANCTIONS_BLOCKED_ACTORS` env var.
For tests, leave it unset.

### Phase 2 API returns 401
Check that `ZOIKO_DEV_MODE=true` and the JWT is signed with `ZOIKO_DEV_SECRET`.

---

## Monitoring

```powershell
# Live row counts
curl http://localhost:8000/admin/db-stats

# Last 20 Kafka events
curl -H "Authorization: Bearer <jwt>" -H "X-Tenant-ID: <tid>" \
     http://localhost:8000/kafka/events?limit=20

# Case status
curl -H "Authorization: Bearer <jwt>" -H "X-Tenant-ID: <tid>" \
     http://localhost:8000/cases/<case_id>
```

---

## Rollback / Abort

To abort a case before execution:
```sql
UPDATE cases SET state = 'ABORTED' WHERE id = '<case_id>';
INSERT INTO case_events (id, case_id, tenant_id, event_type, actor_sub, payload, created_at)
VALUES (gen_random_uuid(), '<case_id>', '<tid>', 'ABORTED', 'ops-engineer', '{}', NOW());
```

Note: `audit_worm_index` rows cannot be deleted (WORM). Abort is a state transition,
not a data deletion.
