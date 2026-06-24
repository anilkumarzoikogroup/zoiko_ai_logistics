"""
Phase 6 (Clarification 06 Slice 1) — Recovery Matching Engine

Matches an expected_recoveries row ("what we are owed") against an available
recovery_instruments row ("what we received"), records the result in
recovery_matches, and updates both sides' status.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import shared.db as _db

import paths  # noqa: F401

from services.recovery.recovery_match_svc.models import RecoveryMatchResult

psycopg2.extras.register_uuid()

_TOLERANCE = 0.01

_OPEN_STATUSES = ("EXPECTED", "AWAITING_INSTRUMENT", "MATCHING", "MATCHED_PARTIAL")


class RecoveryMatchHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    def match(self, expected_recovery_id: str, tenant_id: str, actor_sub: str) -> RecoveryMatchResult | None:
        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                SELECT id, tenant_id, case_id, expected_amount, currency,
                       expected_external_invoice_ref, status
                FROM   expected_recoveries
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
                FOR UPDATE
            """, (expected_recovery_id, tenant_id))
            expected = cur.fetchone()
            if not expected:
                raise ValueError(f"Expected recovery '{expected_recovery_id}' not found")
            if expected["status"] not in _OPEN_STATUSES:
                raise ValueError(f"Expected recovery is in status '{expected['status']}' and cannot be matched")

            cur.execute("""
                SELECT COALESCE(SUM(matched_amount), 0) AS total
                FROM   recovery_matches
                WHERE  expected_recovery_id=%s::uuid AND tenant_id=%s::uuid
                       AND allocation_status <> 'REVERSED'
            """, (expected_recovery_id, tenant_id))
            already_matched_row = cur.fetchone()
            already_matched = float(already_matched_row["total"]) if already_matched_row else 0.0
            expected_amount = float(expected["expected_amount"])
            remaining = expected_amount - already_matched
            if remaining <= 0:
                raise ValueError("Expected recovery has no remaining amount to match")

            candidates: list[dict] = []
            match_tier   = None
            match_method = None
            match_confidence = None

            if expected["expected_external_invoice_ref"]:
                cur.execute("""
                    SELECT id, instrument_amount, currency
                    FROM   recovery_instruments
                    WHERE  tenant_id=%s::uuid AND status='AVAILABLE' AND currency=%s
                           AND related_external_invoice_ref=%s
                    ORDER  BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                """, (tenant_id, expected["currency"], expected["expected_external_invoice_ref"]))
                candidates = cur.fetchall()
                if candidates:
                    match_tier, match_method, match_confidence = 2, "EXTERNAL_REFERENCE", 1.0

            if not candidates:
                cur.execute("""
                    SELECT id, instrument_amount, currency
                    FROM   recovery_instruments
                    WHERE  tenant_id=%s::uuid AND status='AVAILABLE' AND currency=%s
                           AND related_case_id=%s::uuid
                    ORDER  BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                """, (tenant_id, expected["currency"], str(expected["case_id"])))
                candidates = cur.fetchall()
                if candidates:
                    match_tier, match_method, match_confidence = 3, "BUSINESS_KEY_CASE", 0.85

            if not candidates:
                conn.commit()
                return None

            now = datetime.now(timezone.utc)
            match_id = uuid.uuid4()
            instrument = candidates[0]

            if len(candidates) > 1:
                allocation_status   = "REVIEW_REQUIRED"
                matched_amount       = 0.0
                variance             = 0.0
                new_expected_status  = "MATCHING"
                consume_instrument   = False
            else:
                instrument_amount = float(instrument["instrument_amount"])
                matched_amount    = min(instrument_amount, remaining)
                variance          = instrument_amount - remaining

                if abs(variance) <= remaining * _TOLERANCE:
                    allocation_status  = "FULL"
                    new_expected_status = "MATCHED_FULL"
                elif instrument_amount < remaining:
                    allocation_status  = "PARTIAL"
                    new_expected_status = "MATCHED_PARTIAL"
                else:
                    allocation_status  = "OVER"
                    new_expected_status = "OVER_RECOVERED"
                consume_instrument = True

            cur.execute("""
                INSERT INTO recovery_matches
                    (id, tenant_id, expected_recovery_id, recovery_instrument_id,
                     match_tier, match_method, match_confidence,
                     matched_amount, expected_amount, variance, currency,
                     allocation_status, matched_by, matched_at, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s)
            """, (
                match_id, tenant_id, expected_recovery_id, instrument["id"],
                match_tier, match_method, match_confidence,
                matched_amount, expected_amount, variance, expected["currency"],
                allocation_status, actor_sub, now, now,
            ))

            cur.execute("""
                UPDATE expected_recoveries
                SET status=%s, updated_at=%s
                WHERE id=%s::uuid
            """, (new_expected_status, now, expected_recovery_id))

            if consume_instrument:
                cur.execute("""
                    UPDATE recovery_instruments
                    SET status='CONSUMED'
                    WHERE id=%s::uuid
                """, (instrument["id"],))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.match.created",
                str(expected["case_id"]),
                json.dumps({
                    "match_id":             str(match_id),
                    "expected_recovery_id": expected_recovery_id,
                    "allocation_status":    allocation_status,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.match.created",
                key       = str(expected["case_id"]),
                payload   = {"match_id": str(match_id), "allocation_status": allocation_status},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return RecoveryMatchResult(
            match_id               = str(match_id),
            expected_recovery_id   = expected_recovery_id,
            recovery_instrument_id = str(instrument["id"]),
            tenant_id               = tenant_id,
            match_tier              = match_tier,
            match_method            = match_method,
            match_confidence        = match_confidence,
            matched_amount          = matched_amount,
            expected_amount         = expected_amount,
            variance                = variance,
            currency                = expected["currency"],
            allocation_status       = allocation_status,
            matched_by              = actor_sub,
            matched_at              = now,
        )

    def reverse(self, match_id: str, tenant_id: str, actor_sub: str, reason: str = "") -> RecoveryMatchResult:
        match = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, expected_recovery_id, recovery_instrument_id,
                       match_tier, match_method, match_confidence,
                       matched_amount, expected_amount, variance, currency,
                       allocation_status, matched_by, matched_at
                FROM   recovery_matches
                WHERE  id=%s::uuid AND tenant_id=%s::uuid
                LIMIT  1
            """,
            params=(match_id, tenant_id),
        )
        if not match:
            raise ValueError(f"Recovery match '{match_id}' not found")
        if match["allocation_status"] == "REVERSED":
            raise ValueError("Recovery match is already REVERSED")

        expected = _db.q1(
            db_url=self._db_url,
            sql="SELECT id, case_id FROM expected_recoveries WHERE id=%s::uuid AND tenant_id=%s::uuid LIMIT 1",
            params=(str(match["expected_recovery_id"]), tenant_id),
        )

        now = datetime.now(timezone.utc)
        was_consumed = match["allocation_status"] in ("FULL", "PARTIAL", "OVER")

        with _db.get_conn(self._db_url) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE recovery_matches
                SET allocation_status='REVERSED'
                WHERE id=%s::uuid
            """, (match_id,))

            cur.execute("""
                UPDATE expected_recoveries
                SET status='EXPECTED', updated_at=%s
                WHERE id=%s::uuid
            """, (now, str(match["expected_recovery_id"])))

            if was_consumed:
                cur.execute("""
                    UPDATE recovery_instruments
                    SET status='AVAILABLE'
                    WHERE id=%s::uuid
                """, (match["recovery_instrument_id"],))

            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id,
                "zoiko.recovery.match.reversed",
                str(expected["case_id"]) if expected else str(match["expected_recovery_id"]),
                json.dumps({
                    "match_id":             str(match_id),
                    "expected_recovery_id": str(match["expected_recovery_id"]),
                    "reason":               reason,
                }),
                now,
            ))

            conn.commit()

        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.recovery.match.reversed",
                key       = str(expected["case_id"]) if expected else str(match["expected_recovery_id"]),
                payload   = {"match_id": str(match_id), "reason": reason},
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return RecoveryMatchResult(
            match_id               = str(match["id"]),
            expected_recovery_id   = str(match["expected_recovery_id"]),
            recovery_instrument_id = str(match["recovery_instrument_id"]),
            tenant_id               = tenant_id,
            match_tier              = match["match_tier"],
            match_method            = match["match_method"],
            match_confidence        = float(match["match_confidence"]) if match["match_confidence"] is not None else None,
            matched_amount          = float(match["matched_amount"]),
            expected_amount         = float(match["expected_amount"]),
            variance                = float(match["variance"]),
            currency                = match["currency"],
            allocation_status       = "REVERSED",
            matched_by              = match["matched_by"],
            matched_at              = match["matched_at"],
        )

    def list_by_expected(self, expected_recovery_id: str, tenant_id: str) -> list[RecoveryMatchResult]:
        rows = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT id, tenant_id, expected_recovery_id, recovery_instrument_id,
                       match_tier, match_method, match_confidence,
                       matched_amount, expected_amount, variance, currency,
                       allocation_status, matched_by, matched_at
                FROM   recovery_matches
                WHERE  expected_recovery_id=%s::uuid AND tenant_id=%s::uuid
                ORDER  BY matched_at DESC
            """,
            params=(expected_recovery_id, tenant_id),
        )
        return [self._to_result(r) for r in rows]

    def list_by_case(self, case_id: str, tenant_id: str) -> list[RecoveryMatchResult]:
        rows = _db.q(
            db_url=self._db_url,
            sql="""
                SELECT m.id, m.tenant_id, m.expected_recovery_id, m.recovery_instrument_id,
                       m.match_tier, m.match_method, m.match_confidence,
                       m.matched_amount, m.expected_amount, m.variance, m.currency,
                       m.allocation_status, m.matched_by, m.matched_at
                FROM   recovery_matches m
                JOIN   expected_recoveries e ON e.id = m.expected_recovery_id
                WHERE  e.case_id=%s::uuid AND m.tenant_id=%s::uuid
                ORDER  BY m.matched_at DESC
            """,
            params=(case_id, tenant_id),
        )
        return [self._to_result(r) for r in rows]

    @staticmethod
    def _to_result(row: dict) -> RecoveryMatchResult:
        return RecoveryMatchResult(
            match_id               = str(row["id"]),
            expected_recovery_id   = str(row["expected_recovery_id"]),
            recovery_instrument_id = str(row["recovery_instrument_id"]),
            tenant_id               = str(row["tenant_id"]),
            match_tier              = row["match_tier"],
            match_method            = row["match_method"],
            match_confidence        = float(row["match_confidence"]) if row["match_confidence"] is not None else None,
            matched_amount          = float(row["matched_amount"]),
            expected_amount         = float(row["expected_amount"]),
            variance                = float(row["variance"]),
            currency                = row["currency"],
            allocation_status       = row["allocation_status"],
            matched_by              = row["matched_by"],
            matched_at              = row["matched_at"],
        )
