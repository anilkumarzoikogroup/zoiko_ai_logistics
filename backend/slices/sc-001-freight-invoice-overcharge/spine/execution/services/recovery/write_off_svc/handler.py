"""
Phase 6 (Clarification 06 Slice 1) — Write-Off Workflow

Formal close-out path for expected_recoveries that will never be matched
against an instrument: request -> authorize -> post to ledger
(RECOVERY_WRITE_OFF_POSTED) -> expected_recoveries.status = 'WRITTEN_OFF'.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.write_off_svc.models import WriteOffResult

psycopg2.extras.register_uuid()

_CLOSED_EXPECTED_STATUSES = ("LEDGER_CLOSED", "WRITTEN_OFF", "ACR_READY")

_POLICY_VERSION_ID = "writeoff-policy-v1"


class WriteOffHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def request(
        self,
        expected_recovery_id: str,
        tenant_id: str,
        actor_sub: str,
        reason_code: str,
        amount: float | None = None,
    ) -> WriteOffResult:
        expected = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, expected_amount, currency, status
                FROM   expected_recoveries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(expected_recovery_id, tenant_id),
        )
        if not expected:
            raise ValueError(f"Expected recovery '{expected_recovery_id}' not found")
        if expected["status"] in _CLOSED_EXPECTED_STATUSES:
            raise ValueError(f"Expected recovery is in status '{expected['status']}' and cannot be written off")

        already_matched_row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT COALESCE(SUM(matched_amount), 0) AS total
                FROM   recovery_matches
                WHERE  expected_recovery_id=%s::uuid AND tenant_id=%s::uuid
                       AND allocation_status <> 'REVERSED'
            """,
            params=(expected_recovery_id, tenant_id),
        )
        already_matched  = float(already_matched_row["total"]) if already_matched_row else 0.0
        expected_amount  = float(expected["expected_amount"])
        remaining        = expected_amount - already_matched

        write_off_amount = float(amount) if amount is not None else remaining
        if write_off_amount <= 0:
            raise ValueError("Write-off amount must be greater than zero")
        if write_off_amount > remaining:
            raise ValueError(f"Write-off amount {write_off_amount} exceeds remaining amount {remaining}")

        now          = datetime.now(timezone.utc)
        write_off_id = uuid.uuid4()
        case_id      = str(expected["case_id"])

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO write_offs
                    (id, tenant_id, case_id, expected_recovery_id, amount, currency,
                     reason_code, policy_version_id, authorized_by, authorized_at,
                     ledger_entry_id, status, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s,
                        %s, %s, NULL, NULL,
                        NULL, 'REQUESTED', %s)
            """, (
                write_off_id, tenant_id, case_id, expected_recovery_id,
                write_off_amount, expected["currency"],
                reason_code, _POLICY_VERSION_ID,
                now,
            ))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.writeoff.requested",
                case_id,
                json.dumps({
                    "write_off_id":         str(write_off_id),
                    "expected_recovery_id": expected_recovery_id,
                    "amount":               write_off_amount,
                    "reason_code":          reason_code,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.writeoff.requested",
                key       = case_id,
                payload   = {"write_off_id": str(write_off_id), "reason_code": reason_code},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return WriteOffResult(
            write_off_id         = str(write_off_id),
            tenant_id            = tenant_id,
            case_id              = case_id,
            expected_recovery_id = expected_recovery_id,
            amount               = write_off_amount,
            currency             = expected["currency"],
            reason_code          = reason_code,
            policy_version_id    = _POLICY_VERSION_ID,
            authorized_by        = None,
            authorized_at        = None,
            ledger_entry_id      = None,
            status               = "REQUESTED",
            created_at           = now,
        )

    def authorize(self, write_off_id: str, tenant_id: str, actor_sub: str) -> WriteOffResult:
        write_off = self._get_row(write_off_id, tenant_id)
        if not write_off:
            raise ValueError(f"Write-off '{write_off_id}' not found")
        if write_off["status"] != "REQUESTED":
            raise ValueError(f"Write-off has status '{write_off['status']}' and cannot be authorized")

        now = datetime.now(timezone.utc)
        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE write_offs
                SET status='AUTHORIZED', authorized_by=%s, authorized_at=%s
                WHERE id=%s::uuid
            """, (actor_sub, now, write_off_id))
            conn.commit()

        write_off["status"]        = "AUTHORIZED"
        write_off["authorized_by"] = actor_sub
        write_off["authorized_at"] = now
        return self._to_result(write_off)

    def post(self, write_off_id: str, tenant_id: str, actor_sub: str) -> WriteOffResult:
        write_off = self._get_row(write_off_id, tenant_id)
        if not write_off:
            raise ValueError(f"Write-off '{write_off_id}' not found")
        if write_off["status"] != "AUTHORIZED":
            raise ValueError(f"Write-off has status '{write_off['status']}' and cannot be posted")

        now      = datetime.now(timezone.utc)
        entry_id = uuid.uuid4()
        case_id  = str(write_off["case_id"])
        amount   = float(write_off["amount"])

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO ledger_entries
                    (id, tenant_id, case_id, entry_type, amount, currency,
                     debit_account, credit_account, source_recovery_match_id,
                     reversal_of_entry_id, status, posted_at, created_at)
                VALUES (%s, %s::uuid, %s::uuid, 'RECOVERY_WRITE_OFF_POSTED', %s, %s,
                        %s, %s, NULL,
                        NULL, 'POSTED', %s, %s)
            """, (
                entry_id, tenant_id, case_id, amount, write_off["currency"],
                "write_off_expense", "recovery_receivable",
                now, now,
            ))

            cur.execute("""
                UPDATE write_offs
                SET status='POSTED', ledger_entry_id=%s::uuid
                WHERE id=%s::uuid
            """, (entry_id, write_off_id))

            cur.execute("""
                UPDATE expected_recoveries
                SET status='WRITTEN_OFF', updated_at=%s
                WHERE id=%s::uuid
            """, (now, str(write_off["expected_recovery_id"])))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.writeoff.posted",
                case_id,
                json.dumps({
                    "write_off_id":   str(write_off_id),
                    "ledger_entry_id": str(entry_id),
                    "amount":          amount,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.writeoff.posted",
                key       = case_id,
                payload   = {"write_off_id": str(write_off_id), "ledger_entry_id": str(entry_id)},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        write_off["status"]          = "POSTED"
        write_off["ledger_entry_id"] = entry_id
        return self._to_result(write_off)

    def reject(self, write_off_id: str, tenant_id: str, actor_sub: str, reason: str = "") -> WriteOffResult:
        write_off = self._get_row(write_off_id, tenant_id)
        if not write_off:
            raise ValueError(f"Write-off '{write_off_id}' not found")
        if write_off["status"] != "REQUESTED":
            raise ValueError(f"Write-off has status '{write_off['status']}' and cannot be rejected")

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE write_offs
                SET status='REJECTED'
                WHERE id=%s::uuid
            """, (write_off_id,))
            conn.commit()

        write_off["status"] = "REJECTED"
        return self._to_result(write_off)

    def get(self, write_off_id: str, tenant_id: str) -> WriteOffResult | None:
        row = self._get_row(write_off_id, tenant_id)
        if not row:
            return None
        return self._to_result(row)

    def list_by_case(self, case_id: str, tenant_id: str) -> list[WriteOffResult]:
        rows = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, expected_recovery_id, amount, currency,
                       reason_code, policy_version_id, authorized_by, authorized_at,
                       ledger_entry_id, status, created_at
                FROM   write_offs
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY created_at DESC
            """,
            params=(case_id, tenant_id),
        )
        return [self._to_result(r) for r in rows]

    def _get_row(self, write_off_id: str, tenant_id: str) -> dict | None:
        return _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, case_id, expected_recovery_id, amount, currency,
                       reason_code, policy_version_id, authorized_by, authorized_at,
                       ledger_entry_id, status, created_at
                FROM   write_offs
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(write_off_id, tenant_id),
        )

    @staticmethod
    def _to_result(row: dict) -> WriteOffResult:
        return WriteOffResult(
            write_off_id         = str(row["id"]),
            tenant_id            = str(row["tenant_id"]),
            case_id              = str(row["case_id"]),
            expected_recovery_id = str(row["expected_recovery_id"]),
            amount               = float(row["amount"]),
            currency             = row["currency"],
            reason_code          = row["reason_code"],
            policy_version_id    = row["policy_version_id"],
            authorized_by        = row["authorized_by"],
            authorized_at        = row["authorized_at"],
            ledger_entry_id      = str(row["ledger_entry_id"]) if row["ledger_entry_id"] else None,
            status               = row["status"],
            created_at           = row["created_at"],
        )
