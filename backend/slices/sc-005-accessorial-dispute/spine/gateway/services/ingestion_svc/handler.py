import paths  # noqa F401
import uuid
import hashlib
import json
from datetime import datetime, timezone

from shared.db import q, q1, DB_URL
from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

DOMAIN_TAG = b"zoiko.ingestion.invoice.v1:"
SERVICE_SPIFFE = "spiffe://zoiko/system/ingestion-sc005"


class IngestionHandler:
    def __init__(self, db_url: str = DB_URL):
        self._db_url = db_url

    def ingest(
        self,
        tenant_id: str,
        carrier_id: str,
        invoice_reference: str,
        invoice_date: str,
        charge_lines: list,
        currency: str,
    ) -> dict:
        source_record_id = uuid.uuid4()
        idem_key = str(uuid.uuid4())

        source_payload = {
            "carrier_id": carrier_id,
            "charge_lines": charge_lines,
            "currency": currency,
            "invoice_date": invoice_date,
            "invoice_reference": invoice_reference,
            "tenant_id": tenant_id,
        }

        canonical_bytes = canonicalize(source_payload)
        canonical_hash_bytes = hashlib.sha256(DOMAIN_TAG + canonical_bytes).digest()

        # DEV: canonical bytes used as ciphertext (no AES-GCM in dev mode)
        ciphertext = canonical_bytes

        signature_bytes, kid = sign("default", canonical_hash_bytes)

        # Tariff-by-reference: look up contracted caps from accessorial_tariff_caps.
        # Updates each charge_line dict in place; falls back to user-provided cap if no record exists.
        for line in charge_lines:
            tariff_row = q1(
                """
                SELECT cap_amount, tariff_id, tariff_version
                FROM accessorial_tariff_caps
                WHERE tenant_id   = %s::uuid
                  AND carrier_id  = %s
                  AND charge_type = %s
                  AND (effective_to IS NULL OR effective_to > NOW())
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tenant_id, carrier_id, line["charge_type"]),
                self._db_url,
            )
            if tariff_row:
                line["contracted_cap"] = float(tariff_row["cap_amount"])
                if tariff_row.get("tariff_id"):
                    line["tariff_id"] = tariff_row["tariff_id"]
                if tariff_row.get("tariff_version"):
                    line["tariff_version"] = tariff_row["tariff_version"]

        received_at = datetime.now(timezone.utc)

        q(
            """
            INSERT INTO source_records
                (id, tenant_id,
                 source_type, source_type_version,
                 external_source_ref,
                 received_at, received_by_service,
                 canonical_hash, ciphertext,
                 signature, kid,
                 idempotency_key)
            VALUES
                (%s, %s,
                 %s, %s,
                 %s,
                 %s, %s,
                 %s, %s,
                 %s, %s,
                 %s)
            ON CONFLICT DO NOTHING
            """,
            (
                source_record_id,
                uuid.UUID(tenant_id),
                "ACCESSORIAL_INVOICE", "v1",
                invoice_reference,
                received_at, SERVICE_SPIFFE,
                canonical_hash_bytes, ciphertext,
                signature_bytes, kid,
                idem_key,
            ),
            self._db_url,
        )

        # Recompute dispute_total using tariff-validated caps (updated in place above)
        dispute_total = sum(
            max(0, float(line["billed_amount"]) - float(line["contracted_cap"]))
            for line in charge_lines
        )

        return {
            "source_record_id": str(source_record_id),
            "charge_lines": charge_lines,
            "total_billed": sum(float(l["billed_amount"]) for l in charge_lines),
            "total_cap": sum(float(l["contracted_cap"]) for l in charge_lines),
            "dispute_total": dispute_total,
        }
