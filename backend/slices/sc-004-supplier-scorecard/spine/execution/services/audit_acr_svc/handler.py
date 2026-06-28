"""
SC-004 Audit — 8-artifact Merkle ACR (WORM-locked, irreversible).

Artifacts (same 8 as SC-001/002/003):
  1. source_record       — ingested source hash
  2. canonical_invoice   — canonical hash
  3. evidence_bundle     — Merkle root of evidence items
  4. finding             — AI reasoning hash
  5. decision_proposal   — analyst proposal hash
  6. governance_decision — manager approval hash
  7. governance_token    — issuance hash
  8. execution_envelope  — gate-pass hash
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone

import paths  # noqa: F401

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL
from shared.signer import sign


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AuditACRHandler:

    def __init__(self, db_url: str | None = None, broker=None):
        self._db_url = db_url or _DEFAULT_DB_URL
        self._broker = broker

    def issue_acr(self, tenant_id: str, case_id: str, actor_sub: str) -> dict:
        existing = q1(
            "SELECT id::text, merkle_root, artifact_count FROM action_certification_records "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid AND is_locked=true LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if existing:
            return {
                "status":         "ALREADY_ISSUED",
                "acr_id":         existing["id"],
                "merkle_root":    existing["merkle_root"],
                "artifact_count": existing["artifact_count"],
            }

        artifacts = self._collect_artifacts(tenant_id, case_id)
        merkle_root, leaves = self._build_merkle(artifacts)
        acr_id = self._write_acr(tenant_id, case_id, actor_sub, artifacts, merkle_root, leaves)
        self._close_case(tenant_id, case_id, actor_sub)
        self._publish_kafka(tenant_id, case_id, str(acr_id), merkle_root)

        return {
            "status":         "ISSUED",
            "acr_id":         str(acr_id),
            "merkle_root":    merkle_root,
            "artifact_count": len(artifacts),
            "artifacts":      artifacts,
            "issued_at":      datetime.now(timezone.utc).isoformat(),
        }

    def get_acr(self, tenant_id: str, case_id: str) -> dict | None:
        row = q1(
            """SELECT id::text, merkle_root, artifact_count, artifact_hashes, issued_at, is_locked
               FROM action_certification_records
               WHERE case_id=%s::uuid AND tenant_id=%s::uuid LIMIT 1""",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        if not row:
            return None
        return {
            "acr_id":         row["id"],
            "merkle_root":    row["merkle_root"],
            "artifact_count": row["artifact_count"],
            "artifact_hashes": row["artifact_hashes"],
            "issued_at":      row["issued_at"].isoformat() if row.get("issued_at") else None,
            "is_locked":      row["is_locked"],
        }

    def _collect_artifacts(self, tenant_id: str, case_id: str) -> list[dict]:
        artifacts: list[dict] = []

        # SC-004 uses scorecard_periods (not source_records/canonical_invoices).
        # scorecard_periods.case_id links directly to the case.
        sp = q1(
            """SELECT id::text, composite_score, contracted_threshold, carrier_id,
                      period_start, period_end
               FROM scorecard_periods
               WHERE case_id=%s::uuid AND tenant_id=%s::uuid
               LIMIT 1""",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        sp_hash = _sha256_hex(
            b"zoiko.scorecard.period.v1:" +
            f"{(sp or {}).get('id','')}:{(sp or {}).get('composite_score','')}:{(sp or {}).get('contracted_threshold','')}".encode()
        )
        artifacts.append({"name": "scorecard_period", "hash": sp_hash})

        # Artifact 2: canonical case record (case_type, state, opened_at).
        # SCORECARD_BREACH cases have no canonical_invoice — use the case row itself.
        cr = q1(
            "SELECT id::text, case_type, state, opened_at FROM cases "
            "WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        cr_hash = _sha256_hex(
            b"zoiko.case.record.v1:" +
            f"{(cr or {}).get('id','')}:{(cr or {}).get('case_type','')}:{(cr or {}).get('state','')}".encode()
        )
        artifacts.append({"name": "case_record", "hash": cr_hash})

        # evidence_bundles uses bundle_hash column (not merkle_root)
        eb = q1(
            "SELECT bundle_hash FROM evidence_bundles "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        artifacts.append({"name": "evidence_bundle", "hash": (eb or {}).get("bundle_hash") or ""})

        fi = q1(
            "SELECT finding_hash FROM findings "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        artifacts.append({"name": "finding", "hash": (fi or {}).get("finding_hash") or ""})

        dp = q1(
            "SELECT proposal_hash FROM decision_proposals "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        artifacts.append({"name": "decision_proposal", "hash": (dp or {}).get("proposal_hash") or ""})

        # governance_decisions has no case_id — join through governance_tasks
        gd = q1(
            """SELECT gd.decision_hash
               FROM governance_decisions gd
               JOIN governance_tasks gt ON gt.id = gd.proposal_id
               WHERE gt.case_id=%s::uuid AND gt.tenant_id=%s::uuid
               ORDER BY gd.decided_at DESC LIMIT 1""",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        artifacts.append({"name": "governance_decision", "hash": (gd or {}).get("decision_hash") or ""})

        # governance_tokens has case_id; order by issued_at (not created_at)
        gt = q1(
            "SELECT token_hash FROM governance_tokens "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY issued_at DESC LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        artifacts.append({"name": "governance_token", "hash": (gt or {}).get("token_hash") or ""})

        ee = q1(
            "SELECT id::text AS envelope_id FROM execution_envelopes "
            "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
            (case_id, tenant_id),
            db_url=self._db_url,
        )
        ee_hash = _sha256_hex(b"zoiko.execution.envelope.v1:" + ((ee or {}).get("envelope_id") or "").encode())
        artifacts.append({"name": "execution_envelope", "hash": ee_hash})

        return artifacts

    def _build_merkle(self, artifacts: list[dict]) -> tuple[str, list[str]]:
        tag    = b"zoiko/v1/acr"
        leaves = [
            _sha256_hex(tag + b":" + a["hash"].encode())
            for a in artifacts
        ]
        nodes = list(leaves)
        while len(nodes) > 1:
            if len(nodes) % 2 == 1:
                nodes.append(nodes[-1])
            nodes = [
                _sha256_hex((nodes[i] + nodes[i + 1]).encode())
                for i in range(0, len(nodes), 2)
            ]
        return nodes[0] if nodes else _sha256_hex(b"empty"), leaves

    def _write_acr(
        self,
        tenant_id:   str,
        case_id:     str,
        actor_sub:   str,
        artifacts:   list[dict],
        merkle_root: str,
        leaves:      list[str],
    ) -> uuid.UUID:
        acr_id         = uuid.uuid4()
        artifact_hashes = json.dumps({a["name"]: a["hash"] for a in artifacts})
        acr_payload     = json.dumps({"merkle_root": merkle_root, "artifacts": artifacts})
        acr_bytes       = acr_payload.encode()
        sig_bytes, kid  = sign("default", hashlib.sha256(b"zoiko.acr.v1:" + acr_bytes).digest())

        q("""
            INSERT INTO action_certification_records
                (id, tenant_id, case_id, merkle_root, artifact_count,
                 artifact_hashes, signature, kid,
                 issued_by, is_locked, issued_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s,
                    %s::jsonb, %s, %s,
                    %s, true, NOW())
            ON CONFLICT DO NOTHING
        """, (
            acr_id, tenant_id, case_id, merkle_root, len(artifacts),
            artifact_hashes, sig_bytes, kid,
            actor_sub,
        ), db_url=self._db_url)

        q("""
            INSERT INTO audit_worm_index
                (id, tenant_id, record_type, record_id, record_hash, locked_at, locked_by)
            VALUES (gen_random_uuid(), %s::uuid, 'action_certification_record', %s::uuid, %s, NOW(), %s)
            ON CONFLICT DO NOTHING
        """, (tenant_id, acr_id, merkle_root, actor_sub), db_url=self._db_url)

        return acr_id

    def _close_case(self, tenant_id: str, case_id: str, actor_sub: str) -> None:
        q("""
            UPDATE cases SET state='CLOSED'
            WHERE id=%s::uuid AND tenant_id=%s::uuid AND state='OUTCOME_RECORDED'
        """, (case_id, tenant_id), db_url=self._db_url)
        q("""
            INSERT INTO case_events
                (id, tenant_id, case_id, event_type, from_state, to_state,
                 actor_sub, payload, occurred_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'STATE_TRANSITION',
                    'OUTCOME_RECORDED', 'CLOSED', %s,
                    '{"acr_issued":true}'::jsonb, NOW())
        """, (tenant_id, case_id, actor_sub), db_url=self._db_url)

    def _publish_kafka(self, tenant_id: str, case_id: str, acr_id: str, merkle_root: str) -> None:
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            prod = ZoikoProducer(self._broker)
            prod.publish(KafkaMessage(
                topic="acr.issued", key=case_id,
                payload={"case_id": case_id, "acr_id": acr_id, "merkle_root": merkle_root},
                tenant_id=tenant_id,
            ))
        except Exception:
            pass
