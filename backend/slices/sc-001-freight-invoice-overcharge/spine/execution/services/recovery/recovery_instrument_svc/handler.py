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
