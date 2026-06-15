"""Restore Service — C07 Slice 1.

Restore is a verified workflow, not an infrastructure copy action (§13, §14).
A restore is incomplete until verification passes. Failed verification blocks
the restored data from being used for any material action.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import paths  # noqa: F401
import shared.db as _db

from services.restore_svc.models import RestoreJobResult, RestoreVerificationResult

_VALID_TYPES = {
    "tenant_restore", "case_restore", "source_record_restore",
    "evidence_restore", "acr_restore", "ledger_recovery_restore",
    "regional_dr_restore", "archive_restore", "projection_rebuild",
}


class RestoreHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker

    # ── Create restore job ────────────────────────────────────────────────────

    def create_job(
        self,
        tenant_id:      str,
        restore_type:   str,
        restored_scope: str,
        requested_by:   str,
    ) -> RestoreJobResult:
        if restore_type not in _VALID_TYPES:
            raise ValueError(f"Invalid restore_type '{restore_type}'")

        job_id = str(uuid.uuid4())
        _db.q("""
            INSERT INTO restore_jobs
                (id, tenant_id, restore_type, restored_scope, status, requested_by)
            VALUES (%s::uuid, %s::uuid, %s, %s, 'PENDING', %s)
        """, (job_id, tenant_id, restore_type, restored_scope, requested_by))

        self._emit("zoiko.restore.requested", tenant_id, {
            "restore_job_id": job_id, "restore_type": restore_type,
            "restored_scope": restored_scope,
        })
        return self._fetch_job(job_id)

    # ── Submit verification ───────────────────────────────────────────────────

    def verify(
        self,
        restore_job_id:                  str,
        tenant_id:                       str,
        source_records_verified:         bool = False,
        evidence_chain_verified:         bool = False,
        acr_verified:                    bool = False,
        ledger_continuity_verified:      bool = False,
        tenant_isolation_verified:       bool = False,
        residency_verified:              bool = False,
        permissions_verified:            bool = False,
        legal_hold_verified:             bool = False,
        indexes_rebuilt:                 bool = False,
        projection_consistency_verified: bool = False,
    ) -> RestoreVerificationResult:
        job = _db.q1("""
            SELECT * FROM restore_jobs
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (restore_job_id, tenant_id))
        if not job:
            raise ValueError(f"Restore job '{restore_job_id}' not found")

        all_pass = all([
            source_records_verified, evidence_chain_verified, acr_verified,
            ledger_continuity_verified, tenant_isolation_verified,
            residency_verified, permissions_verified, legal_hold_verified,
            indexes_rebuilt, projection_consistency_verified,
        ])
        v_status    = "PASSED" if all_pass else "FAILED"
        evidence_id = str(uuid.uuid4())
        ver_id      = str(uuid.uuid4())

        # Upsert — one verification record per job
        _db.q("""
            INSERT INTO restore_verification_records
                (id, restore_job_id, tenant_id,
                 source_records_verified, evidence_chain_verified, acr_verified,
                 ledger_continuity_verified, tenant_isolation_verified,
                 residency_verified, permissions_verified, legal_hold_verified,
                 indexes_rebuilt, projection_consistency_verified,
                 verification_status, verified_at, evidence_id)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid,
                 %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                 %s, NOW(), %s::uuid)
            ON CONFLICT (restore_job_id) DO UPDATE SET
                source_records_verified         = EXCLUDED.source_records_verified,
                evidence_chain_verified         = EXCLUDED.evidence_chain_verified,
                acr_verified                    = EXCLUDED.acr_verified,
                ledger_continuity_verified      = EXCLUDED.ledger_continuity_verified,
                tenant_isolation_verified       = EXCLUDED.tenant_isolation_verified,
                residency_verified              = EXCLUDED.residency_verified,
                permissions_verified            = EXCLUDED.permissions_verified,
                legal_hold_verified             = EXCLUDED.legal_hold_verified,
                indexes_rebuilt                 = EXCLUDED.indexes_rebuilt,
                projection_consistency_verified = EXCLUDED.projection_consistency_verified,
                verification_status             = EXCLUDED.verification_status,
                verified_at                     = EXCLUDED.verified_at
        """, (ver_id, restore_job_id, tenant_id,
              source_records_verified, evidence_chain_verified, acr_verified,
              ledger_continuity_verified, tenant_isolation_verified,
              residency_verified, permissions_verified, legal_hold_verified,
              indexes_rebuilt, projection_consistency_verified,
              v_status, evidence_id))

        job_status = "VERIFICATION_PASSED" if all_pass else "VERIFICATION_FAILED"
        _db.q("""
            UPDATE restore_jobs SET status=%s, updated_at=NOW()
            WHERE id=%s::uuid
        """, (job_status, restore_job_id))

        topic = "zoiko.restore.verification_passed" if all_pass else "zoiko.restore.verification_failed"
        self._emit(topic, tenant_id, {
            "restore_job_id": restore_job_id, "verification_status": v_status,
        })
        return self._fetch_verification(restore_job_id)

    # ── Approve for use ───────────────────────────────────────────────────────

    def approve_use(
        self,
        restore_job_id: str,
        tenant_id:      str,
        approved_by:    str,
    ) -> RestoreJobResult:
        job = _db.q1("""
            SELECT * FROM restore_jobs
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (restore_job_id, tenant_id))
        if not job:
            raise ValueError(f"Restore job '{restore_job_id}' not found")
        if job["status"] != "VERIFICATION_PASSED":
            raise ValueError(
                f"Restore job '{restore_job_id}' cannot be approved — "
                f"status is '{job['status']}'; must be VERIFICATION_PASSED"
            )

        _db.q("""
            UPDATE restore_jobs
            SET status='APPROVED_FOR_USE', approved_by=%s, approved_at=NOW(), updated_at=NOW()
            WHERE id=%s::uuid
        """, (approved_by, restore_job_id))

        self._emit("zoiko.restore.completed", tenant_id, {
            "restore_job_id": restore_job_id, "approved_by": approved_by,
        })
        return self._fetch_job(restore_job_id)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_job(self, restore_job_id: str, tenant_id: str) -> RestoreJobResult:
        job = _db.q1("""
            SELECT * FROM restore_jobs WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (restore_job_id, tenant_id))
        if not job:
            raise ValueError(f"Restore job '{restore_job_id}' not found")
        return self._to_job(job)

    def get_verification(self, restore_job_id: str, tenant_id: str) -> RestoreVerificationResult:
        ver = self._fetch_verification(restore_job_id)
        if not ver:
            raise ValueError(f"No verification record for restore job '{restore_job_id}'")
        return ver

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_job(self, job_id: str) -> RestoreJobResult:
        return self._to_job(
            _db.q1("SELECT * FROM restore_jobs WHERE id=%s::uuid", (job_id,))
        )

    def _fetch_verification(self, restore_job_id: str) -> Optional[RestoreVerificationResult]:
        row = _db.q1("""
            SELECT * FROM restore_verification_records WHERE restore_job_id=%s::uuid
        """, (restore_job_id,))
        return self._to_verification(row) if row else None

    def _emit(self, topic: str, tenant_id: str, payload: dict):
        try:
            from zoiko_common.kafka.schemas import KafkaEventEnvelope
            self._broker.publish(KafkaEventEnvelope(
                topic=topic, tenant_id=tenant_id,
                payload=payload, event_id=str(uuid.uuid4()),
            ))
        except Exception:
            pass

    def _to_job(self, row: dict) -> RestoreJobResult:
        return RestoreJobResult(
            restore_job_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            restore_type=row["restore_type"],
            restored_scope=row["restored_scope"],
            status=row["status"],
            requested_by=row["requested_by"],
            approved_by=row.get("approved_by"),
            approved_at=row["approved_at"].isoformat() if row.get("approved_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["created_at"].isoformat(),
            updated_at=row["updated_at"].isoformat(),
        )

    def _to_verification(self, row: dict) -> RestoreVerificationResult:
        return RestoreVerificationResult(
            restore_verification_id=str(row["id"]),
            restore_job_id=str(row["restore_job_id"]),
            tenant_id=str(row["tenant_id"]),
            source_records_verified=row["source_records_verified"],
            evidence_chain_verified=row["evidence_chain_verified"],
            acr_verified=row["acr_verified"],
            ledger_continuity_verified=row["ledger_continuity_verified"],
            tenant_isolation_verified=row["tenant_isolation_verified"],
            residency_verified=row["residency_verified"],
            permissions_verified=row["permissions_verified"],
            legal_hold_verified=row["legal_hold_verified"],
            indexes_rebuilt=row["indexes_rebuilt"],
            projection_consistency_verified=row["projection_consistency_verified"],
            verification_status=row["verification_status"],
            verified_at=row["verified_at"].isoformat() if row.get("verified_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["created_at"].isoformat(),
        )
