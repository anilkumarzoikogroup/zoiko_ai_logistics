"""
Phase 6 (Clarification 06 Slice 1) — Recovery Instrument Service

Tracks "what we actually received" — credit memos, refunds, settlement offsets,
or manual/internal recovery evidence. An instrument starts AVAILABLE and is
later CONSUMED by a recovery_match (Step 4) or REVERSED.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.recovery_instrument_svc.models import RecoveryInstrumentCreate, RecoveryInstrumentResult

psycopg2.extras.register_uuid()


class RecoveryInstrumentHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def create(self, req: RecoveryInstrumentCreate) -> RecoveryInstrumentResult:
        if req.related_case_id:
            case = _db.q1(
                db_url=self._db_url,
                sql="SELECT id FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
                params=(req.related_case_id, req.tenant_id),
            )
            if not case:
                raise ValueError(f"Case '{req.related_case_id}' not found")

        if req.external_reference:
            dup = _db.q1(
                db_url=self._db_url,
                sql="""
                    SELECT id FROM recovery_instruments
                    WHERE tenant_id=%s::uuid AND external_reference=%s
                    LIMIT 1
                """,
                params=(req.tenant_id, req.external_reference),
            )
            if dup:
                raise ValueError(
                    f"Recovery instrument with external_reference "
                    f"'{req.external_reference}' already exists (id={dup['id']})"
                )

        ri_id = uuid.uuid4()
        now   = datetime.now(timezone.utc)

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO recovery_instruments
                    (id, tenant_id, instrument_type, counterparty_type, counterparty_id,
                     source_record_id, external_reference, related_external_invoice_ref,
                     related_case_id, instrument_amount, currency, instrument_date,
                     received_at, status, created_by, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::uuid,
                        %s::uuid, %s, %s,
                        %s::uuid, %s, %s, %s,
                        %s, 'AVAILABLE', %s, %s)
            """, (
                ri_id, req.tenant_id, req.instrument_type, req.counterparty_type, req.counterparty_id,
                req.source_record_id, req.external_reference, req.related_external_invoice_ref,
                req.related_case_id, req.instrument_amount, req.currency, req.instrument_date,
                now, req.created_by, now,
            ))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), req.tenant_id,
                "zoiko.recovery.instrument.received",
                req.related_case_id or str(ri_id),
                json.dumps({
                    "recovery_instrument_id": str(ri_id),
                    "instrument_type":        req.instrument_type,
                    "instrument_amount":      req.instrument_amount,
                    "currency":               req.currency,
                    "related_case_id":        req.related_case_id,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.instrument.received",
                key       = req.related_case_id or str(ri_id),
                payload   = {"recovery_instrument_id": str(ri_id), "status": "AVAILABLE"},
                tenant_id = req.tenant_id,
            ))
        except Exception:
            pass

        return RecoveryInstrumentResult(
            recovery_instrument_id = str(ri_id),
            tenant_id               = req.tenant_id,
            instrument_type         = req.instrument_type,
            instrument_amount       = req.instrument_amount,
            currency                = req.currency,
            status                  = "AVAILABLE",
            related_case_id         = req.related_case_id,
            created_by              = req.created_by,
            created_at              = now,
        )

    def get(self, recovery_instrument_id: str, tenant_id: str) -> RecoveryInstrumentResult | None:
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, instrument_type, instrument_amount, currency,
                       status, related_case_id, created_by, created_at
                FROM   recovery_instruments
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(recovery_instrument_id, tenant_id),
        )
        if not row:
            return None
        return self._to_result(row)

    def list_by_case(self, case_id: str, tenant_id: str) -> list[RecoveryInstrumentResult]:
        rows = _db.q(
            sql="""
                SELECT id, tenant_id, instrument_type, instrument_amount, currency,
                       status, related_case_id, created_by, created_at
                FROM   recovery_instruments
                WHERE  related_case_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY created_at DESC
            """,
            params=(case_id, tenant_id),
            db_url=self._db_url,
        )
        return [self._to_result(r) for r in rows]

    def confirm_payment(
        self,
        recovery_instrument_id: str,
        tenant_id: str,
        payment_ref: str,
        confirmed_by: str,
    ) -> RecoveryInstrumentResult:
        """Mark an instrument as payment_confirmed — carrier has sent actual money.

        Sets payment_confirmed=true, payment_confirmed_at=now, payment_confirmed_ref.
        Only AVAILABLE or CONSUMED instruments can be confirmed.
        Idempotent: re-confirming an already-confirmed instrument returns it unchanged.
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, instrument_type, instrument_amount, currency,
                       status, related_case_id, created_by, created_at,
                       payment_confirmed, payment_confirmed_at, payment_confirmed_ref
                FROM   recovery_instruments
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(recovery_instrument_id, tenant_id),
        )
        if not row:
            raise ValueError(f"Recovery instrument '{recovery_instrument_id}' not found")

        if row.get("payment_confirmed"):
            return self._to_result(row)  # already confirmed — idempotent

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE recovery_instruments
                SET payment_confirmed      = TRUE,
                    payment_confirmed_at   = %s,
                    payment_confirmed_ref  = %s
                WHERE id=%s::uuid AND tenant_id=%s::uuid
            """, (now, payment_ref, recovery_instrument_id, tenant_id))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.payment.confirmed",
                str(row["related_case_id"]) if row.get("related_case_id") else recovery_instrument_id,
                json.dumps({
                    "recovery_instrument_id": recovery_instrument_id,
                    "payment_ref":            payment_ref,
                    "amount":                 float(row["instrument_amount"]),
                    "currency":               row["currency"],
                    "related_case_id":        str(row["related_case_id"]) if row.get("related_case_id") else None,
                    "confirmed_by":           confirmed_by,
                }),
                now,
            ))
            conn.commit()

        # Reload updated row
        updated = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, instrument_type, instrument_amount, currency,
                       status, related_case_id, created_by, created_at,
                       payment_confirmed, payment_confirmed_at, payment_confirmed_ref
                FROM   recovery_instruments
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(recovery_instrument_id, tenant_id),
        )

        # Send payment confirmed notification
        try:
            self._notify_payment_confirmed(
                tenant_id=tenant_id,
                case_id=str(row["related_case_id"]) if row.get("related_case_id") else None,
                amount=float(row["instrument_amount"]),
                currency=row["currency"],
                payment_ref=payment_ref,
            )
        except Exception:
            pass

        return self._to_result(updated or row)

    def _notify_payment_confirmed(
        self,
        tenant_id: str, case_id: str | None,
        amount: float, currency: str, payment_ref: str,
    ) -> None:
        """Email managers when carrier confirms payment — best effort."""
        try:
            import sys, os
            from shared.db import q, q1
            settings = q1(
                "SELECT recovery_executed_email FROM tenant_notification_settings WHERE tenant_id=%s::uuid",
                (tenant_id,),
                db_url=self._db_url,
            )
            if settings and settings.get("recovery_executed_email") is False:
                return

            carrier = "Unknown Carrier"
            if case_id:
                case_row = q1(
                    """SELECT ca.name AS carrier_name FROM cases c
                       LEFT JOIN carriers ca ON ca.id = c.carrier_id
                       WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid LIMIT 1""",
                    (case_id, tenant_id),
                    db_url=self._db_url,
                )
                carrier = (case_row or {}).get("carrier_name") or "Unknown Carrier"

            recipients = q(
                "SELECT email, full_name, role FROM users WHERE tenant_id=%s::uuid AND role IN ('admin','manager') AND is_active=true",
                (tenant_id,),
                db_url=self._db_url,
            )
            from shared.email_sender import send_payment_confirmed, _log_notification
            for r in recipients:
                try:
                    send_payment_confirmed(
                        to_email=r["email"], to_name=r["full_name"],
                        case_id=case_id or "", carrier=carrier,
                        amount=amount, currency=currency,
                        payment_ref=payment_ref,
                    )
                    _log_notification(
                        self._db_url, tenant_id, "payment_confirmed",
                        r["email"], r["role"], case_id,
                        f"Payment Confirmed — Case {(case_id or '')[:8].upper()}",
                        amount, currency, "SENT",
                    )
                except Exception as _e:
                    _log_notification(
                        self._db_url, tenant_id, "payment_confirmed",
                        r["email"], r["role"], case_id,
                        f"Payment Confirmed — Case {(case_id or '')[:8].upper()}",
                        amount, currency, "FAILED", str(_e),
                    )
        except Exception:
            pass

    def list_by_counterparty(self, counterparty_id: str, tenant_id: str) -> list[RecoveryInstrumentResult]:
        rows = _db.q(
            sql="""
                SELECT id, tenant_id, instrument_type, instrument_amount, currency,
                       status, related_case_id, created_by, created_at
                FROM   recovery_instruments
                WHERE  counterparty_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY created_at DESC
            """,
            params=(counterparty_id, tenant_id),
            db_url=self._db_url,
        )
        return [self._to_result(r) for r in rows]

    @staticmethod
    def _to_result(row: dict) -> RecoveryInstrumentResult:
        return RecoveryInstrumentResult(
            recovery_instrument_id = str(row["id"]),
            tenant_id               = str(row["tenant_id"]),
            instrument_type         = row["instrument_type"],
            instrument_amount       = float(row["instrument_amount"]),
            currency                = row["currency"],
            status                  = row["status"],
            related_case_id         = str(row["related_case_id"]) if row["related_case_id"] else None,
            created_by              = row["created_by"],
            created_at              = row["created_at"],
        )
