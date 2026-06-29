"""
SC-004 Ingestion Service — Domain 2.

Receives supplier performance feed (from API, file, or scheduled job),
hashes the payload before storage, and writes a source_record row.
Hash-before-store is a non-negotiable platform rule.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

from shared.signer import sign


class IngestionHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.tenant_slug = tenant_slug

    def ingest(self, tenant_id: str, payload: dict) -> dict:
        """
        Write a source_record for a supplier scorecard feed payload.
        Returns the source_record_id and record_hash.
        """
        tenant_id = str(tenant_id)
        now       = datetime.now(timezone.utc)

        # Hash-before-store (Domain 2 platform rule)
        raw_bytes   = json.dumps(payload, sort_keys=True).encode("utf-8")
        record_hash = hashlib.sha256(b"zoiko.ingestion.scorecard.v1:" + raw_bytes).digest()
        sig, kid    = sign(self.tenant_slug, record_hash)

        source_id = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO source_records
                    (id, tenant_id, source_type, channel, raw_payload,
                     record_hash, signature, kid, received_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                source_id, tenant_id,
                "SUPPLIER_SCORECARD_FEED", "API",
                json.dumps(payload),
                record_hash, sig, kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {
            "source_record_id": str(source_id),
            "record_hash":      record_hash.hex(),
            "received_at":      now.isoformat(),
        }
