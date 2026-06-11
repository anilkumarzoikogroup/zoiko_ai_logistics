"""
Clears all demo/seed data from the database (Neon-compatible — no superuser needed).
Keeps: tenants that have users, users, alembic_version.
Removes: all cases, invoices, source records, evidence, findings, tokens — everything.

Run:
  $env:DB_URL = "postgresql://..."
  python clear_demo_data.py
"""
import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DB_URL")
if not DB_URL:
    raise SystemExit("DB_URL env var not set.")

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur  = conn.cursor()

print("Clearing all demo/seed data...\n")

# Delete in strict child-before-parent order to satisfy FK constraints.
# Each DELETE is wrapped individually so a missing table doesn't abort the batch.

ORDERED = [
    # ── deepest leaves first ──────────────────────────────────────────────────
    "audit_worm_index",
    "action_certification_records",
    "reconciliations",
    "execution_envelopes",
    "variance_records",
    "governance_tokens",
    "approval_requests",
    "approval_tasks",
    "governance_decisions",
    "decision_proposals",
    "reasoning_traces",
    "action_intents",
    "findings",
    "evidence_items",
    "evidence_bundles",
    "case_events",
    "validation_results",
    "cases",
    # ── ingestion / canonical ─────────────────────────────────────────────────
    "lineage_records",
    "canonical_shipments",
    "canonical_invoices",
    "batch_records",
    "batch_artifacts",
    "ambiguity_queue",
    "dedup_index",
    "source_records",
    # ── config / misc ─────────────────────────────────────────────────────────
    "validation_rule_sets",
    "connector_responses",
    "contract_rates",
    "outbox",
    "certification_runs",
    "tenant_keys",
    "kafka_events",
]

total = 0
for table in ORDERED:
    try:
        cur.execute(f"DELETE FROM {table}")
        n = cur.rowcount
        total += n
        tag = "cleared" if n > 0 else "empty  "
        print(f"  {tag}  {table:<40s}  {n:>6} rows")
        conn.commit()
    except psycopg2.errors.UndefinedTable:
        conn.rollback()
        print(f"  skip     {table:<40s}  (table not found)")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR    {table:<40s}  {e}")

# Remove dummy tenants (those with no users) ─ these are demo-run artifacts
try:
    cur.execute("""
        DELETE FROM tenants
        WHERE id NOT IN (
            SELECT DISTINCT tenant_id FROM users WHERE tenant_id IS NOT NULL
        )
    """)
    n = cur.rowcount
    conn.commit()
    print(f"\n  removed  {'dummy tenants':<40s}  {n:>6} rows")
except Exception as e:
    conn.rollback()
    print(f"\n  skip     dummy tenant cleanup: {e}")

conn.close()
print(f"\nDone — {total} data rows removed.")
print("Database is clean. Submit a real invoice at http://localhost:5173 to start.")
