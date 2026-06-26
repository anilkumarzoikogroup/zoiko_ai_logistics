"""
SC-003 Golden Path Demo — Shipment Exception / SLA Penalty
===========================================================
Walks the full SC-003 pipeline end-to-end against a running local stack:

  Step 1  Submit shipment exception      POST /v1/shipment-exceptions/submit
  Step 2  Poll until FINDING_GENERATED   GET  /v1/shipment-exceptions/{id}
  Step 3  Analyst proposes SLA credit    POST /v1/shipment-exceptions/{id}/propose
  Step 4  Manager approves (SoD OK)      POST /v1/shipment-exceptions/{id}/decide
  Step 5  Execute (8-gate)               POST /v1/execute        (port 8021)
  Step 6  Reconcile (Commitment Match)   POST /v1/reconcile       (port 8021)
  Step 7  Issue ACR (WORM lock)          POST /v1/cases/{id}/acr  (port 8021)

Usage:
  cd backend\\slices\\sc-003-shipment-exception\\spine\\gateway
  ..\\..\\..\\..\\venv\\Scripts\\activate
  $env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
  $env:ZOIKO_DEV_MODE = "true"
  python scripts\\demo_sc003.py

Backend must already be running on ports 8020 (gateway) and 8021 (execution).
"""
import json
import os
import sys
import time
import uuid

try:
    import requests
except ImportError:
    sys.exit("pip install requests first")

# ── Config ────────────────────────────────────────────────────────────────────

GATEWAY_URL   = os.getenv("SC003_GATEWAY_URL",   "http://localhost:8020")
EXECUTION_URL = os.getenv("SC003_EXECUTION_URL",  "http://localhost:8021")
TENANT_ID     = os.getenv("VITE_DEV_TENANT", "11111111-1111-1111-1111-111111111111")
JWT           = os.getenv("VITE_DEV_JWT", "")

# Two different sub values for SoD enforcement
ANALYST_SUB = "analyst@zoikotech.com"
MANAGER_SUB = "manager@zoikotech.com"

# SC-003 scenario: BlueDart committed 14:00, arrived 20:00 → 6h breach @ ₹500/h = ₹3,000
CARRIER             = "BLUEDART"
SHIPMENT_REF        = f"AWB-SC003-{uuid.uuid4().hex[:6].upper()}"
COMMITTED_ETA       = "2026-06-01T14:00:00+05:30"   # 14:00 IST
ACTUAL_DELIVERY     = "2026-06-01T20:00:00+05:30"   # 20:00 IST → 6-hour breach
PENALTY_RATE_PER_H  = 500.00                          # ₹500/hour
PENALTY_CAP         = 50000.00                        # ₹50,000 max
EXPECTED_BREACH_H   = 6.0
EXPECTED_PENALTY    = min(PENALTY_CAP, EXPECTED_BREACH_H * PENALTY_RATE_PER_H)  # 3000.00
CURRENCY            = "INR"


def _h(sub: str) -> dict:
    headers = {
        "X-Tenant-ID":     TENANT_ID,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type":    "application/json",
        "X-Actor-Sub":     sub,
    }
    if JWT:
        headers["Authorization"] = f"Bearer {JWT}"
    return headers


def _ok(resp: requests.Response, step: str) -> dict:
    if resp.status_code not in (200, 201, 202):
        print(f"\n  [FAIL] {step}: HTTP {resp.status_code}")
        try:
            print(f"         {json.dumps(resp.json(), indent=2)}")
        except Exception:
            print(f"         {resp.text[:400]}")
        sys.exit(1)
    return resp.json()


def _sep(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


# ── Steps ─────────────────────────────────────────────────────────────────────

def step1_submit() -> str:
    _sep("Step 1 — Submit shipment exception (SC-003)")
    body = {
        "shipment_reference":   SHIPMENT_REF,
        "carrier_id":           CARRIER,
        "committed_eta":        COMMITTED_ETA,
        "actual_delivery":      ACTUAL_DELIVERY,
        "penalty_rate_per_hour": PENALTY_RATE_PER_H,
        "penalty_cap":          PENALTY_CAP,
        "currency":             CURRENCY,
        "origin":               "Mumbai",
        "destination":          "Delhi",
        "service_type":         "EXPRESS",
        "description":          "Demo: BlueDart committed 14:00, arrived 20:00 — 6h SLA breach",
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/shipment-exceptions/submit",
        json=body,
        headers=_h(ANALYST_SUB),
        timeout=30,
    )
    data = _ok(resp, "submit shipment exception")
    case_id = data.get("case_id") or data.get("id", "")
    print(f"  case_id          : {case_id}")
    print(f"  state            : {data.get('state', '?')}")
    print(f"  sla_breach_hours : {data.get('sla_breach_hours', '?')}")
    print(f"  sla_penalty      : {data.get('sla_penalty_amount') or data.get('penalty_amount', '?')}")
    return case_id


def step2_poll(case_id: str) -> None:
    _sep("Step 2 — Poll until FINDING_GENERATED")
    for attempt in range(30):
        resp = requests.get(
            f"{GATEWAY_URL}/v1/shipment-exceptions/{case_id}",
            headers={
                "X-Tenant-ID":  TENANT_ID,
                "X-Actor-Sub":  ANALYST_SUB,
                "Authorization": f"Bearer {JWT}" if JWT else "",
            },
            timeout=10,
        )
        data = _ok(resp, "poll exception state")
        state = data.get("state", "?")
        conf  = data.get("confidence", 0)
        breach = data.get("sla_breach_hours", "?")
        print(f"  [{attempt+1:02d}] state={state}  conf={conf:.4f}  breach_h={breach}")
        if state in ("FINDING_GENERATED", "APPROVAL_PENDING", "EXECUTION_READY",
                     "DISPATCHED", "CLOSED"):
            break
        time.sleep(2)
    else:
        print("  [WARN] timed out waiting for FINDING_GENERATED — continuing anyway")


def step3_propose(case_id: str) -> str:
    _sep("Step 3 — Analyst proposes SLA credit")
    body = {
        "proposed_action": "ISSUE_SLA_CREDIT",
        "amount":          EXPECTED_PENALTY,
        "currency":        CURRENCY,
        "rationale":       (
            f"SC003 confidence 0.9520. Breach {EXPECTED_BREACH_H}h × ₹{PENALTY_RATE_PER_H}/h = "
            f"₹{EXPECTED_PENALTY:.2f}. Recommend SLA credit issuance."
        ),
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/shipment-exceptions/{case_id}/propose",
        json=body,
        headers=_h(ANALYST_SUB),
        timeout=15,
    )
    data = _ok(resp, "propose SLA credit")
    proposal_id = data.get("proposal_id") or data.get("id", "")
    print(f"  proposal_id : {proposal_id}")
    print(f"  amount      : ₹{data.get('amount', '?')}")
    return proposal_id


def step4_decide(case_id: str) -> str:
    _sep("Step 4 — Manager approves (SoD: manager ≠ analyst)")
    body = {
        "decision":  "APPROVE",
        "rationale": "Confidence 0.9520. 6-hour breach verified by carrier events. Approve SLA credit.",
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/shipment-exceptions/{case_id}/decide",
        json=body,
        headers=_h(MANAGER_SUB),   # SoD: different sub from analyst
        timeout=15,
    )
    data = _ok(resp, "decide")
    token_id = data.get("token_id") or data.get("governance_token_id", "")
    print(f"  decision  : {data.get('decision', '?')}")
    print(f"  token_id  : {token_id}")
    print(f"  scope     : {data.get('scope', '?')}")
    return token_id


def step5_execute(token_id: str) -> str:
    _sep("Step 5 — 8-gate execution (port 8021)")
    body = {
        "token_id":  token_id,
        "tenant_id": TENANT_ID,
        "actor_sub": MANAGER_SUB,
    }
    resp = requests.post(
        f"{EXECUTION_URL}/v1/execute",
        json=body,
        headers=_h(MANAGER_SUB),
        timeout=20,
    )
    data = _ok(resp, "execute")
    env_id = data.get("envelope_id") or data.get("id", "")
    print(f"  envelope_id : {env_id}")
    print(f"  status      : {data.get('status', '?')}")
    print(f"  action      : {data.get('action', 'ISSUE_SLA_CREDIT')}")
    gates = data.get("gate_results", [])
    for g in gates:
        icon = "✓" if g.get("passed") else "✗"
        print(f"    Gate {g.get('gate', '?'):1} [{icon}] {g.get('name', '?')} — {g.get('detail', '')}")
    return env_id


def step6_reconcile(case_id: str, env_id: str) -> None:
    _sep("Step 6 — Reconcile (Commitment Match strategy)")
    body = {
        "envelope_id":       env_id,
        "case_id":           case_id,
        "tenant_id":         TENANT_ID,
        "actor_sub":         MANAGER_SUB,
        "committed_eta":     COMMITTED_ETA,
        "actual_delivery":   ACTUAL_DELIVERY,
        "credit_issued":     EXPECTED_PENALTY,
        "currency":          CURRENCY,
    }
    resp = requests.post(
        f"{EXECUTION_URL}/v1/reconcile",
        json=body,
        headers=_h(MANAGER_SUB),
        timeout=15,
    )
    data = _ok(resp, "reconcile")
    print(f"  reconciliation_id : {data.get('reconciliation_id') or data.get('id', '?')}")
    print(f"  outcome           : {data.get('outcome', '?')}")
    print(f"  variance_count    : {data.get('variance_count', 0)}")
    breach_h = data.get("sla_breach_hours_confirmed", EXPECTED_BREACH_H)
    print(f"  breach_hours_confirmed: {breach_h}")


def step7_acr(case_id: str) -> None:
    _sep("Step 7 — Issue ACR (WORM lock — irreversible)")
    body = {
        "case_id":   case_id,
        "tenant_id": TENANT_ID,
        "actor_sub": MANAGER_SUB,
    }
    resp = requests.post(
        f"{EXECUTION_URL}/v1/cases/{case_id}/acr",
        json=body,
        headers=_h(MANAGER_SUB),
        timeout=15,
    )
    data = _ok(resp, "issue ACR")
    print(f"  acr_id       : {data.get('acr_id') or data.get('id', '?')}")
    print(f"  is_locked    : {data.get('is_locked', '?')}")
    print(f"  merkle_root  : {str(data.get('merkle_root', ''))[:32]}…")
    artifacts = data.get("artifacts", [])
    if artifacts:
        print(f"  artifacts ({len(artifacts)}):")
        for a in artifacts:
            print(f"    [{a.get('position', '?')}] {a.get('artifact_type', '?')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  SC-003 SHIPMENT EXCEPTION — GOLDEN PATH DEMO")
    print("  Scenario: BlueDart commit 14:00 → arrived 20:00")
    print(f"  Breach: {EXPECTED_BREACH_H}h × ₹{PENALTY_RATE_PER_H}/h = ₹{EXPECTED_PENALTY:.2f} SLA credit")
    print(f"  Confidence: 0.9520  |  Shipment: {SHIPMENT_REF}")
    print("=" * 60)

    try:
        r = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        if r.status_code != 200:
            sys.exit(f"Gateway not healthy: {r.status_code}")
        print(f"\n  Gateway  : {GATEWAY_URL}  ✓")
    except Exception as e:
        sys.exit(f"SC-003 Gateway unreachable at {GATEWAY_URL}: {e}")

    try:
        r = requests.get(f"{EXECUTION_URL}/health", timeout=5)
        print(f"  Execution: {EXECUTION_URL}  {'✓' if r.status_code == 200 else '? (non-200)'}")
    except Exception:
        print(f"  Execution: {EXECUTION_URL}  ✗ (unreachable — steps 5–7 will fail)")

    case_id = step1_submit()
    step2_poll(case_id)
    _       = step3_propose(case_id)
    token_id = step4_decide(case_id)
    env_id   = step5_execute(token_id)
    step6_reconcile(case_id, env_id)
    step7_acr(case_id)

    print(f"\n{'=' * 60}")
    print("  SC-003 GOLDEN PATH COMPLETE")
    print(f"  case_id = {case_id}")
    print("  Pipeline: submit → find → propose → approve → execute → reconcile → ACR")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
