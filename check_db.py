import psycopg2, psycopg2.extras, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ["DB_URL"])
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 60)
print("TENANTS")
print("=" * 60)
cur.execute("SELECT id, display_name, slug, status FROM tenants")
for r in cur.fetchall():
    print(f"  {r['display_name']} | {r['slug']} | {r['status']}")

print()
print("=" * 60)
print("USERS")
print("=" * 60)
cur.execute("SELECT email, role, is_active FROM users ORDER BY role")
for r in cur.fetchall():
    print(f"  [{r['role'].upper():8}] {r['email']} | active={r['is_active']}")

print()
print("=" * 60)
print("CASES (latest 10)")
print("=" * 60)
cur.execute("""
    SELECT c.id::text, c.state, c.opened_at::text,
           ci.carrier_id AS carrier, ci.total_amount, ci.currency
    FROM   cases c
    JOIN   canonical_invoices ci ON ci.id = c.invoice_id
    ORDER  BY c.opened_at DESC LIMIT 10
""")
rows = cur.fetchall()
print(f"  Total cases: {len(rows)}")
for r in rows:
    print(f"  {r['id'][:8]}... | {r['state']:25} | {r['carrier']:12} | {r['total_amount']} {r['currency']}")

print()
print("=" * 60)
print("CONTRACT RATES")
print("=" * 60)
cur.execute("SELECT carrier_id, rate_type, rate_value, currency FROM contract_rates LIMIT 10")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r['carrier_id']:15} | {r['rate_type']:15} | {r['rate_value']} {r['currency']}")
else:
    print("  No contract rates yet")

conn.close()
print()
print("All data stored in: Neon PostgreSQL (cloud)")
