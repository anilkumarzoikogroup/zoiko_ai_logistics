"""
SC-003 Audit ACR — Action Certification Record.

8 artifacts assembled into a Merkle tree, then WORM-locked.

Artifacts:
  1. source_record_hash        — ingestion canonical hash
  2. canonical_shipment_hash   — canonical_shipment_exceptions hash
  3. evidence_bundle_hash      — evidence_bundles.bundle_hash
  4. finding_hash              — findings.finding_hash
  5. proposal_hash             — decision_proposals.proposal_hash
  6. governance_decision_hash  — governance_decisions.decision_hash
  7. governance_token_hash     — governance_tokens.token_hash
  8. execution_envelope_hash   — execution_envelopes.signature (sha256 of envelope payload)
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone

import paths  # noqa: F401

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL


_DOMAIN = "zoiko/v1/acr"


def _sha256(tag: str, data: bytes) -> bytes:
    return hashlib.sha256(tag.encode() + b":" + data).digest()


class AuditACRHandler:

    def __init__(self, db_url: str | None = None, broker=None):
        self._db_url = db_url or _DEFAULT_DB_URL
        self._broker = broker

    def issue_acr(
        self,
        tenant_id:   str,
        case_id:     str,
        envelope_id: str,
        actor_sub:   str,
    ) -> dict:
        """Gather 8 artifacts, build Merkle ACR, write WORM record."""
        artifacts = self._gather_artifacts(tenant_id, case_id, envelope_id)
        if not artifacts:
            return {"status": "ERROR", "detail": "Insufficient artifacts to issue ACR"}

        acr_root = self._build_merkle(artifacts)
        acr_id   = self._write_acr(tenant_id, case_id, envelope_id, actor_sub, artifacts, acr_root)
        self._write_worm(tenant_id, case_id, str(acr_id), acr_root)
        self._advance_case(tenant_id, case_id, actor_sub)
        self._publish_kafka(tenant_id, case_id, str(acr_id))

        try:
            from services.transparency_log_svc.handler import TransparencyLogHandler
            slug_row = q1("SELECT slug FROM tenants WHERE id=%s::uuid", (tenant_id,))
            slug = slug_row["slug"] if slug_row else "default"
            TransparencyLogHandler(self._db_url, slug).append(
                tenant_id, str(acr_id), acr_root.hex()
            )
        except Exception:
            pass   # transparency log is best-effort — never block ACR issuance

        return {
            "status":        "ISSUED",
            "acr_id":        str(acr_id),
            "case_id":       case_id,
            "acr_root_hash": acr_root.hex(),
            "artifact_count": len(artifacts),
            "issued_at":     datetime.now(timezone.utc).isoformat(),
        }

    def get_acr(self, tenant_id: str, case_id: str) -> dict | None:
        row = q1("""
            SELECT id::text, case_id::text, acr_root_hash, artifact_count,
                   artifact_hashes, is_locked, issued_at
            FROM   action_certification_records
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY issued_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if not row:
            return None
        return {
            "acr_id":         row["id"],
            "case_id":        row["case_id"],
            "acr_root_hash":  bytes(row["acr_root_hash"]).hex() if row["acr_root_hash"] else "",
            "artifact_count": row["artifact_count"],
            "artifact_hashes": row["artifact_hashes"],
            "is_locked":      row["is_locked"],
            "issued_at":      row["issued_at"].isoformat() if row["issued_at"] else None,
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    def _gather_artifacts(self, tenant_id: str, case_id: str, envelope_id: str) -> dict:
        arts = {}

        # 1. source_record_hash
        row = q1("""
            SELECT sr.canonical_hash
            FROM   source_records sr
            JOIN   cases c ON c.tenant_id = sr.tenant_id
                          AND c.shipment_reference = sr.external_source_ref
            WHERE  c.id=%s::uuid AND c.tenant_id=%s::uuid
            LIMIT 1
        """, (case_id, tenant_id))
        if row and row["canonical_hash"]:
            arts["source_record_hash"] = bytes(row["canonical_hash"])

        # 2. canonical_shipment_hash
        row = q1("""
            SELECT canonical_hash FROM canonical_shipment_exceptions
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1
        """, (case_id, tenant_id))
        if row and row["canonical_hash"]:
            arts["canonical_shipment_hash"] = bytes(row["canonical_hash"])

        # 3. evidence_bundle_hash
        row = q1("""
            SELECT bundle_hash FROM evidence_bundles
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY created_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if row and row["bundle_hash"]:
            arts["evidence_bundle_hash"] = bytes(row["bundle_hash"])

        # 4. finding_hash
        row = q1("""
            SELECT finding_hash FROM findings
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY created_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if row and row["finding_hash"]:
            arts["finding_hash"] = bytes(row["finding_hash"])

        # 5. proposal_hash
        row = q1("""
            SELECT proposal_hash FROM decision_proposals
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY created_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if row and row["proposal_hash"]:
            arts["proposal_hash"] = bytes(row["proposal_hash"])

        # 6. governance_decision_hash
        row = q1("""
            SELECT decision_hash FROM governance_decisions
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY decided_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if row and row["decision_hash"]:
            arts["governance_decision_hash"] = bytes(row["decision_hash"])

        # 7. governance_token_hash
        row = q1("""
            SELECT token_hash FROM governance_tokens
            WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            ORDER BY issued_at DESC LIMIT 1
        """, (case_id, tenant_id))
        if row and row["token_hash"]:
            arts["governance_token_hash"] = bytes(row["token_hash"])

        # 8. execution_envelope_hash — sha256 of envelope payload
        row = q1("""
            SELECT payload FROM execution_envelopes
            WHERE  id=%s::uuid AND tenant_id=%s::uuid
        """, (envelope_id, tenant_id))
        if row and row["payload"]:
            payload_str = row["payload"] if isinstance(row["payload"], str) else json.dumps(row["payload"])
            arts["execution_envelope_hash"] = hashlib.sha256(payload_str.encode()).digest()

        return arts

    def _build_merkle(self, artifacts: dict) -> bytes:
        """Simple sequential Merkle: hash each leaf with domain tag, then fold pairs."""
        leaves = []
        for name, raw_hash in artifacts.items():
            tag = f"{_DOMAIN}/{name}"
            leaves.append(_sha256(tag, raw_hash))

        if not leaves:
            return b"\x00" * 32

        nodes = leaves[:]
        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left  = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
                next_level.append(hashlib.sha256(left + right).digest())
            nodes = next_level

        return nodes[0]

    def _write_acr(
        self, tenant_id, case_id, envelope_id, actor_sub, artifacts, acr_root,
    ) -> uuid.UUID:
        acr_id = uuid.uuid4()
        artifact_hashes = {k: v.hex() for k, v in artifacts.items()}
        q("""
            INSERT INTO action_certification_records
                (id, tenant_id, case_id, envelope_id, actor_sub,
                 acr_root_hash, artifact_count, artifact_hashes, is_locked, issued_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s,
                    %s, %s, %s::jsonb, true, NOW())
            ON CONFLICT DO NOTHING
        """, (
            acr_id, tenant_id, case_id, envelope_id, actor_sub,
            acr_root,
            len(artifacts),
            json.dumps(artifact_hashes),
        ))
        return acr_id

    def _write_worm(self, tenant_id: str, case_id: str, acr_id: str, acr_root: bytes) -> None:
        q("""
            INSERT INTO audit_worm_index
                (id, tenant_id, record_type, record_id, record_hash, is_locked, locked_at)
            VALUES (gen_random_uuid(), %s::uuid, 'ACR', %s, %s, true, NOW())
            ON CONFLICT DO NOTHING
        """, (tenant_id, acr_id, acr_root))

    def _advance_case(self, tenant_id: str, case_id: str, actor_sub: str) -> None:
        q("""
            UPDATE cases SET state='CLOSED'
            WHERE  id=%s::uuid AND tenant_id=%s::uuid AND state='OUTCOME_RECORDED'
        """, (case_id, tenant_id))
        q("""
            INSERT INTO case_events
                (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'STATE_TRANSITION',
                    'OUTCOME_RECORDED', 'CLOSED', %s,
                    '{"action":"ACR_ISSUED"}'::jsonb, NOW())
        """, (tenant_id, case_id, actor_sub))

    def _publish_kafka(self, tenant_id: str, case_id: str, acr_id: str) -> None:
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            prod = ZoikoProducer(self._broker)
            prod.publish(KafkaMessage(
                topic="zoiko.audit.locked", key=case_id,
                payload={"case_id": case_id, "acr_id": acr_id},
                tenant_id=tenant_id,
            ))
        except Exception:
            pass
