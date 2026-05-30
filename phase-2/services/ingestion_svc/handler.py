"""
Ingestion Service — implements the exact 5-step write pattern from CLAUDE.md:
  1. JCS canonicalize
  2. SHA-256 with domain tag  (BEFORE encryption)
  3. AES-256-GCM encrypt via KMS DEK  (dev: store canonical bytes as placeholder)
  4. INSERT source_records + lineage_records + outbox  (single DB transaction)
  5. Redis idempotency key stored AFTER commit  (crash-safe: DB is authoritative)
"""
import json, hashlib, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import shared.db  # noqa: F401 — registers UUID adapter
from zoiko_common.crypto.jcs import canonicalize

from shared.signer     import sign
from shared.redis_idem import mark_in_progress, mark_complete, get_status
from services.ingestion_svc.models import InvoiceInput, IngestResult

DOMAIN_TAG = b"zoiko.ingestion.invoice.v1:"


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
    ) -> IngestResult:
        tenant_id = str(tenant_id)   # normalise UUID object → str
        idem_key  = idempotency_key or str(uuid.uuid4())

        # Fast-path: if Redis already shows COMPLETE, short-circuit
        if get_status(tenant_id, idem_key) == "COMPLETE":
            existing = _fetch_existing(self.db_url, tenant_id, idem_key)
            if existing:
                return existing

        # Step 1 — JCS canonicalize (keys sorted by Unicode code point)
        payload_dict = {
            "carrier_id":          invoice.carrier_id,
            "currency":            invoice.currency,
            "invoice_number":      invoice.invoice_number,
            "route_destination":   invoice.route_destination,
            "route_origin":        invoice.route_origin,
            "total_amount":        str(invoice.total_amount),
        }
        canonical_bytes = canonicalize(payload_dict)

        # Step 2 — domain-tagged SHA-256 (BEFORE encryption)
        canonical_hash = hashlib.sha256(DOMAIN_TAG + canonical_bytes).digest()

        # Step 3 — AES-256-GCM encrypt via KMS DEK (FR-001)
        # Rule: hash BEFORE encrypt (canonical_hash computed above, now encrypt content)
        _dev_mode = __import__("os").getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
        try:
            from zoiko_common.crypto.aes_gcm import get_dek, encrypt as _aes_encrypt
            dek        = get_dek(tenant_id)
            ciphertext = _aes_encrypt(dek, canonical_bytes)
        except Exception as _enc_err:
            if not _dev_mode:
                raise RuntimeError(
                    f"AES-256-GCM encryption required in production (FR-001): {_enc_err}"
                ) from _enc_err
            ciphertext = canonical_bytes   # DEV_MODE only — store plaintext

        # Sign the canonical_hash with the tenant signing key
        signature, kid = sign(self.tenant_slug, canonical_hash)

        source_id = uuid.uuid4()
        now       = datetime.now(timezone.utc)

        # Step 4 — single DB transaction: source_records + lineage_records + outbox
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO source_records
                    (id, tenant_id, source_type, canonical_hash,
                     ciphertext, signature, kid, idempotency_key, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING id
            """, (
                source_id, tenant_id, "INVOICE",
                canonical_hash, ciphertext, signature, kid,
                idem_key, now,
            ))
            inserted = cur.fetchone()
            if inserted is None:
                # Duplicate — DB-level guard triggered; return existing record
                conn.rollback()
                conn.close()
                existing = _fetch_existing(self.db_url, tenant_id, idem_key)
                if existing:
                    return existing

            # APPEND-ONLY lineage_records — one row per ingestion event
            cur.execute("""
                INSERT INTO lineage_records
                    (id, tenant_id, entity_type, entity_id, parent_id,
                     event_type, payload_hash, recorded_at)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "INVOICE", source_id,
                "INGESTED", canonical_hash, now,
            ))

            outbox_payload = {
                "source_record_id":  str(source_id),
                "tenant_id":         tenant_id,
                "invoice_number":    invoice.invoice_number,
                "carrier_id":        invoice.carrier_id,
                "total_amount":      float(invoice.total_amount),
                "currency":          invoice.currency,
                "route_origin":      invoice.route_origin,
                "route_destination": invoice.route_destination,
                "canonical_hash":    canonical_hash.hex(),
            }
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.source.record.received",
                str(source_id), json.dumps(outbox_payload), now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Step 5 — Kafka publish AFTER commit (crash here is safe — outbox relay recovers)
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic           = "zoiko.source.record.received",
            key             = str(source_id),
            payload         = outbox_payload,
            tenant_id       = tenant_id,
            idempotency_key = idem_key,
        ))

        # Step 5b — Redis idempotency AFTER commit (crash-safe: DB is authoritative)
        mark_in_progress(tenant_id, idem_key)
        mark_complete(tenant_id, idem_key)

        return IngestResult(
            source_record_id = source_id,
            canonical_hash   = canonical_hash.hex(),
            idempotency_key  = idem_key,
            tenant_id        = tenant_id,
        )


def _fetch_existing(db_url: str, tenant_id: str, idem_key: str) -> IngestResult | None:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur  = conn.cursor()
    cur.execute(
        "SELECT id, encode(canonical_hash,'hex') FROM source_records "
        "WHERE tenant_id=%s AND idempotency_key=%s",
        (tenant_id, idem_key),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return IngestResult(
            source_record_id = row[0],
            canonical_hash   = row[1],
            idempotency_key  = idem_key,
            tenant_id        = tenant_id,
        )
    return None
