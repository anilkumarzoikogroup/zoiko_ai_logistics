"""
Phase 6 (Clarification 06 Slice 1) — Recovery Exceptions / Observability

Read-only rollup of recovery-pipeline items that need a human to look at them:
  - MISMATCHED expected_recoveries
  - REVIEW_REQUIRED recovery_matches (multiple AVAILABLE instruments matched)
  - expected_recoveries stuck in a non-terminal status for too long
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import shared.db as _db

import paths  # noqa: F401

from services.recovery.recovery_exceptions_svc.models import RecoveryExceptionResult

_STUCK_STATUSES = (
    "EXPECTED", "AWAITING_INSTRUMENT", "INSTRUMENT_RECEIVED", "MATCHING",
    "MATCHED_PARTIAL", "UNRECOVERABLE_PENDING_APPROVAL", "LEDGER_PENDING",
)


class RecoveryExceptionsHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def list_exceptions(
        self,
        tenant_id: str,
        case_id: str | None = None,
        stuck_after_days: int = 7,
    ) -> list[RecoveryExceptionResult]:
        now = datetime.now(timezone.utc)
        results: list[RecoveryExceptionResult] = []

        case_filter = " AND case_id=%s::uuid" if case_id else ""

        mismatched = _db.q(
            db_url=self._db_url,
            sql=f"""
                SELECT id, case_id, expected_amount, currency, status, updated_at
                FROM   expected_recoveries
                WHERE  tenant_id=%s::uuid AND status='MISMATCHED'{case_filter}
                ORDER  BY updated_at ASC
            """,
            params=(tenant_id, case_id) if case_id else (tenant_id,),
        )
        for row in mismatched:
            results.append(RecoveryExceptionResult(
                exception_type       = "MISMATCHED",
                tenant_id            = tenant_id,
                case_id              = str(row["case_id"]),
                expected_recovery_id = str(row["id"]),
                recovery_match_id    = None,
                status               = row["status"],
                amount               = float(row["expected_amount"]),
                currency             = row["currency"],
                age_days             = (now - row["updated_at"]).days,
                detail               = "Expected recovery is MISMATCHED — variance exceeds tolerance, needs manual review",
                detected_at          = row["updated_at"],
            ))

        case_filter_m = " AND e.case_id=%s::uuid" if case_id else ""
        review_required = _db.q(
            db_url=self._db_url,
            sql=f"""
                SELECT m.id AS match_id, m.expected_recovery_id, e.case_id,
                       e.expected_amount, e.currency, e.status, m.matched_at
                FROM   recovery_matches m
                JOIN   expected_recoveries e ON e.id = m.expected_recovery_id
                WHERE  m.tenant_id=%s::uuid AND m.allocation_status='REVIEW_REQUIRED'{case_filter_m}
                ORDER  BY m.matched_at ASC
            """,
            params=(tenant_id, case_id) if case_id else (tenant_id,),
        )
        for row in review_required:
            results.append(RecoveryExceptionResult(
                exception_type       = "REVIEW_REQUIRED",
                tenant_id            = tenant_id,
                case_id              = str(row["case_id"]),
                expected_recovery_id = str(row["expected_recovery_id"]),
                recovery_match_id    = str(row["match_id"]),
                status               = row["status"],
                amount               = float(row["expected_amount"]),
                currency             = row["currency"],
                age_days             = (now - row["matched_at"]).days,
                detail               = "Multiple AVAILABLE recovery instruments matched the same expected recovery — needs manual selection",
                detected_at          = row["matched_at"],
            ))

        cutoff = now - timedelta(days=stuck_after_days)
        stuck = _db.q(
            db_url=self._db_url,
            sql=f"""
                SELECT id, case_id, expected_amount, currency, status, updated_at
                FROM   expected_recoveries
                WHERE  tenant_id=%s::uuid AND status = ANY(%s) AND updated_at < %s{case_filter}
                ORDER  BY updated_at ASC
            """,
            params=(tenant_id, list(_STUCK_STATUSES), cutoff, case_id) if case_id
                   else (tenant_id, list(_STUCK_STATUSES), cutoff),
        )
        for row in stuck:
            age_days = (now - row["updated_at"]).days
            results.append(RecoveryExceptionResult(
                exception_type       = "STUCK_PENDING",
                tenant_id            = tenant_id,
                case_id              = str(row["case_id"]),
                expected_recovery_id = str(row["id"]),
                recovery_match_id    = None,
                status               = row["status"],
                amount               = float(row["expected_amount"]),
                currency             = row["currency"],
                age_days             = age_days,
                detail               = f"No progress for {age_days}d (status={row['status']})",
                detected_at          = row["updated_at"],
            ))

        results.sort(key=lambda r: r.age_days, reverse=True)
        return results
