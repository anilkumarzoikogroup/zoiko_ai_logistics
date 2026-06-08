"""
DDL: carriers table, users.title, tenants.address fields.
Run: python scripts/ddl_carriers_profile.py
"""
import os, sys, psycopg2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import DB_URL

DDL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''",

    """CREATE TABLE IF NOT EXISTS carriers (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL DEFAULT '',
        address         TEXT NOT NULL DEFAULT '',
        contact_person  TEXT NOT NULL DEFAULT '',
        contact_phone   TEXT NOT NULL DEFAULT '',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",

    "ALTER TABLE carriers ADD CONSTRAINT IF NOT EXISTS uq_carrier_tenant UNIQUE (tenant_id, name)",

    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS address TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS city TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS pincode TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT ''",
]

def run():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL:
        try:
            cur.execute(stmt)
            print(f"  OK: {stmt[:70]}...")
        except Exception as e:
            print(f"  SKIP ({e}): {stmt[:60]}...")
    cur.close()
    conn.close()
    print("Done — schema updated.")

if __name__ == "__main__":
    run()
