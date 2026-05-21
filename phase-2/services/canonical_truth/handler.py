"""
Canonical Truth Service — takes a validated source_record and produces the single
authoritative canonical_invoice + canonical_shipment rows that all downstream
services (evidence, reasoning, governance) treat as ground truth.
"""
import json, hashlib, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import shared.db  # noqa: F401 — registers UUID adapter

from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign
from services.canonical_truth.models import CanonicalResult

DOMAIN_TAG = b"zoiko.canonical.invoice.v1:"


class CanonicalHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def canonicalize_invoice(
        self,
        tenant_id: str,
        source_record_id: uuid.UUID,
        invoice_number: str,
        carrier_id: str,
        total_amount: float,
        currency: str,
        origin_city: str,
        dest_city: str,
        weight_lbs: float = 0.0,
    ) -> CanonicalResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))
        # Compute the authoritative canonical_hash — JCS over the canonical form
        canonical_dict = {
            "carrier_id":      carrier_id,
            "currency":        currency,
            "invoice_number":  invoice_number,
            "source_record_id": str(source_record_id),
            "tenant_id":       tenant_id,
            "total_amount":    str(total_amount),
        }
        canonical_bytes = canonicalize(canonical_dict)
        canonical_hash  = hashlib.sha256(DOMAIN_TAG + canonical_bytes).digest()
        signature, kid  = sign(self.tenant_slug, canonical_hash)

        inv_id  = uuid.uuid4()
        ship_id = uuid.uuid4()
        now     = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            # UNIQUE (tenant_id, invoice_number) — idempotent upsert
            cur.execute("""
                INSERT INTO canonical_invoices
                    (id, tenant_id, source_record_id, invoice_number, carrier_id,
                     total_amount, currency, canonical_hash, signature, kid, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, invoice_number) DO NOTHING
                RETURNING id
            """, (
                inv_id, tenant_id, source_record_id,
                invoice_number, carrier_id, total_amount, currency,
                canonical_hash, signature, kid, now,
            ))
            row = cur.fetchone()
            if row is None:
                # Row already existed — fetch the existing id
                cur.execute(
                    "SELECT id FROM canonical_invoices WHERE tenant_id=%s AND invoice_number=%s",
                    (tenant_id, invoice_number),
                )
                inv_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO canonical_shipments
                    (id, tenant_id, invoice_id, origin_city, dest_city, weight_lbs, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (ship_id, tenant_id, inv_id, origin_city, dest_city, weight_lbs, now))

            conn.commit()
        finally:
            conn.close()

        # Publish invoice.canonical
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.canonical.invoice.created",
            key       = str(inv_id),
            payload   = {
                "canonical_invoice_id": str(inv_id),
                "invoice_number":       invoice_number,
                "carrier_id":           carrier_id,
                "total_amount":         float(total_amount),
                "canonical_hash":       canonical_hash.hex(),
            },
            tenant_id = tenant_id,
        ))

        return CanonicalResult(
            canonical_invoice_id  = inv_id,
            canonical_shipment_id = ship_id,
            source_record_id      = source_record_id,
            tenant_id             = tenant_id,
            invoice_number        = invoice_number,
            carrier_id            = carrier_id,
            total_amount          = float(total_amount),
            canonical_hash        = canonical_hash.hex(),
        )
