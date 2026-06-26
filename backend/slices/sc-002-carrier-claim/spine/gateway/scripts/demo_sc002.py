"""
SC-002 Golden Path Demo — Carrier Claim Pipeline
=================================================
Walks the full SC-002 pipeline end-to-end against a running local stack:

  Step 1  Submit carrier claim           POST /v1/claims/submit
  Step 2  Poll until FINDING_GENERATED   GET  /v1/claims/{id}
  Step 3  Analyst proposes settlement    POST /v1/cases/{id}/propose
  Step 4  Manager approves (SoD OK)      POST /v1/cases/{id}/decide
  Step 5  Issue governance token         POST /v1/cases/{id}/issue-token
  Step 6  Execute (8-gate)               POST /v1/execute        (port 8011)
  Step 7  Reconcile                      POST /v1/reconcile       (port 8011)
  Step 8  Issue ACR (WORM lock)          POST /v1/cases/{id}/acr  (port 8011)

Usage:
  cd backend\\slices\\sc-002-carrier-claim\\spine\\gateway
  ..\\..\\..\\..\\venv\\Scripts\\activate
  $env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
  $env:ZOIKO_DEV_MODE = "true"
  python scripts\\demo_sc002.py

Backend must already be running on ports 8010 (gateway) and 8011 (execution).
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

GATEWAY_URL   = os.getenv("SC002_GATEWAY_URL",   "http://localhost:8010")
EXECUTION_URL = os.getenv("SC002_EXECUTION_URL",  "http://localhost:8011")
TENANT_ID     = os.getenv("VITE_DEV_TENANT", "11111111-1111-1111-1111-111111111111")
JWT           = os.getenv("VITE_DEV_JWT", "")    # set in .env.local; demo uses dev secret

# For the demo we use two different sub values to satisfy SoD
ANALYST_SUB = "analyst@zoikotech.com"
MANAGER_SUB = "manager@zoikotech.com"

CARRIER       = "BLUEDART"
CLAIM_AMOUNT  = 4500.00      # ₹4,500 overcharge on ₹12,500 invoice vs ₹8,000 contract
CURRENCY      = "INR"
CLAIM_TYPE    = "OVERCHARGE"


def _h(sub: str) -> dict:
    """Build request headers for the given actor_sub."""
    headers = {
        "X-Tenant-ID":     TENANT_ID,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type":    "application/json",
    }
    if JWT:
        headers["Authorization"] = f"Bearer {JWT}"
    # Dev mode: pass actor via custom header (gateway reads X-Actor-Sub when DEV_MODE=true)
    headers["X-Actor-Sub"] = sub
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
    _sep("Step 1 — Submit carrier claim (SC-002)")
    claim_ref = f"DEMO-SC002-{uuid.uuid4().hex[:6].upper()}"
    body = {
        "carrier":                CARRIER,
        "claim_reference":        claim_ref,
        "claim_type":             CLAIM_TYPE,
        "claimed_amount":         CLAIM_AMOUNT,
        "currency":               CURRENCY,
        "description":            "Demo: BlueDart billed ₹12,500 against ₹8,000 contract rate",
        "related_invoice_number": "INV-DEMO-001",
        "awb_number":             "AWB-12345678",
        "incident_date":          "2026-06-01",
        "origin_location":        "Mumbai",
        "destination_location":   "Delhi",
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/claims/submit",
        json=body,
        headers=_h(ANALYST_SUB),
        timeout=30,
    )
    data = _ok(resp, "submit claim")
    case_id = data["id"]
    print(f"  case_id   : {case_id}")
    print(f"  state     : {data.get('state', '?')}")
    print(f"  confidence: {data.get('confidence', 0):.4f}")
    return case_id


def step2_poll(case_id: str) -> None:
    _sep("Step 2 — Poll until FINDING_GENERATED")
    for attempt in range(30):
        resp = requests.get(
            f"{GATEWAY_URL}/v1/claims/{case_id}",
            headers={
                "X-Tenant-ID": TENANT_ID,
                "Authorization": f"Bearer {JWT}" if JWT else "",
                "X-Actor-Sub": ANALYST_SUB,
            },
            timeout=10,
        )
        data = _ok(resp, "poll claim state")
        state = data.get("state", "?")
        conf  = data.get("confidence", 0)
        print(f"  [{attempt+1:02d}] state={state}  confidence={conf:.4f}")
        if state in ("FINDING_GENERATED", "APPROVAL_PENDING", "EXECUTION_READY",
                     "DISPATCHED", "CLOSED"):
            break
        time.sleep(2)
    else:
        print("  [WARN] timed out waiting for FINDING_GENERATED — continuing anyway")


def step3_propose(case_id: str) -> str:
    _sep("Step 3 — Analyst proposes settlement")
    body = {
        "finding_id":       None,   # gateway resolves from case
        "proposed_action":  "SETTLE_CLAIM",
        "amount":           CLAIM_AMOUNT,
        "currency":         CURRENCY,
        "rationale":        "SC002 confidence 0.9275 exceeds threshold. Recommend full settlement.",
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/cases/{case_id}/propose",
        json=body,
        headers=_h(ANALYST_SUB),
        timeout=15,
    )
    data = _ok(resp, "propose")
    proposal_id = data.get("proposal_id") or data.get("id", "")
    print(f"  proposal_id: {proposal_id}")
    print(f"  action     : {data.get('proposed_action', '?')}")
    return proposal_id


def step4_decide(case_id: str) -> str:
    _sep("Step 4 — Manager approves (SoD: different actor)")
    body = {
        "decision":   "APPROVE",
        "rationale":  "Confidence 0.9275 confirmed. Overcharge is valid. Approve settlement.",
    }
    resp = requests.post(
        f"{GATEWAY_URL}/v1/cases/{case_id}/decide",
        json=body,
        headers=_h(MANAGER_SUB),   # SoD: manager ≠ analyst
        timeout=15,
    )
    data = _ok(resp, "decide")
    token_id = data.get("token_id") or data.get("governance_token_id", "")
    print(f"  decision : {data.get('decision', '?')}")
    print(f"  token_id : {token_id}")
    return token_id


def step5_issue_token(case_id: str, token_id: str) -> str:
    _sep("Step 5 — Governance token")
    if token_id:
        print(f"  token_id : {token_id}  (already issued by decide endpoint)")
        return token_id
    # Some versions issue the token via a separate endpoint
    resp = requests.post(
        f"{GATEWAY_URL}/v1/cases/{case_id}/issue-token",
        json={"scope": "SETTLE_CLAIM"},
        headers=_h(MANAGER_SUB),
        timeout=15,
    )
    data = _ok(resp, "issue-token")
    token_id = data.get("token_id") or data.get("id", "")
    print(f"  token_id : {token_id}")
    print(f"  scope    : {data.get('scope', '?')}")
    print(f"  expires  : {data.get('expires_at', '?')}")
    return token_id


def step6_execute(token_id: str) -> str:
    _sep("Step 6 — 8-gate execution (port 8011)")
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
    gates = data.get("gate_results", [])
    for g in gates:
        icon = "✓" if g.get("passed") else "✗"
        print(f"    Gate {g.get('gate', '?'):1} [{icon}] {g.get('name', '?')} — {g.get('detail', '')}")
    return env_id


def step7_reconcile(case_id: str, env_id: str) -> None:
    _sep("Step 7 — Reconcile (commitment match)")
    body = {
        "envelope_id": env_id,
        "case_id":     case_id,
        "tenant_id":   TENANT_ID,
        "actor_sub":   MANAGER_SUB,
        "outcome":     "SETTLED",
        "settled_amount": CLAIM_AMOUNT,
        "currency":    CURRENCY,
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


def step8_acr(case_id: str) -> None:
    _sep("Step 8 — Issue ACR (WORM lock)")
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
            print(f"    [{a.get('position','?')}] {a.get('artifact_type','?')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 60)
    print("  SC-002 CARRIER CLAIM — GOLDEN PATH DEMO")
    print("  Scenario: BlueDart ₹12,500 billed vs ₹8,000 contract")
    print("  Overcharge: ₹4,500 | Confidence: 0.9275")
    print("=" * 60)

    # Verify backend is up
    try:
        r = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        if r.status_code != 200:
            sys.exit(f"Gateway not healthy: {r.status_code}")
        print(f"\n  Gateway  : {GATEWAY_URL}  ✓")
    except Exception as e:
        sys.exit(f"Gateway unreachable at {GATEWAY_URL}: {e}")

    try:
        r = requests.get(f"{EXECUTION_URL}/health", timeout=5)
        print(f"  Execution: {EXECUTION_URL}  {'✓' if r.status_code == 200 else '? (non-200)'}")
    except Exception:
        print(f"  Execution: {EXECUTION_URL}  ✗ (unreachable — steps 6–8 will fail)")

    case_id   = step1_submit()
    step2_poll(case_id)
    _          = step3_propose(case_id)
    token_id   = step4_decide(case_id)
    token_id   = step5_issue_token(case_id, token_id)
    env_id     = step6_execute(token_id)
    step7_reconcile(case_id, env_id)
    step8_acr(case_id)

    print(f"\n{'=' * 60}")
    print("  SC-002 GOLDEN PATH COMPLETE")
    print(f"  case_id = {case_id}")
    print("  Pipeline: submit → find → propose → approve → execute → reconcile → ACR")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
