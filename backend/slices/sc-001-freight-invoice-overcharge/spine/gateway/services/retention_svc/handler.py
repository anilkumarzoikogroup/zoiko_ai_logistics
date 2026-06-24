"""Retention Service — C07 Slice 1.

Manages retention policies and assigns retention dates to governed records.
Every governed record must be able to answer: retention_class, retention_until,
archive_after, purge_after.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import paths  # noqa: F401
import shared.db as _db

from services.retention_svc.models import RetentionPolicyResult, RetentionAssignResult

_RECORD_TABLE = {
    "case":              "cases",
    "source_record":     "source_records",
    "evidence_bundle":   "evidence_bundles",
    "finding":           "findings",
    "acr":               "action_certification_records",
    "governance_token":  "governance_tokens",
    "ledger_entry":      "ledger_entries",
    "recovery_proof":    "recovery_proofs",
    "expected_recovery": "expected_recoveries",
}


class RetentionHandler:
    def __init__(self, db_url: str, kafka_broker):
        self._db_url = db_url
        self._broker = kafka_broker

    # ── Policies ──────────────────────────────────────────────────────────────

    def create_policy(
        self,
        tenant_id:         str,
        policy_name:       str,
        data_class:        str,
        retention_class:   str,
        retention_days:    int,
        archive_after_days: Optional[int],
        purge_after_days:   Optional[int],
        created_by:        str,
    ) -> RetentionPolicyResult:
        policy_id = str(uuid.uuid4())
        _db.q("""
            INSERT INTO retention_policies
                (id, tenant_id, policy_name, data_class, retention_class,
                 retention_days, archive_after_days, purge_after_days,
                 status, created_by)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s)
        """, (policy_id, tenant_id, policy_name, data_class, retention_class,
              retention_days, archive_after_days, purge_after_days, created_by))
        return self._fetch_policy(policy_id)

    def get_policy(self, policy_id: str, tenant_id: str) -> RetentionPolicyResult:
        row = _db.q1("""
            SELECT * FROM retention_policies
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (policy_id, tenant_id))
        if not row:
            raise ValueError(f"Retention policy '{policy_id}' not found")
        return self._to_policy(row)

    # ── Assign ────────────────────────────────────────────────────────────────

    def assign(
        self,
        tenant_id:   str,
        record_type: str,
        record_id:   str,
        policy_id:   str,
    ) -> RetentionAssignResult:
        table = _RECORD_TABLE.get(record_type)
        if not table:
            raise ValueError(f"Unknown record_type '{record_type}'")

        policy = _db.q1("""
            SELECT * FROM retention_policies
            WHERE id=%s::uuid AND tenant_id=%s::uuid AND status='ACTIVE'
        """, (policy_id, tenant_id))
        if not policy:
            raise ValueError(f"Active retention policy '{policy_id}' not found")

        now            = datetime.now(timezone.utc)
        retention_until = now + timedelta(days=policy["retention_days"])
        archive_after   = (now + timedelta(days=policy["archive_after_days"])
                           if policy["archive_after_days"] else None)
        purge_after     = (now + timedelta(days=policy["purge_after_days"])
                           if policy["purge_after_days"] else None)

        _db.q(f"""
            UPDATE {table}
            SET retention_class=%s,
                retention_until=%s,
                archive_after=%s,
                purge_after=%s
            WHERE id=%s::uuid AND tenant_id=%s::uuid
        """, (policy["retention_class"], retention_until, archive_after,
              purge_after, record_id, tenant_id))

        return RetentionAssignResult(
            record_id=record_id,
            record_type=record_type,
            policy_id=policy_id,
            retention_class=policy["retention_class"],
            retention_until=retention_until.isoformat(),
            archive_after=archive_after.isoformat() if archive_after else None,
            purge_after=purge_after.isoformat() if purge_after else None,
        )

    # ── By record ─────────────────────────────────────────────────────────────

    def by_record(self, record_id: str, tenant_id: str) -> dict:
        for record_type, table in _RECORD_TABLE.items():
            row = _db.q1(f"""
                SELECT id, retention_class, retention_until, archive_after,
                       purge_after, legal_hold_status, data_residency_region
                FROM {table}
                WHERE id=%s::uuid AND tenant_id=%s::uuid
                LIMIT 1
            """, (record_id, tenant_id))
            if row:
                return {
                    "record_id":           record_id,
                    "record_type":         record_type,
                    "retention_class":     row.get("retention_class"),
                    "retention_until":     row["retention_until"].isoformat() if row.get("retention_until") else None,
                    "archive_after":       row["archive_after"].isoformat() if row.get("archive_after") else None,
                    "purge_after":         row["purge_after"].isoformat() if row.get("purge_after") else None,
                    "legal_hold_status":   row.get("legal_hold_status", "NONE"),
                    "data_residency_region": row.get("data_residency_region"),
                }
        raise ValueError(f"Record '{record_id}' not found in any governed table")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_policy(self, policy_id: str) -> RetentionPolicyResult:
        return self._to_policy(
            _db.q1("SELECT * FROM retention_policies WHERE id=%s::uuid", (policy_id,))
        )

    def _to_policy(self, row: dict) -> RetentionPolicyResult:
        return RetentionPolicyResult(
            policy_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            policy_name=row["policy_name"],
            data_class=row["data_class"],
            retention_class=row["retention_class"],
            retention_days=row["retention_days"],
            archive_after_days=row.get("archive_after_days"),
            purge_after_days=row.get("purge_after_days"),
            status=row["status"],
            created_by=row["created_by"],
            created_at=row["created_at"].isoformat(),
        )
