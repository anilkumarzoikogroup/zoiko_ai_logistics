"""
Seed contract rates for amazon-india tenant.
Populates both carrier_id (backward compat) and lane_hash (spec §8.1).

Run AFTER starting the backend (so the tenant exists):
    $env:DB_URL = "postgresql://postgres:1234@localhost/zoiko"
    cd phase-2
    python seed_contract_rates.py
"""
import os, sys, uuid, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import paths  # noqa

from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()

DB_URL = os.getenv("DB_URL")

# Agreed rates per carrier for amazon-india
# rate_value = maximum allowed charge (INR) per shipment
RATES = [
    ("BlueDart",   "FUEL_CHARGE", 8000.00,  "INR"),
    ("Delhivery",  "FUEL_CHARGE", 7500.00,  "INR"),
    ("FedEx",      "FUEL_CHARGE", 9200.00,  "INR"),
    ("DTDC",       "FUEL_CHARGE", 6500.00,  "INR"),
    ("Ekart",      "FUEL_CHARGE", 7000.00,  "INR"),
    ("Gati",       "FUEL_CHARGE", 6800.00,  "INR"),
    ("UPS India",  "FUEL_CHARGE", 10500.00, "INR"),
]

def seed():
    psycopg2.extras.register_uuid()
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Find amazon-india tenant
    cur.execute("SELECT id, slug FROM tenants WHERE slug = 'amazon-india' OR slug LIKE '%amazon%' LIMIT 1")
    row = cur.fetchone()
    if not row:
        # Try any active tenant
        cur.execute("SELECT id, slug FROM tenants WHERE status = 'ACTIVE' ORDER BY created_at LIMIT 1")
        row = cur.fetchone()
    if not row:
        print("ERROR: No tenant found. Start the backend first with ZOIKO_DEV_MODE=true, then run this script.")
        conn.close()
        sys.exit(1)

    tenant_id, slug = str(row[0]), row[1]
    print(f"Seeding contract rates for tenant: {slug} ({tenant_id})")

    inserted = 0
    skipped  = 0
    for carrier, rate_type, rate_value, currency in RATES:
        cur.execute("""
            SELECT id FROM contract_rates
            WHERE tenant_id = %s::uuid AND carrier_id = %s AND rate_type = %s
        """, (tenant_id, carrier, rate_type))
        exists = cur.fetchone()
        if exists:
            print(f"  [skip] {carrier} {rate_type} already exists")
            skipped += 1
            continue
        # Compute lane_hash per spec §8.1: SHA-256("zoiko/v1/lane:" + carrier + "|" + currency)
        lane_hash = "sha256:" + hashlib.sha256(
            f"zoiko/v1/lane:{carrier}|{currency}".encode()
        ).hexdigest()
        cur.execute("""
            INSERT INTO contract_rates
                (id, tenant_id, carrier_id, rate_type, rate_value, currency, effective_on,
                 lane_hash, base_rate, effective_from)
            VALUES (%s, %s::uuid, %s, %s, %s, %s, '2025-01-01', %s, %s, '2025-01-01')
        """, (uuid.uuid4(), tenant_id, carrier, rate_type, rate_value, currency,
              lane_hash, rate_value))
        print(f"  [ok]   {carrier:12s} {rate_type:15s} {currency} {rate_value:>10,.2f}")
        inserted += 1

    conn.close()
    print(f"\nDone — {inserted} rates inserted, {skipped} already existed.")
    print("\nNow when you submit a BlueDart invoice for $12,500:")
    print("  Contract rate = $8,000")
    print("  Overcharge    = $4,500  ← FAIL detected automatically")

if __name__ == "__main__":
    seed()
