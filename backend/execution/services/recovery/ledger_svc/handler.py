"""
Phase 6 (Clarification 06 Slice 1) — Ledger Closure

Posts double-entry ledger records for resolved recovery_matches and advances
expected_recoveries.status to LEDGER_PENDING / LEDGER_CLOSED — the financial
close that Step 8 (Recovery Proof / ACR Readiness) requires.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.ledger_svc.models import LedgerEntryResult

psycopg2.extras.register_uuid()

_ENTRY_TYPE_BY_ALLOCATION = {
    "FULL":    "RECOVERY_CREDIT_APPLIED",
    "PARTIAL": "RECOVERY_PARTIAL_APPLIED",
    "OVER":    "OVER_RECOVERY_PENDING_REVIEW",
}

_EXPECTED_STATUS_BY_ALLOCATION = {
    "FULL":    "LEDGER_CLOSED",
    "PARTIAL": "LEDGER_PENDING",
    "OVER":    "LEDGER_PENDING",
}

_CREDIT_ACCOUNT_BY_ALLOCATION = {
    "FULL":    "recovery_receivable",
    "PARTIAL": "recovery_receivable",
    "OVER":    "over_recovery_clearing",
}


class LedgerHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def post_for_match(self, match_id: str, tenant_id: str, actor_sub: str) -> LedgerEntryResult:
        match = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, expected_recovery_id, allocation_status,
                       matched_amount, currency
                FROM   recovery_matches
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(match_id, tenant_id),
        )
        if not match:
            raise ValueError(f"Recovery match '{match_id}' not found")
        if match["allocation_status"] not in _ENTRY_TYPE_BY_ALLOCATION:
            raise ValueError(
                f"Recovery match has allocation_status '{match['allocation_status']}' "
                f"and cannot be posted to the ledger"
            )

        already_posted = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id FROM ledger_entries
                WHERE  source_recovery_match_id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(match_id, tenant_id),
        )
        if already_posted:
            raise ValueError(f"Recovery match '{match_id}' has already been posted to the ledger")

        expected = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, case_id, expected_amount
                FROM   expected_recoveries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(str(match["expected_recovery_id"]), tenant_id),
        )
        if not expected:
            raise ValueError(f"Expected recovery '{match['expected_recovery_id']}' not found")

        case_id    = str(expected["case_id"])
        allocation = match["allocation_status"]
        now        = datetime.now(timezone.utc)

        receivable_created = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id FROM ledger_entries
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid AND entry_type='RECOVERY_RECEIVABLE_CREATED'
                LIMIT  1
            """,
            params=(case_id, tenant_id),
        )

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()

            if not receivable_created:
                cur.execute("""
                    INSERT INTO ledger_entries
                        (id, tenant_id, case_id, entry_type, amount, currency,
                         debit_account, credit_account, source_recovery_match_id,
                         reversal_of_entry_id, status, posted_at, created_at)
                    VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s,
                            %s, %s, NULL,
                            NULL, 'POSTED', %s, %s)
                """, (
                    uuid.uuid4(), tenant_id, case_id, "RECOVERY_RECEIVABLE_CREATED",
                    float(expected["expected_amount"]), match["currency"],
                    "recovery_receivable", "overcharge_recovery_income",
                    now, now,
                ))

            entry_id     = uuid.uuid4()
            entry_type   = _ENTRY_TYPE_BY_ALLOCATION[allocation]
            credit_acc   = _CREDIT_ACCOUNT_BY_ALLOCATION[allocation]
            matched_amt  = float(match["matched_amount"])

            cur.execute("""
                INSERT INTO ledger_entries
                    (id, tenant_id, case_id, entry_type, amount, currency,
                     debit_account, credit_account, source_recovery_match_id,
                     reversal_of_entry_id, status, posted_at, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s,
                        %s, %s, %s::uuid,
                        NULL, 'POSTED', %s, %s)
            """, (
                entry_id, tenant_id, case_id, entry_type,
                matched_amt, match["currency"],
                "carrier_credit_memo", credit_acc, match_id,
                now, now,
            ))

            cur.execute("""
                UPDATE expected_recoveries
                SET status=%s, updated_at=%s
                WHERE id=%s::uuid
            """, (_EXPECTED_STATUS_BY_ALLOCATION[allocation], now, str(match["expected_recovery_id"])))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.ledger.entry.posted",
                case_id,
                json.dumps({
                    "entry_id":   str(entry_id),
                    "case_id":    case_id,
                    "entry_type": entry_type,
                    "amount":     matched_amt,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.ledger.entry.posted",
                key       = case_id,
                payload   = {"entry_id": str(entry_id), "entry_type": entry_type},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return LedgerEntryResult(
            entry_id                  = str(entry_id),
            tenant_id                  = tenant_id,
            case_id                    = case_id,
            entry_type                 = entry_type,
            amount                     = matched_amt,
            currency                   = match["currency"],
            debit_account              = "carrier_credit_memo",
            credit_account             = credit_acc,
            source_recovery_match_id   = match_id,
            reversal_of_entry_id       = None,
            status                     = "POSTED",
            posted_at                  = now,
            created_at                 = now,
        )

    def reverse_entry(self, entry_id: str, tenant_id: str, actor_sub: str, reason: str = "") -> LedgerEntryResult:
        entry = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, entry_type, amount, currency,
                       debit_account, credit_account, source_recovery_match_id, status
                FROM   ledger_entries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(entry_id, tenant_id),
        )
        if not entry:
            raise ValueError(f"Ledger entry '{entry_id}' not found")
        if entry["status"] != "POSTED":
            raise ValueError(f"Ledger entry has status '{entry['status']}' and cannot be reversed")

        existing_reversal = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id FROM ledger_entries
                WHERE  reversal_of_entry_id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(entry_id, tenant_id),
        )
        if existing_reversal:
            raise ValueError(f"Ledger entry '{entry_id}' has already been reversed")

        now           = datetime.now(timezone.utc)
        reversal_id   = uuid.uuid4()
        case_id       = str(entry["case_id"])

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ledger_entries
                    (id, tenant_id, case_id, entry_type, amount, currency,
                     debit_account, credit_account, source_recovery_match_id,
                     reversal_of_entry_id, status, posted_at, created_at)
                VALUES (%s, %s::uuid, %s::uuid, 'REVERSAL', %s, %s,
                        %s, %s, %s,
                        %s::uuid, 'POSTED', %s, %s)
            """, (
                reversal_id, tenant_id, case_id,
                float(entry["amount"]), entry["currency"],
                entry["credit_account"], entry["debit_account"], entry["source_recovery_match_id"],
                entry_id, now, now,
            ))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.ledger.entry.reversed",
                case_id,
                json.dumps({
                    "entry_id":             str(reversal_id),
                    "reversal_of_entry_id": entry_id,
                    "case_id":              case_id,
                    "reason":               reason,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.ledger.entry.reversed",
                key       = case_id,
                payload   = {"entry_id": str(reversal_id), "reversal_of_entry_id": entry_id},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return LedgerEntryResult(
            entry_id                  = str(reversal_id),
            tenant_id                  = tenant_id,
            case_id                    = case_id,
            entry_type                 = "REVERSAL",
            amount                     = float(entry["amount"]),
            currency                   = entry["currency"],
            debit_account              = entry["credit_account"],
            credit_account             = entry["debit_account"],
            source_recovery_match_id   = str(entry["source_recovery_match_id"]) if entry["source_recovery_match_id"] else None,
            reversal_of_entry_id       = entry_id,
            status                     = "POSTED",
            posted_at                  = now,
            created_at                 = now,
        )

    def get(self, entry_id: str, tenant_id: str) -> LedgerEntryResult | None:
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, entry_type, amount, currency,
                       debit_account, credit_account, source_recovery_match_id,
                       reversal_of_entry_id, status, posted_at, created_at
                FROM   ledger_entries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(entry_id, tenant_id),
        )
        if not row:
            return None
        return self._to_result(row)

    def list_by_case(self, case_id: str, tenant_id: str) -> list[LedgerEntryResult]:
        rows = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, entry_type, amount, currency,
                       debit_account, credit_account, source_recovery_match_id,
                       reversal_of_entry_id, status, posted_at, created_at
                FROM   ledger_entries
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY posted_at ASC
            """,
            params=(case_id, tenant_id),
        )
        return [self._to_result(r) for r in rows]

    @staticmethod
    def _to_result(row: dict) -> LedgerEntryResult:
        return LedgerEntryResult(
            entry_id                  = str(row["id"]),
            tenant_id                  = str(row["tenant_id"]),
            case_id                    = str(row["case_id"]),
            entry_type                 = row["entry_type"],
            amount                     = float(row["amount"]),
            currency                   = row["currency"],
            debit_account              = row["debit_account"],
            credit_account             = row["credit_account"],
            source_recovery_match_id   = str(row["source_recovery_match_id"]) if row["source_recovery_match_id"] else None,
            reversal_of_entry_id       = str(row["reversal_of_entry_id"]) if row["reversal_of_entry_id"] else None,
            status                     = row["status"],
            posted_at                  = row["posted_at"],
            created_at                 = row["created_at"],
        )
