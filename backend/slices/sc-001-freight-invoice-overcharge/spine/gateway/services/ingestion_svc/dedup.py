"""
Deduplication engine — §11 of the Tier-0 Ingestion spec.

Three outcomes:
  FIRST_SEEN   — no prior record with this key exists
  DUPLICATE_OF — same external_source_ref AND same payload hash
  AMBIGUOUS    — same external_source_ref but DIFFERENT payload hash

The dedup_index table is the durable audit record.
Redis (via shared.redis_idem) accelerates hot-path lookups but is NOT the only store.

Dedup key formula (§11.1):
  base64url( SHA-256(
      domain_tag || tenant_id || source_type || source_type_version
      || external_source_ref || payload_hash_hex
  ))[:32]
"""
import base64
import hashlib
import uuid
from datetime import datetime, timezone

from services.ingestion_svc.models import DeduplicationOutcome


def compute_dedup_key(
    domain_tag: str,
    tenant_id: str,
    source_type: str,
    source_type_version: str,
    external_source_ref: str,
    payload_hash_hex: str,
) -> str:
    raw = "|".join([
        domain_tag, tenant_id, source_type,
        source_type_version, external_source_ref or "", payload_hash_hex,
    ]).encode()
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest).decode()[:32]


def check_deduplication(
    cur,
    tenant_id: str,
    external_source_ref: str,
    payload_hash_hex: str,
) -> tuple[str, "uuid.UUID | None"]:
    """
    Read-only dedup check — no writes.

    Returns (outcome, original_record_id).
    Call this BEFORE inserting the source_record so we know the outcome to store on it.
    Then call write_dedup_index() AFTER the source_record row exists (FK satisfied).
    """
    cur.execute("""
        SELECT deduplication_key, source_record_id, payload_hash, outcome
        FROM dedup_index
        WHERE tenant_id = %s AND external_source_ref = %s
        ORDER BY decided_at DESC
        LIMIT 1
    """, (tenant_id, external_source_ref))
    existing = cur.fetchone()

    if existing is None:
        return DeduplicationOutcome.FIRST_SEEN, None

    prior_payload_hash = existing[2]
    if prior_payload_hash == payload_hash_hex:
        return DeduplicationOutcome.DUPLICATE_OF, existing[1]
    return DeduplicationOutcome.AMBIGUOUS, existing[1]


def write_dedup_index(
    cur,
    tenant_id: str,
    dedup_key: str,
    outcome: str,
    source_record_id: uuid.UUID,
    original_id: "uuid.UUID | None",
    external_source_ref: str,
    payload_hash_hex: str,
    source_type: str,
    source_type_version: str,
) -> None:
    """
    Write the durable dedup audit record.
    MUST be called AFTER the source_record row is inserted so the FK is satisfied.
    """
    cur.execute("""
        INSERT INTO dedup_index (
            id, tenant_id, deduplication_key, outcome,
            source_record_id, original_record_id,
            external_source_ref, payload_hash,
            source_type, source_type_version, decided_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, deduplication_key) DO UPDATE
            SET outcome = EXCLUDED.outcome,
                source_record_id = EXCLUDED.source_record_id,
                decided_at = EXCLUDED.decided_at
    """, (
        uuid.uuid4(), tenant_id, dedup_key, outcome,
        source_record_id, original_id,
        external_source_ref, payload_hash_hex,
        source_type, source_type_version,
        datetime.now(timezone.utc),
    ))


def run_deduplication(
    cur,
    tenant_id: str,
    dedup_key: str,
    source_record_id: uuid.UUID,
    external_source_ref: str,
    payload_hash_hex: str,
    source_type: str,
    source_type_version: str,
) -> tuple[str, "uuid.UUID | None"]:
    """
    Legacy combined helper kept for backward compatibility with tests.
    WARNING: do NOT call this before the source_record row exists — the FK on
    dedup_index.source_record_id will fail.  Use check_deduplication() +
    write_dedup_index() directly from the ingestion handler instead.
    """
    outcome, original_id = check_deduplication(
        cur, tenant_id, external_source_ref, payload_hash_hex
    )
    write_dedup_index(
        cur, tenant_id, dedup_key, outcome,
        source_record_id, original_id,
        external_source_ref, payload_hash_hex,
        source_type, source_type_version,
    )
    return outcome, original_id
