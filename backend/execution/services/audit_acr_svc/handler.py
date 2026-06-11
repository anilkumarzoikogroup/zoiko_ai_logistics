"""
Phase 4 — Audit ACR (Action Certification Record) Service

The ACR is the final artifact in the Zoiko pipeline. It provides an offline-
verifiable audit trail over the 8 artifacts that collectively prove a freight
overcharge was detected, reviewed, approved, and credited correctly.

8 artifacts included in the ACR Merkle tree:
  1. source_record_hash       — SHA-256 of the canonical invoice bytes
  2. canonical_invoice_hash   — SHA-256 of the canonical truth row
  3. evidence_bundle_hash     — Merkle root of evidence items
  4. finding_hash             — SHA-256 of the reasoning output
  5. proposal_hash            — SHA-256 of the recovery proposal
  6. governance_decision_hash — SHA-256 of the approval decision
  7. token_hash               — SHA-256 of the governance token
  8. envelope_hash            — SHA-256 of the execution envelope

The ACR row is written with is_locked=FALSE. An async WORM relay locks it
(is_locked=TRUE, irreversible) and uploads to Cloud Storage after creation.

Zoiko ACR verify package format (acr_verify_<case_id>.json):
  {
    "acr_id":        "<uuid>",
    "case_id":       "<uuid>",
    "merkle_root":   "<hex>",
    "artifacts":     [{"name": "...", "hash": "...", "domain_tag": "..."}],
    "public_keys":   {"<kid>": "<base64-encoded DER>"},
    "tenant_id":     "<uuid>",
    "issued_at":     "<iso8601>",
    "acr_signature": "<hex>",
    "acr_kid":       "<kid>"
  }
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401
from shared.signer import sign as _sign
from zoiko_common.crypto.merkle import MerkleTree
from zoiko_common.crypto.jcs import canonicalize as _jcs

psycopg2.extras.register_uuid()

_DOMAIN_TAG = b"zoiko/v1/acr"
_ARTIFACT_DOMAIN_TAG = b"zoiko.acr.artifact.v1:"


@dataclass
class ACRResult:
    acr_id:       str
    case_id:      str
    tenant_id:    str
    merkle_root:  str
    artifact_count: int
    is_locked:    bool
    issued_at:    datetime
    verify_bundle: dict   # JSON-serialisable verify package
    closure_reason:  str = ""
    recovered_amount: float = 0.0
    currency:        str = "USD"


class AuditACRHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def issue_acr(self, case_id: str, tenant_id: str, actor_sub: str = "system") -> ACRResult:
        """
        Build and write the ACR for a completed case.
        Raises ValueError if required artifacts are missing.
        """
        # T-011: block ACR/CLOSE if any open variance records exist for this case
        open_vars = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT COUNT(*) AS cnt FROM variance_records
                WHERE case_id=%s::uuid AND tenant_id=%s::uuid
                  AND status = 'OPEN'
            """,
            params=(case_id, tenant_id),
        )
        if open_vars and int(open_vars["cnt"]) > 0:
            raise ValueError(
                f"Case '{case_id}' has {open_vars['cnt']} open variance record(s) — "
                f"resolve or waive all variances before issuing ACR (T-011)"
            )

        artifacts = self._collect_artifacts(case_id, tenant_id)
        if len(artifacts) < 8:
            raise ValueError(
                f"ACR requires 8 artifacts, only {len(artifacts)} found for case '{case_id}'"
            )

        # Build Merkle tree over artifact hashes
        tree = MerkleTree(_DOMAIN_TAG.decode())
        for a in artifacts:
            tree.append(bytes.fromhex(a["hash"]))
        merkle_root = tree.root()

        # Sign the Merkle root
        acr_payload = _jcs({
            "artifacts":    [{"name": a["name"], "hash": a["hash"]} for a in artifacts],
            "case_id":      case_id,
            "merkle_root":  merkle_root.hex(),
            "tenant_id":    tenant_id,
        })
        acr_hash       = hashlib.sha256(_DOMAIN_TAG + acr_payload).digest()
        acr_sig, acr_kid = _sign(self._tenant_slug, acr_hash)

        now    = datetime.now(timezone.utc)
        acr_id = uuid.uuid4()

        # Clarification 05 §16 — derive closure_reason + recovered_amount from
        # the most recent reconciliation (if any) for this case.
        recon = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT reconciliation_type, observed_amount, expected_amount, currency
                FROM reconciliations
                WHERE case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER BY reconciled_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if recon and recon.get("reconciliation_type") == "MATCHED":
            closure_reason   = "RECOVERED_FULL"
            recovered_amount = float(recon["observed_amount"] or 0)
            currency         = recon.get("currency") or "USD"
            new_state        = "CLOSED_RECOVERED"
        elif recon and recon.get("reconciliation_type") == "PARTIAL_MATCH":
            closure_reason   = "RECOVERED_PARTIAL"
            recovered_amount = float(recon["observed_amount"] or 0)
            currency         = recon.get("currency") or "USD"
            new_state        = "CLOSED_RECOVERED"
        elif recon and recon.get("reconciliation_type") == "MISMATCH":
            closure_reason   = "UNRECOVERABLE"
            recovered_amount = float(recon["observed_amount"] or 0)
            currency         = recon.get("currency") or "USD"
            new_state        = "CLOSED_UNRECOVERABLE"
        else:
            closure_reason   = "NO_ACTION_REQUIRED"
            recovered_amount = 0.0
            currency         = "USD"
            new_state        = "CLOSED_NO_ACTION"

        # Clarification 05 §16 — supersession: link to any prior ACR for this case
        prior_acr = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id FROM action_certification_records
                WHERE case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER BY certified_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        supersedes_acr_id = prior_acr["id"] if prior_acr else None

        verify_bundle = self._build_verify_bundle(
            acr_id, case_id, tenant_id, merkle_root, artifacts, acr_sig, acr_kid, now
        )
        verify_bundle["closure_reason"]   = closure_reason
        verify_bundle["recovered_amount"] = recovered_amount
        verify_bundle["currency"]         = currency

        with _db.get_conn(self._db_url) as conn:
          try:
            cur = conn.cursor()

            # Write ACR row (APPEND-ONLY)
            cur.execute("""
                INSERT INTO action_certification_records
                    (id, tenant_id, case_id, merkle_root, artifact_hashes, signature,
                     kid, acr_version, certified_at,
                     closure_reason, recovered_amount, currency, supersedes_acr_id)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                acr_id, tenant_id, uuid.UUID(case_id),
                merkle_root, json.dumps(verify_bundle), acr_sig, acr_kid,
                "1.0", now,
                closure_reason, recovered_amount, currency, supersedes_acr_id,
            ))

            # Link prior ACR (if any) to the one that supersedes it
            if supersedes_acr_id:
                cur.execute("""
                    UPDATE action_certification_records
                    SET superseded_by_acr_id=%s
                    WHERE id=%s AND tenant_id=%s::uuid
                """, (acr_id, supersedes_acr_id, tenant_id))

            # Write audit_worm_index row (APPEND-ONLY)
            cur.execute("""
                INSERT INTO audit_worm_index
                    (id, tenant_id, entity_type, entity_id, content_hash,
                     signature, kid, is_locked, recorded_at)
                VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s, %s, FALSE, %s)
            """, (
                uuid.uuid4(), tenant_id, "ACR", acr_id,
                acr_hash, acr_sig, acr_kid, now,
            ))

            # Close the case
            cur.execute("""
                UPDATE cases SET state='CLOSED'
                WHERE id=%s::uuid AND tenant_id=%s::uuid
                  AND state IN ('OUTCOME_RECORDED', 'RECONCILED')
            """, (uuid.UUID(case_id), tenant_id))
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s::uuid, %s::uuid, 'ACR_ISSUED', 'OUTCOME_RECORDED', 'CLOSED', %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, uuid.UUID(case_id),
                actor_sub,
                json.dumps({"acr_id": str(acr_id), "merkle_root": merkle_root.hex()}),
                now,
            ))

            # Outbox event
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.acr.generated",
                case_id,
                json.dumps({"acr_id": str(acr_id), "case_id": case_id}),
                now,
            ))

            conn.commit()
          finally:
            pass  # pool returns connection via context manager

        # Kafka publish
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.acr.generated",
                key       = case_id,
                payload   = {"acr_id": str(acr_id), "case_id": case_id, "merkle_root": merkle_root.hex()},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return ACRResult(
            acr_id        = str(acr_id),
            case_id       = case_id,
            tenant_id     = tenant_id,
            merkle_root   = merkle_root.hex(),
            artifact_count= len(artifacts),
            is_locked     = False,
            issued_at     = now,
            verify_bundle = verify_bundle,
        )

    def get_acr(self, case_id: str, tenant_id: str) -> Optional[dict]:
        """Return the ACR verify bundle for a case (or None if not yet issued)."""
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id::text, case_id::text, tenant_id::text,
                       merkle_root,
                       artifact_hashes AS verify_bundle,
                       acr_version, kid,
                       certified_at AS issued_at
                FROM   action_certification_records
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER BY certified_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        return row

    # ── Artifact collection ─────────────────────────────────────────────────────

    def _collect_artifacts(self, case_id: str, tenant_id: str) -> list[dict]:
        """Collect the 8 audit artifacts for a case from the DB."""
        artifacts = []

        # 1. Source record hash
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT encode(sr.canonical_hash,'hex') AS hash
                FROM source_records sr
                JOIN canonical_invoices ci ON ci.source_record_id = sr.id
                JOIN cases c ON c.invoice_id = ci.id
                WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "source_record_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.ingestion.invoice.v1:"})

        # 2. Canonical invoice hash
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT encode(ci.canonical_hash,'hex') AS hash
                FROM canonical_invoices ci
                JOIN cases c ON c.invoice_id = ci.id
                WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "canonical_invoice_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.canonical.invoice.v1:"})

        # 3. Evidence bundle hash
        row = _db.q1(
            db_url=self._db_url,
            sql="SELECT encode(bundle_hash,'hex') AS hash FROM evidence_bundles WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "evidence_bundle_hash", "hash": row["hash"],
                               "domain_tag": "zoiko/v1/evidence-item"})

        # 4. Finding hash
        row = _db.q1(
            db_url=self._db_url,
            sql="SELECT encode(signature,'hex') AS hash FROM findings WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "finding_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.finding.v1:"})

        # 5. Proposal hash
        row = _db.q1(
            db_url=self._db_url,
            sql="SELECT encode(proposal_hash,'hex') AS hash FROM decision_proposals WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "proposal_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.proposal.v1:"})

        # 6. Governance decision hash
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT encode(gd.decision_hash,'hex') AS hash
                FROM governance_decisions gd
                JOIN decision_proposals dp ON dp.id = gd.proposal_id
                WHERE dp.case_id=%s::uuid AND gd.tenant_id=%s::uuid
                ORDER BY gd.decided_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "governance_decision_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.governance.decision.v1:"})

        # 7. Token hash
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT encode(gt.token_hash,'hex') AS hash
                FROM governance_tokens gt
                JOIN governance_decisions gd ON gd.id = gt.decision_id
                JOIN decision_proposals dp ON dp.id = gd.proposal_id
                WHERE dp.case_id=%s::uuid AND gt.tenant_id=%s::uuid
                ORDER BY gt.issued_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "token_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.token.v1:"})

        # 8. Execution envelope hash
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT encode(
                    digest(
                        'zoiko.execution.envelope.v1:' || id::text,
                        'sha256'
                    ), 'hex') AS hash
                FROM execution_envelopes
                WHERE case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER BY dispatched_at DESC LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if row:
            artifacts.append({"name": "envelope_hash", "hash": row["hash"],
                               "domain_tag": "zoiko.execution.envelope.v1:"})

        return artifacts

    def _build_verify_bundle(
        self,
        acr_id: uuid.UUID,
        case_id: str,
        tenant_id: str,
        merkle_root: bytes,
        artifacts: list[dict],
        acr_sig: bytes,
        acr_kid: str,
        issued_at: datetime,
    ) -> dict:
        """Build the offline-verifiable JSON bundle."""
        try:
            from zoiko_kms.hierarchy import KeyHierarchy
            kh = KeyHierarchy()
            pub = kh.get_public_key(acr_kid)
            pub_b64 = base64.b64encode(pub.public_bytes(
                encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).Encoding.DER,
                format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).PublicFormat.SubjectPublicKeyInfo,
            )).decode()
        except Exception:
            pub_b64 = ""

        return {
            "acr_id":       str(acr_id),
            "case_id":      case_id,
            "tenant_id":    tenant_id,
            "merkle_root":  merkle_root.hex(),
            "artifacts":    artifacts,
            "public_keys":  {acr_kid: pub_b64},
            "issued_at":    issued_at.isoformat(),
            "acr_signature": acr_sig.hex() if isinstance(acr_sig, bytes) else acr_sig,
            "acr_kid":      acr_kid,
            "schema_version": "1.0",
        }
