"""
Ingestion Service — Tier-0 compliant implementation.

Spec §5 pipeline:
  1. Capture raw bytes (before interpretation)
  2. Compute plaintext hash BEFORE encryption  (§2.2)
  3. Envelope-encrypt payload                  (§2.3)
  4. Create source record                      (§8)
  5. Run deduplication                         (§11)
  6. Sign source record                        (§16)
  7. Write outbox event
  8. Advance record_status FSM

Channel metadata shape is injected by the caller (channel adapter).
"""
import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401 — sys.path bootstrap
import psycopg2
import shared.db  # noqa: F401 — registers UUID adapter
from zoiko_common.crypto.jcs import canonicalize

from shared.signer import sign
from shared.redis_idem import mark_in_progress, mark_complete, get_status
from services.ingestion_svc.models import (
    InvoiceInput, IngestResult, ChannelEnum, DeduplicationOutcome,
)
from services.ingestion_svc.dedup import compute_dedup_key, check_deduplication, write_dedup_index

DOMAIN_TAG      = b"zoiko.ingestion.invoice.v1:"
SCHEMA_VERSION  = "source-record.v1"
DOMAIN_TAG_STR  = "zoiko/v1/source-record"
DEV_MODE        = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
SERVICE_SPIFFE  = "spiffe://zoiko/system/ingestion"


class IngestionHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def ingest_invoice(
        self,
        tenant_id: str,
        invoice: InvoiceInput,
        idempotency_key: str = None,
        *,
        channel: str = ChannelEnum.REST_API_PUSH,
        channel_metadata: dict = None,
        received_at: datetime = None,
        received_by_user: str = None,
        correlation_id: str = None,
        causation_id: str = None,
        data_residency_region: str = "ap-south-1",
        jurisdiction_code: str = None,
        brand_id: str = None,
    ) -> IngestResult:
        tenant_id   = str(tenant_id)
        idem_key    = idempotency_key or str(uuid.uuid4())
        recv_at     = received_at or datetime.now(timezone.utc)
        corr_id     = correlation_id or str(uuid.uuid4())
        ch_metadata = channel_metadata or {}

        # Fast-path: Redis shows COMPLETE — return existing without DB round-trip
        if get_status(tenant_id, idem_key) == "COMPLETE":
            existing = _fetch_existing(self.db_url, tenant_id, idem_key)
            if existing:
                return existing

        # ── Step 1: Build raw payload dict (capture before interpretation) ──
        payload_dict = {
            "carrier_id":          invoice.carrier_id,
            "currency":            invoice.currency,
            "invoice_number":      invoice.invoice_number,
            "route_destination":   invoice.route_destination,
            "route_origin":        invoice.route_origin,
            "total_amount":        str(invoice.total_amount),
        }
        if invoice.invoice_date:
            payload_dict["invoice_date"] = invoice.invoice_date
        if invoice.transport_mode:
            payload_dict["transport_mode"] = invoice.transport_mode
        if invoice.charge_lines:
            payload_dict["charge_lines"] = invoice.charge_lines
        if invoice.shipper_reference:
            payload_dict["shipper_reference"] = invoice.shipper_reference

        # JCS canonicalize (RFC 8785 — keys sorted, no whitespace)
        canonical_bytes = canonicalize(payload_dict)
        payload_size    = len(canonical_bytes)

        # ── Step 2: Hash BEFORE encryption (§2.2) ──────────────────────────
        raw_payload_hash = hashlib.sha256(DOMAIN_TAG + canonical_bytes).digest()

        # ── Step 3: Envelope-encrypt (§2.3) ────────────────────────────────
        aad = f"carrier_invoice|{tenant_id}|{invoice.invoice_number}"
        iv_bytes = None
        dek_id   = None
        try:
            from zoiko_common.crypto.aes_gcm import get_dek, encrypt as _aes_encrypt
            dek        = get_dek(tenant_id)
            ciphertext = _aes_encrypt(dek, canonical_bytes, aad=aad.encode())
            iv_bytes   = ciphertext[:12]
            dek_id     = f"dek-{tenant_id}-default"
        except Exception as _enc_err:
            if not DEV_MODE:
                raise RuntimeError(
                    f"AES-256-GCM encryption required in production: {_enc_err}"
                ) from _enc_err
            ciphertext = canonical_bytes

        # ── Step 4: Sign source record ──────────────────────────────────────
        signature_bytes, kid = sign(self.tenant_slug, raw_payload_hash)
        signature_block = {
            "alg":       "Ed25519",
            "key_id":    kid,
            "signature": base64.b64encode(signature_bytes).decode(),
        }

        source_id = uuid.uuid4()
        now       = datetime.now(timezone.utc)

        # ── Step 5: Compute deduplication key ──────────────────────────────
        dedup_key = compute_dedup_key(
            domain_tag          = DOMAIN_TAG_STR,
            tenant_id           = tenant_id,
            source_type         = "INVOICE",
            source_type_version = "v1",
            external_source_ref = invoice.invoice_number,
            payload_hash_hex    = raw_payload_hash.hex(),
        )

        # ── Step 6: DB transaction ──────────────────────────────────────────
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            dedup_outcome, original_id = check_deduplication(
                cur=cur,
                tenant_id           = tenant_id,
                external_source_ref = invoice.invoice_number,
                payload_hash_hex    = raw_payload_hash.hex(),
            )

            cur.execute("""
                INSERT INTO source_records (
                    id, tenant_id,
                    schema_version, domain_tag,
                    brand_id, jurisdiction_code,
                    data_residency_region, data_classification, retention_class,
                    channel, channel_metadata,
                    source_type, source_type_version,
                    external_source_ref,
                    received_at, received_by_service, received_by_user,
                    raw_payload_content_type, raw_payload_encoding,
                    raw_payload_size_bytes, raw_payload_hash_alg,
                    raw_payload_aad, raw_payload_dek_id,
                    raw_payload_iv,
                    canonical_hash, ciphertext,
                    signature, kid,
                    signature_block,
                    deduplication_key, deduplication_outcome,
                    deduplication_canonical_record_id,
                    validation_status, record_status,
                    correlation_id, causation_id,
                    idempotency_key, created_at
                ) VALUES (
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING id
            """, (
                source_id, tenant_id,
                SCHEMA_VERSION, DOMAIN_TAG_STR,
                brand_id, jurisdiction_code,
                data_residency_region, "confidential", "tier-A",
                channel, json.dumps(ch_metadata),
                "INVOICE", "v1",
                invoice.invoice_number,
                recv_at, SERVICE_SPIFFE, received_by_user,
                "application/json", "utf-8",
                payload_size, "sha-256",
                aad, dek_id,
                iv_bytes,
                raw_payload_hash, ciphertext,
                signature_bytes, kid,
                json.dumps(signature_block),
                dedup_key, dedup_outcome,
                original_id if dedup_outcome == DeduplicationOutcome.DUPLICATE_OF else None,
                "PENDING", "SIGNED",
                corr_id, causation_id,
                idem_key, now,
            ))

            inserted = cur.fetchone()
            if inserted is None:
                conn.rollback()
                conn.close()
                return _fetch_existing(self.db_url, tenant_id, idem_key) or IngestResult(
                    source_record_id = source_id,
                    canonical_hash   = raw_payload_hash.hex(),
                    idempotency_key  = idem_key,
                    tenant_id        = tenant_id,
                    deduplication_outcome = dedup_outcome,
                )

            write_dedup_index(
                cur                 = cur,
                tenant_id           = tenant_id,
                dedup_key           = dedup_key,
                outcome             = dedup_outcome,
                source_record_id    = source_id,
                original_id         = original_id,
                external_source_ref = invoice.invoice_number,
                payload_hash_hex    = raw_payload_hash.hex(),
                source_type         = "INVOICE",
                source_type_version = "v1",
            )

            _write_state_transition(cur, tenant_id, source_id, "SIGNED", "PENDING_VALIDATION", SERVICE_SPIFFE)
            cur.execute(
                "UPDATE source_records SET record_status='PENDING_VALIDATION' WHERE id=%s",
                (source_id,)
            )

            if dedup_outcome == DeduplicationOutcome.AMBIGUOUS and original_id:
                cur.execute("""
                    INSERT INTO ambiguity_queue
                        (id, tenant_id, source_record_id, original_record_id,
                         external_source_ref, reason, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    uuid.uuid4(), tenant_id, source_id, original_id,
                    invoice.invoice_number,
                    "Same external_source_ref received with different payload hash",
                    now,
                ))

            cur.execute("""
                INSERT INTO lineage_records
                    (id, tenant_id, entity_type, entity_id, parent_id,
                     event_type, payload_hash, recorded_at)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "INVOICE", source_id,
                "INGESTED", raw_payload_hash, now,
            ))

            outbox_payload = {
                "source_record_id":      str(source_id),
                "tenant_id":             tenant_id,
                "invoice_number":        invoice.invoice_number,
                "carrier_id":            invoice.carrier_id,
                "total_amount":          float(invoice.total_amount),
                "currency":              invoice.currency,
                "route_origin":          invoice.route_origin,
                "route_destination":     invoice.route_destination,
                "canonical_hash":        raw_payload_hash.hex(),
                "channel":               channel,
                "deduplication_outcome": dedup_outcome,
                "correlation_id":        corr_id,
            }
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.source.record.received",
                str(source_id), json.dumps(outbox_payload), now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic           = "zoiko.source.record.received",
                key             = str(source_id),
                payload         = outbox_payload,
                tenant_id       = tenant_id,
                idempotency_key = idem_key,
            ))
        except Exception:
            pass

        mark_in_progress(tenant_id, idem_key)
        mark_complete(tenant_id, idem_key)

        return IngestResult(
            source_record_id      = source_id,
            canonical_hash        = raw_payload_hash.hex(),
            idempotency_key       = idem_key,
            tenant_id             = tenant_id,
            deduplication_outcome = dedup_outcome,
            correlation_id        = corr_id,
            channel               = channel,
        )


# ── helpers ────────────────────────────────────────────────────────────────────

def _write_state_transition(cur, tenant_id, source_record_id, from_status, to_status, actor):
    cur.execute("""
        INSERT INTO source_record_states
            (id, tenant_id, source_record_id, from_status, to_status, actor, occurred_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
    """, (uuid.uuid4(), tenant_id, source_record_id, from_status, to_status, actor))


def _fetch_existing(db_url: str, tenant_id: str, idem_key: str) -> "IngestResult | None":
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur  = conn.cursor()
    cur.execute(
        """SELECT id, encode(canonical_hash,'hex'), deduplication_outcome,
                  correlation_id, channel
           FROM source_records
           WHERE tenant_id=%s AND idempotency_key=%s""",
        (tenant_id, idem_key),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return IngestResult(
            source_record_id      = row[0],
            canonical_hash        = row[1],
            idempotency_key       = idem_key,
            tenant_id             = tenant_id,
            deduplication_outcome = row[2] or DeduplicationOutcome.FIRST_SEEN,
            correlation_id        = str(row[3]) if row[3] else None,
            channel               = row[4] or ChannelEnum.REST_API_PUSH,
        )
    return None
