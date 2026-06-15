"""
Phase 6 (Clarification 06 Slice 1) — Expected Recovery Service

Tracks "what we are owed" once a case has been authorized for recovery action.
This is the finance-grade counterpart to the case's workflow state — a case
reaching CLOSED_RECOVERED means nothing financially until an expected_recoveries
row exists, is matched against a recovery_instrument, and posted to the ledger.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.expected_recovery_svc.models import ExpectedRecoveryCreate, ExpectedRecoveryResult

psycopg2.extras.register_uuid()


class ExpectedRecoveryHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def create(self, req: ExpectedRecoveryCreate) -> ExpectedRecoveryResult:
        case = _db.q1(
            db_url=self._db_url,
            sql="SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
            params=(req.case_id, req.tenant_id),
        )
        if not case:
            raise ValueError(f"Case '{req.case_id}' not found")

        if req.authorization_decision_id:
            dup = _db.q1(
                db_url=self._db_url,
                sql="""
                    SELECT id FROM expected_recoveries
                    WHERE tenant_id=%s::uuid AND case_id=%s::uuid
                          AND authorization_decision_id=%s::uuid AND superseded_by IS NULL
                    LIMIT 1
                """,
                params=(req.tenant_id, req.case_id, req.authorization_decision_id),
            )
            if dup:
                raise ValueError(
                    f"Expected recovery for authorization_decision_id "
                    f"'{req.authorization_decision_id}' already exists (id={dup['id']})"
                )

        er_id = uuid.uuid4()
        now   = datetime.now(timezone.utc)

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO expected_recoveries
                    (id, tenant_id, case_id, authorization_decision_id,
                     counterparty_type, counterparty_id, expected_amount, currency,
                     expected_recovery_method, expected_invoice_id, expected_external_invoice_ref,
                     tolerance_policy_id, status, created_at, updated_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                        %s, %s::uuid, %s, %s,
                        %s, %s::uuid, %s,
                        %s, 'EXPECTED', %s, %s)
            """, (
                er_id, req.tenant_id, req.case_id, req.authorization_decision_id,
                req.counterparty_type, req.counterparty_id, req.expected_amount, req.currency,
                req.expected_recovery_method, req.expected_invoice_id, req.expected_external_invoice_ref,
                req.tolerance_policy_id, now, now,
            ))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), req.tenant_id,
                "zoiko.recovery.expected.created",
                req.case_id,
                json.dumps({
                    "expected_recovery_id": str(er_id),
                    "case_id":              req.case_id,
                    "expected_amount":      req.expected_amount,
                    "currency":             req.currency,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.expected.created",
                key       = req.case_id,
                payload   = {"expected_recovery_id": str(er_id), "status": "EXPECTED"},
                tenant_id = req.tenant_id,
            ))
        except Exception:
            pass

        return ExpectedRecoveryResult(
            expected_recovery_id    = str(er_id),
            case_id                  = req.case_id,
            tenant_id                = req.tenant_id,
            expected_amount          = req.expected_amount,
            currency                 = req.currency,
            expected_recovery_method = req.expected_recovery_method,
            status                   = "EXPECTED",
            created_at               = now,
        )

    def get(self, expected_recovery_id: str, tenant_id: str) -> ExpectedRecoveryResult | None:
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, case_id, tenant_id, expected_amount, currency,
                       expected_recovery_method, status, created_at
                FROM   expected_recoveries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(expected_recovery_id, tenant_id),
        )
        if not row:
            return None
        return self._to_result(row)

    def list_by_case(self, case_id: str, tenant_id: str) -> list[ExpectedRecoveryResult]:
        rows = _db.q(
            sql="""
                SELECT id, case_id, tenant_id, expected_amount, currency,
                       expected_recovery_method, status, created_at
                FROM   expected_recoveries
                WHERE  case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY created_at DESC
            """,
            params=(case_id, tenant_id),
            db_url=self._db_url,
        )
        return [self._to_result(r) for r in rows]

    def supersede(
        self,
        expected_recovery_id: str,
        tenant_id: str,
        expected_amount: float,
        currency: str | None = None,
        expected_recovery_method: str | None = None,
        reason: str = "",
    ) -> ExpectedRecoveryResult:
        """Replace an expected_recoveries row with a new one (corrections are never mutated in place)."""
        old = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, case_id, tenant_id, currency, expected_recovery_method,
                       counterparty_type, counterparty_id, expected_invoice_id,
                       expected_external_invoice_ref, tolerance_policy_id, authorization_decision_id, status
                FROM   expected_recoveries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(expected_recovery_id, tenant_id),
        )
        if not old:
            raise ValueError(f"Expected recovery '{expected_recovery_id}' not found")
        if old["status"] in ("LEDGER_CLOSED", "ACR_READY"):
            raise ValueError(f"Expected recovery is already '{old['status']}' and cannot be superseded")

        new_id = uuid.uuid4()
        now    = datetime.now(timezone.utc)
        new_currency = currency or old["currency"]
        new_method   = expected_recovery_method or old["expected_recovery_method"]

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            # Clear the old row's "live" marker first — the partial unique
            # index uq_expected_recoveries_tenant_case_authdec only allows
            # one row with superseded_by IS NULL per
            # (tenant_id, case_id, authorization_decision_id), so the old row
            # must stop qualifying before the new row (same authorization_decision_id) is inserted.
            cur.execute("""
                UPDATE expected_recoveries
                SET superseded_by=%s::uuid, updated_at=%s
                WHERE id=%s::uuid
            """, (new_id, now, expected_recovery_id))
            cur.execute("""
                INSERT INTO expected_recoveries
                    (id, tenant_id, case_id, authorization_decision_id,
                     counterparty_type, counterparty_id, expected_amount, currency,
                     expected_recovery_method, expected_invoice_id, expected_external_invoice_ref,
                     tolerance_policy_id, status, created_at, updated_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                        %s, %s::uuid, %s, %s,
                        %s, %s::uuid, %s,
                        %s, 'EXPECTED', %s, %s)
            """, (
                new_id, tenant_id, str(old["case_id"]), old["authorization_decision_id"],
                old["counterparty_type"], old["counterparty_id"], expected_amount, new_currency,
                new_method, old["expected_invoice_id"], old["expected_external_invoice_ref"],
                old["tolerance_policy_id"], now, now,
            ))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.expected.created",
                str(old["case_id"]),
                json.dumps({
                    "expected_recovery_id":    str(new_id),
                    "supersedes":              expected_recovery_id,
                    "case_id":                 str(old["case_id"]),
                    "expected_amount":         expected_amount,
                    "currency":                new_currency,
                    "reason":                  reason,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.expected.created",
                key       = str(old["case_id"]),
                payload   = {"expected_recovery_id": str(new_id), "supersedes": expected_recovery_id},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return ExpectedRecoveryResult(
            expected_recovery_id    = str(new_id),
            case_id                  = str(old["case_id"]),
            tenant_id                = tenant_id,
            expected_amount          = expected_amount,
            currency                 = new_currency,
            expected_recovery_method = new_method,
            status                   = "EXPECTED",
            created_at               = now,
        )

    @staticmethod
    def _to_result(row: dict) -> ExpectedRecoveryResult:
        return ExpectedRecoveryResult(
            expected_recovery_id    = str(row["id"]),
            case_id                  = str(row["case_id"]),
            tenant_id                = str(row["tenant_id"]),
            expected_amount          = float(row["expected_amount"]),
            currency                 = row["currency"],
            expected_recovery_method = row["expected_recovery_method"],
            status                   = row["status"],
            created_at               = row["created_at"],
        )
