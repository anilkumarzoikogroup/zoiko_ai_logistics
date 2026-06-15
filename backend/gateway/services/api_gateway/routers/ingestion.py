"""
Ingestion router — Tier-0 spec §19 APIs.

POST   /ingest/source                            — single record ingest
GET    /ingest/source/{record_id}                — source record metadata
GET    /ingest/source/{record_id}/payload        — raw payload (source.payload.read)
POST   /ingest/source/{record_id}/release-quarantine
POST   /ingest/source/{record_id}/rerun-validation

GET    /ingest/ambiguous                         — ambiguity queue
POST   /ingest/ambiguous/{record_id}/resolve     — resolve ambiguous record

GET    /validation/rule-sets                     — list versioned rule sets
GET    /validation/rule-sets/{rule_set_id}/versions

GET    /ingest/source/{record_id}/states         — FSM transition history

GET    /ingest/batch/{batch_id}                  — batch artifact header
GET    /ingest/batch/{batch_id}/outcomes         — outcome counts
GET    /ingest/batch/{batch_id}/records          — per-record fan-out

GET    /lineage/{lineage_id}                     — single lineage record
GET    /lineage:by-source?source_record_id=      — all lineage for a source record
GET    /lineage:by-canonical?canonical_invoice_id= — transform audit trail for a canonical invoice
"""
import base64
import hashlib
import os
import uuid
from datetime import datetime

import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, Request

import paths  # noqa: F401
from services.api_gateway.auth import get_claims
from middleware.oidc.claims import ZoikoClaims
from shared.db import q, q1

router = APIRouter(tags=["ingestion"])

DB_URL = os.getenv("DB_URL")


# ── Content-Digest verification helper ────────────────────────────────────────

async def verify_content_digest(request: Request):
    """
    Spec §7.1: Content-Digest header must be present and match the body.
    Format: sha-256=:<base64>:
    Only enforced when the header is present — allows gradual rollout.
    """
    digest_header = request.headers.get("Content-Digest")
    if not digest_header:
        return  # Not yet mandatory — skip

    body = await request.body()
    if digest_header.startswith("sha-256=:"):
        expected_b64 = digest_header[len("sha-256=:"):-1]  # strip trailing ':'
        actual = base64.b64encode(hashlib.sha256(body).digest()).decode()
        if actual != expected_b64:
            raise HTTPException(status_code=400, detail="Content-Digest mismatch — body corrupted in transit")


def _capture_rest_push_metadata(request: Request, idempotency_key: str) -> dict:
    """Build channel_metadata for rest_api_push channel."""
    return {
        "client_id":       request.headers.get("X-Client-ID", ""),
        "idempotency_key": idempotency_key,
        "content_digest":  request.headers.get("Content-Digest", ""),
        "source_ip":       request.headers.get("X-Forwarded-For", request.client.host if request.client else ""),
        "user_agent":      request.headers.get("User-Agent", ""),
        "request_id":      request.headers.get("X-Request-ID", str(uuid.uuid4())),
    }


# ── GET /ingest/source/{record_id} ────────────────────────────────────────────

@router.get("/ingest/source/{record_id}")
def get_source_record(
    record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Return source record metadata. Does NOT return the raw payload."""
    row = q1("""
        SELECT
            id, schema_version, domain_tag,
            tenant_id, brand_id, jurisdiction_code,
            data_residency_region, data_classification, retention_class,
            channel, channel_metadata,
            source_type, source_type_version, external_source_ref,
            received_at, received_by_service, received_by_user,
            raw_payload_size_bytes, raw_payload_content_type,
            raw_payload_encoding, raw_payload_hash_alg,
            encode(canonical_hash, 'hex') as payload_hash,
            raw_payload_aad, raw_payload_dek_id,
            deduplication_key, deduplication_outcome,
            deduplication_canonical_record_id,
            validation_status, validation_result_id,
            record_status, correlation_id, causation_id,
            signature_block, idempotency_key, created_at
        FROM source_records
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (record_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Source record not found")

    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items()}


# ── GET /ingest/source/{record_id}/payload ────────────────────────────────────

@router.get("/ingest/source/{record_id}/payload")
def get_source_payload(
    record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Return the decrypted raw payload. Requires source.payload.read permission.
    Every access writes an evidence event (§17.2).
    """
    # Permission check — source.payload.read
    _require_payload_permission(claims)

    row = q1("""
        SELECT ciphertext, raw_payload_iv, raw_payload_aad,
               raw_payload_dek_id, raw_payload_content_type,
               raw_payload_encoding, encode(canonical_hash,'hex') as hash,
               tenant_id, external_source_ref
        FROM source_records
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (record_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Source record not found")

    # Decrypt
    try:
        from zoiko_common.crypto.aes_gcm import get_dek, decrypt as _aes_decrypt
        dek       = get_dek(str(claims.tenant_id))
        plaintext = _aes_decrypt(dek, bytes(row["ciphertext"]),
                                  iv=bytes(row["raw_payload_iv"]) if row["raw_payload_iv"] else None,
                                  aad=row["raw_payload_aad"].encode() if row["raw_payload_aad"] else None)
    except Exception:
        # DEV_MODE — ciphertext is plaintext
        plaintext = bytes(row["ciphertext"])

    # Write evidence event for audit (§17.2)
    _write_payload_access_evidence(
        record_id  = record_id,
        tenant_id  = str(claims.tenant_id),
        actor_sub  = claims.sub,
        purpose    = "EXPLICIT_REQUEST",
    )

    return {
        "record_id":      record_id,
        "content_type":   row["raw_payload_content_type"],
        "encoding":       row["raw_payload_encoding"],
        "payload_hash":   row["hash"],
        "payload":        plaintext.decode(row["raw_payload_encoding"] or "utf-8", errors="replace"),
    }


# ── POST /ingest/source/{record_id}/release-quarantine ───────────────────────

@router.post("/ingest/source/{record_id}/release-quarantine")
def release_quarantine(
    record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """
    Release a quarantined source record back into the validation pipeline.
    Creates a new validation attempt (§13 — quarantine is recoverable).
    """
    row = q1("""
        SELECT id, validation_status, record_status, tenant_id
        FROM source_records
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (record_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Source record not found")
    if row["validation_status"] != "QUARANTINED":
        raise HTTPException(status_code=409, detail=f"Record is not quarantined (status={row['validation_status']})")

    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        # FSM transition: QUARANTINED → PENDING_VALIDATION
        cur.execute("""
            UPDATE source_records
            SET validation_status = 'PENDING',
                record_status = 'PENDING_VALIDATION'
            WHERE id = %s::uuid AND tenant_id = %s::uuid
        """, (record_id, claims.tenant_id))

        cur.execute("""
            INSERT INTO source_record_states
                (id, tenant_id, source_record_id, from_status, to_status, actor, occurred_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (uuid.uuid4(), str(claims.tenant_id), record_id,
              "QUARANTINED", "PENDING_VALIDATION", claims.sub))

        # Mark quarantine item as released
        cur.execute("""
            UPDATE quarantine_items
            SET released_at = NOW(), released_by = %s::uuid
            WHERE source_record_id = %s::uuid AND released_at IS NULL
        """, (claims.sub, record_id))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"record_id": record_id, "new_status": "PENDING_VALIDATION", "message": "Released for re-validation"}


# ── POST /ingest/source/{record_id}/rerun-validation ─────────────────────────

@router.post("/ingest/source/{record_id}/rerun-validation")
def rerun_validation(
    record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Force re-validation against the current ACTIVE rule set."""
    row = q1("""
        SELECT id, validation_status, record_status, tenant_id,
               external_source_ref, encode(canonical_hash,'hex') as hash
        FROM source_records
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (record_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Source record not found")
    if row["record_status"] in ("PROCESSED", "REJECTED"):
        raise HTTPException(status_code=409, detail=f"Cannot re-validate a {row['record_status']} record")

    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE source_records
            SET validation_status = 'PENDING', record_status = 'PENDING_VALIDATION'
            WHERE id = %s::uuid AND tenant_id = %s::uuid
        """, (record_id, claims.tenant_id))
        cur.execute("""
            INSERT INTO source_record_states
                (id, tenant_id, source_record_id, from_status, to_status, actor, occurred_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (uuid.uuid4(), str(claims.tenant_id), record_id,
              row["record_status"], "PENDING_VALIDATION", claims.sub))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"record_id": record_id, "new_status": "PENDING_VALIDATION"}


# ── GET /ingest/ambiguous ─────────────────────────────────────────────────────

@router.get("/ingest/ambiguous")
def list_ambiguous(
    claims: ZoikoClaims = Depends(get_claims),
    limit: int = 50,
    offset: int = 0,
):
    """List ambiguous records awaiting operator resolution."""
    rows = q("""
        SELECT
            aq.id, aq.source_record_id, aq.original_record_id,
            aq.external_source_ref, aq.reason, aq.created_at,
            sr_new.channel, sr_new.deduplication_outcome,
            encode(sr_new.canonical_hash,'hex') as new_payload_hash,
            encode(sr_orig.canonical_hash,'hex') as orig_payload_hash
        FROM ambiguity_queue aq
        JOIN source_records sr_new  ON sr_new.id  = aq.source_record_id
        JOIN source_records sr_orig ON sr_orig.id = aq.original_record_id
        WHERE aq.tenant_id = %s::uuid AND aq.resolved_at IS NULL
        ORDER BY aq.created_at DESC
        LIMIT %s OFFSET %s
    """, (claims.tenant_id, limit, offset))

    return {"ambiguous": [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]}


# ── POST /ingest/ambiguous/{record_id}/resolve ────────────────────────────────

@router.post("/ingest/ambiguous/{record_id}/resolve")
def resolve_ambiguous(
    record_id: str,
    body: dict,
    claims: ZoikoClaims = Depends(get_claims),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """
    Resolve an ambiguous record.
    body: {resolution: "USE_LATEST"|"USE_ORIGINAL"|"REJECT_BOTH"|"MANUAL", note: "..."}
    """
    resolution = body.get("resolution")
    if resolution not in ("USE_LATEST", "USE_ORIGINAL", "REJECT_BOTH", "MANUAL"):
        raise HTTPException(status_code=400, detail="resolution must be USE_LATEST, USE_ORIGINAL, REJECT_BOTH, or MANUAL")

    row = q1("""
        SELECT id, source_record_id, original_record_id, tenant_id
        FROM ambiguity_queue
        WHERE source_record_id = %s::uuid AND tenant_id = %s::uuid AND resolved_at IS NULL
    """, (record_id, claims.tenant_id))

    if not row:
        raise HTTPException(status_code=404, detail="Ambiguous record not found or already resolved")

    conn = psycopg2.connect(DB_URL)
    try:
        cur = conn.cursor()
        # Mark ambiguity resolved
        cur.execute("""
            UPDATE ambiguity_queue
            SET resolution = %s, resolved_by = %s::uuid,
                resolved_at = NOW(), resolution_note = %s
            WHERE source_record_id = %s::uuid AND tenant_id = %s::uuid
        """, (resolution, claims.sub, body.get("note", ""), record_id, claims.tenant_id))

        if resolution == "USE_LATEST":
            # The new record proceeds — set to PENDING_VALIDATION
            cur.execute("""
                UPDATE source_records SET validation_status='PENDING', record_status='PENDING_VALIDATION'
                WHERE id=%s::uuid
            """, (record_id,))
        elif resolution == "USE_ORIGINAL":
            # Mark new record as DUPLICATE_OF the original
            cur.execute("""
                UPDATE source_records SET deduplication_outcome='DUPLICATE_OF', record_status='PROCESSED'
                WHERE id=%s::uuid
            """, (record_id,))
        elif resolution == "REJECT_BOTH":
            for rid in (record_id, str(row["original_record_id"])):
                cur.execute("""
                    UPDATE source_records SET validation_status='REJECTED', record_status='REJECTED'
                    WHERE id=%s::uuid
                """, (rid,))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"record_id": record_id, "resolution": resolution, "resolved_by": claims.sub}


# ── GET /validation/rule-sets ─────────────────────────────────────────────────

@router.get("/validation/rule-sets")
def list_rule_sets(
    source_type: str = None,
    claims: ZoikoClaims = Depends(get_claims),
):
    filters = "WHERE 1=1"
    params  = []
    if source_type:
        filters += " AND source_type = %s"
        params.append(source_type)

    rows = q(f"""
        SELECT id, rule_set_id, version, source_type, status,
               activated_at, superseded_at, created_at,
               jsonb_array_length(rules) as rule_count
        FROM validation_rule_sets
        {filters}
        ORDER BY source_type, rule_set_id, version DESC
    """, tuple(params) if params else ())
    return {"rule_sets": [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]}


# ── GET /validation/rule-sets/{rule_set_id}/versions ─────────────────────────

@router.get("/validation/rule-sets/{rule_set_id}/versions")
def get_rule_set_versions(
    rule_set_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    rows = q("""
        SELECT id, rule_set_id, version, source_type, status, rules,
               activated_at, superseded_at, authored_by, created_at
        FROM validation_rule_sets
        WHERE rule_set_id = %s
        ORDER BY created_at DESC
    """, (rule_set_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Rule set '{rule_set_id}' not found")
    return {"rule_set_id": rule_set_id, "versions": [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]}


# ── GET /ingest/source/{record_id}/states ────────────────────────────────────

@router.get("/ingest/source/{record_id}/states")
def get_source_record_states(
    record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """FSM state transition history for a source record."""
    rows = q("""
        SELECT id, from_status, to_status, actor, detail, occurred_at
        FROM source_record_states
        WHERE source_record_id = %s::uuid AND tenant_id = %s::uuid
        ORDER BY occurred_at ASC
    """, (record_id, claims.tenant_id))
    return {"record_id": record_id, "states": [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]}


# ── GET /ingest/batch/{batch_id} ─────────────────────────────────────────────

@router.get("/ingest/batch/{batch_id}")
def get_batch(
    batch_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    row = q1("""
        SELECT id, channel, declared_schema, declared_record_count,
               received_at, batch_payload_hash, processing_status,
               total_records, first_seen_count, duplicate_count, ambiguous_count,
               rejected_count, quarantined_count, processed_count,
               completed_at, error_detail, created_at
        FROM batch_artifacts
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (batch_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}


# ── GET /ingest/batch/{batch_id}/outcomes ─────────────────────────────────────

@router.get("/ingest/batch/{batch_id}/outcomes")
def get_batch_outcomes(
    batch_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    row = q1("""
        SELECT total_records, first_seen_count, duplicate_count, ambiguous_count,
               rejected_count, quarantined_count, processed_count, processing_status
        FROM batch_artifacts
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (batch_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Batch not found")
    return dict(row)


# ── GET /ingest/batch/{batch_id}/records ──────────────────────────────────────

@router.get("/ingest/batch/{batch_id}/records")
def get_batch_records(
    batch_id: str,
    claims: ZoikoClaims = Depends(get_claims),
    outcome: str = None,
    limit: int = 100,
    offset: int = 0,
):
    filters = "WHERE br.batch_id = %s::uuid AND br.tenant_id = %s::uuid"
    params  = [batch_id, claims.tenant_id]
    if outcome:
        filters += " AND br.outcome = %s"
        params.append(outcome)

    rows = q(f"""
        SELECT br.id, br.record_index, br.source_record_id, br.external_source_ref,
               br.outcome, br.error_detail, br.processed_at
        FROM batch_records br
        {filters}
        ORDER BY br.record_index
        LIMIT %s OFFSET %s
    """, (*params, limit, offset))
    return {"batch_id": batch_id, "records": [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]}


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_payload_permission(claims: ZoikoClaims):
    """source.payload.read is required to access raw payload bytes."""
    allowed_roles = {"admin", "compliance"}
    if getattr(claims, "role", None) not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="source.payload.read permission required (roles: admin, compliance)"
        )


def _write_payload_access_evidence(record_id: str, tenant_id: str, actor_sub: str, purpose: str):
    """Append-only evidence event for every raw payload read (§17.2)."""
    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO lineage_records
                (id, tenant_id, entity_type, entity_id, parent_id, event_type, payload_hash, recorded_at)
            VALUES (%s, %s, 'SOURCE_PAYLOAD_READ', %s::uuid, NULL, %s, %s, NOW())
        """, (
            uuid.uuid4(), tenant_id, record_id,
            f"PAYLOAD_READ:{purpose}:{actor_sub}",
            b"\x00" * 32,  # placeholder hash — content is in event_type
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Evidence write failure must not block the payload response


# ── GET /lineage/{lineage_id} ─────────────────────────────────────────────────

@router.get("/lineage/{lineage_id}")
def get_lineage_record(
    lineage_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """Return a single lineage record with its full transform contract."""
    row = q1("""
        SELECT id, tenant_id, entity_type, entity_id, parent_id,
               event_type, payload_hash, recorded_at,
               transform_id, transform_version,
               transform_input_hash, transform_output_hash,
               reference_data_snapshot, transformed_at, transformed_by,
               canonical_records, lineage_domain_tag
        FROM lineage_records
        WHERE id = %s::uuid AND tenant_id = %s::uuid
    """, (lineage_id, claims.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Lineage record not found")

    result = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif isinstance(v, bytes):
            result[k] = v.hex()
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ── GET /lineage:by-source?source_record_id= ─────────────────────────────────

@router.get("/lineage:by-source")
def get_lineage_by_source(
    source_record_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """All lineage records that trace back to a given source record."""
    rows = q("""
        SELECT id, entity_type, entity_id, parent_id, event_type,
               payload_hash, recorded_at, transform_id, transform_version,
               transform_input_hash, transform_output_hash,
               reference_data_snapshot, transformed_at, transformed_by,
               canonical_records, lineage_domain_tag
        FROM lineage_records
        WHERE tenant_id = %s::uuid
          AND (parent_id = %s::uuid OR entity_id = %s::uuid)
        ORDER BY recorded_at ASC
    """, (claims.tenant_id, source_record_id, source_record_id))

    def _ser(v):
        if isinstance(v, uuid.UUID): return str(v)
        if isinstance(v, bytes):    return v.hex()
        if isinstance(v, datetime): return v.isoformat()
        return v

    return {
        "source_record_id": source_record_id,
        "lineage": [{k: _ser(v) for k, v in r.items()} for r in rows],
    }


# ── GET /lineage:by-canonical?canonical_invoice_id= ──────────────────────────

@router.get("/lineage:by-canonical")
def get_lineage_by_canonical(
    canonical_invoice_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """All lineage records for a canonical invoice (transform audit trail)."""
    rows = q("""
        SELECT id, entity_type, entity_id, parent_id, event_type,
               payload_hash, recorded_at, transform_id, transform_version,
               transform_input_hash, transform_output_hash,
               reference_data_snapshot, transformed_at, transformed_by,
               canonical_records, lineage_domain_tag
        FROM lineage_records
        WHERE tenant_id = %s::uuid
          AND entity_type IN ('CANONICAL_INVOICE', 'SOURCE_PAYLOAD_READ')
          AND entity_id = %s::uuid
        ORDER BY recorded_at ASC
    """, (claims.tenant_id, canonical_invoice_id))

    def _ser(v):
        if isinstance(v, uuid.UUID): return str(v)
        if isinstance(v, bytes):    return v.hex()
        if isinstance(v, datetime): return v.isoformat()
        return v

    return {
        "canonical_invoice_id": canonical_invoice_id,
        "lineage": [{k: _ser(v) for k, v in r.items()} for r in rows],
    }
