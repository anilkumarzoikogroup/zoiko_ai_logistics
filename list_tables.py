import psycopg2, psycopg2.extras

conn = psycopg2.connect("postgresql://postgres:1234@localhost/zoiko")
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    SELECT t.table_name,
           (SELECT COUNT(*) FROM information_schema.columns c
            WHERE c.table_name = t.table_name
              AND c.table_schema = 'public') AS col_count,
           pg_stat_user_tables.n_live_tup AS row_count
    FROM   information_schema.tables t
    LEFT   JOIN pg_stat_user_tables
           ON pg_stat_user_tables.relname = t.table_name
    WHERE  t.table_schema = 'public'
      AND  t.table_type   = 'BASE TABLE'
    ORDER  BY t.table_name
""")
rows = cur.fetchall()

# Group by category
categories = {
    "AUTH":        ["users","password_reset_tokens","invitation_tokens","sso_domains","step_up_assertions","workspace_access_requests"],
    "TENANT":      ["tenants","tenant_keys"],
    "INGESTION":   ["source_records","canonical_invoices","canonical_shipments","contract_rates"],
    "CASES":       ["cases","case_events"],
    "VALIDATION":  ["validation_results"],
    "EVIDENCE":    ["evidence_bundles","evidence_items"],
    "GOVERNANCE":  ["findings","decision_proposals","approval_tasks","governance_decisions","governance_tokens","policy_bundles","action_intents","approval_requests","approval_decisions"],
    "EXECUTION":   ["execution_envelopes","connector_responses","reconciliations","outcomes","variance_records"],
    "AUDIT":       ["action_certification_records","audit_worm_index","lineage_records"],
    "SYSTEM":      ["outbox","idempotency_keys"],
}

table_map = {r["table_name"]: r for r in rows}
categorized = set()

print(f"{'=' * 62}")
print(f"  DATABASE TABLES — Total: {len(rows)}")
print(f"{'=' * 62}")

for cat, tables in categories.items():
    found = [t for t in tables if t in table_map]
    if not found:
        continue
    print(f"\n  [{cat}]")
    for t in found:
        r = table_map[t]
        rows_str = str(r["row_count"] or 0)
        print(f"    {t:45} {r['col_count']:2} cols  {rows_str:>6} rows")
        categorized.add(t)

# Any uncategorized tables
other = [r for r in rows if r["table_name"] not in categorized]
if other:
    print("\n  [OTHER]")
    for r in other:
        print(f"    {r['table_name']:45} {r['col_count']:2} cols  {r['row_count'] or 0:>6} rows")

print(f"\n{'=' * 62}")
print(f"  TOTAL: {len(rows)} tables")
print(f"{'=' * 62}")
conn.close()
