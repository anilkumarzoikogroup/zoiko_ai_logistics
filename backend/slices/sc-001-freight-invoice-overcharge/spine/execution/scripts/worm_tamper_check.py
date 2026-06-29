"""
WORM tamper-proof check (SC-001 acceptance criterion):
"Audit-log streaming to WORM with a dedicated tamper-proof check."

For every audit_worm_index row, independently:
  1. Recomputes the ACR's signed hash from action_certification_records
     .artifact_hashes (the same verify bundle the offline verifier checks)
     and confirms the Ed25519 signature and Merkle root still verify.
  2. Confirms the WORM index's own object_hash still matches that recomputed
     hash — catching tampering of the WORM index row independent of the ACR
     row it points at.

LIMITATION: this checks what's verifiable from the database today. A real
production WORM bucket additionally guarantees the *uploaded object* itself
can't be altered (S3 Object Lock / GCS Bucket Lock) — once a real bucket is
wired up, this script should also fetch the object and re-hash it; right now
there is no real bucket to fetch from (see AuditACRHandler._resolve_worm_bucket).

Run:
  cd backend/slices/sc-001-freight-invoice-overcharge/spine/execution
  DB_URL=... python scripts/worm_tamper_check.py [--tenant-id UUID]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..")))

import psycopg2          # noqa: E402
import psycopg2.extras   # noqa: E402
psycopg2.extras.register_uuid()

from services.audit_acr_svc.verifier import verify_bundle  # noqa: E402
from zoiko_common.crypto.jcs import canonicalize as _jcs    # noqa: E402

_ACR_DOMAIN_TAG = b"zoiko/v1/acr"


def _recompute_acr_hash(bundle: dict) -> str:
    payload_dict = {
        "artifacts":   [{"name": a["name"], "hash": a["hash"]} for a in bundle.get("artifacts", [])],
        "case_id":     bundle.get("case_id", ""),
        "merkle_root": bundle.get("merkle_root", ""),
        "tenant_id":   bundle.get("tenant_id", ""),
    }
    return hashlib.sha256(_ACR_DOMAIN_TAG + _jcs(payload_dict)).hexdigest()


def check_worm_row(bundle: dict, worm_object_hash_hex: str) -> dict:
    """Pure function — no DB access — so it's independently testable."""
    result   = verify_bundle(bundle)
    acr_hash = _recompute_acr_hash(bundle)
    worm_hash_match = (acr_hash == worm_object_hash_hex)
    return {
        "signature_valid":   result.signature_valid,
        "merkle_root_match": result.merkle_root_match,
        "worm_hash_match":   worm_hash_match,
        "passed":            result.passed and worm_hash_match,
        "errors":            result.errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", default=None)
    args = ap.parse_args()

    db_url = os.environ["DB_URL"]
    conn = psycopg2.connect(db_url)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT w.id AS worm_id, w.object_hash, w.worm_bucket, w.object_name,
               a.id AS acr_id, a.artifact_hashes
        FROM audit_worm_index w
        JOIN action_certification_records a ON a.id = w.acr_id
    """
    params: tuple = ()
    if args.tenant_id:
        sql += " WHERE a.tenant_id = %s::uuid"
        params = (args.tenant_id,)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No audit_worm_index rows found.")
        return 0

    failures = []
    for r in rows:
        bundle = r["artifact_hashes"]
        if isinstance(bundle, str):
            bundle = json.loads(bundle)

        outcome = check_worm_row(bundle, bytes(r["object_hash"]).hex())
        if outcome["passed"]:
            continue
        failures.append({"acr_id": str(r["acr_id"]), "worm_id": str(r["worm_id"]), **outcome})

    total = len(rows)
    print(f"Checked {total} WORM index entries: {total - len(failures)} PASS, {len(failures)} FAIL")
    for f in failures:
        print(f"  FAIL acr_id={f['acr_id']} worm_id={f['worm_id']} "
              f"sig_valid={f['signature_valid']} merkle_match={f['merkle_root_match']} "
              f"worm_hash_match={f['worm_hash_match']} errors={f['errors']}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
