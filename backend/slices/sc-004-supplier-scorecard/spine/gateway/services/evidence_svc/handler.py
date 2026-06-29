"""
SC-004 Evidence Service — Domain 7.

Builds a Merkle evidence bundle over supplier scorecard data.
The bundle root is signed and stored in evidence_bundles.
Each piece of evidence (scorecard metrics, raw data) is an evidence_item.
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


class EvidenceHandler:
    def __init__(self, db_url: str, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.tenant_slug = tenant_slug

    def build_bundle(
        self,
        tenant_id:    str,
        case_id:      str,
        scorecard_id: str,
        carrier_id:   str,
        scores:       dict,
        raw_metrics:  dict,
        threshold:    float,
    ) -> dict:
        """
        Build and persist an evidence bundle for the scorecard breach.
        Returns bundle_id and bundle_hash.
        """
        tenant_id    = str(tenant_id)
        case_id      = str(case_id)
        scorecard_id = str(scorecard_id)
        now          = datetime.now(timezone.utc)

        # Evidence item payload
        evidence_payload = json.dumps({
            "scorecard_period_id":  scorecard_id,
            "carrier_id":           carrier_id,
            "composite_score":      scores.get("composite_score"),
            "contracted_threshold": threshold,
            "breach_delta":         round(scores.get("composite_score", 0) - threshold, 2),
            "sub_scores": {
                "on_time":    scores.get("on_time_score"),
                "quality":    scores.get("quality_score"),
                "frequency":  scores.get("frequency_score"),
                "resolution": scores.get("resolution_score"),
            },
            "raw_metrics": raw_metrics,
        }, sort_keys=True).encode()

        item_hash   = hashlib.sha256(b"zoiko.evidence.item.v1:" + evidence_payload).digest()
        bundle_hash = hashlib.sha256(b"zoiko/v1/evidence-item:" + item_hash).digest()

        bundle_sig, bundle_kid = sign(self.tenant_slug, bundle_hash)

        bundle_id = uuid.uuid4()

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO evidence_bundles
                    (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (str(bundle_id), tenant_id, case_id, bundle_hash, bundle_sig, bundle_kid, now))

            ei_payload  = json.dumps({
                "scorecard_period_id": scorecard_id,
                "carrier_id":          carrier_id,
                "composite_score":     scores.get("composite_score"),
                "breach_amount":       scores.get("breach_amount"),
            })
            ei_hash    = hashlib.sha256(b"zoiko.evidence.item.v1:" + ei_payload.encode()).hexdigest()
            ei_sig, ei_kid = sign(self.tenant_slug, ei_hash.encode())

            cur.execute("""
                INSERT INTO evidence_items
                    (id, tenant_id, bundle_id, item_type, entity_id,
                     item_hash, signature, kid, added_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                        'SCORECARD_METRICS', %s::uuid, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                tenant_id, str(bundle_id), scorecard_id,
                ei_hash, ei_sig, ei_kid, now,
            ))

            conn.commit()
        finally:
            conn.close()

        return {
            "bundle_id":   str(bundle_id),
            "bundle_hash": bundle_hash.hex(),
            "item_hash":   item_hash.hex(),
        }
