"""Extend all ACTIVE governance tokens by 24 hours so they can be executed."""
import psycopg2, datetime, os

db = os.environ.get("DB_URL", "postgresql://postgres:1234@localhost/zoiko")
conn = psycopg2.connect(db)
cur  = conn.cursor()

new_exp = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
cur.execute("UPDATE governance_tokens SET expires_at = %s WHERE status = 'ACTIVE'", (new_exp,))
print(f"Extended {cur.rowcount} tokens. New expiry (UTC): {new_exp}")
conn.commit()
conn.close()
print("Done.")
