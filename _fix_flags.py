import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ["DB_URL"])
cur = conn.cursor()

# Find the feature flags table
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    AND (table_name LIKE '%flag%' OR table_name LIKE '%feature%')
""")
print("Feature tables:", [r[0] for r in cur.fetchall()])

# Check tenant_feature_flags or feature_flags
for tbl in ("tenant_feature_flags", "feature_flags", "feature_flag_enrollments"):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"{tbl}: {cur.fetchone()[0]} rows")
        cur.execute(f"SELECT * FROM {tbl} LIMIT 3")
        cols = [d[0] for d in cur.description]
        print("  columns:", cols)
        for row in cur.fetchall():
            print("  ", dict(zip(cols, row)))
    except Exception as e:
        print(f"{tbl}: not found ({e})")
        conn.rollback()

conn.close()
