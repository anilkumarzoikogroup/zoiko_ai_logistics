"""
One-time script: creates the default admin, manager, and analyst users in the DB.
Run once after migrations are applied:
    python scripts/seed_users.py
"""
import psycopg2, bcrypt, uuid, os
from dotenv import load_dotenv

load_dotenv()

db = os.environ["DB_URL"]
conn = psycopg2.connect(db)
cur = conn.cursor()

cur.execute("SELECT id FROM tenants WHERE status='ACTIVE' ORDER BY created_at LIMIT 1")
row = cur.fetchone()
if not row:
    # No tenant exists — create the default one automatically
    print("No tenant found — creating default tenant...")
    tenant_id = str(uuid.uuid4())
    company   = os.getenv("ZOIKO_COMPANY_NAME", "Zoiko")
    slug      = company.lower().replace(" ", "-")
    cur.execute(
        "INSERT INTO tenants (id, display_name, slug, status) VALUES (%s, %s, %s, 'ACTIVE')"
        " ON CONFLICT DO NOTHING",
        (tenant_id, company, slug),
    )
    print(f"  Created tenant: {company} (id={tenant_id})")
else:
    tenant_id = str(row[0])
    print(f"  Using existing tenant: {tenant_id}")

USERS = [
    ("lennox@zoiko.com", "Lennox", "admin",   "Lennox@123"),
    ("venky@zoiko.com",  "Venky",  "manager", "Venky@123"),
    ("anil@zoiko.com",   "Anil",   "analyst", "Anil@123"),
]

for email, name, role, pw in USERS:
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        print(f"  Already exists: {email}")
        continue
    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    cur.execute(
        "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (str(uuid.uuid4()), tenant_id, email, pw_hash, name, role),
    )
    print(f"  Created [{role}]: {email}  /  {pw}")

conn.commit()
conn.close()
print("\nDone. Login at http://localhost:5173")
