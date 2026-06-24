"""
Golden-path determinism check (SC-001 acceptance criterion):
"Running the identical scenario N times produces byte-identical
deterministic outputs every time."

Finds a real case + evidence bundle already in the database, then calls
the real AgentRuntime.run() reasoning engine N times against the exact
same inputs — read-only, no writes — and asserts that the deterministic
parts of the output (rule_trace, SC001_CONFIDENCE, and the finding_hash
formula ReasoningHandler.analyze() uses) are byte-identical across every
run. A mismatch means something non-deterministic (wall-clock, randomness,
unseeded AI output) has leaked into a field that SC-001 requires to be
reproducible.

Run:
  cd backend/slices/sc-001-freight-invoice-overcharge/spine/governance
  DB_URL=... python scripts/golden_path_determinism.py --runs 100
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

_HERE       = os.path.dirname(os.path.abspath(__file__))
_GOVERNANCE = os.path.normpath(os.path.join(_HERE, ".."))
sys.path.insert(0, _GOVERNANCE)
import paths  # noqa: E402  — governance's sys.path bootstrap

import psycopg2          # noqa: E402
import psycopg2.extras   # noqa: E402
psycopg2.extras.register_uuid()

from services.reasoning_svc.handler import AgentRuntime  # noqa: E402
from zoiko_common.crypto.jcs import canonicalize          # noqa: E402


def _finding_hash(bundle_id: str, case_id: str, confidence: float, rule_trace: dict, tenant_id: str) -> str:
    payload = canonicalize({
        "bundle_id":   bundle_id,
        "case_id":     case_id,
        "confidence":  confidence,
        "rule_trace":  rule_trace,
        "tenant_id":   tenant_id,
    })
    return hashlib.sha256(b"zoiko.finding.v1:" + payload).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=100)
    args = ap.parse_args()

    db_url = os.environ["DB_URL"]
    conn = psycopg2.connect(db_url)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT eb.id AS bundle_id, eb.case_id, eb.tenant_id, ci.carrier_id
        FROM evidence_bundles eb
        JOIN cases c ON c.id = eb.case_id
        JOIN canonical_invoices ci ON ci.id = c.invoice_id
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if not row:
        print("No real case + evidence bundle found in the database — "
              "run a case through the pipeline first (e.g. demo_sc001 / a webhook ingest).")
        return 1

    bundle_id, case_id, tenant_id, carrier = (
        str(row["bundle_id"]), str(row["case_id"]), str(row["tenant_id"]), row["carrier_id"],
    )
    print(f"Using real case_id={case_id}, bundle_id={bundle_id}, tenant_id={tenant_id}")
    print(f"Running AgentRuntime.run() {args.runs} times with identical inputs...\n")

    runtime = AgentRuntime()
    seen_traces: set[str] = set()
    seen_hashes: set[str] = set()

    for i in range(args.runs):
        rule_trace, _steps, _tools, _evidence_refs, _ai_result = runtime.run(
            db_url=db_url, tenant_id=tenant_id, case_id=case_id, bundle_id=bundle_id,
            amount=100.0, currency="USD", proposed_action="RECOVER",
            carrier=carrier, route="DAL-ATL", contract_rate=120.0,
        )
        confidence = rule_trace["weighted_average"]
        trace_bytes = canonicalize(rule_trace)
        fhash = _finding_hash(bundle_id, case_id, confidence, rule_trace, tenant_id)

        seen_traces.add(trace_bytes.hex())
        seen_hashes.add(fhash)

        if (i + 1) % max(1, args.runs // 10) == 0 or i == args.runs - 1:
            print(f"  run {i+1}/{args.runs}: confidence={confidence}  finding_hash={fhash[:16]}...")

    print()
    determinism_ok = len(seen_traces) == 1 and len(seen_hashes) == 1
    if determinism_ok:
        print(f"PASS — all {args.runs} runs produced byte-identical rule_trace and finding_hash.")
        print(f"  confidence: {confidence}")
        print(f"  finding_hash: {next(iter(seen_hashes))}")
        return 0
    else:
        print(f"FAIL — non-determinism detected.")
        print(f"  distinct rule_trace encodings: {len(seen_traces)}")
        print(f"  distinct finding_hash values: {len(seen_hashes)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
