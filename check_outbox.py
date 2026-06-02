import psycopg2
conn = psycopg2.connect("postgresql://postgres:1234@localhost/zoiko")
cur  = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='outbox' ORDER BY ordinal_position")
print("outbox columns:")
for r in cur.fetchall():
    print(f"  {r[0]:30} {r[1]}")
conn.close()
