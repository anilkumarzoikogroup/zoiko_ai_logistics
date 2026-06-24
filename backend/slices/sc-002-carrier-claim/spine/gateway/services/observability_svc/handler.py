"""Observability Service — C07 §19.

Computes the 15 required metrics and 9 required alert conditions
defined in Clarification 07 §19.1 and §19.2.

All metrics are derived from live DB state — no separate metrics store needed
for Slice 1. In production these feed a Prometheus exporter or a dashboard.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import paths  # noqa: F401
import shared.db as _db

# Governed tables that carry retention metadata
_GOVERNED = [
    "cases",
    "source_records",
    "evidence_bundles",
    "findings",
    "action_certification_records",
    "governance_tokens",
    "validation_results",
    "expected_recoveries",
    "recovery_instruments",
    "recovery_matches",
    "ledger_entries",
    "write_offs",
    "recovery_proofs",
]

# Tables that carry retention_class (Class A + B governed tables)
_RETENTION_TABLES = [
    "cases",
    "source_records",
    "evidence_bundles",
    "action_certification_records",
    "ledger_entries",
    "recovery_proofs",
]


class ObservabilityHandler:
    def __init__(self, db_url: str):
        self._db_url = db_url

    # ── §19.1 — 15 Required Metrics ───────────────────────────────────────────

    def metrics(self, tenant_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        expiry_window = now + timedelta(days=30)

        return {
            "tenant_id":                   tenant_id,
            "computed_at":                 now.isoformat(),

            # 1. Records by retention class
            "records_by_retention_class":  self._records_by_retention_class(tenant_id),

            # 2. Records approaching retention expiry (within 30 days)
            "records_approaching_expiry":  self._approaching_expiry(tenant_id, expiry_window),

            # 3. Records blocked by legal hold
            "records_blocked_by_legal_hold": self._legal_hold_count(tenant_id),

            # 4. Archive job success and failure
            "archive_jobs":                self._job_summary("archive_jobs", tenant_id),

            # 5. Archive restore latency (avg seconds from PENDING to APPROVED_FOR_USE)
            "archive_restore_latency_avg_seconds": self._restore_latency(tenant_id),

            # 6. Restore verification failures
            "restore_verification_failures": self._restore_verification_failures(tenant_id),

            # 7. Evidence-chain verification failures
            "evidence_chain_verification_failures": self._evidence_chain_failures(tenant_id),

            # 8. ACR verification failures after restore
            "acr_verification_failures_after_restore": self._acr_restore_failures(tenant_id),

            # 9. Purge jobs blocked and completed
            "purge_jobs":                  self._job_summary("purge_jobs", tenant_id),

            # 10. Crypto-shred requests and failures
            "crypto_shred_requests":       self._job_summary("crypto_shred_requests", tenant_id),

            # 11. Cross-region access attempts (residency violations)
            "cross_region_access_attempts": self._residency_violations(tenant_id),

            # 12. Residency violations detected
            "residency_violations_detected": self._residency_violations(tenant_id),

            # 13. Backup restore test results (not yet automated — placeholder)
            "backup_restore_test_results": {"note": "not_yet_automated"},

            # 14. Payload access events
            "payload_access_events":       self._payload_access_events(tenant_id),

            # 15. Legal hold active count by scope
            "legal_hold_active_by_scope":  self._legal_hold_by_scope(tenant_id),
        }

    # ── §19.2 — 9 Required Alerts ─────────────────────────────────────────────

    def alerts(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Returns list of currently firing alert conditions."""
        active_alerts: List[Dict[str, Any]] = []

        # Alert 1 — residency violation detected
        violations = self._residency_violations(tenant_id)
        if violations > 0:
            active_alerts.append({
                "alert":    "RESIDENCY_VIOLATION_DETECTED",
                "severity": "CRITICAL",
                "count":    violations,
                "detail":   "Records found with data_residency_region mismatch against tenant region",
            })

        # Alert 2 — restore verification failed
        rv_failures = self._restore_verification_failures(tenant_id)
        if rv_failures > 0:
            active_alerts.append({
                "alert":    "RESTORE_VERIFICATION_FAILED",
                "severity": "CRITICAL",
                "count":    rv_failures,
                "detail":   "One or more restore jobs have a FAILED verification record",
            })

        # Alert 3 — evidence verification failed
        ev_failures = self._evidence_chain_failures(tenant_id)
        if ev_failures > 0:
            active_alerts.append({
                "alert":    "EVIDENCE_VERIFICATION_FAILED",
                "severity": "HIGH",
                "count":    ev_failures,
                "detail":   "Restore jobs with evidence_chain_verified=FALSE in latest verification",
            })

        # Alert 4 — ACR verification failed after restore
        acr_failures = self._acr_restore_failures(tenant_id)
        if acr_failures > 0:
            active_alerts.append({
                "alert":    "ACR_VERIFICATION_FAILED_AFTER_RESTORE",
                "severity": "CRITICAL",
                "count":    acr_failures,
                "detail":   "Restore jobs where acr_verified=FALSE in verification record",
            })

        # Alert 5 — purge attempted on legal-hold data (BLOCKED jobs)
        blocked_purges = _db.q1("""
            SELECT COUNT(*) AS cnt FROM purge_jobs
            WHERE tenant_id=%s::uuid AND legal_hold_blocked=TRUE
              AND created_at > NOW() - INTERVAL '24 hours'
        """, (tenant_id,))
        if blocked_purges and int(blocked_purges["cnt"]) > 0:
            active_alerts.append({
                "alert":    "PURGE_ATTEMPTED_ON_LEGAL_HOLD_DATA",
                "severity": "HIGH",
                "count":    int(blocked_purges["cnt"]),
                "detail":   "Purge jobs blocked by legal hold in last 24 hours",
            })

        # Alert 6 — crypto-shred blocked by legal hold
        blocked_shreds = _db.q1("""
            SELECT COUNT(*) AS cnt FROM crypto_shred_requests
            WHERE tenant_id=%s::uuid AND legal_hold_blocked=TRUE
              AND created_at > NOW() - INTERVAL '24 hours'
        """, (tenant_id,))
        if blocked_shreds and int(blocked_shreds["cnt"]) > 0:
            active_alerts.append({
                "alert":    "CRYPTO_SHRED_BLOCKED_BY_LEGAL_HOLD",
                "severity": "HIGH",
                "count":    int(blocked_shreds["cnt"]),
                "detail":   "Crypto-shred requests blocked by legal hold in last 24 hours",
            })

        # Alert 7 — archive job failed
        failed_archives = _db.q1("""
            SELECT COUNT(*) AS cnt FROM archive_jobs
            WHERE tenant_id=%s::uuid AND status='FAILED'
              AND created_at > NOW() - INTERVAL '24 hours'
        """, (tenant_id,))
        if failed_archives and int(failed_archives["cnt"]) > 0:
            active_alerts.append({
                "alert":    "ARCHIVE_JOB_FAILED",
                "severity": "HIGH",
                "count":    int(failed_archives["cnt"]),
                "detail":   "Archive jobs in FAILED status in last 24 hours",
            })

        # Alert 8 — backup restore test failed (placeholder — not yet automated)
        # Will fire when backup_restore_tests table is implemented

        # Alert 9 — cross-tenant restore contamination (tenant isolation check failed)
        cross_tenant = _db.q1("""
            SELECT COUNT(*) AS cnt
            FROM restore_verification_records
            WHERE tenant_id=%s::uuid AND tenant_isolation_verified=FALSE
              AND verification_status='FAILED'
        """, (tenant_id,))
        if cross_tenant and int(cross_tenant["cnt"]) > 0:
            active_alerts.append({
                "alert":    "CROSS_TENANT_RESTORE_CONTAMINATION_DETECTED",
                "severity": "CRITICAL",
                "count":    int(cross_tenant["cnt"]),
                "detail":   "Restore verification records with tenant_isolation_verified=FALSE",
            })

        return active_alerts

    # ── Internal metric helpers ────────────────────────────────────────────────

    def _records_by_retention_class(self, tenant_id: str) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for table in _RETENTION_TABLES:
            rows = _db.q(f"""
                SELECT retention_class, COUNT(*) AS cnt
                FROM {table}
                WHERE tenant_id=%s::uuid
                GROUP BY retention_class
            """, (tenant_id,))
            for r in rows:
                key = r["retention_class"] or "unknown"
                result[key] = result.get(key, 0) + int(r["cnt"])
        return result

    def _approaching_expiry(self, tenant_id: str, window: datetime) -> int:
        total = 0
        for table in ["evidence_bundles", "action_certification_records",
                      "ledger_entries", "recovery_proofs", "source_records"]:
            row = _db.q1(f"""
                SELECT COUNT(*) AS cnt FROM {table}
                WHERE tenant_id=%s::uuid
                  AND retention_until IS NOT NULL
                  AND retention_until < %s
                  AND retention_until > NOW()
            """, (tenant_id, window))
            if row:
                total += int(row["cnt"])
        return total

    def _legal_hold_count(self, tenant_id: str) -> int:
        row = _db.q1("""
            SELECT COUNT(*) AS cnt FROM legal_hold_records
            WHERE tenant_id=%s::uuid AND status='ACTIVE'
        """, (tenant_id,))
        return int(row["cnt"]) if row else 0

    def _legal_hold_by_scope(self, tenant_id: str) -> Dict[str, int]:
        rows = _db.q("""
            SELECT hold_scope, COUNT(*) AS cnt
            FROM legal_hold_records
            WHERE tenant_id=%s::uuid AND status='ACTIVE'
            GROUP BY hold_scope
        """, (tenant_id,))
        return {r["hold_scope"]: int(r["cnt"]) for r in rows}

    def _job_summary(self, table: str, tenant_id: str) -> Dict[str, int]:
        rows = _db.q(f"""
            SELECT status, COUNT(*) AS cnt
            FROM {table}
            WHERE tenant_id=%s::uuid
            GROUP BY status
        """, (tenant_id,))
        return {r["status"]: int(r["cnt"]) for r in rows}

    def _restore_latency(self, tenant_id: str) -> float:
        row = _db.q1("""
            SELECT AVG(EXTRACT(EPOCH FROM (approved_at - created_at))) AS avg_sec
            FROM restore_jobs
            WHERE tenant_id=%s::uuid AND status='APPROVED_FOR_USE'
              AND approved_at IS NOT NULL
        """, (tenant_id,))
        return float(row["avg_sec"]) if row and row.get("avg_sec") else 0.0

    def _restore_verification_failures(self, tenant_id: str) -> int:
        row = _db.q1("""
            SELECT COUNT(*) AS cnt FROM restore_verification_records
            WHERE tenant_id=%s::uuid AND verification_status='FAILED'
        """, (tenant_id,))
        return int(row["cnt"]) if row else 0

    def _evidence_chain_failures(self, tenant_id: str) -> int:
        row = _db.q1("""
            SELECT COUNT(*) AS cnt FROM restore_verification_records
            WHERE tenant_id=%s::uuid AND evidence_chain_verified=FALSE
              AND verification_status <> 'PENDING'
        """, (tenant_id,))
        return int(row["cnt"]) if row else 0

    def _acr_restore_failures(self, tenant_id: str) -> int:
        row = _db.q1("""
            SELECT COUNT(*) AS cnt FROM restore_verification_records
            WHERE tenant_id=%s::uuid AND acr_verified=FALSE
              AND verification_status <> 'PENDING'
        """, (tenant_id,))
        return int(row["cnt"]) if row else 0

    def _residency_violations(self, tenant_id: str) -> int:
        """Records whose data_residency_region doesn't match the tenant's pinned region."""
        tenant = _db.q1("""
            SELECT data_residency_region FROM tenants WHERE id=%s::uuid
        """, (tenant_id,))
        if not tenant or not tenant.get("data_residency_region"):
            return 0
        pinned = tenant["data_residency_region"]
        total = 0
        for table in _GOVERNED:
            row = _db.q1(f"""
                SELECT COUNT(*) AS cnt FROM {table}
                WHERE tenant_id=%s::uuid AND data_residency_region <> %s
            """, (tenant_id, pinned))
            if row:
                total += int(row["cnt"])
        return total

    def _payload_access_events(self, tenant_id: str) -> int:
        """Count payload access evidence events from the case_events or audit tables."""
        row = _db.q1("""
            SELECT COUNT(*) AS cnt FROM case_events
            WHERE tenant_id=%s::uuid AND actor LIKE '%%payload_read%%'
        """, (tenant_id,))
        return int(row["cnt"]) if row else 0
