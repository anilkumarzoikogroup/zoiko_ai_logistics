"""
SC-003 Canonical Truth Service — takes a validated source_record for a shipment
exception and produces the single authoritative canonical_shipment_exceptions row
that all downstream services (evidence, reasoning, governance) treat as ground truth.

Key computations:
  sla_breach_hours   = max(0, (actual_delivery - committed_eta).total_seconds() / 3600)
  sla_penalty_amount = min(penalty_cap, sla_breach_hours * penalty_rate_per_hour)

Domain tag: b"zoiko.canonical.shipment_exception.v1:"
Kafka topic: zoiko.shipment.exception.canonical
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import shared.db  # noqa: F401 — registers UUID adapter
from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign

from services.canonical_truth.models import CanonicalShipmentExceptionResult

DOMAIN_TAG     = b"zoiko.canonical.shipment_exception.v1:"
INGESTION_TAG  = b"zoiko.ingestion.shipment_exception.v1:"
TRANSFORM_ID   = "shipment-exception-normalizer"
TRANSFORM_VER  = "v1.0.0"
SERVICE_SPIFFE = "spiffe://zoiko/system/canonical-truth-sc003"


class CanonicalHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def canonicalize_shipment_exception(
        self,
        tenant_id:             str,
        source_record_id:      uuid.UUID,
        shipment_reference:    str,
        carrier_id:            str,
        committed_eta:         datetime,
        actual_delivery:       datetime,
        penalty_rate_per_hour: float,
        penalty_cap:           float,
        currency:              str,
        origin:                str,
        destination:           str,
    ) -> CanonicalShipmentExceptionResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))

        # Compute breach — deterministic, same formula as SC003_CONFIDENCE rule
        breach_secs    = max(0.0, (actual_delivery - committed_eta).total_seconds())
        breach_hours   = round(breach_secs / 3600, 4)
        penalty_amount = round(min(penalty_cap, breach_hours * penalty_rate_per_hour), 4)

        # Build canonical dict — keys sorted by JCS (RFC 8785)
        canonical_dict = {
            "actual_delivery":       actual_delivery.isoformat(),
            "carrier_id":            carrier_id,
            "committed_eta":         committed_eta.isoformat(),
            "currency":              currency,
            "destination":           destination,
            "origin":                origin,
            "shipment_reference":    shipment_reference,
            "sla_breach_hours":      str(breach_hours),
            "sla_penalty_amount":    str(penalty_amount),
            "source_record_id":      str(source_record_id),
            "tenant_id":             tenant_id,
        }
        canonical_bytes = canonicalize(canonical_dict)
        canonical_hash  = hashlib.sha256(DOMAIN_TAG + canonical_bytes).digest()
        _signature, _kid = sign(self.tenant_slug, canonical_hash)

        exception_id = uuid.uuid4()
        now          = datetime.now(timezone.utc)

        # Lineage hashes — same pattern as SC-002
        input_hash  = hashlib.sha256(INGESTION_TAG + canonical_bytes).hexdigest()
        output_hash = canonical_hash.hex()

        reference_data_snapshot = json.dumps({
            "shipment_exception_normalizer": TRANSFORM_VER,
            "currency_table":                "iso-4217-v2026.01",
            "transform_applied_at":          now.isoformat(),
        })
        canonical_records_json = json.dumps([
            {
                "type":         "shipment_exception",
                "id":           str(exception_id),
                "payload_hash": "sha256:" + output_hash,
            }
        ])

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            # Ensure the canonical table exists (idempotent DDL guard — migration 0005 is
            # authoritative; this CREATE IF NOT EXISTS is a safety net for test environments)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS canonical_shipment_exceptions (
                    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id            UUID        NOT NULL,
                    source_record_id     UUID        NOT NULL,
                    case_id              UUID,
                    shipment_reference   TEXT        NOT NULL,
                    carrier_id           TEXT        NOT NULL,
                    committed_eta        TIMESTAMPTZ NOT NULL,
                    actual_delivery      TIMESTAMPTZ NOT NULL,
                    sla_breach_hours     FLOAT       NOT NULL DEFAULT 0,
                    sla_penalty_amount   FLOAT       NOT NULL DEFAULT 0,
                    currency             TEXT        NOT NULL DEFAULT 'INR',
                    origin               TEXT,
                    destination          TEXT,
                    canonical_hash       BYTEA       NOT NULL,
                    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_canonical_shipment_ref
                        UNIQUE (tenant_id, shipment_reference)
                )
            """)

            # Upsert canonical row — dedup on (tenant_id, shipment_reference)
            cur.execute("""
                INSERT INTO canonical_shipment_exceptions
                    (id, tenant_id, source_record_id, case_id,
                     shipment_reference, carrier_id,
                     committed_eta, actual_delivery,
                     sla_breach_hours, sla_penalty_amount,
                     currency, origin, destination,
                     canonical_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, shipment_reference) DO NOTHING
                RETURNING id
            """, (
                exception_id, tenant_id, source_record_id, None,
                shipment_reference, carrier_id,
                committed_eta, actual_delivery,
                breach_hours, penalty_amount,
                currency, origin, destination,
                canonical_hash, now,
            ))
            row = cur.fetchone()
            if row is None:
                # Row already existed — fetch the existing PK
                cur.execute(
                    "SELECT id FROM canonical_shipment_exceptions "
                    "WHERE tenant_id=%s AND shipment_reference=%s",
                    (tenant_id, shipment_reference),
                )
                exception_id = cur.fetchone()[0]

            # Full lineage record — mirrors SC-002 exactly (17 columns)
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
                uuid.uuid4(), tenant_id,
                "CANONICAL_SHIPMENT_EXCEPTION", exception_id, source_record_id,
                "CANONICALIZED", canonical_hash, now,
                TRANSFORM_ID, TRANSFORM_VER,
                input_hash, output_hash,
                reference_data_snapshot, now, SERVICE_SPIFFE,
                canonical_records_json, "zoiko/v1/lineage-record",
            ))

            # Mark the source record as processed
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

        # Kafka publish — best-effort, never blocks the caller
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "zoiko.shipment.exception.canonical",
                key       = str(exception_id),
                payload   = {
                    "exception_id":       str(exception_id),
                    "shipment_reference": shipment_reference,
                    "carrier_id":         carrier_id,
                    "sla_breach_hours":   breach_hours,
                    "penalty_amount":     penalty_amount,
                    "canonical_hash":     output_hash,
                    "transform_version":  TRANSFORM_VER,
                },
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return CanonicalShipmentExceptionResult(
            id                 = exception_id,
            tenant_id          = tenant_id,
            source_record_id   = source_record_id,
            case_id            = None,
            shipment_reference = shipment_reference,
            carrier_id         = carrier_id,
            committed_eta      = committed_eta,
            actual_delivery    = actual_delivery,
            sla_breach_hours   = breach_hours,
            penalty_amount     = penalty_amount,
            currency           = currency,
            origin             = origin,
            destination        = destination,
            canonical_hash     = output_hash,
            created_at         = now,
        )
