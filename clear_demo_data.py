"""
Clears all demo/seed data from the database.
Keeps: real tenant (zoiko-demo), users, contract_rates structure.
Removes: all cases, invoices, source records, evidence, findings, tokens — everything.

Run: python clear_demo_data.py
"""
import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DB_URL"])
cur  = conn.cursor()

print("Clearing demo data...")

# Disable FK checks so we can delete in any order
cur.execute("SET session_replication_role = 'replica'")

TABLES = [
    "audit_worm_index",
    "action_certification_records",
    "reconciliations",
    "execution_envelopes",
    "governance_tokens",
    "approval_requests",
    "approval_tasks",
    "governance_decisions",
    "decision_proposals",
    "findings",
    "reasoning_traces",
    "action_intents",
    "evidence_items",
    "evidence_bundles",
    "case_events",
    "cases",
    "validation_results",
    "lineage_records",
    "canonical_shipments",
    "canonical_invoices",
    "source_records",
    "contract_rates",
    "outbox",
    "certification_runs",
    "tenant_keys",
]

for table in TABLES:
    try:
        cur.execute(f"DELETE FROM {table}")
        print(f"  Cleared: {table:35s} ({cur.rowcount} rows)")
    except Exception as e:
        print(f"  SKIP:    {table:35s} (not found or error — {e})")
        conn.rollback()
        cur.execute("SET session_replication_role = 'replica'")

# Remove dummy tenants (keep only the one with users)
cur.execute("DELETE FROM tenants WHERE id NOT IN (SELECT DISTINCT tenant_id FROM users)")
print(f"  Removed dummy tenants:                    ({cur.rowcount} rows)")

# Re-enable FK checks
cur.execute("SET session_replication_role = 'origin'")

conn.commit()
conn.close()

print("\nDone. Database is clean.")
print("Login at http://localhost:5173 and submit a real invoice to start.")
