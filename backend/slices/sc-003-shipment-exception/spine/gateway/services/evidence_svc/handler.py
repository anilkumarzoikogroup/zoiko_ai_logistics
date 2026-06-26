"""
Evidence Service — adds items to an evidence bundle, maintains the Merkle root.

Every add_item call:
  1. SHA-256 domain-tagged hash of raw content bytes
  2. Sign the item hash
  3. Upsert evidence_bundle for this (tenant_id, case_id)
  4. INSERT evidence_item (APPEND-ONLY — no UPDATE/DELETE ever)
  5. Recompute Merkle root over ALL items in bundle → UPDATE bundle
  6. Publish evidence.added to Kafka

Merkle domain tag: "zoiko/v1/evidence-item"  (matches MerkleTree domain format)
Item hash domain:  b"zoiko.evidence.item.v1:"

SC-003 requires exactly 5 artifact types (spec §SC-003 evidence domain):
  1. source_record               — raw shipment event stream hash
  2. canonical_shipment_exception — canonical truth hash (breach + penalty computed)
  3. sla_contract_clause          — the SLA clause that governs the breach
  4. breach_calculation           — detailed breach-hours and penalty computation
  5. rule_trace                   — the reasoning rule weights (delivery_window_breach, sla_clause_applicable)

No contract_rate_version artifact — shipment_exception has no contract rate version.
"""
import hashlib, uuid, json
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.merkle import MerkleTree

from services.evidence_svc.models import EvidenceItemResult, EvidenceBundleResult

DOMAIN_TAG    = b"zoiko.evidence.item.v1:"
MERKLE_DOMAIN = "zoiko/v1/evidence-item"

# All 5 artifact types required by SC-003 acceptance criteria.
# seal_bundle() will reject with ValueError if any are absent.
REQUIRED_ITEM_TYPES = {
    "source_record",
    "canonical_shipment_exception",
    "sla_contract_clause",
    "breach_calculation",
    "rule_trace",
}


class EvidenceHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def add_item(
        self,
        tenant_id:     str,
        case_id:       str,
        item_type:     str,
        content_bytes: bytes,
        entity_id:     uuid.UUID = None,
        actor_sub:     str = "system",
    ) -> EvidenceItemResult:
        tenant_id = str(tenant_id)
        case_id   = str(case_id)
        entity_id = uuid.UUID(str(entity_id)) if entity_id else uuid.uuid4()
        now       = datetime.now(timezone.utc)

        # Step 1 — domain-tagged SHA-256 of content
        item_hash = hashlib.sha256(DOMAIN_TAG + content_bytes).digest()

        # Step 2 — sign item hash
        signature, kid = sign(self.tenant_slug, item_hash)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Step 3 — upsert evidence_bundle (one bundle per case)
            cur.execute(
                "SELECT id FROM evidence_bundles WHERE tenant_id=%s AND case_id=%s LIMIT 1",
                (tenant_id, uuid.UUID(case_id)),
            )
            row = cur.fetchone()

            if row:
                bundle_id = row["id"]
            else:
                bundle_id = uuid.uuid4()
                # Placeholder hash (single-leaf Merkle = item_hash itself via leaf function)
                placeholder = item_hash
                cur.execute("""
                    INSERT INTO evidence_bundles
                        (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (bundle_id, tenant_id, uuid.UUID(case_id), placeholder, signature, kid, now))

            # Step 4 — APPEND-ONLY insert of evidence_item
            # signature/kid were already computed in Step 2 — store them so
            # this item is independently verifiable, not just folded into the
            # bundle-level signature.
            item_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO evidence_items
                    (id, tenant_id, bundle_id, item_type, entity_id, item_hash,
                     signature, kid, added_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (item_id, tenant_id, bundle_id, item_type, entity_id, item_hash,
                  signature, kid, now))

            # Step 5 — recompute Merkle root over ALL items in bundle
            cur.execute(
                "SELECT item_hash FROM evidence_items WHERE bundle_id=%s ORDER BY added_at ASC",
                (bundle_id,),
            )
            all_hashes = [bytes(r["item_hash"]) for r in cur.fetchall()]

            tree = MerkleTree(MERKLE_DOMAIN)
            for h in all_hashes:
                tree.append(h)
            bundle_hash = tree.root()

            bundle_sig, bundle_kid = sign(self.tenant_slug, bundle_hash)
            cur.execute("""
                UPDATE evidence_bundles
                SET bundle_hash=%s, signature=%s, kid=%s
                WHERE id=%s
            """, (bundle_hash, bundle_sig, bundle_kid, bundle_id))

            # Atomic outbox INSERT in same transaction (crash-safe)
            outbox_payload = {
                "bundle_id": str(bundle_id),
                "item_id":   str(item_id),
                "case_id":   case_id,
                "item_type": item_type,
                "item_hash": item_hash.hex(),
            }
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.evidence.bundled",
                str(bundle_id), json.dumps(outbox_payload), now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Step 6 — Kafka publish AFTER commit (outbox relay recovers if this crashes)
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic          = "zoiko.evidence.bundled",
            key            = str(bundle_id),
            payload        = outbox_payload,
            tenant_id      = tenant_id,
            correlation_id = case_id,
        ))

        return EvidenceItemResult(
            item_id     = item_id,
            bundle_id   = bundle_id,
            tenant_id   = tenant_id,
            case_id     = case_id,
            item_type   = item_type,
            item_hash   = item_hash.hex(),
            bundle_hash = bundle_hash.hex(),
            added_at    = now,
        )

    def get_bundle(self, tenant_id: str, case_id: str) -> EvidenceBundleResult:
        tenant_id = str(tenant_id)
        case_id   = str(case_id)

        conn = psycopg2.connect(self.db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "SELECT id, bundle_hash, created_at, completeness_status "
            "FROM evidence_bundles "
            "WHERE tenant_id=%s AND case_id=%s LIMIT 1",
            (tenant_id, uuid.UUID(case_id)),
        )
        bundle = cur.fetchone()
        if not bundle:
            raise ValueError(f"No evidence bundle found for case {case_id}")

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM evidence_items WHERE bundle_id=%s",
            (bundle["id"],),
        )
        item_count = cur.fetchone()["cnt"]
        conn.close()

        return EvidenceBundleResult(
            bundle_id           = bundle["id"],
            tenant_id           = tenant_id,
            case_id             = case_id,
            bundle_hash         = bytes(bundle["bundle_hash"]).hex(),
            item_count          = item_count,
            created_at          = bundle["created_at"],
            completeness_status = bundle.get("completeness_status", "INCOMPLETE"),
        )

    def seal_bundle(self, tenant_id: str, case_id: str, actor_sub: str = "system") -> EvidenceBundleResult:
        """Mark the evidence bundle as COMPLETE. Reasoning is blocked until this is called."""
        tenant_id = str(tenant_id)
        case_id   = str(case_id)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, bundle_hash, created_at, completeness_status "
                "FROM evidence_bundles WHERE tenant_id=%s AND case_id=%s LIMIT 1",
                (tenant_id, uuid.UUID(case_id)),
            )
            bundle = cur.fetchone()
            if not bundle:
                raise ValueError(f"No evidence bundle found for case {case_id}")
            if bundle["completeness_status"] == "COMPLETE":
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM evidence_items WHERE bundle_id=%s",
                    (bundle["id"],),
                )
                item_count = cur.fetchone()["cnt"]
                conn.close()
                return EvidenceBundleResult(
                    bundle_id           = bundle["id"],
                    tenant_id           = tenant_id,
                    case_id             = case_id,
                    bundle_hash         = bytes(bundle["bundle_hash"]).hex(),
                    item_count          = item_count,
                    created_at          = bundle["created_at"],
                    completeness_status = "COMPLETE",
                )

            # Completeness check — all 5 required artifact types must be present
            # before the bundle can be sealed. Reasoning is blocked until this passes.
            cur.execute(
                "SELECT DISTINCT item_type FROM evidence_items WHERE bundle_id=%s",
                (bundle["id"],),
            )
            present_types = {row["item_type"] for row in cur.fetchall()}
            missing_types = REQUIRED_ITEM_TYPES - present_types
            if missing_types:
                raise ValueError(
                    f"Evidence bundle {bundle['id']} is missing required artifact "
                    f"type(s): {sorted(missing_types)}. All 5 types must be added "
                    f"before sealing: {sorted(REQUIRED_ITEM_TYPES)}"
                )

            cur.execute(
                "UPDATE evidence_bundles SET completeness_status='COMPLETE' "
                "WHERE id=%s",
                (bundle["id"],),
            )
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM evidence_items WHERE bundle_id=%s",
                (bundle["id"],),
            )
            item_count = cur.fetchone()["cnt"]
            conn.commit()
            bundle_id = bundle["id"]
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic          = "zoiko.evidence.bundled",
            key            = str(bundle_id),
            payload        = {
                "bundle_id":            str(bundle_id),
                "case_id":              case_id,
                "completeness_status":  "COMPLETE",
                "sealed_by":            actor_sub,
            },
            tenant_id      = tenant_id,
            correlation_id = case_id,
        ))

        return EvidenceBundleResult(
            bundle_id           = bundle_id,
            tenant_id           = tenant_id,
            case_id             = case_id,
            bundle_hash         = bytes(bundle["bundle_hash"]).hex(),
            item_count          = item_count,
            created_at          = bundle["created_at"],
            completeness_status = "COMPLETE",
        )
