import psycopg2, psycopg2.extras, os

conn = psycopg2.connect(os.environ.get("DB_URL", "postgresql://postgres:1234@localhost/zoiko"))
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 60)
print("TENANTS")
print("=" * 60)
cur.execute("SELECT id, display_name, slug, status, created_at FROM tenants ORDER BY created_at")
for r in cur.fetchall():
    print(f"  ID     : {r['id']}")
    print(f"  Name   : {r['display_name']}")
    print(f"  Slug   : {r['slug']}")
    print(f"  Status : {r['status']}")
    print(f"  Created: {r['created_at']}")
    print()

print("=" * 60)
print("USERS")
print("=" * 60)
cur.execute("""
    SELECT u.id, u.full_name, u.email, u.role, u.is_active, u.created_at,
           t.display_name AS tenant
    FROM   users u
    JOIN   tenants t ON t.id = u.tenant_id
    ORDER  BY u.created_at
""")
rows = cur.fetchall()
print(f"Total users: {len(rows)}")
print()
for r in rows:
    status = "ACTIVE" if r['is_active'] else "INACTIVE"
    print(f"  [{r['role'].upper():8}] {r['full_name']:25} | {r['email']:35} | {status} | tenant: {r['tenant']}")

print()
print("=" * 60)
print("CASES (last 5)")
print("=" * 60)
cur.execute("""
    SELECT c.id, c.state, c.opened_at,
           t.display_name AS tenant
    FROM   cases c
    JOIN   tenants t ON t.id = c.tenant_id
    ORDER  BY c.opened_at DESC
    LIMIT  5
""")
for r in cur.fetchall():
    print(f"  {str(r['id'])[:8]}... | {r['state']:25} | {r['tenant']} | {r['opened_at']}")

conn.close()
print()
print("DB check complete.")
