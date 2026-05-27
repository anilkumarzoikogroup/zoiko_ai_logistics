"""Minimal CI seed: create the amazon-india tenant so contract rates can be inserted."""
import os
import psycopg2

DB_URL = os.environ["DB_URL"]

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
    INSERT INTO tenants (id, slug, display_name, status)
    VALUES ('11111111-1111-1111-1111-111111111111', 'amazon-india', 'Amazon India', 'ACTIVE')
    ON CONFLICT (slug) DO NOTHING
""")
conn.close()
print("Tenant amazon-india ready.")
