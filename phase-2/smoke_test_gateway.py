"""
API Gateway smoke test — run directly:  python smoke_test_gateway.py

Hits all 6 routes in sequence and prints a pass/fail summary.
No pytest required. Uses FastAPI TestClient (no server needed).
"""
import sys, os, uuid
from dotenv import load_dotenv

import paths  # noqa: F401

load_dotenv()

from fastapi.testclient import TestClient
from middleware.oidc.token_verifier import TokenVerifier

# ── Config ────────────────────────────────────────────────────────────────────

DEV_SECRET = os.getenv("ZOIKO_DEV_SECRET").encode()
ISSUER     = os.getenv("ZOIKO_ISSUER",     "https://auth.zoikotech.com")
DB_URL     = os.getenv("DB_URL")

_minter    = TokenVerifier(dev_secret=DEV_SECRET, issuer=ISSUER)

# ── Helpers ───────────────────────────────────────────────────────────────────

results = []

def check(label: str, condition: bool, detail: str = ""):
    icon = "PASS" if condition else "FAIL"
    print(f"  [{icon}]  {label}" + (f"  ->  {detail}" if detail else ""))
    results.append((label, condition))

def _headers(tenant_id: str, with_idem: bool = False) -> dict:
    token = _minter.make_dev_token(sub="smoke-test-user", tenant_id=tenant_id)
    h = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID":   tenant_id,
    }
    if with_idem:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h

def _get_tenant() -> dict:
    """Fetch first active tenant from DB."""
    import psycopg2, psycopg2.extras
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=3)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, slug FROM tenants WHERE status='ACTIVE' ORDER BY created_at LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return {"id": str(row["id"]), "slug": row["slug"]} if row else None
    except Exception as e:
        print(f"  DB error: {e}")
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

print("\n=== Zoiko API Gateway — Smoke Test ===\n")

# ── Step 0: Import app ────────────────────────────────────────────────────────
print("[0] Loading app...")
try:
    from services.api_gateway.app import app
    client = TestClient(app, raise_server_exceptions=False)
    check("App imported OK", True)
except Exception as e:
    check("App imported OK", False, str(e))
    sys.exit(1)

# ── Step 1: Health ────────────────────────────────────────────────────────────
print("\n[1] GET /health")
r = client.get("/health")
check("HTTP 200",            r.status_code == 200, f"got {r.status_code}")
check("status == 'ok'",      r.json().get("status") == "ok")
check("service == 'api-gateway'", r.json().get("service") == "api-gateway")

# ── Step 2: Auth guard ────────────────────────────────────────────────────────
print("\n[2] Auth guard")
fake_tid = str(uuid.uuid4())
# No token
r = client.post("/invoices", json={
    "carrier_id": "X", "invoice_number": "X", "total_amount": 1.0,
    "currency": "USD", "route_origin": "A", "route_destination": "B",
}, headers={"X-Tenant-ID": fake_tid, "Idempotency-Key": str(uuid.uuid4())})
check("No token → 401/403",  r.status_code in (401, 403, 422), f"got {r.status_code}")

# Bad token
r = client.post("/invoices", json={
    "carrier_id": "X", "invoice_number": "X", "total_amount": 1.0,
    "currency": "USD", "route_origin": "A", "route_destination": "B",
}, headers={"Authorization": "Bearer bad.token.here", "X-Tenant-ID": fake_tid,
            "Idempotency-Key": str(uuid.uuid4())})
check("Bad token → 401",     r.status_code == 401, f"got {r.status_code}")

# Tenant mismatch
good_token = _minter.make_dev_token(sub="x", tenant_id=fake_tid)
r = client.post("/invoices", json={
    "carrier_id": "X", "invoice_number": "X", "total_amount": 1.0,
    "currency": "USD", "route_origin": "A", "route_destination": "B",
}, headers={"Authorization": f"Bearer {good_token}",
            "X-Tenant-ID": str(uuid.uuid4()),   # different from JWT
            "Idempotency-Key": str(uuid.uuid4())})
check("Tenant mismatch → 403", r.status_code == 403, f"got {r.status_code}")

# ── Step 3: Get tenant from DB ────────────────────────────────────────────────
print("\n[3] Resolve tenant")
tenant = _get_tenant()
if not tenant:
    print("  No active tenant — skipping DB integration steps.")
    print("  Run: python phase-0/seed_dummy_data.py\n")
else:
    tid    = tenant["id"]
    print(f"  tenant_id = {tid}  slug = {tenant['slug']}")

    inv_no  = f"SMOKE-{uuid.uuid4().hex[:8].upper()}"
    carrier = f"DHL-{uuid.uuid4().hex[:6]}"

    # ── Step 4: Ingest ────────────────────────────────────────────────────────
    print("\n[4] POST /invoices  (ingest)")
    r = client.post("/invoices", json={
        "carrier_id":        carrier,
        "invoice_number":    inv_no,
        "total_amount":      220.0,
        "currency":          "USD",
        "route_origin":      "Dallas",
        "route_destination": "Chicago",
        "weight_lbs":        100.0,
    }, headers=_headers(tid, with_idem=True))
    check("HTTP 201",                  r.status_code == 201, f"got {r.status_code}  {r.text[:120]}")
    src_id = r.json().get("source_record_id", "")
    check("source_record_id present",  bool(src_id))
    check("canonical_hash is 64 hex",  len(r.json().get("canonical_hash", "")) == 64)
    check("tenant_id matches",         r.json().get("tenant_id") == tid)

    # Idempotency: second call with same key returns same record
    ikey = str(uuid.uuid4())
    inv_no2 = f"SMOKE-IDEM-{uuid.uuid4().hex[:6].upper()}"
    h2 = {**_headers(tid), "Idempotency-Key": ikey}
    pl = {"carrier_id": carrier, "invoice_number": inv_no2, "total_amount": 50.0,
          "currency": "USD", "route_origin": "X", "route_destination": "Y"}
    r1 = client.post("/invoices", json=pl, headers=h2)
    r2 = client.post("/invoices", json=pl, headers=h2)
    check("Idempotent (same key → same record)",
          r1.status_code == 201 and r2.json()["source_record_id"] == r1.json()["source_record_id"])

    # ── Step 5: Validate ──────────────────────────────────────────────────────
    print("\n[5] POST /invoices/{id}/validate")
    r = client.post(f"/invoices/{src_id}/validate", json={
        "invoice_number": inv_no,
        "carrier_id":     carrier,
        "total_amount":   220.0,
        "currency":       "USD",
    }, headers=_headers(tid))
    check("HTTP 200",              r.status_code == 200, f"got {r.status_code}  {r.text[:120]}")
    check("status in PASS/WARN/FAIL", r.json().get("status") in ("PASS", "WARN", "FAIL"))
    check("validation_id present", bool(r.json().get("validation_id")))
    print(f"     status={r.json().get('status')}  overcharge={r.json().get('overcharge_amount')}")

    # ── Step 6: Canonicalize ──────────────────────────────────────────────────
    print("\n[6] POST /invoices/{id}/canonicalize")
    r = client.post(f"/invoices/{src_id}/canonicalize", json={
        "invoice_number": inv_no,
        "carrier_id":     carrier,
        "total_amount":   220.0,
        "currency":       "USD",
        "origin_city":    "Dallas",
        "dest_city":      "Chicago",
        "weight_lbs":     100.0,
    }, headers=_headers(tid))
    check("HTTP 200",                    r.status_code == 200, f"got {r.status_code}  {r.text[:120]}")
    canonical_id = r.json().get("canonical_invoice_id", "")
    check("canonical_invoice_id present", bool(canonical_id))
    check("canonical_hash is 64 hex",    len(r.json().get("canonical_hash", "")) == 64)
    check("invoice_number echoed back",  r.json().get("invoice_number") == inv_no)

    # ── Step 7: Open case ─────────────────────────────────────────────────────
    print("\n[7] POST /cases  (open case)")
    r = client.post("/cases", json={"canonical_invoice_id": canonical_id},
                    headers=_headers(tid))
    check("HTTP 201",            r.status_code == 201, f"got {r.status_code}  {r.text[:120]}")
    case_id = r.json().get("case_id", "")
    check("case_id present",     bool(case_id))
    check("state == 'OPENED'",   r.json().get("state") == "OPENED")
    check("is_new == True",      r.json().get("is_new") is True)

    # Idempotent re-open
    r2 = client.post("/cases", json={"canonical_invoice_id": canonical_id},
                     headers=_headers(tid))
    check("Re-open same invoice → same case_id",
          r2.json().get("case_id") == case_id)

    # ── Step 8: Transition ────────────────────────────────────────────────────
    print("\n[8] PATCH /cases/{id}/state")
    r = client.patch(f"/cases/{case_id}/state", json={
        "new_state": "EVIDENCE_GATHERING",
        "actor_sub": "smoke-test-user",
        "payload":   {"note": "smoke test transition"},
    }, headers=_headers(tid))
    check("HTTP 200",                          r.status_code == 200, f"got {r.status_code}  {r.text[:120]}")
    check("new_state == EVIDENCE_GATHERING",   r.json().get("new_state") == "EVIDENCE_GATHERING")
    check("case_id echoed back",               r.json().get("case_id") == case_id)

    # Invalid transition
    r_bad = client.patch(f"/cases/{case_id}/state", json={
        "new_state": "APPROVED",   # can't jump from EVIDENCE_GATHERING → APPROVED
        "actor_sub": "smoke-test-user",
        "payload":   {},
    }, headers=_headers(tid))
    check("Invalid transition → 422",          r_bad.status_code == 422, f"got {r_bad.status_code}")

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"\n{'='*40}")
print(f"  {passed}/{total} checks passed")
if passed == total:
    print("  ALL SMOKE TESTS PASSED ✓")
else:
    failed = [name for name, ok in results if not ok]
    print(f"  FAILED: {failed}")
print(f"{'='*40}\n")
sys.exit(0 if passed == total else 1)
