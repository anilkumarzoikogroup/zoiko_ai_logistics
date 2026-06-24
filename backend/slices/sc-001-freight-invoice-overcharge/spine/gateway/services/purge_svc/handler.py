"""Purge Service — C07 Slice 1.

Purge is permitted only when retention has expired, no legal hold exists,
no active case depends on the data, and approval is recorded (§15).
Purge must be provable — silent deletion is prohibited.
"""
import uuid
from typing import Optional

import paths  # noqa: F401
import shared.db as _db

from services.purge_svc.models      import PurgeJobResult
from services.legal_hold_svc.handler import LegalHoldHandler


class PurgeHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker
        self._lh     = LegalHoldHandler(db_url, kafka_broker)

    # ── Create ────────────────────────────────────────────────────────────────

    def create_job(
        self,
        tenant_id:           str,
        purge_scope:         str,
        record_count:        int,
        retention_policy_id: Optional[str],
        requested_by:        str,
        scope_ids:           list,          # IDs to legal-hold check
    ) -> PurgeJobResult:
        # C07 §15.1 — check legal hold before creating a purge job
        held = any(self._lh.is_held(sid, tenant_id) for sid in scope_ids)
        evidence_id = str(uuid.uuid4())
        job_id      = str(uuid.uuid4())
        status      = "BLOCKED" if held else "PENDING"

        _db.q("""
            INSERT INTO purge_jobs
                (id, tenant_id, purge_scope, record_count,
                 retention_policy_id, legal_hold_checked, legal_hold_blocked,
                 status, evidence_id)
            VALUES (%s::uuid, %s::uuid, %s, %s,
                    %s, TRUE, %s, %s, %s::uuid)
        """, (job_id, tenant_id, purge_scope, record_count,
              retention_policy_id, held, status, evidence_id))

        if held:
            self._emit("zoiko.purge.blocked", tenant_id, {
                "purge_job_id": job_id, "reason": "legal_hold_active",
            })
        else:
            self._emit("zoiko.purge.requested", tenant_id, {"purge_job_id": job_id})

        return self._fetch(job_id)

    # ── Approve ───────────────────────────────────────────────────────────────

    def approve(
        self,
        purge_job_id: str,
        tenant_id:    str,
        approval_id:  str,
        approved_by:  str,
    ) -> PurgeJobResult:
        job = _db.q1("""
            SELECT * FROM purge_jobs WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (purge_job_id, tenant_id))
        if not job:
            raise ValueError(f"Purge job '{purge_job_id}' not found")
        if job["status"] == "BLOCKED":
            raise ValueError(
                f"Purge job '{purge_job_id}' is BLOCKED by legal hold — release the hold first"
            )
        if job["status"] not in ("PENDING",):
            raise ValueError(f"Purge job '{purge_job_id}' cannot be approved in status '{job['status']}'")

        _db.q("""
            UPDATE purge_jobs
            SET status='APPROVED', approval_id=%s, approved_by=%s, approved_at=NOW()
            WHERE id=%s::uuid
        """, (approval_id, approved_by, purge_job_id))

        self._emit("zoiko.purge.approved", tenant_id, {
            "purge_job_id": purge_job_id, "approved_by": approved_by,
        })
        return self._fetch(purge_job_id)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_job(self, purge_job_id: str, tenant_id: str) -> PurgeJobResult:
        row = _db.q1("""
            SELECT * FROM purge_jobs WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (purge_job_id, tenant_id))
        if not row:
            raise ValueError(f"Purge job '{purge_job_id}' not found")
        return self._to_result(row)

    def get_evidence(self, purge_job_id: str, tenant_id: str) -> dict:
        row = _db.q1("""
            SELECT id, purge_scope, record_count, status,
                   legal_hold_checked, legal_hold_blocked,
                   approval_id, approved_by, approved_at,
                   completed_at, evidence_id, created_at
            FROM purge_jobs WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (purge_job_id, tenant_id))
        if not row:
            raise ValueError(f"Purge job '{purge_job_id}' not found")
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(row).items()}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch(self, job_id: str) -> PurgeJobResult:
        return self._to_result(
            _db.q1("SELECT * FROM purge_jobs WHERE id=%s::uuid", (job_id,))
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

    def _to_result(self, row: dict) -> PurgeJobResult:
        return PurgeJobResult(
            purge_job_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            purge_scope=row["purge_scope"],
            record_count=row["record_count"],
            retention_policy_id=str(row["retention_policy_id"]) if row.get("retention_policy_id") else None,
            legal_hold_checked=bool(row["legal_hold_checked"]),
            legal_hold_blocked=bool(row["legal_hold_blocked"]),
            approval_id=row.get("approval_id"),
            approved_by=row.get("approved_by"),
            approved_at=row["approved_at"].isoformat() if row.get("approved_at") else None,
            status=row["status"],
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["created_at"].isoformat(),
        )
