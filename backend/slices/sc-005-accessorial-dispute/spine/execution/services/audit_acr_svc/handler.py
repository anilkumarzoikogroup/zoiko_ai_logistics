import paths  # noqa: F401 — sys.path bootstrap, must be first
import uuid
import hashlib
import json
from datetime import datetime, timezone

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL
from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize as jcs

try:
    from zoiko_common.crypto.merkle import MerkleTree
    _HAS_MERKLE = True
except ImportError:
    _HAS_MERKLE = False


def _to_bytes(value) -> bytes:
    """Normalise a hash value (bytes, hex str, or memoryview) to bytes."""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, str):
        try:
            return bytes.fromhex(value)
        except ValueError:
            return value.encode()
    return bytes(value)


class AuditACRHandler:
    def __init__(self, db_url=None, broker=None):
        self._db_url = db_url or _DEFAULT_DB_URL
        self._broker = broker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_artifacts(self, tenant_id: str, case_id: str) -> list:
        """Collect 8 artifact rows from the database."""
        artifacts = []

        # a. source_record
        row = q1(
            "SELECT id, canonical_hash FROM source_records "
            "WHERE tenant_id=%s::uuid ORDER BY created_at LIMIT 1",
            (tenant_id,),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "source_record",
                "id": str(row["id"]),
                "hash": _to_bytes(row["canonical_hash"]),
            })

        # b. canonical_invoice
        row = q1(
            "SELECT ci.id, ci.canonical_hash "
            "FROM canonical_invoices ci "
            "JOIN cases c ON c.invoice_id = ci.id "
            "WHERE c.id = %s::uuid",
            (case_id,),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "canonical_invoice",
                "id": str(row["id"]),
                "hash": _to_bytes(row["canonical_hash"]),
            })

        # c. evidence_bundle
        row = q1(
            "SELECT id, bundle_hash AS content_hash "
            "FROM evidence_bundles "
            "WHERE case_id = %s::uuid AND tenant_id = %s::uuid "
            "ORDER BY created_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "evidence_bundle",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        # d. finding
        row = q1(
            "SELECT id, finding_hash AS content_hash "
            "FROM findings "
            "WHERE case_id = %s::uuid AND tenant_id = %s::uuid "
            "ORDER BY created_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "finding",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        # e. decision_proposal
        row = q1(
            "SELECT id, proposal_hash AS content_hash "
            "FROM decision_proposals "
            "WHERE case_id = %s::uuid AND tenant_id = %s::uuid "
            "ORDER BY created_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "decision_proposal",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        # f. governance_decision
        row = q1(
            "SELECT gd.id, gd.decision_hash AS content_hash "
            "FROM governance_decisions gd "
            "JOIN governance_tasks gt ON gt.id = gd.proposal_id "
            "WHERE gt.case_id = %s::uuid AND gt.tenant_id = %s::uuid "
            "ORDER BY gd.decided_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "governance_decision",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        # g. governance_token
        row = q1(
            "SELECT gt.id, gt.token_hash AS content_hash "
            "FROM governance_tokens gt "
            "JOIN governance_decisions gd ON gd.id = gt.decision_id "
            "JOIN governance_tasks task ON task.id = gd.proposal_id "
            "WHERE task.case_id = %s::uuid AND gt.tenant_id = %s::uuid "
            "ORDER BY gt.issued_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "governance_token",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        # h. execution_envelope
        row = q1(
            "SELECT id, signature AS content_hash "
            "FROM execution_envelopes "
            "WHERE case_id = %s::uuid AND tenant_id = %s::uuid "
            "ORDER BY created_at LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if row:
            artifacts.append({
                "type": "execution_envelope",
                "id": str(row["id"]),
                "hash": _to_bytes(row["content_hash"]),
            })

        return artifacts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def issue_acr(self, tenant_id: str, case_id: str, actor_sub: str) -> dict:
        """
        Issue an 8-artifact Merkle Action Certification Record (ACR).

        Steps:
          1. Collect 8 artifacts from DB.
          2. Build Merkle tree (or SHA-256 concat fallback).
          3. Sign the Merkle root.
          4. INSERT action_certification_records (WORM, is_locked=True).
          5. INSERT audit_worm_index rows for each artifact.
          6. Advance case to CLOSED state.
          7. Return ACR summary dict.
        """
        now = datetime.now(timezone.utc)

        # 1. Collect artifacts
        artifacts = self._collect_artifacts(tenant_id, case_id)

        # 2. Build Merkle tree / fallback
        artifact_hashes = [a["hash"] for a in artifacts]

        if _HAS_MERKLE and artifact_hashes:
            try:
                tree = MerkleTree("zoiko/v1/acr")
                for h in artifact_hashes:
                    tree.append(h)
                merkle_root: bytes = tree.root()
            except Exception:
                # Fallback: SHA-256 of all hashes concatenated
                combined = b"".join(artifact_hashes)
                merkle_root = hashlib.sha256(combined).digest()
        elif artifact_hashes:
            combined = b"".join(artifact_hashes)
            merkle_root = hashlib.sha256(combined).digest()
        else:
            # No artifacts found — hash an empty sentinel
            merkle_root = hashlib.sha256(b"zoiko/v1/acr:empty").digest()

        # 3. Sign the Merkle root
        acr_sig, acr_kid = sign("default", merkle_root)

        # 4. INSERT action_certification_records
        acr_id = uuid.uuid4()

        q(
            """
            INSERT INTO action_certification_records
                (id, tenant_id, case_id, artifact_count, merkle_root,
                 signature, kid, issued_by, is_locked, issued_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(acr_id),
                str(tenant_id),
                str(case_id),
                8,
                merkle_root,
                acr_sig,
                acr_kid,
                actor_sub,
                True,   # is_locked — WORM, irreversible
                now,
            ),
            db_url=self._db_url,
        )

        # 5. INSERT audit_worm_index rows (one per artifact, ON CONFLICT DO NOTHING)
        for artifact in artifacts:
            worm_id = uuid.uuid4()
            q(
                """
                INSERT INTO audit_worm_index
                    (id, tenant_id, record_type, record_id, record_hash,
                     locked_at, locked_by)
                VALUES
                    (%s::uuid, %s::uuid, %s, %s::uuid, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(worm_id),
                    str(tenant_id),
                    artifact["type"],
                    artifact["id"],
                    artifact["hash"],
                    now,
                    actor_sub,
                ),
                db_url=self._db_url,
            )

        # 6. Close the case
        q(
            "UPDATE cases SET state = 'CLOSED' WHERE id = %s::uuid",
            (str(case_id),),
            db_url=self._db_url,
        )

        # Append-only CLOSED event
        event_id = uuid.uuid4()
        q(
            """
            INSERT INTO case_events
                (id, case_id, tenant_id, event_type, actor_sub, payload, occurred_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s)
            """,
            (
                str(event_id),
                str(case_id),
                str(tenant_id),
                "CLOSED",
                actor_sub,
                json.dumps({"acr_id": str(acr_id), "artifact_count": 8}),
                now,
            ),
            db_url=self._db_url,
        )

        # 7. Emit Kafka event (best-effort, non-blocking)
        if self._broker is not None:
            try:
                from zoiko_common.kafka.schemas import KafkaEventEnvelope
                envelope = KafkaEventEnvelope(
                    topic="acr.issued",
                    tenant_id=str(tenant_id),
                    payload={
                        "acr_id": str(acr_id),
                        "case_id": str(case_id),
                        "merkle_root": merkle_root.hex(),
                        "artifact_count": 8,
                        "issued_by": actor_sub,
                    },
                )
                self._broker.publish(envelope)
            except Exception:
                pass  # Kafka is best-effort; never block the ACR write

        return {
            "acr_id": str(acr_id),
            "case_id": str(case_id),
            "artifact_count": 8,
            "is_locked": True,
            "merkle_root": merkle_root.hex(),
            "issued_at": now.isoformat(),
        }
