import paths  # noqa: F401
import uuid
import hashlib
import json
from datetime import datetime, timezone

from shared.db import q, q1, DB_URL
from zoiko_common.crypto.jcs import canonicalize as jcs
from shared.signer import sign


class CanonicalHandler:
    def __init__(self, db_url: str = DB_URL):
        self._db_url = db_url

    def canonicalize(
        self,
        tenant_id,
        source_record_id,
        carrier_id,
        invoice_reference,
        invoice_date,
        charge_lines,
        currency,
        dispute_total,
    ) -> dict:
        canonical_dict = {
            "carrier_id": carrier_id,
            "charge_lines": charge_lines,
            "currency": currency,
            "dispute_total": dispute_total,
            "invoice_date": invoice_date,
            "invoice_reference": invoice_reference,
            "tenant_id": str(tenant_id),
        }

        canonical_bytes = jcs(canonical_dict)
        canonical_hash = hashlib.sha256(
            b"zoiko.canonical.invoice.v1:" + canonical_bytes
        ).digest()
        sig_bytes, kid = sign("default", canonical_hash)

        invoice_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        import json as _json
        q(
            """
            INSERT INTO canonical_invoices
                (id, tenant_id, source_record_id, carrier_id, invoice_number,
                 total_amount, currency, canonical_hash, signature, kid, created_at,
                 invoice_date, transport_mode, charge_lines)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, invoice_number) DO NOTHING
            """,
            (
                str(invoice_id),
                str(tenant_id),
                str(source_record_id),
                carrier_id,
                invoice_reference,
                dispute_total,
                currency,
                canonical_hash,
                sig_bytes,
                kid,
                now,
                invoice_date,
                "ROAD",
                _json.dumps(charge_lines),
            ),
            self._db_url,
        )

        # Fetch actual ID — ON CONFLICT DO NOTHING skips INSERT if row already exists,
        # so we must look up the persisted row rather than assuming invoice_id was written.
        existing = q1(
            "SELECT id FROM canonical_invoices WHERE tenant_id = %s::uuid AND invoice_number = %s LIMIT 1",
            (str(tenant_id), invoice_reference),
            self._db_url,
        )
        actual_invoice_id = str(existing["id"]) if existing else str(invoice_id)

        return {
            "canonical_invoice_id": actual_invoice_id,
            "canonical_hash": canonical_hash.hex(),
            "dispute_total": dispute_total,
        }
