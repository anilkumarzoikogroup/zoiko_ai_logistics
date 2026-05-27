"""
Phase 4 end-to-end demo: Execution Gateway → Reconciliation → ACR

Prerequisites:
  - Run demo_phase2.py first (produces a case in PENDING_APPROVAL)
  - Run demo_phase3.py (advances case to EXECUTION_READY + ACTIVE token)
  - OR manually set DEMO_TOKEN_ID / DEMO_CASE_ID / DEMO_TENANT_ID env vars

Usage:
  cd phase-4
  $env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
  $env:PYTHONIOENCODING = "utf-8"
  py demo_phase4.py
"""
import os, sys
from dotenv import load_dotenv
import paths  # noqa: F401

load_dotenv()

from kafka.mock_kafka import MockKafkaBroker

DB_URL      = os.getenv("DB_URL")
TENANT_SLUG = os.getenv("TENANT_SLUG", "default")
BROKER      = MockKafkaBroker()

import shared.db as _db

print("\n=== Phase 4 Demo: Execution Gateway → Reconciliation → ACR ===\n")

# ── 1. Find an ACTIVE token ───────────────────────────────────────────────────
token_id    = os.getenv("DEMO_TOKEN_ID")
case_id     = os.getenv("DEMO_CASE_ID")
tenant_id   = os.getenv("DEMO_TENANT_ID")

if not token_id:
    row = _db.q1("""
        SELECT gt.id, gt.tenant_id, dp.case_id
        FROM   governance_tokens gt
        JOIN   governance_decisions gd ON gd.id = gt.decision_id
        JOIN   decision_proposals  dp ON dp.id  = gd.proposal_id
        WHERE  gt.status='ACTIVE'
        ORDER BY gt.issued_at DESC LIMIT 1
    """, db_url=DB_URL)
    if not row:
        print("No ACTIVE governance token found.")
        print("Run demo_phase2.py + demo_phase3.py first.")
        sys.exit(1)
    token_id  = str(row["id"])
    case_id   = str(row["case_id"])
    tenant_id = str(row["tenant_id"])

print(f"  Token  : {token_id}")
print(f"  Case   : {case_id}")
print(f"  Tenant : {tenant_id}")

# ── 2. Run 8-gate execution ───────────────────────────────────────────────────
from services.execution_gateway.handler import ExecutionGateway
from services.execution_gateway.models  import ExecutionRequest

print("\n[Step 1] Running 8-gate execution check...")
gw  = ExecutionGateway(DB_URL, BROKER, TENANT_SLUG)
req = ExecutionRequest(token_id=token_id, tenant_id=tenant_id, actor_sub="demo-user")

try:
    env_result = gw.execute(req)
    print(f"  Envelope : {env_result.envelope_id}")
    print(f"  Status   : {env_result.status}")
    print(f"  Connector: {env_result.connector_ref}")
    for g in env_result.gate_results:
        mark = "PASS" if g.passed else "FAIL"
        print(f"  Gate {g.gate} [{mark}] {g.name}: {g.detail}")
except ValueError as e:
    print(f"  Execution REJECTED: {e}")
    sys.exit(1)

# ── 3. Reconcile ──────────────────────────────────────────────────────────────
from services.reconciliation_svc.handler import ReconciliationHandler

print("\n[Step 2] Reconciling settlement...")
rec_handler = ReconciliationHandler(DB_URL, BROKER, TENANT_SLUG)
rec_result  = rec_handler.reconcile(
    envelope_id = env_result.envelope_id,
    tenant_id   = tenant_id,
    actor_sub   = "demo-user",
)
print(f"  Reconciliation: {rec_result.reconciliation_id}")
print(f"  Status        : {rec_result.status}")
print(f"  Delta         : {rec_result.delta}")

# ── 4. Issue ACR ──────────────────────────────────────────────────────────────
from services.audit_acr_svc.handler import AuditACRHandler

print("\n[Step 3] Issuing ACR...")
acr_handler = AuditACRHandler(DB_URL, BROKER, TENANT_SLUG)
try:
    acr_result = acr_handler.issue_acr(
        case_id   = case_id,
        tenant_id = tenant_id,
        actor_sub = "demo-user",
    )
    print(f"  ACR ID       : {acr_result.acr_id}")
    print(f"  Merkle Root  : {acr_result.merkle_root[:32]}...")
    print(f"  Artifacts    : {acr_result.artifact_count}")
    print(f"  Locked       : {acr_result.is_locked}")
    print(f"  Case state   : CLOSED")
except ValueError as e:
    print(f"  ACR skipped  : {e}")

print("\n=== Phase 4 Demo complete ===")
print("Full pipeline: INGESTED → VALIDATED → CANONICAL → CASE → EVIDENCE → FINDING")
print("               → PROPOSAL → DECISION → TOKEN → EXECUTED → RECONCILED → ACR → CLOSED")
