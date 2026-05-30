"""
One-time script: creates admin, analyst, and manager users in the DB.
Run once after the first migration:
    python seed_users.py
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
    print("ERROR: No tenant found.")
    exit(1)

tenant_id = row[0]

USERS = [
    (os.getenv("ZOIKO_ADMIN_EMAIL",    "admin@zoiko.com"),   os.getenv("ZOIKO_ADMIN_NAME",    "Platform Admin"),  "admin",   os.getenv("ZOIKO_ADMIN_PASSWORD", "changeme123")),
    ("analyst@zoiko.com", "Freight Analyst", "analyst", "analyst123"),
    ("manager@zoiko.com", "Finance Manager", "manager", "manager123"),
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
