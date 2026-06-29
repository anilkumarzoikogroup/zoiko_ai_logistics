#!/usr/bin/env python3
"""
seed_all_slices.py  —  Populate demo data for all 5 Zoiko AI Logistics slices.

Run WHILE all backends are live (launch.bat).

Usage:
    python seed_all_slices.py

Seeds:
  SC-001  4 invoice overcharge cases (BlueDart, DHL, Delhivery, FedEx)
          2 of them advanced through governance (APPROVAL_PENDING / EXECUTION_READY)
  SC-002  3 carrier claims (DAMAGE, LOSS, DELAY)
  SC-003  3 SLA breach exceptions (BlueDart, Delhivery, Ekart)
  SC-004  3 supplier scorecards (breach triggered)
  SC-005  3 accessorial charge disputes (multi-line)
"""

import uuid, sys, time
import requests
from datetime import datetime, timedelta, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
TENANT_ID = "f5f3c9a1-facd-438f-b24f-3bfd63013536"   # resolved from /auth/login at startup

GW001 = "http://localhost:8000"
GW002 = "http://localhost:8010"
GW003 = "http://localhost:8020"
GW004 = "http://localhost:8030"
GW005 = "http://localhost:8040"

SESSION_TIMEOUT = 30   # seconds per HTTP call
POLL_TIMEOUT    = 25   # seconds to wait for FINDING_GENERATED


# ── Helpers ────────────────────────────────────────────────────────────────────

def url(base: str, path: str) -> str:
    return f"{base}/v1{path}"


def get_token(email: str, password: str) -> tuple[str, str]:
    """Login via /auth/login (JWT is in Set-Cookie). Returns (jwt, tenant_id)."""
    import re
    r = requests.post(
        f"{GW001}/auth/login",
        json={"email": email, "password": password},
        timeout=8,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    cookie = r.headers.get("set-cookie", "")
    m = re.search(r"zoiko_jwt=([^;]+)", cookie)
    if not m:
        raise RuntimeError(f"No zoiko_jwt cookie in login response for {email}")
    jwt = m.group(1)
    tenant_id = r.json().get("tenant_id", TENANT_ID)
    return jwt, tenant_id


def hdr(token: str) -> dict:
    return {
        "X-Tenant-ID":     TENANT_ID,
        "Authorization":   f"Bearer {token}",
        "Content-Type":    "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def post(base: str, path: str, body: dict, token: str, label: str) -> dict | None:
    try:
        r = requests.post(url(base, path), json=body, headers=hdr(token), timeout=SESSION_TIMEOUT)
        if r.status_code in (200, 201, 202):
            d = r.json()
            cid   = str(d.get("id") or d.get("job_id") or "")[:8]
            state = d.get("state") or d.get("status") or ""
            conf  = d.get("confidence")
            conf_s = f"  confidence={conf:.4f}" if isinstance(conf, float) else ""
            print(f"    ✓ {label}  [{cid}] {state}{conf_s}")
            return d
        print(f"    ✗ {label}  → {r.status_code}: {r.text[:160]}")
    except requests.exceptions.ConnectionError:
        print(f"    ✗ {label}  → backend not reachable (is the service running?)")
    except Exception as exc:
        print(f"    ✗ {label}  → {exc}")
    return None


def poll(base: str, path: str, token: str, label: str) -> dict | None:
    """Poll until state leaves NEW/EVIDENCE_PENDING (evidence+reasoning done)."""
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(url(base, path), headers={
                "X-Tenant-ID":   TENANT_ID,
                "Authorization": f"Bearer {token}",
            }, timeout=8)
            if r.status_code == 200:
                d = r.json()
                if d.get("state") not in (None, "NEW", "EVIDENCE_PENDING"):
                    print(f"    ↳ {label} → {d.get('state')}")
                    return d
        except Exception:
            pass
        time.sleep(2)
    print(f"    ⚠ {label} still pending after {POLL_TIMEOUT}s — AI thread still running")
    return None


def submit_async(base: str, submit_path: str, status_path_prefix: str, body: dict,
                 token: str, label: str, wait_s: int = 45) -> dict | None:
    """POST to submit-async, then poll submit-status until done. Works for SC-001 and SC-002."""
    r = requests.post(url(base, submit_path), json=body, headers=hdr(token), timeout=15)
    if r.status_code not in (200, 201, 202):
        print(f"    ✗ {label}  → {r.status_code}: {r.text[:160]}")
        return None
    job_id = r.json().get("job_id") or r.json().get("id")
    print(f"    ↳ {label}  queued [{str(job_id)[:8]}], waiting up to {wait_s}s...")
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(3)
        try:
            r2 = requests.get(
                url(base, f"{status_path_prefix}/{job_id}"),
                headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {token}"},
                timeout=8,
            )
            if r2.status_code == 200:
                d = r2.json()
                status = d.get("status")
                if status == "done":
                    case = d.get("case") or d
                    cid  = str(case.get("id") or "")[:8]
                    state = case.get("state") or ""
                    conf  = case.get("confidence")
                    conf_s = f"  confidence={conf:.4f}" if isinstance(conf, float) else ""
                    print(f"    ✓ {label}  [{cid}] {state}{conf_s}")
                    return case
                if status == "error":
                    print(f"    ✗ {label}  pipeline error: {d.get('error', '')[:200]}")
                    return None
        except Exception:
            pass
    print(f"    ⚠ {label}  timed out after {wait_s}s")
    return None


def check_alive(base: str, name: str) -> bool:
    try:
        r = requests.get(f"{base}/health", timeout=4)
        if r.status_code == 200:
            print(f"  ✓ {name} is live")
            return True
    except Exception:
        pass
    print(f"  ✗ {name} not reachable at {base}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SC-001  Freight Invoice Overcharge
# ─────────────────────────────────────────────────────────────────────────────

def seed_sc001(analyst: str, manager: str):
    print("\n── SC-001  Freight Invoice Overcharge  (port 8000) ──────────────")

    # Contract rates — needed so validation has something to compare against
    contract_rates = [
        {"carrier_id": "BLUEDART",  "rate_type": "FUEL_CHARGE",  "rate_value": 8000,  "currency": "INR",
         "effective_on": "2026-01-01", "expires_on": "2027-12-31",
         "origin": "Mumbai", "destination": "Delhi", "transport_mode": "TRUCKLOAD"},
        {"carrier_id": "BLUEDART",  "rate_type": "ACCESSORIAL",  "rate_value": 2000,  "currency": "INR",
         "effective_on": "2026-01-01", "expires_on": "2027-12-31",
         "origin": "Mumbai", "destination": "Delhi", "transport_mode": "TRUCKLOAD"},
        {"carrier_id": "DHL",       "rate_type": "FUEL_CHARGE",  "rate_value": 9500,  "currency": "INR",
         "effective_on": "2026-01-01", "expires_on": "2027-12-31",
         "origin": "Chennai", "destination": "Bangalore", "transport_mode": "COURIER"},
        {"carrier_id": "DELHIVERY", "rate_type": "FUEL_CHARGE",  "rate_value": 5500,  "currency": "INR",
         "effective_on": "2026-01-01", "expires_on": "2027-12-31",
         "origin": "Kolkata", "destination": "Hyderabad", "transport_mode": "TRUCKLOAD"},
        {"carrier_id": "FEDEX",     "rate_type": "FUEL_CHARGE",  "rate_value": 16000, "currency": "INR",
         "effective_on": "2026-01-01", "expires_on": "2027-12-31",
         "origin": "Mumbai", "destination": "Singapore", "transport_mode": "AIR"},
    ]
    print("  Creating contract rates...")
    for rate in contract_rates:
        try:
            r = requests.post(url(GW001, "/contract-rates"), json=rate, headers=hdr(analyst), timeout=10)
            if r.status_code in (200, 201):
                print(f"    ✓ {rate['carrier_id']} {rate['rate_type']} @ {rate['rate_value']}")
        except Exception:
            pass

    # 4 invoice cases
    invoices = [
        {
            "label":   "BlueDart Mumbai→Delhi (fuel overcharge)",
            "carrier": "BLUEDART", "route": "Mumbai-Delhi",     "amount": 12500,
            "charge_lines": [
                {"description": "Fuel surcharge", "amount": 10500, "type": "FUEL"},
                {"description": "Accessorial",    "amount":  2000, "type": "ACCESSORIAL"},
            ],
        },
        {
            "label":   "DHL Chennai→Bangalore (accessorial excess)",
            "carrier": "DHL",       "route": "Chennai-Bangalore","amount": 15800,
            "charge_lines": [
                {"description": "Fuel surcharge", "amount": 13200, "type": "FUEL"},
                {"description": "Handling fee",   "amount":  2600, "type": "ACCESSORIAL"},
            ],
        },
        {
            "label":   "Delhivery Kolkata→Hyderabad (fuel excess)",
            "carrier": "DELHIVERY", "route": "Kolkata-Hyderabad","amount":  9200,
            "charge_lines": [
                {"description": "Fuel surcharge", "amount": 8000, "type": "FUEL"},
                {"description": "Fuel adj.",      "amount": 1200, "type": "FUEL"},
            ],
        },
        {
            "label":   "FedEx Mumbai→Singapore (air freight overcharge)",
            "carrier": "FEDEX",     "route": "Mumbai-Singapore", "amount": 42000,
            "charge_lines": [
                {"description": "Air freight",    "amount": 35000, "type": "FUEL"},
                {"description": "Surcharge",      "amount":  7000, "type": "ACCESSORIAL"},
            ],
        },
    ]

    # Submit all 4 cases using submit-async (blocking /cases/submit times out on Neon)
    cases = []
    for inv in invoices:
        body = {
            "carrier":        inv["carrier"],
            "route":          inv["route"],
            "amount":         inv["amount"],
            "currency":       "INR",
            "invoice_number": f"INV-{uuid.uuid4().hex[:8].upper()}",
            "invoice_date":   "2026-06-20",
            "charge_lines":   inv["charge_lines"],
            "transport_mode": "TRUCKLOAD",
        }
        case = submit_async(GW001, "/cases/submit-async", "/cases/submit-status",
                            body, analyst, inv["label"])
        if case:
            cases.append((case, inv["amount"]))

    if not cases:
        print("  ⚠ No SC-001 cases created — skipping governance flow")
        return

    # Advance first case → APPROVAL_PENDING (propose only)
    print("  Running governance on case 1 (→ APPROVAL_PENDING)...")
    case1, amt1 = cases[0]
    if case1.get("state") == "FINDING_GENERATED":
        # POST /cases/{id}/proposal — UIProposalRequest: action, amount, currency
        post(GW001, f"/cases/{case1['id']}/proposal",
             {"action": "EXECUTE_CREDIT_MEMO", "amount": round(amt1 * 0.36, 2), "currency": "INR"},
             analyst, "propose case 1")

    # Advance second case → EXECUTION_READY (propose + decide)
    if len(cases) > 1:
        print("  Running governance on case 2 (→ EXECUTION_READY)...")
        case2, amt2 = cases[1]
        if case2.get("state") == "FINDING_GENERATED":
            prop2 = post(GW001, f"/cases/{case2['id']}/proposal",
                         {"action": "EXECUTE_CREDIT_MEMO", "amount": round(amt2 * 0.40, 2), "currency": "INR"},
                         analyst, "propose case 2")
            if prop2:
                # POST /cases/{id}/decide — UIDecideRequest: decision, note (no task_id needed)
                post(GW001, f"/cases/{case2['id']}/decide",
                     {"decision": "EXECUTION_READY", "note": "Seed: manager approves"},
                     manager, "decide case 2")


# ─────────────────────────────────────────────────────────────────────────────
# SC-002  Carrier Claims
# ─────────────────────────────────────────────────────────────────────────────

def seed_sc002(analyst: str):
    print("\n── SC-002  Carrier Claims  (port 8010) ──────────────────────────")
    claims = [
        {
            "label":    "BlueDart — DAMAGE (electronics)",
            "carrier":  "BLUEDART",  "claim_type": "DAMAGE",    "claimed_amount": 18500,
            "awb_number": f"AWB-BD-{uuid.uuid4().hex[:6].upper()}",
            "description": "Laptop shipment damaged in transit Mumbai→Delhi — packaging crushed",
            "incident_date": "2026-06-18", "origin_location": "Mumbai", "destination_location": "Delhi",
        },
        {
            "label":    "DHL — LOSS (pharma parcel)",
            "carrier":  "DHL",       "claim_type": "LOSS",      "claimed_amount": 32000,
            "awb_number": f"AWB-DH-{uuid.uuid4().hex[:6].upper()}",
            "description": "Pharmaceutical parcel not delivered, last scan Chennai hub 4 days ago",
            "incident_date": "2026-06-15", "origin_location": "Chennai", "destination_location": "Hyderabad",
        },
        {
            "label":    "Delhivery — DELAY (auto parts)",
            "carrier":  "DELHIVERY", "claim_type": "DELAY",     "claimed_amount": 4500,
            "awb_number": f"AWB-DL-{uuid.uuid4().hex[:6].upper()}",
            "description": "3-day delay on auto parts shipment caused production line halt at Bangalore plant",
            "incident_date": "2026-06-20", "origin_location": "Kolkata", "destination_location": "Bangalore",
        },
    ]

    for c in claims:
        body = {
            "carrier":              c["carrier"],
            "claim_type":           c["claim_type"],
            "claimed_amount":       c["claimed_amount"],
            "currency":             "INR",
            "description":          c["description"],
            "awb_number":           c["awb_number"],
            "incident_date":        c["incident_date"],
            "origin_location":      c["origin_location"],
            "destination_location": c["destination_location"],
        }
        # SC-002 also uses async submit pattern (blocking /claims/submit times out on Neon)
        submit_async(GW002, "/claims/submit-async", "/claims/submit-status",
                     body, analyst, c["label"])


# ─────────────────────────────────────────────────────────────────────────────
# SC-003  Shipment Exceptions / SLA Breaches
# ─────────────────────────────────────────────────────────────────────────────

def seed_sc003(analyst: str):
    print("\n── SC-003  Shipment Exceptions / SLA Breaches  (port 8020) ─────")
    now = datetime.now(timezone.utc)

    exceptions = [
        {
            "label":               "BlueDart — 6 hr SLA breach (electronics)",
            "carrier":             "BLUEDART",
            "shipment_reference":  f"SHP-BD-{uuid.uuid4().hex[:6].upper()}",
            "committed_eta":       (now - timedelta(days=4, hours=6)).isoformat(),
            "actual_delivery":     (now - timedelta(days=4)).isoformat(),
            "penalty_rate_per_hour": 500.0,
            "penalty_cap":         5000.0,
        },
        {
            "label":               "Delhivery — 4 hr SLA breach (FMCG)",
            "carrier":             "DELHIVERY",
            "shipment_reference":  f"SHP-DL-{uuid.uuid4().hex[:6].upper()}",
            "committed_eta":       (now - timedelta(days=3, hours=4)).isoformat(),
            "actual_delivery":     (now - timedelta(days=3)).isoformat(),
            "penalty_rate_per_hour": 300.0,
            "penalty_cap":         3000.0,
        },
        {
            "label":               "Ekart — 9 hr SLA breach (e-commerce returns)",
            "carrier":             "EKART",
            "shipment_reference":  f"SHP-EK-{uuid.uuid4().hex[:6].upper()}",
            "committed_eta":       (now - timedelta(days=2, hours=9)).isoformat(),
            "actual_delivery":     (now - timedelta(days=1, hours=22)).isoformat(),
            "penalty_rate_per_hour": 250.0,
            "penalty_cap":         4000.0,
        },
    ]

    for e in exceptions:
        body = {
            "carrier":               e["carrier"],
            "shipment_reference":    e["shipment_reference"],
            "committed_eta":         e["committed_eta"],
            "actual_delivery":       e["actual_delivery"],
            "origin":                "Mumbai",
            "destination":           "Delhi",
            "penalty_rate_per_hour": e["penalty_rate_per_hour"],
            "penalty_cap":           e["penalty_cap"],
            "currency":              "INR",
        }
        post(GW003, "/shipment-exceptions/submit", body, analyst, e["label"])
        time.sleep(0.4)


# ─────────────────────────────────────────────────────────────────────────────
# SC-004  Supplier Scorecard Breaches
# ─────────────────────────────────────────────────────────────────────────────

def seed_sc004(analyst: str):
    print("\n── SC-004  Supplier Scorecards  (port 8030) ─────────────────────")
    scorecards = [
        {"label": "BlueDart  — 30-day review (threshold 75)",  "carrier_id": "BLUEDART",  "period_days": 30, "contracted_threshold": 75.0},
        {"label": "DHL       — 30-day review (threshold 80)",  "carrier_id": "DHL",       "period_days": 30, "contracted_threshold": 80.0},
        {"label": "Delhivery — 60-day review (threshold 70)",  "carrier_id": "DELHIVERY", "period_days": 60, "contracted_threshold": 70.0},
    ]
    for s in scorecards:
        body = {
            "carrier_id":           s["carrier_id"],
            "period_days":          s["period_days"],
            "contracted_threshold": s["contracted_threshold"],
        }
        post(GW004, "/scorecards/compute", body, analyst, s["label"])
        time.sleep(0.4)


# ─────────────────────────────────────────────────────────────────────────────
# SC-005  Accessorial Charge Disputes
# ─────────────────────────────────────────────────────────────────────────────

def seed_sc005(analyst: str):
    print("\n── SC-005  Accessorial Charge Disputes  (port 8040) ─────────────")
    disputes = [
        {
            "label":             "BlueDart — detention + liftgate excess",
            "carrier_id":        "BLUEDART",
            "invoice_reference": f"ACC-INV-{uuid.uuid4().hex[:8].upper()}",
            "invoice_date":      "2026-06-22",
            "currency":          "INR",
            "charge_lines": [
                {"charge_type": "DETENTION",   "billed_amount": 4500, "contracted_cap": 2000},
                {"charge_type": "LIFTGATE",    "billed_amount": 1800, "contracted_cap": 1200},
            ],
        },
        {
            "label":             "Delhivery — fuel surcharge + residential excess",
            "carrier_id":        "DELHIVERY",
            "invoice_reference": f"ACC-INV-{uuid.uuid4().hex[:8].upper()}",
            "invoice_date":      "2026-06-24",
            "currency":          "INR",
            "charge_lines": [
                {"charge_type": "FUEL_SURCHARGE", "billed_amount": 6200, "contracted_cap": 4000},
                {"charge_type": "RESIDENTIAL",    "billed_amount": 2200, "contracted_cap": 1500},
            ],
        },
        {
            "label":             "DHL — demurrage excess (container delay)",
            "carrier_id":        "DHL",
            "invoice_reference": f"ACC-INV-{uuid.uuid4().hex[:8].upper()}",
            "invoice_date":      "2026-06-25",
            "currency":          "INR",
            "charge_lines": [
                {"charge_type": "DEMURRAGE",   "billed_amount": 8800, "contracted_cap": 5000},
            ],
        },
    ]
    for d in disputes:
        body = {
            "carrier_id":        d["carrier_id"],
            "invoice_reference": d["invoice_reference"],
            "invoice_date":      d["invoice_date"],
            "currency":          d["currency"],
            "charge_lines":      d["charge_lines"],
        }
        post(GW005, "/accessorial-disputes/submit", body, analyst, d["label"])
        time.sleep(0.4)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 62)
    print("  Zoiko AI Logistics  —  Seed All 5 Slices")
    print("=" * 62)

    # Health-check all gateways first
    print("\n[1/7] Checking services...")
    alive = {
        "SC-001": check_alive(GW001, "SC-001 gateway (8000)"),
        "SC-002": check_alive(GW002, "SC-002 gateway (8010)"),
        "SC-003": check_alive(GW003, "SC-003 gateway (8020)"),
        "SC-004": check_alive(GW004, "SC-004 gateway (8030)"),
        "SC-005": check_alive(GW005, "SC-005 gateway (8040)"),
    }

    if not any(alive.values()):
        print("\n  ERROR: No backends reachable. Run launch.bat first.")
        sys.exit(1)

    # Auth
    print("\n[2/7] Authenticating...")
    analyst, real_tenant = get_token("anil@zoiko.com",  "Anil@123")
    manager, _           = get_token("venky@zoiko.com", "Venky@123")
    # Patch module-level TENANT_ID so hdr() picks up the real tenant on every call
    import sys as _sys
    _mod = _sys.modules[__name__]
    _mod.TENANT_ID = real_tenant
    print(f"  ✓ Tokens ready  (tenant: {real_tenant})")

    # Seed each live slice
    errors = []
    slices = [
        ("SC-001", alive["SC-001"], seed_sc001, (analyst, manager)),
        ("SC-002", alive["SC-002"], seed_sc002, (analyst,)),
        ("SC-003", alive["SC-003"], seed_sc003, (analyst,)),
        ("SC-004", alive["SC-004"], seed_sc004, (analyst,)),
        ("SC-005", alive["SC-005"], seed_sc005, (analyst,)),
    ]
    for name, is_alive, fn, args in slices:
        if not is_alive:
            print(f"\n── {name}  SKIPPED (service not running)")
            continue
        try:
            fn(*args)
        except Exception as exc:
            print(f"  ✗ {name} seeding failed: {exc}")
            errors.append(name)

    # Summary
    print("\n" + "=" * 62)
    if errors:
        print(f"  ⚠  Finished with errors in: {', '.join(errors)}")
        print("     Check terminal output above for details.")
    else:
        print("  ✓  All live slices seeded successfully!")
    print("  → Dashboard: http://localhost:5173")
    print("  → Reload the browser and check each tab (All / Invoices / Claims ...)")
    print("=" * 62)
