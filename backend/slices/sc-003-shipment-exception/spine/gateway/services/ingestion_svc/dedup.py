"""SC-003 deduplication helpers — same pattern as SC-002."""
import hashlib


def compute_dedup_key(
    domain_tag: str, tenant_id: str, source_type: str,
    source_type_version: str, external_source_ref: str, payload_hash_hex: str,
) -> str:
    return f"{domain_tag}|{tenant_id}|{source_type}|{source_type_version}|{external_source_ref}|{payload_hash_hex}"


def check_deduplication(cur, tenant_id: str, external_source_ref: str, payload_hash_hex: str):
    """Returns (outcome, original_id|None)."""
    cur.execute(
        "SELECT id, encode(canonical_hash,'hex') AS hash FROM source_records "
        "WHERE tenant_id=%s AND external_source_ref=%s LIMIT 1",
        (tenant_id, external_source_ref),
    )
    row = cur.fetchone()
    if row is None:
        return "FIRST_SEEN", None
    existing_hash = row[1] if isinstance(row, (list, tuple)) else row["hash"]
    if existing_hash == payload_hash_hex:
        return "DUPLICATE_OF", row[0] if isinstance(row, (list, tuple)) else row["id"]
    return "AMBIGUOUS", row[0] if isinstance(row, (list, tuple)) else row["id"]


def write_dedup_index(
    cur, tenant_id: str, dedup_key: str, outcome: str,
    source_record_id, original_id, external_source_ref: str,
    payload_hash_hex: str, source_type: str, source_type_version: str,
) -> None:
    import uuid, datetime
    # Use a savepoint so a failure (e.g. table missing) doesn't abort the outer transaction.
    try:
        cur.execute("SAVEPOINT write_dedup_index")
        cur.execute("""
            INSERT INTO deduplication_index
                (id, tenant_id, dedup_key, outcome, source_record_id, original_record_id,
                 external_source_ref, payload_hash_hex, source_type, source_type_version, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            uuid.uuid4(), tenant_id, dedup_key, outcome, source_record_id,
            original_id, external_source_ref, payload_hash_hex,
            source_type, source_type_version,
        ))
        cur.execute("RELEASE SAVEPOINT write_dedup_index")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT write_dedup_index")
