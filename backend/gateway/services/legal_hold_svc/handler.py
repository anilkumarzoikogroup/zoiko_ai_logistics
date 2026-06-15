"""Legal Hold Service — C07 Slice 1.

Manages legal hold lifecycle: create, release, check, by-scope.
Legal hold blocks purge, crypto-shred and destructive archive lifecycle.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

import paths  # noqa: F401
import shared.db as _db

from services.legal_hold_svc.models import LegalHoldResult


class LegalHoldHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker

    # ── Create ────────────────────────────────────────────────────────────────

    def create(
        self,
        tenant_id:    str,
        hold_scope:   str,
        scope_id:     str,
        reason_code:  str,
        requested_by: str,
        approved_by:  Optional[str] = None,
    ) -> LegalHoldResult:
        hold_id   = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        now       = datetime.now(timezone.utc).isoformat()

        _db.q("""
            INSERT INTO legal_hold_records
                (id, tenant_id, subject_type, subject_id,
                 hold_scope, reason_code, status,
                 requested_by, approved_by, applied_by, applied_at,
                 effective_from, evidence_id, reason)
            VALUES
                (%s::uuid, %s::uuid, %s, %s::uuid,
                 %s, %s, 'ACTIVE',
                 %s, %s, %s, NOW(),
                 NOW(), %s::uuid, %s)
        """, (hold_id, tenant_id, hold_scope, scope_id,
              hold_scope, reason_code,
              requested_by, approved_by, requested_by,
              evidence_id, reason_code))

        # Flip legal_hold_status on the scoped record if it's a known table
        self._apply_hold_flag(scope_id, tenant_id, hold_scope, "HELD")

        self._emit("zoiko.legal_hold.created", tenant_id, {
            "legal_hold_id": hold_id, "scope_id": scope_id,
            "hold_scope": hold_scope, "reason_code": reason_code,
        })
        return self._to_result(_db.q1(
            "SELECT * FROM legal_hold_records WHERE id=%s::uuid", (hold_id,)
        ))

    # ── Release ───────────────────────────────────────────────────────────────

    def release(
        self,
        legal_hold_id: str,
        tenant_id:     str,
        released_by:   str,
    ) -> LegalHoldResult:
        row = _db.q1("""
            SELECT * FROM legal_hold_records
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (legal_hold_id, tenant_id))
        if not row:
            raise ValueError(f"Legal hold '{legal_hold_id}' not found")
        if row["status"] == "RELEASED":
            raise ValueError(f"Legal hold '{legal_hold_id}' already released")

        _db.q("""
            UPDATE legal_hold_records
            SET status='RELEASED', lifted_at=NOW(), lifted_by=%s
            WHERE id=%s::uuid
        """, (released_by, legal_hold_id))

        # Clear hold flag only if no other active holds cover same scope
        remaining = _db.q1("""
            SELECT 1 FROM legal_hold_records
            WHERE tenant_id=%s::uuid AND subject_id=%s::uuid
              AND status='ACTIVE' AND id <> %s::uuid
            LIMIT 1
        """, (tenant_id, row["subject_id"], legal_hold_id))
        if not remaining:
            self._apply_hold_flag(str(row["subject_id"]), tenant_id, row["hold_scope"], "NONE")

        self._emit("zoiko.legal_hold.released", tenant_id, {
            "legal_hold_id": legal_hold_id, "released_by": released_by,
        })
        return self._to_result(_db.q1(
            "SELECT * FROM legal_hold_records WHERE id=%s::uuid", (legal_hold_id,)
        ))

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, legal_hold_id: str, tenant_id: str) -> LegalHoldResult:
        row = _db.q1("""
            SELECT * FROM legal_hold_records
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (legal_hold_id, tenant_id))
        if not row:
            raise ValueError(f"Legal hold '{legal_hold_id}' not found")
        return self._to_result(row)

    def by_scope(self, scope_id: str, tenant_id: str) -> List[LegalHoldResult]:
        rows = _db.q("""
            SELECT * FROM legal_hold_records
            WHERE tenant_id=%s::uuid AND subject_id=%s::uuid
            ORDER BY applied_at DESC
        """, (tenant_id, scope_id))
        return [self._to_result(r) for r in rows]

    def is_held(self, scope_id: str, tenant_id: str) -> bool:
        """Used by purge and crypto-shred to block destructive actions."""
        row = _db.q1("""
            SELECT 1 FROM legal_hold_records
            WHERE tenant_id=%s::uuid AND subject_id=%s::uuid AND status='ACTIVE'
            LIMIT 1
        """, (tenant_id, scope_id))
        return row is not None

    # ── Helpers ───────────────────────────────────────────────────────────────

    _SCOPE_TABLE = {
        "case":         "cases",
        "source_record":"source_records",
        "evidence":     "evidence_bundles",
        "acr":          "action_certification_records",
        "recovery_proof":"recovery_proofs",
        "ledger_entry": "ledger_entries",
    }

    def _apply_hold_flag(self, scope_id: str, tenant_id: str, hold_scope: str, status: str):
        table = self._SCOPE_TABLE.get(hold_scope)
        if table:
            _db.q(f"""
                UPDATE {table} SET legal_hold_status=%s
                WHERE id=%s::uuid AND tenant_id=%s::uuid
            """, (status, scope_id, tenant_id))

    def _emit(self, topic: str, tenant_id: str, payload: dict):
        try:
            from zoiko_common.kafka.schemas import KafkaEventEnvelope
            self._broker.publish(KafkaEventEnvelope(
                topic=topic, tenant_id=tenant_id,
                payload=payload, event_id=str(uuid.uuid4()),
            ))
        except Exception:
            pass

    def _to_result(self, row: dict) -> LegalHoldResult:
        return LegalHoldResult(
            legal_hold_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            hold_scope=row.get("hold_scope") or row.get("subject_type", "case"),
            scope_id=str(row["subject_id"]),
            reason_code=row.get("reason_code") or row.get("reason", ""),
            requested_by=row.get("requested_by") or row.get("applied_by", ""),
            approved_by=row.get("approved_by"),
            status=row.get("status") or ("ACTIVE" if not row.get("lifted_at") else "RELEASED"),
            effective_from=(row.get("effective_from") or row.get("applied_at", "")).isoformat()
                           if hasattr(row.get("effective_from") or row.get("applied_at"), "isoformat")
                           else str(row.get("effective_from") or row.get("applied_at", "")),
            released_at=row["lifted_at"].isoformat() if row.get("lifted_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["applied_at"].isoformat() if row.get("applied_at") else "",
        )
