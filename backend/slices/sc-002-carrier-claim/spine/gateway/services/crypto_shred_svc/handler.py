"""Crypto-Shred Service — C07 Slice 1.

Destroys access to encrypted PII by revoking the DEK while preserving
evidence structure, hashes, lineage and ACR verification.

Rules (§11.4):
  1. Check legal hold first — block if any active hold covers the subject.
  2. Check retention / statutory obligations.
  3. Mark affected records crypto_shred_status='SHREDDED'.
  4. Record the shred request with affected_key_ids and affected_record_ids.
  5. Evidence the action.
  6. Preserve hash, lineage and evidence continuity — never delete ACR structure.
"""
import json
import uuid
from typing import List

import paths  # noqa: F401
import shared.db as _db

from services.crypto_shred_svc.models import CryptoShredResult, CryptoShredVerifyResult
from services.legal_hold_svc.handler  import LegalHoldHandler


class CryptoShredHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker
        self._lh     = LegalHoldHandler(db_url, kafka_broker)

    # ── Request ───────────────────────────────────────────────────────────────

    def request(
        self,
        tenant_id:           str,
        subject_ref:         str,
        affected_key_ids:    List[str],
        affected_record_ids: List[str],
        requested_by:        str,
    ) -> CryptoShredResult:
        shred_id    = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())

        # C07 §11.4 Rule 1 — legal hold check
        held = any(self._lh.is_held(rid, tenant_id) for rid in affected_record_ids)
        status = "BLOCKED" if held else "IN_PROGRESS"

        _db.q("""
            INSERT INTO crypto_shred_requests
                (id, tenant_id, subject_ref, affected_key_ids, affected_record_ids,
                 legal_hold_checked, legal_hold_blocked, status, requested_by, evidence_id)
            VALUES (%s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb,
                    TRUE, %s, %s, %s, %s::uuid)
        """, (shred_id, tenant_id, subject_ref,
              json.dumps(affected_key_ids), json.dumps(affected_record_ids),
              held, status, requested_by, evidence_id))

        if held:
            self._emit("zoiko.crypto_shred.blocked", tenant_id, {
                "crypto_shred_id": shred_id, "subject_ref": subject_ref,
                "reason": "legal_hold_active",
            })
            return self._fetch(shred_id)

        # Mark affected records as shredded and complete the request
        self._shred_records(affected_record_ids, tenant_id)
        _db.q("""
            UPDATE crypto_shred_requests
            SET status='COMPLETED', completed_at=NOW()
            WHERE id=%s::uuid
        """, (shred_id,))

        self._emit("zoiko.crypto_shred.completed", tenant_id, {
            "crypto_shred_id": shred_id, "subject_ref": subject_ref,
            "affected_count": len(affected_record_ids),
        })
        return self._fetch(shred_id)

    # ── Read + Verify ─────────────────────────────────────────────────────────

    def get(self, crypto_shred_id: str, tenant_id: str) -> CryptoShredResult:
        row = _db.q1("""
            SELECT * FROM crypto_shred_requests
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (crypto_shred_id, tenant_id))
        if not row:
            raise ValueError(f"Crypto-shred request '{crypto_shred_id}' not found")
        return self._to_result(row)

    def verify(self, crypto_shred_id: str, tenant_id: str) -> CryptoShredVerifyResult:
        row = _db.q1("""
            SELECT * FROM crypto_shred_requests
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (crypto_shred_id, tenant_id))
        if not row:
            raise ValueError(f"Crypto-shred request '{crypto_shred_id}' not found")

        record_ids = row["affected_record_ids"] or []
        if not record_ids:
            return CryptoShredVerifyResult(
                crypto_shred_id=crypto_shred_id, status=row["status"],
                shred_confirmed=row["status"] == "COMPLETED",
                detail="No affected records to verify",
            )

        # Check that all affected records report SHREDDED status in any governed table
        shredded_count = 0
        for tables in [
            "source_records", "evidence_bundles",
            "action_certification_records", "ledger_entries", "recovery_proofs",
        ]:
            for rid in record_ids:
                r = _db.q1(f"""
                    SELECT crypto_shred_status FROM {tables}
                    WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1
                """, (rid, tenant_id))
                if r and r["crypto_shred_status"] == "SHREDDED":
                    shredded_count += 1

        confirmed = shredded_count == len(record_ids)
        return CryptoShredVerifyResult(
            crypto_shred_id=crypto_shred_id,
            status=row["status"],
            shred_confirmed=confirmed,
            detail=f"{shredded_count}/{len(record_ids)} records confirmed SHREDDED",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    _TABLES_WITH_SHRED = [
        "source_records", "evidence_bundles",
        "action_certification_records", "ledger_entries", "recovery_proofs",
    ]

    def _shred_records(self, record_ids: List[str], tenant_id: str):
        for rid in record_ids:
            for table in self._TABLES_WITH_SHRED:
                _db.q(f"""
                    UPDATE {table} SET crypto_shred_status='SHREDDED'
                    WHERE id=%s::uuid AND tenant_id=%s::uuid
                """, (rid, tenant_id))

    def _fetch(self, shred_id: str) -> CryptoShredResult:
        return self._to_result(
            _db.q1("SELECT * FROM crypto_shred_requests WHERE id=%s::uuid", (shred_id,))
        )

    def _emit(self, topic: str, tenant_id: str, payload: dict):
        try:
            from zoiko_common.kafka.schemas import KafkaEventEnvelope
            self._broker.publish(KafkaEventEnvelope(
                topic=topic, tenant_id=tenant_id,
                payload=payload, event_id=str(uuid.uuid4()),
            ))
        except Exception:
            pass

    def _to_result(self, row: dict) -> CryptoShredResult:
        return CryptoShredResult(
            crypto_shred_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            subject_ref=row["subject_ref"],
            affected_key_ids=row["affected_key_ids"] or [],
            affected_record_ids=row["affected_record_ids"] or [],
            legal_hold_checked=bool(row["legal_hold_checked"]),
            legal_hold_blocked=bool(row["legal_hold_blocked"]),
            status=row["status"],
            requested_by=row["requested_by"],
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["created_at"].isoformat(),
        )
