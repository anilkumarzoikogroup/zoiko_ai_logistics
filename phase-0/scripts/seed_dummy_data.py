"""Seed dummy data for local development and testing.

Inserts one complete SC-001 case into the database:
  Tenant → Source Record → Validation → Canonical Invoice →
  Contract Rate → Case → Finding → Decision Proposal →
  Policy Bundle → Governance Decision → Approval Task →
  Governance Token → Execution Envelope → Reconciliation → Outcome → ACR

Run:
  set DB_URL=postgresql://postgres:yourpassword@localhost/zoiko
  py -3.13 scripts/seed_dummy_data.py
"""
import sys, os, hashlib, uuid, json
sys.path.insert(0, "packages/zoiko-common")

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
from zoiko_common.crypto.jcs import canonicalize
from zoiko_common.crypto.merkle import MerkleTree, hash_leaf
from zoiko_common.crypto.signing import ZoikoSigner, LocalEd25519Backend

DB_URL = os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost/zoiko")

# Fixed UUIDs so re-running seed is idempotent
TENANT_ID      = "11111111-1111-1111-1111-111111111111"
TENANT_KEY_ID  = "22222222-2222-2222-2222-222222222222"

def now():
    return datetime.now(timezone.utc)

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def connect():
    return psycopg2.connect(DB_URL)

def run(conn, sql, params=None):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        try:
            return cur.fetchone()
        except Exception:
            return None

def seed(conn):
    signer = ZoikoSigner(LocalEd25519Backend())
    pub_key = signer.public_key_der

    print("\n[1] Creating tenant: Zoiko Demo...")
    run(conn, """
        INSERT INTO tenants (id, slug, display_name, status)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (slug) DO NOTHING
    """, (TENANT_ID, "zoiko-demo", "Zoiko Demo Shipper", "ACTIVE"))

    print("[2] Creating tenant key entry...")
    run(conn, """
        INSERT INTO tenant_keys (id, tenant_id, key_purpose, kms_resource, key_ciphertext)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (TENANT_KEY_ID, TENANT_ID, "DEK_ENCRYPT",
          "local/dev/ingestion-key", pub_key))

    # --- Source record (the raw DHL invoice) ---
    print("[3] Creating source record (raw DHL invoice)...")
    raw_invoice = {
        "invoice_number": "DHL-2026-00441",
        "carrier": "DHL",
        "route": "DAL-ATL",
        "charges": {"fuel": 120.0, "accessorial": 100.0},
        "total": 220.0,
        "currency": "USD",
        "billed_at": "2026-05-17T09:00:00Z"
    }
    canonical_bytes  = canonicalize(raw_invoice)
    canonical_hash   = hash_leaf("zoiko/v1/source-record", canonical_bytes)
    envelope         = signer.sign(canonical_hash)
    src_id           = str(uuid.uuid4())

    run(conn, """
        INSERT INTO source_records
          (id, tenant_id, source_type, canonical_hash, ciphertext, signature, kid, idempotency_key)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
    """, (src_id, TENANT_ID, "CARRIER_INVOICE",
          canonical_hash,
          canonical_bytes,           # ciphertext: using canonical bytes as plaintext in dev
          envelope.signature,
          envelope.kid,
          "idem-sc001-source-001"))

    # --- Lineage record ---
    run(conn, """
        INSERT INTO lineage_records
          (id, tenant_id, entity_type, entity_id, event_type, payload_hash)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), TENANT_ID, "source_record", src_id,
          "CREATED", canonical_hash))

    # --- Validation result ---
    print("[4] Creating validation result (PASS)...")
    val_payload  = json.dumps({"status": "PASS", "violations": []}).encode()
    val_hash     = hash_leaf("zoiko/v1/validation-result", val_payload)
    val_envelope = signer.sign(val_hash)
    val_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO validation_results
          (id, tenant_id, source_record_id, status, rule_violations, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (val_id, TENANT_ID, src_id, "PASS",
          json.dumps([]), val_envelope.signature, val_envelope.kid))

    # --- Canonical invoice ---
    print("[5] Creating canonical invoice...")
    inv_payload  = canonicalize({
        "invoice_number": "DHL-2026-00441", "carrier_id": "DHL",
        "total_amount": 220.0, "currency": "USD"
    })
    inv_hash     = hash_leaf("zoiko/v1/canonical-invoice", inv_payload)
    inv_envelope = signer.sign(inv_hash)
    inv_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO canonical_invoices
          (id, tenant_id, source_record_id, invoice_number, carrier_id,
           total_amount, currency, canonical_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, invoice_number) DO NOTHING
    """, (inv_id, TENANT_ID, src_id,
          "DHL-2026-00441", "DHL", 220.0, "USD",
          inv_hash, inv_envelope.signature, inv_envelope.kid))

    # --- Contract rate ---
    print("[6] Creating contract rate (fuel $120/shipment)...")
    rate_id = str(uuid.uuid4())
    run(conn, """
        INSERT INTO contract_rates
          (id, tenant_id, carrier_id, rate_type, rate_value, currency, effective_on)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (rate_id, TENANT_ID, "DHL", "FUEL_SURCHARGE", 120.0, "USD", "2026-01-01"))

    # --- Case ---
    print("[7] Opening case SC-001...")
    case_id = str(uuid.uuid4())
    run(conn, """
        INSERT INTO cases (id, tenant_id, invoice_id, state)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (tenant_id, invoice_id) DO NOTHING
    """, (case_id, TENANT_ID, inv_id, "OPENED"))

    run(conn, """
        INSERT INTO case_events
          (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), TENANT_ID, case_id,
          "CASE_OPENED", None, "OPENED", "system", json.dumps({})))

    # --- Evidence bundle ---
    print("[8] Building evidence bundle...")
    bundle_payload  = json.dumps({"items": [src_id, val_id, inv_id]}).encode()
    bundle_hash     = hash_leaf("zoiko/v1/evidence-bundle", bundle_payload)
    bundle_envelope = signer.sign(bundle_hash)
    bundle_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO evidence_bundles
          (id, tenant_id, case_id, bundle_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (bundle_id, TENANT_ID, case_id,
          bundle_hash, bundle_envelope.signature, bundle_envelope.kid))

    for etype, eid, ehash in [
        ("source_record",    src_id, canonical_hash),
        ("validation_result",val_id, val_hash),
        ("canonical_invoice",inv_id, inv_hash),
    ]:
        run(conn, """
            INSERT INTO evidence_items
              (id, tenant_id, bundle_id, item_type, entity_id, item_hash)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (str(uuid.uuid4()), TENANT_ID, bundle_id, etype, eid, ehash))

    # --- Finding ---
    print("[9] Creating finding (confidence=0.96, accessorial=OVERCHARGE)...")
    rule_trace = {
        "fuel_charge":       {"billed": 120.0, "contract": 120.0, "delta": 0.0,   "status": "OK",         "confidence": 1.00},
        "accessorial_charge":{"billed": 100.0, "contract": 0.0,   "delta": 100.0, "status": "OVERCHARGE", "confidence": 0.92},
        "combined_confidence": 0.96
    }
    finding_payload  = canonicalize(rule_trace)
    finding_hash     = hash_leaf("zoiko/v1/finding", finding_payload)
    finding_envelope = signer.sign(finding_hash)
    finding_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO findings
          (id, tenant_id, case_id, bundle_id, confidence, rule_trace, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (finding_id, TENANT_ID, case_id, bundle_id,
          0.96, json.dumps(rule_trace),
          finding_envelope.signature, finding_envelope.kid))

    # --- Decision proposal ---
    print("[10] Creating decision proposal (recover $100)...")
    proposal_payload  = canonicalize({"action": "RECOVER", "amount": 100.0, "currency": "USD"})
    proposal_hash     = hash_leaf("zoiko/v1/decision-proposal", proposal_payload)
    proposal_envelope = signer.sign(proposal_hash)
    proposal_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO decision_proposals
          (id, tenant_id, case_id, finding_id, proposed_action,
           amount, currency, proposer_sub, proposal_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (proposal_id, TENANT_ID, case_id, finding_id,
          "RECOVER", 100.0, "USD", "analyst@zoikotech.com",
          proposal_hash, proposal_envelope.signature, proposal_envelope.kid))

    run(conn, """
        INSERT INTO case_events
          (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), TENANT_ID, case_id,
          "PROPOSAL_CREATED", "OPENED", "UNDER_REVIEW",
          "analyst@zoikotech.com", json.dumps({"proposal_id": proposal_id})))

    # --- Policy bundle ---
    print("[11] Creating active policy bundle...")
    policy_id = str(uuid.uuid4())
    run(conn, """
        INSERT INTO policy_bundles
          (id, tenant_id, version, rego_hash, active)
        VALUES (%s,%s,%s,%s,%s)
    """, (policy_id, TENANT_ID, "v1.2",
          sha256(b"package zoiko.recovery\ndefault allow = false"), True))

    # --- Governance decision (Human A approves) ---
    print("[12] Human A approves (governance decision)...")
    gov_payload  = canonicalize({"outcome": "APPROVED", "policy_version": "v1.2"})
    gov_hash     = hash_leaf("zoiko/v1/governance-decision", gov_payload)
    gov_envelope = signer.sign(gov_hash)
    gov_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO governance_decisions
          (id, tenant_id, proposal_id, policy_bundle_id,
           outcome, decision_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (gov_id, TENANT_ID, proposal_id, policy_id,
          "APPROVED", gov_hash, gov_envelope.signature, gov_envelope.kid))

    # --- Approval task (Human B signs off — different person = SoD) ---
    print("[13] Human B signs off (separation of duties)...")
    task_id = str(uuid.uuid4())
    run(conn, """
        INSERT INTO approval_tasks
          (id, tenant_id, proposal_id, proposer_sub, actor_sub, status, actioned_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (task_id, TENANT_ID, proposal_id,
          "analyst@zoikotech.com",   # proposer
          "manager@zoikotech.com",   # approver — DIFFERENT PERSON (SoD enforced)
          "APPROVED", now()))

    # --- Governance token ---
    print("[14] Issuing governance token...")
    tenant_binding = sha256((TENANT_ID + gov_id).encode())
    token_payload  = canonicalize({
        "scope": "EXECUTE", "tenant_id": TENANT_ID,
        "decision_id": gov_id, "amount": 100.0
    })
    token_hash     = hash_leaf("zoiko/v1/governance-token", token_payload)
    token_envelope = signer.sign(token_hash)
    token_id       = str(uuid.uuid4())
    expires_at     = now() + timedelta(hours=24)

    run(conn, """
        INSERT INTO governance_tokens
          (id, tenant_id, decision_id, scope, tenant_binding,
           status, expires_at, token_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (token_id, TENANT_ID, gov_id,
          "EXECUTE", tenant_binding, "ACTIVE", expires_at,
          token_hash, token_envelope.signature, token_envelope.kid))

    # --- Execution envelope (8-gate results) ---
    print("[15] Executing recovery through 8-gate gateway...")
    gate_results = {
        "gate_1_token_sig_valid":   "PASS",
        "gate_2_not_expired":       "PASS",
        "gate_3_tenant_binding":    "PASS",
        "gate_4_scope_matches":     "PASS",
        "gate_5_sanctions":         "PASS (CLEAR)",
        "gate_6_fx_lock":           "PASS (USD/USD = 1.0)",
        "gate_7_connector_cert":    "PASS (DHL-CONNECTOR v2.1 CERTIFIED)",
        "gate_8_idempotency":       "PASS (new key)"
    }
    env_payload  = canonicalize(gate_results)
    env_hash     = hash_leaf("zoiko/v1/execution-envelope", env_payload)
    env_envelope = signer.sign(env_hash)
    exec_id      = str(uuid.uuid4())

    run(conn, """
        INSERT INTO execution_envelopes
          (id, tenant_id, token_id, case_id, gate_results, status, env_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (exec_id, TENANT_ID, token_id, case_id,
          json.dumps(gate_results), "CONFIRMED",
          env_hash, env_envelope.signature, env_envelope.kid))

    run(conn, """
        INSERT INTO idempotency_keys
          (id, tenant_id, key_value, status, completed_at)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (tenant_id, key_value) DO NOTHING
    """, (str(uuid.uuid4()), TENANT_ID,
          "exec-sc001-dhl-2026-00441", "COMPLETE", now()))

    run(conn, """
        INSERT INTO connector_responses
          (id, tenant_id, envelope_id, connector_id, status_code, response_body)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), TENANT_ID, exec_id,
          "DHL-CARRIER-API", 200,
          json.dumps({"credit_reference": "CR-88221", "status": "ACCEPTED"})))

    # Token consumed after execution
    run(conn, """
        UPDATE governance_tokens SET status = 'CONSUMED', consumed_at = %s WHERE id = %s
    """, (now(), token_id))

    # --- Reconciliation ---
    print("[16] Reconciling: confirming $100 credit received...")
    recon_payload  = canonicalize({"delta": -100.0, "currency": "USD", "ref": "CR-88221"})
    recon_hash     = hash_leaf("zoiko/v1/reconciliation", recon_payload)
    recon_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO reconciliations
          (id, tenant_id, case_id, envelope_id, delta_amount, currency, recon_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (recon_id, TENANT_ID, case_id, exec_id, -100.0, "USD", recon_hash))

    # --- Outcome ---
    print("[17] Recording outcome...")
    outcome_payload  = canonicalize({"recovered": 100.0, "currency": "USD"})
    outcome_hash     = hash_leaf("zoiko/v1/outcome", outcome_payload)
    outcome_envelope = signer.sign(outcome_hash)
    outcome_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO outcomes
          (id, tenant_id, case_id, recon_id, outcome_type,
           outcome_hash, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (outcome_id, TENANT_ID, case_id, recon_id,
          "RECOVERY_COMPLETE", outcome_hash,
          outcome_envelope.signature, outcome_envelope.kid))

    # --- ACR: build Merkle tree over all 8 artifacts ---
    print("[18] Building ACR Merkle tree (8 artifacts)...")
    tree = MerkleTree("zoiko/v1/acr")
    artifact_hashes = {}
    for art_name, art_hash in [
        ("source_record",       canonical_hash),
        ("validation_result",   val_hash),
        ("canonical_invoice",   inv_hash),
        ("finding",             finding_hash),
        ("decision_proposal",   proposal_hash),
        ("governance_decision", gov_hash),
        ("governance_token",    token_hash),
        ("outcome",             outcome_hash),
    ]:
        tree.append(art_hash)
        artifact_hashes[art_name] = art_hash.hex()

    merkle_root  = tree.root()
    acr_payload  = canonicalize({"merkle_root": merkle_root.hex(), "case_id": case_id})
    acr_envelope = signer.sign(merkle_root)
    acr_id       = str(uuid.uuid4())

    run(conn, """
        INSERT INTO action_certification_records
          (id, tenant_id, case_id, acr_version,
           merkle_root, artifact_hashes, signature, kid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (acr_id, TENANT_ID, case_id, "v1",
          merkle_root,
          json.dumps(artifact_hashes),
          acr_envelope.signature, acr_envelope.kid))

    run(conn, """
        INSERT INTO audit_worm_index
          (id, tenant_id, acr_id, worm_bucket, object_name, object_hash)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), TENANT_ID, acr_id,
          "zoiko-logistics-dev-worm",
          f"acr-verify-sc001/{acr_id}.zip",
          sha256(merkle_root)))

    run(conn, "UPDATE cases SET state = 'CLOSED', closed_at = %s WHERE id = %s",
        (now(), case_id))

    conn.commit()

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  SEED COMPLETE — SC-001 case fully seeded")
    print("=" * 60)
    print(f"  tenant_id    : {TENANT_ID}")
    print(f"  case_id      : {case_id}")
    print(f"  invoice      : DHL-2026-00441 ($220 billed)")
    print(f"  overcharge   : $100.00 accessorial (unauthorized)")
    print(f"  confidence   : 0.96")
    print(f"  approved by  : analyst@zoikotech.com + manager@zoikotech.com")
    print(f"  merkle_root  : {merkle_root.hex()[:32]}...")
    print(f"  acr_id       : {acr_id}")
    print(f"  case_state   : CLOSED")
    print()
    print("  Run this to verify in psql:")
    print("  SELECT table_name, (SELECT count(*) FROM information_schema.tables")
    print("    WHERE table_schema='public') AS total_tables FROM information_schema.tables")
    print("    WHERE table_schema='public' LIMIT 1;")

if __name__ == "__main__":
    print(f"Connecting to: {DB_URL.split('@')[-1]}")
    try:
        conn = connect()
        print("Connected OK.")
        seed(conn)
        conn.close()
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nMake sure PostgreSQL is running and DB_URL is set correctly.")
        print("  set DB_URL=postgresql://postgres:yourpassword@localhost/zoiko")
        sys.exit(1)
