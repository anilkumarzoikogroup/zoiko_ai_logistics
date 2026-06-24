"""
Canonical Truth Service — takes a validated source_record and produces the single
authoritative canonical_invoice + canonical_shipment rows that all downstream
services (evidence, reasoning, governance) treat as ground truth.
"""
import json
import hashlib
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import shared.db  # noqa: F401 — registers UUID adapter
from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign

from services.canonical_truth.models import CanonicalClaimResult

CLAIM_DOMAIN_TAG = b"zoiko.canonical.claim.v1:"


class CanonicalHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def canonicalize_claim(
        self, tenant_id: str, source_record_id: uuid.UUID, claim_reference: str,
        carrier_id: str, claim_type: str, claimed_amount: float, currency: str,
    ) -> CanonicalClaimResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))
        canonical_dict = {
            "carrier_id":       carrier_id,
            "claim_reference":  claim_reference,
            "claim_type":       claim_type,
            "claimed_amount":   str(claimed_amount),
            "currency":         currency,
            "source_record_id": str(source_record_id),
            "tenant_id":        tenant_id,
        }
        canonical_bytes = canonicalize(canonical_dict)
        canonical_hash  = hashlib.sha256(CLAIM_DOMAIN_TAG + canonical_bytes).digest()
        signature, kid  = sign(self.tenant_slug, canonical_hash)

        claim_id = uuid.uuid4()
        now      = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO claims
                    (id, tenant_id, claim_reference, claim_type, claimed_amount,
                     currency, status, filed_at, source_record_id, carrier_id,
                     claim_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, claim_reference) WHERE claim_reference <> '' DO NOTHING
                RETURNING id
            """, (
                claim_id, tenant_id, claim_reference, claim_type, claimed_amount,
                currency, "SUBMITTED", now, source_record_id, carrier_id,
                canonical_hash, now,
            ))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT id FROM claims WHERE tenant_id=%s AND claim_reference=%s",
                    (tenant_id, claim_reference),
                )
                claim_id = cur.fetchone()[0]

            input_hash  = hashlib.sha256(b"zoiko.ingestion.claim.v1:" + canonical_bytes).hexdigest()
            output_hash = canonical_hash.hex()

            reference_data_snapshot = json.dumps({
                "carrier_claim_normalizer": "v1.0.0",
                "currency_table":           "iso-4217-v2026.01",
                "transform_applied_at":     now.isoformat(),
            })
            canonical_records_json = json.dumps([
                {"type": "claim", "id": str(claim_id), "payload_hash": "sha256:" + output_hash},
            ])

            cur.execute("""
                INSERT INTO lineage_records
                    (id, tenant_id, entity_type, entity_id, parent_id,
                     event_type, payload_hash, recorded_at,
                     transform_id, transform_version,
                     transform_input_hash, transform_output_hash,
                     reference_data_snapshot, transformed_at, transformed_by,
                     canonical_records, lineage_domain_tag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "CANONICAL_CLAIM", claim_id, source_record_id,
                "CANONICALIZED", canonical_hash, now,
                "carrier-claim-normalizer", "v1.0.0",
                input_hash, output_hash,
                reference_data_snapshot, now, "spiffe://zoiko/system/canonical-truth",
                canonical_records_json, "zoiko/v1/lineage-record",
            ))

            cur.execute("""
                UPDATE source_records
                SET record_status = 'PROCESSED', lineage_id = %s
                WHERE id = %s AND tenant_id = %s
            """, (uuid.uuid4(), source_record_id, tenant_id))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "zoiko.canonical.claim.created",
                key       = str(claim_id),
                payload   = {
                    "claim_id":         str(claim_id),
                    "claim_reference":  claim_reference,
                    "carrier_id":       carrier_id,
                    "claimed_amount":   float(claimed_amount),
                    "canonical_hash":   canonical_hash.hex(),
                    "transform_version": "v1.0.0",
                },
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return CanonicalClaimResult(
            claim_id          = claim_id,
            source_record_id  = source_record_id,
            tenant_id         = tenant_id,
            claim_reference   = claim_reference,
            carrier_id        = carrier_id,
            claimed_amount    = float(claimed_amount),
            canonical_hash    = canonical_hash.hex(),
        )
