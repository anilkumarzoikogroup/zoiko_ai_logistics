"""
SC-004 Canonical Truth — Domain 4.

Writes the canonical supplier scorecard period entity after metrics have
been computed. This is the authoritative, lineage-linked record of a
supplier's performance for a given period.

Canonical entity: scorecard_periods (already exists from scorecard_svc).
This service writes the lineage_record linking source → canonical.
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


class CanonicalTruthHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.tenant_slug = tenant_slug

    def write_lineage(
        self,
        tenant_id:        str,
        source_record_id: str,
        scorecard_id:     str,
        carrier_id:       str,
        composite_score:  float,
        period_start:     datetime,
        period_end:       datetime,
    ) -> dict:
        """
        Write a lineage_record linking the source_record to the canonical
        scorecard_period entity. Returns the lineage_record_id.
        """
        tenant_id        = str(tenant_id)
        source_record_id = str(source_record_id)
        scorecard_id     = str(scorecard_id)
        now              = datetime.now(timezone.utc)

        lineage_payload = {
            "source_record_id": source_record_id,
            "canonical_id":     scorecard_id,
            "canonical_type":   "SCORECARD_PERIOD",
            "carrier_id":       carrier_id,
            "composite_score":  composite_score,
            "period_start":     period_start.isoformat(),
            "period_end":       period_end.isoformat(),
        }
        lineage_bytes = json.dumps(lineage_payload, sort_keys=True).encode()
        lineage_hash  = hashlib.sha256(b"zoiko.canonical.scorecard.v1:" + lineage_bytes).digest()
        sig, kid      = sign(self.tenant_slug, lineage_hash)

        lineage_id = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO lineage_records
                    (id, tenant_id, source_record_id, canonical_entity_type,
                     canonical_entity_id, transform_version, lineage_hash,
                     signature, kid, created_at)
                VALUES (%s, %s, %s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                lineage_id, tenant_id, source_record_id,
                "SCORECARD_PERIOD", scorecard_id,
                "sc004-canonical-v1",
                lineage_hash, sig, kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {
            "lineage_record_id":  str(lineage_id),
            "canonical_type":     "SCORECARD_PERIOD",
            "canonical_id":       scorecard_id,
            "lineage_hash":       lineage_hash.hex(),
        }
