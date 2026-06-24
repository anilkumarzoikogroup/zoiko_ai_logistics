"""
Phase 6 (Clarification 06 Slice 1) — Recovery Proof / ACR Readiness

Builds a case-level recovery_proofs snapshot once every expected_recoveries
row for a case has reached a terminal state (LEDGER_CLOSED or WRITTEN_OFF),
then flips those rows to ACR_READY. This is the input the audit_acr_svc will
eventually consume.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.recovery_proof_svc.models import RecoveryProofResult

psycopg2.extras.register_uuid()

_TOLERANCE = 0.01

_PENDING_STATUSES = {
    "EXPECTED", "AWAITING_INSTRUMENT", "INSTRUMENT_RECEIVED", "MATCHING",
    "MATCHED_PARTIAL", "UNRECOVERABLE_PENDING_APPROVAL", "LEDGER_PENDING",
}
_TERMINAL_STATUSES = {"LEDGER_CLOSED", "WRITTEN_OFF", "ACR_READY"}


class RecoveryProofHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def generate(self, case_id: str, tenant_id: str, actor_sub: str) -> RecoveryProofResult:
        expected_rows = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id, status, expected_amount, currency
                FROM   expected_recoveries
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
            """,
            params=(case_id, tenant_id),
        )
        if not expected_rows:
            raise ValueError(f"No expected recoveries found for case '{case_id}'")

        expected_recovery_ids = [str(r["id"]) for r in expected_rows]
        currency        = expected_rows[0]["currency"]
        total_expected  = sum(float(r["expected_amount"]) for r in expected_rows)
        statuses        = {r["status"] for r in expected_rows}

        matches = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id, recovery_instrument_id, allocation_status, matched_amount
                FROM   recovery_matches
                WHERE  expected_recovery_id = ANY(%s::uuid[]) AND tenant_id=%s::uuid
                       AND allocation_status <> 'REVERSED'
            """,
            params=(expected_recovery_ids, tenant_id),
        )
        recovery_match_ids      = [str(m["id"]) for m in matches]
        recovery_instrument_ids = sorted({str(m["recovery_instrument_id"]) for m in matches})
        total_recovered = sum(
            float(m["matched_amount"]) for m in matches
            if m["allocation_status"] in ("FULL", "PARTIAL", "OVER")
        )

        write_offs = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT amount, reason_code
                FROM   write_offs
                WHERE  expected_recovery_id = ANY(%s::uuid[]) AND tenant_id=%s::uuid
                       AND status='POSTED'
            """,
            params=(expected_recovery_ids, tenant_id),
        )
        total_written_off = sum(float(w["amount"]) for w in write_offs)

        ledger_entries = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id
                FROM   ledger_entries
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid AND status='POSTED'
            """,
            params=(case_id, tenant_id),
        )
        ledger_entry_ids = [str(e["id"]) for e in ledger_entries]

        total_unrecovered = max(total_expected - total_recovered - total_written_off, 0.0)

        if all(s in _TERMINAL_STATUSES for s in statuses):
            ledger_status = "LEDGER_CLOSED"
        else:
            ledger_status = "LEDGER_PENDING"

        if "MISMATCHED" in statuses:
            recovery_status = "MISMATCHED"
        elif statuses & _PENDING_STATUSES:
            recovery_status = "AWAITING_INSTRUMENT"
        elif "OVER_RECOVERED" in statuses:
            recovery_status = "OVER_RECOVERED"
        elif all(s in _TERMINAL_STATUSES for s in statuses):
            if total_recovered <= 0 and total_written_off > 0:
                if any(w["reason_code"] == "counterparty_rejection" for w in write_offs):
                    recovery_status = "REJECTED_BY_COUNTERPARTY"
                else:
                    recovery_status = "UNRECOVERABLE_APPROVED"
            elif total_recovered >= total_expected * (1 - _TOLERANCE):
                recovery_status = "RECOVERED_FULL"
            else:
                recovery_status = "RECOVERED_PARTIAL"
        else:
            recovery_status = "LEDGER_PENDING"

        acr_ready = ledger_status == "LEDGER_CLOSED"

        now      = datetime.now(timezone.utc)
        proof_id = uuid.uuid4()

        prior_proof = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id FROM recovery_proofs
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid AND superseded_by IS NULL
                LIMIT  1
            """,
            params=(case_id, tenant_id),
        )

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO recovery_proofs
                    (id, tenant_id, case_id, claimed_amount, currency,
                     expected_recovery_ids, recovery_instrument_ids,
                     recovery_match_ids, ledger_entry_ids,
                     total_expected, total_recovered, total_unrecovered,
                     recovery_status, ledger_status, acr_ready,
                     superseded_by, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s,
                        %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s, %s, %s,
                        NULL, %s)
            """, (
                proof_id, tenant_id, case_id, total_expected, currency,
                json.dumps(expected_recovery_ids), json.dumps(recovery_instrument_ids),
                json.dumps(recovery_match_ids), json.dumps(ledger_entry_ids),
                total_expected, total_recovered, total_unrecovered,
                recovery_status, ledger_status, acr_ready,
                now,
            ))

            if prior_proof:
                cur.execute("""
                    UPDATE recovery_proofs
                    SET superseded_by=%s::uuid
                    WHERE id=%s::uuid
                """, (proof_id, prior_proof["id"]))

            if acr_ready:
                cur.execute("""
                    UPDATE expected_recoveries
                    SET status='ACR_READY', updated_at=%s
                    WHERE id = ANY(%s::uuid[]) AND status IN ('LEDGER_CLOSED','WRITTEN_OFF')
                """, (now, expected_recovery_ids))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.proof.generated",
                case_id,
                json.dumps({
                    "proof_id":        str(proof_id),
                    "case_id":         case_id,
                    "recovery_status": recovery_status,
                    "ledger_status":   ledger_status,
                    "acr_ready":       acr_ready,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.proof.generated",
                key       = case_id,
                payload   = {"proof_id": str(proof_id), "acr_ready": acr_ready},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return RecoveryProofResult(
            proof_id                = str(proof_id),
            tenant_id               = tenant_id,
            case_id                 = case_id,
            claimed_amount          = total_expected,
            currency                = currency,
            expected_recovery_ids   = expected_recovery_ids,
            recovery_instrument_ids = recovery_instrument_ids,
            recovery_match_ids      = recovery_match_ids,
            ledger_entry_ids        = ledger_entry_ids,
            total_expected          = total_expected,
            total_recovered         = total_recovered,
            total_unrecovered       = total_unrecovered,
            recovery_status         = recovery_status,
            ledger_status           = ledger_status,
            acr_ready               = acr_ready,
            superseded_by           = None,
            created_at              = now,
        )

    def get(self, proof_id: str, tenant_id: str) -> RecoveryProofResult | None:
        row = _db.q1(
            db_url=self._db_url,
            sql=self._SELECT + " WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
            params=(proof_id, tenant_id),
        )
        if not row:
            return None
        return self._to_result(row)

    def list_by_case(self, case_id: str, tenant_id: str) -> list[RecoveryProofResult]:
        rows = _db.q(
            db_url=self._db_url,
            sql=self._SELECT + " WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC",
            params=(case_id, tenant_id),
        )
        return [self._to_result(r) for r in rows]

    def get_latest_by_case(self, case_id: str, tenant_id: str) -> RecoveryProofResult | None:
        row = _db.q1(
            db_url=self._db_url,
            sql=self._SELECT + """
                WHERE case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER BY (superseded_by IS NULL) DESC, created_at DESC
                LIMIT 1
            """,
            params=(case_id, tenant_id),
        )
        if not row:
            return None
        return self._to_result(row)

    _SELECT = """
        SELECT id, tenant_id, case_id, claimed_amount, currency,
               expected_recovery_ids, recovery_instrument_ids,
               recovery_match_ids, ledger_entry_ids,
               total_expected, total_recovered, total_unrecovered,
               recovery_status, ledger_status, acr_ready,
               superseded_by, created_at
        FROM   recovery_proofs
    """

    @staticmethod
    def _to_result(row: dict) -> RecoveryProofResult:
        return RecoveryProofResult(
            proof_id                = str(row["id"]),
            tenant_id               = str(row["tenant_id"]),
            case_id                 = str(row["case_id"]),
            claimed_amount          = float(row["claimed_amount"]),
            currency                = row["currency"],
            expected_recovery_ids   = list(row["expected_recovery_ids"]),
            recovery_instrument_ids = list(row["recovery_instrument_ids"]),
            recovery_match_ids      = list(row["recovery_match_ids"]),
            ledger_entry_ids        = list(row["ledger_entry_ids"]),
            total_expected          = float(row["total_expected"]),
            total_recovered         = float(row["total_recovered"]),
            total_unrecovered       = float(row["total_unrecovered"]),
            recovery_status         = row["recovery_status"],
            ledger_status           = row["ledger_status"],
            acr_ready               = bool(row["acr_ready"]),
            superseded_by           = str(row["superseded_by"]) if row["superseded_by"] else None,
            created_at              = row["created_at"],
        )
