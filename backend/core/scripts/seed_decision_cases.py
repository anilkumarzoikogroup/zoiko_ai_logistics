"""
Seed 10 decision cases (5 overcharge, 5 undercharge) into the database.
Run AFTER alembic migrations have been applied.

Usage:
    cd backend\core
    python scripts/seed_decision_cases.py
"""
import psycopg2, uuid, os, sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Windows console encoding workaround
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

DB_URL = os.getenv("DB_URL", "postgresql://postgres:1234@localhost/zoiko")

conn = psycopg2.connect(DB_URL)
cur  = conn.cursor()

# â”€â”€ Find or create a tenant â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
cur.execute("SELECT id, slug FROM tenants ORDER BY created_at LIMIT 1")
row = cur.fetchone()
if row:
    TENANT_ID = row[0]
    SLUG      = row[1]
    print(f"Using existing tenant: {SLUG}  ({TENANT_ID})")
else:
    TENANT_ID = uuid.uuid4()
    SLUG      = "seed-demo"
    cur.execute(
        "INSERT INTO tenants (id, slug, display_name, status, created_at, updated_at)"
        " VALUES (%s, %s, %s, 'ACTIVE', NOW(), NOW())",
        (str(TENANT_ID), SLUG, "Seed Demo"),
    )
    print(f"Created tenant: {SLUG}  ({TENANT_ID})")

# â”€â”€ 10 test cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 5 overcharge (diff > 0), 5 undercharge (diff < 0)
CARRIERS = ["BlueDart", "DHL", "FedEx", "DTDC", "Ekart",
            "BlueDart", "DHL", "FedEx", "DTDC", "Ekart"]
CITIES   = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata",
            "Hyderabad", "Pune", "Ahmedabad", "Jaipur", "Lucknow"]
STATES   = ["NEW", "EVIDENCE_PENDING", "FINDING_GENERATED",
            "APPROVAL_PENDING", "EXECUTION_READY", "DISPATCHED", "CLOSED"]
NOW      = datetime.now(timezone.utc).replace(tzinfo=None)

for i in range(10):
    is_overcharge   = i < 5
    carrier         = CARRIERS[i]
    contract_amount = 8000.0
    if is_overcharge:
        billed_amount = 13000.0 - (i * 300)
        delta         = billed_amount - contract_amount  # +5000, +4700, +4400, +4100, +3800
    else:
        billed_amount = 8000.0 - ((i - 4) * 200)         # 7800, 7600, 7400, 7200, 7000
        delta         = billed_amount - contract_amount  # -200, -400, -600, -800, -1000
    origin_city     = CITIES[i]
    dest_city       = CITIES[9 - i]
    invoice_number  = f"INV-SEED-{(i+1):04d}"
    opened_days_ago = i + 1
    opened_at       = NOW - timedelta(days=opened_days_ago)
    state           = STATES[i % len(STATES)]
    confidence      = round(0.70 + (i * 0.03), 2)  # 0.70, 0.73, 0.76... 0.97

    SRC_ID    = str(uuid.uuid4())
    INV_ID    = str(uuid.uuid4())
    SHIP_ID   = str(uuid.uuid4())
    VAL_ID    = str(uuid.uuid4())
    CASE_ID   = str(uuid.uuid4())
    BUNDLE_ID = str(uuid.uuid4())
    FIND_ID   = str(uuid.uuid4())
    EVENT_ID  = str(uuid.uuid4())

    # source_record
    cur.execute("""
        INSERT INTO source_records (id, tenant_id, source_type, canonical_hash, ciphertext, signature, kid, idempotency_key, created_at)
        VALUES (%s, %s, 'edi', decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                'seed-key', %s, %s)
    """, (SRC_ID, str(TENANT_ID), i+1, i+100, i+200, f"seed-idem-{i}", opened_at))

    # canonical_invoice
    cur.execute("""
        INSERT INTO canonical_invoices (id, tenant_id, source_record_id, invoice_number, carrier_id, total_amount, currency, canonical_hash, signature, kid, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'INR',
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                'seed-key', %s)
    """, (INV_ID, str(TENANT_ID), SRC_ID, invoice_number, carrier, billed_amount, i+300, i+400, opened_at))

    # canonical_shipment
    cur.execute("""
        INSERT INTO canonical_shipments (id, tenant_id, invoice_id, origin_city, dest_city, weight_lbs, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (SHIP_ID, str(TENANT_ID), INV_ID, origin_city, dest_city, 1000.0 + i * 100, opened_at))

    # validation_result â€” diff comes from this (subquery where status='FAIL')
    cur.execute("""
        INSERT INTO validation_results (id, tenant_id, source_record_id, status, rule_violations, signature, kid, validated_at)
        VALUES (%s, %s, %s, 'FAIL',
                jsonb_build_array(jsonb_build_object(
                    'rule', 'contract_rate_check',
                    'delta', %s,
                    'billed', %s,
                    'contract', %s
                )),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                'seed-key', %s)
    """, (VAL_ID, str(TENANT_ID), SRC_ID, delta, billed_amount, contract_amount, i+500, opened_at))

    # case
    cur.execute("""
        INSERT INTO cases (id, tenant_id, invoice_id, state, opened_at, version)
        VALUES (%s, %s, %s, %s, %s, 1)
    """, (CASE_ID, str(TENANT_ID), INV_ID, state, opened_at))

    # evidence_bundle â€” needed by findings FK
    cur.execute("""
        INSERT INTO evidence_bundles (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
        VALUES (%s, %s, %s,
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                'seed-key', %s)
    """, (BUNDLE_ID, str(TENANT_ID), CASE_ID, i+600, i+700, opened_at))

    # finding â€” provides confidence in UI
    cur.execute("""
        INSERT INTO findings (id, tenant_id, case_id, bundle_id, confidence, ai_confidence, risk_level, ai_reasoning, rule_trace, signature, kid, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'MEDIUM', '[]',
                jsonb_build_object(
                    'fuel_charge', jsonb_build_object('confidence', 1.0, 'weight', 0.5),
                    'accessorial', jsonb_build_object('confidence', 0.92, 'weight', 0.5)
                ),
                decode(lpad(to_hex(%s), 64, '0'), 'hex'),
                'seed-key', %s)
    """, (FIND_ID, str(TENANT_ID), CASE_ID, BUNDLE_ID, confidence, confidence, i+800, opened_at))

    # case_event â€” append-only audit trail
    cur.execute("""
        INSERT INTO case_events (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
        VALUES (%s, %s, %s, 'CASE_OPENED', NULL, 'NEW', 'seed-script',
                jsonb_build_object('source', 'seed_decision_script'), %s)
    """, (EVENT_ID, str(TENANT_ID), CASE_ID, opened_at))

    tag = "OVERCHARGE" if is_overcharge else "UNDERCHARGE"
    print(f"  [{tag:>11}] {carrier:>8} | {invoice_number} | â‚¹{billed_amount:>7,.0f} | Î” {delta:>+7,.0f} | {state:>18} | {confidence:.0%} confidence")

conn.commit()
conn.close()
print("\nDone. 10 decision cases seeded. Go to the Decision page in the UI.")
