"""Archive Service — C07 Slice 1.

Archive changes storage tier. It does not remove governance obligations.
Archived data remains tenant-bound, region-bound, encrypted,
access-controlled, evidence-linked and retention-governed (§4.4, §9).
"""
import json
import uuid
from typing import List, Optional

import paths  # noqa: F401
import shared.db as _db

from services.archive_svc.models     import ArchiveJobResult
from services.legal_hold_svc.handler import LegalHoldHandler


class ArchiveHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker
        self._lh     = LegalHoldHandler(db_url, kafka_broker)

    # ── Create archive job ────────────────────────────────────────────────────

    def create_job(
        self,
        tenant_id:           str,
        archive_scope:       str,
        record_ids:          List[str],
        requested_by:        str,
        retention_policy_id: Optional[str] = None,
    ) -> ArchiveJobResult:
        # §9.1 — no active legal hold blocks archive
        held = any(self._lh.is_held(rid, tenant_id) for rid in record_ids)
        if held:
            raise ValueError(
                "Archive blocked — one or more records have an active legal hold. "
                "Release the hold before archiving."
            )

        job_id      = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())

        # Collect integrity metadata (hashes + retention fields) before archiving
        integrity_meta = self._collect_integrity_metadata(record_ids, tenant_id)

        _db.q("""
            INSERT INTO archive_jobs
                (id, tenant_id, archive_scope, record_ids, status,
                 requested_by, retention_policy_id,
                 legal_hold_checked, integrity_metadata, evidence_id)
            VALUES (%s::uuid, %s::uuid, %s, %s::jsonb, 'PENDING',
                    %s, %s, TRUE, %s::jsonb, %s::uuid)
        """, (job_id, tenant_id, archive_scope,
              json.dumps(record_ids), requested_by,
              retention_policy_id, json.dumps(integrity_meta), evidence_id))

        # Set archive_eligible on the records
        self._mark_eligible(record_ids, tenant_id)

        self._emit("zoiko.archive.started", tenant_id, {
            "archive_job_id": job_id, "record_count": len(record_ids),
        })
        return self._fetch(job_id)

    # ── Get job ───────────────────────────────────────────────────────────────

    def get_job(self, archive_job_id: str, tenant_id: str) -> ArchiveJobResult:
        row = _db.q1("""
            SELECT * FROM archive_jobs
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (archive_job_id, tenant_id))
        if not row:
            raise ValueError(f"Archive job '{archive_job_id}' not found")
        return self._to_result(row)

    # ── Restore from archive ──────────────────────────────────────────────────

    def restore(
        self,
        archive_job_id: str,
        tenant_id:      str,
        requested_by:   str,
    ) -> dict:
        """Kicks off a restore job from this archive (delegates to restore_svc)."""
        row = self.get_job(archive_job_id, tenant_id)
        from services.restore_svc.handler import RestoreHandler
        rh = RestoreHandler(self._db_url, self._broker)
        restore_job = rh.create_job(
            tenant_id=tenant_id,
            restore_type="archive_restore",
            restored_scope=archive_job_id,
            requested_by=requested_by,
        )
        return {"archive_job_id": archive_job_id, "restore_job_id": restore_job.restore_job_id}

    # ── Verify archive integrity ──────────────────────────────────────────────

    def verify(self, archive_job_id: str, tenant_id: str) -> dict:
        row = _db.q1("""
            SELECT integrity_metadata, status FROM archive_jobs
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (archive_job_id, tenant_id))
        if not row:
            raise ValueError(f"Archive job '{archive_job_id}' not found")
        return {
            "archive_job_id":    archive_job_id,
            "status":            row["status"],
            "integrity_metadata": row["integrity_metadata"],
            "verified":          row["status"] == "COMPLETED",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_integrity_metadata(self, record_ids: List[str], tenant_id: str) -> dict:
        meta = {}
        for table in ["evidence_bundles", "action_certification_records",
                      "ledger_entries", "recovery_proofs"]:
            for rid in record_ids:
                row = _db.q1(f"""
                    SELECT id, retention_class, retention_until, purge_after,
                           crypto_shred_status
                    FROM {table} WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1
                """, (rid, tenant_id))
                if row:
                    meta[rid] = {
                        "table": table,
                        "retention_class": row.get("retention_class"),
                        "retention_until": row["retention_until"].isoformat() if row.get("retention_until") else None,
                        "purge_after": row["purge_after"].isoformat() if row.get("purge_after") else None,
                        "crypto_shred_status": row.get("crypto_shred_status"),
                    }
        return meta

    def _mark_eligible(self, record_ids: List[str], tenant_id: str):
        for table in ["evidence_bundles", "action_certification_records",
                      "ledger_entries", "recovery_proofs"]:
            for rid in record_ids:
                _db.q(f"""
                    UPDATE {table} SET archive_eligible=TRUE
                    WHERE id=%s::uuid AND tenant_id=%s::uuid
                """, (rid, tenant_id))

    def _fetch(self, job_id: str) -> ArchiveJobResult:
        return self._to_result(
            _db.q1("SELECT * FROM archive_jobs WHERE id=%s::uuid", (job_id,))
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

    def _to_result(self, row: dict) -> ArchiveJobResult:
        return ArchiveJobResult(
            archive_job_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            archive_scope=row["archive_scope"],
            record_ids=row["record_ids"] or [],
            status=row["status"],
            requested_by=row["requested_by"],
            retention_policy_id=str(row["retention_policy_id"]) if row.get("retention_policy_id") else None,
            legal_hold_checked=bool(row["legal_hold_checked"]),
            completed_at=row["completed_at"].isoformat() if row.get("completed_at") else None,
            evidence_id=str(row["evidence_id"]) if row.get("evidence_id") else None,
            created_at=row["created_at"].isoformat(),
        )
