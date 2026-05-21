"""
Validation Service — reads contract_rates from DB, compares against the ingested invoice,
detects overcharges, inserts validation_results, publishes zoiko.source.record.validated to Kafka.

Contract rate lookup order (spec §8.1):
  1. By lane_hash = SHA-256("zoiko/v1/lane:" + origin + "|" + dest) — exact lane match
  2. By carrier_id — carrier-level flat rate (backward compat)
"""
import json, hashlib, uuid
from datetime import datetime, timezone, date

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from services.validation_svc.models import ValidationResult, RateViolation


class ValidationHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def validate(
        self,
        tenant_id: str,
        source_record_id: uuid.UUID,
        invoice_number: str,
        carrier_id: str,
        total_amount: float,
        currency: str = "USD",
    ) -> ValidationResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))
        today            = date.today()

        # Compute lane_hash for spec-aligned lane-level lookup (§8.1)
        lane_hash = "sha256:" + hashlib.sha256(
            ("zoiko/v1/lane:" + carrier_id + "|" + currency).encode()
        ).hexdigest()

        conn = psycopg2.connect(self.db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Priority 1: lane-level match (spec §8.1)
        cur.execute("""
            SELECT rate_type, COALESCE(base_rate, rate_value) AS rate_value, currency
            FROM   contract_rates
            WHERE  tenant_id    = %s
              AND  lane_hash    = %s
              AND  COALESCE(effective_from, effective_on) <= %s
              AND  (COALESCE(effective_to, expires_on) IS NULL
                    OR COALESCE(effective_to, expires_on) >= %s)
        """, (tenant_id, lane_hash, today, today))
        rates = cur.fetchall()

        # Priority 2: carrier-level fallback (backward compat)
        if not rates:
            cur.execute("""
                SELECT rate_type, rate_value, currency
                FROM   contract_rates
                WHERE  tenant_id   = %s
                  AND  carrier_id  = %s
                  AND  effective_on <= %s
                  AND  (expires_on IS NULL OR expires_on >= %s)
            """, (tenant_id, carrier_id, today, today))
            rates = cur.fetchall()

        conn.close()

        violations: list[RateViolation] = []
        expected_total = 0.0

        if not rates:
            violations.append(RateViolation(
                rule="NO_CONTRACT_RATE",
                carrier_id=carrier_id,
                rate_type="*",
                expected=0.0,
                actual=float(total_amount),
                delta=float(total_amount),
            ))
            status = "WARN"
        else:
            expected_total = sum(float(r["rate_value"]) for r in rates)
            if total_amount > expected_total + 0.005:          # 0.5-cent tolerance
                delta = round(float(total_amount) - expected_total, 4)
                for r in rates:
                    if float(total_amount) > float(r["rate_value"]) + 0.005:
                        violations.append(RateViolation(
                            rule="CARRIER_RATE_EXCEEDED",
                            carrier_id=carrier_id,
                            rate_type=r["rate_type"],
                            expected=float(r["rate_value"]),
                            actual=float(total_amount),
                            delta=delta,
                        ))
                        break
                status = "FAIL"
            else:
                status = "PASS"

        overcharge = max(0.0, round(float(total_amount) - expected_total, 4)) if rates else float(total_amount)

        # Build result blob for signing
        result_blob = json.dumps({
            "source_record_id": str(source_record_id),
            "status":           status,
            "total_amount":     float(total_amount),
            "expected_total":   expected_total,
        }, sort_keys=True).encode()
        result_hash = hashlib.sha256(b"zoiko.validation.result.v1:" + result_blob).digest()
        signature, kid = sign(self.tenant_slug, result_hash)

        violations_json = json.dumps([
            {"rule": v.rule, "carrier_id": v.carrier_id, "rate_type": v.rate_type,
             "expected": v.expected, "actual": v.actual, "delta": v.delta}
            for v in violations
        ])

        val_id = uuid.uuid4()
        now    = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO validation_results
                    (id, tenant_id, source_record_id, status, rule_violations,
                     signature, kid, validated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """, (
                val_id, tenant_id, source_record_id,
                status, violations_json,
                signature, kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Publish invoice.validated
        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.source.record.validated",
            key       = str(source_record_id),
            payload   = {
                "invoice_number":    invoice_number,
                "status":            status,
                "overcharge_amount": overcharge,
                "currency":          currency,
                "violations":        len(violations),
            },
            tenant_id = tenant_id,
        ))

        return ValidationResult(
            validation_id    = val_id,
            source_record_id = source_record_id,
            tenant_id        = tenant_id,
            status           = status,
            rule_violations  = violations,
            overcharge_amount= overcharge,
            currency         = currency,
        )
