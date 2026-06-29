"""SC-003 Validation Service — SLA/Shipment Exception Validator.

Build Map Domain 3 coverage for SC-003.
Validates a shipment exception at four stages before canonicalization:
  1. Structural  — required fields present
  2. Semantic    — values make sense (breach is positive, currency valid, etc.)
  3. Cross-record — duplicate shipment_reference detection
  4. Policy cap  — breach hours or penalty within configured limits

PASS = all checks pass (or only WARNs).
FAIL = at least one FAIL-severity rule violated → submit_exception() raises HTTP 422.

Writes:
  - validation_results  (one row per validation run)
  - source_record_states (one VALIDATED state row)
  - Kafka: zoiko.source.record.validated
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timezone

VALID_CURRENCIES = {"INR", "USD", "EUR", "GBP", "SGD", "AED"}

DEFAULT_MAX_BREACH_HOURS = 720.0   # 30 days — anything beyond is suspect
DEFAULT_MIN_PENALTY      = 0.0     # no minimum; a 0-INR breach is still valid
DEFAULT_PENALTY_CAP      = 1_000_000.0   # ₹10L per-exception policy default


@dataclass
class RuleViolation:
    rule: str
    severity: str       # FAIL | WARN
    message: str


@dataclass
class ValidationResult:
    status: str                             # PASS | FAIL | WARN
    rule_violations: list[RuleViolation] = field(default_factory=list)
    validation_result_id: str | None = None


class ShipmentExceptionValidationHandler:
    """Validates a shipment exception before it enters the canonical truth phase."""

    def __init__(self, db_url: str, broker, tenant_slug: str):
        self._db_url = db_url
        self._broker = broker
        self._slug   = tenant_slug

    def validate(
        self,
        *,
        tenant_id: str,
        source_record_id: str,
        carrier_id: str,
        shipment_reference: str,
        committed_eta,
        actual_delivery,
        penalty_rate_per_hour: float,
        penalty_cap: float,
        currency: str,
    ) -> ValidationResult:
        violations: list[RuleViolation] = []

        # ── 1. Structural ─────────────────────────────────────────────────────
        if not carrier_id or not str(carrier_id).strip():
            violations.append(RuleViolation(
                "STRUCT_MISSING_CARRIER_ID", "FAIL",
                "carrier_id is required"))

        if not shipment_reference or not str(shipment_reference).strip():
            violations.append(RuleViolation(
                "STRUCT_MISSING_SHIPMENT_REFERENCE", "FAIL",
                "shipment_reference is required"))

        if committed_eta is None:
            violations.append(RuleViolation(
                "STRUCT_MISSING_COMMITTED_ETA", "FAIL",
                "committed_eta is required"))

        if actual_delivery is None:
            violations.append(RuleViolation(
                "STRUCT_MISSING_ACTUAL_DELIVERY", "FAIL",
                "actual_delivery is required"))

        if not currency or not str(currency).strip():
            violations.append(RuleViolation(
                "STRUCT_MISSING_CURRENCY", "FAIL",
                "currency is required"))

        # ── 2. Semantic ───────────────────────────────────────────────────────
        if currency and currency.upper() not in VALID_CURRENCIES:
            violations.append(RuleViolation(
                "SEM_INVALID_CURRENCY", "FAIL",
                f"currency '{currency}' is not supported (use one of {sorted(VALID_CURRENCIES)})"))

        if committed_eta is not None and actual_delivery is not None:
            try:
                tz = timezone.utc
                eta = committed_eta.astimezone(tz) if hasattr(committed_eta, "astimezone") else committed_eta
                adl = actual_delivery.astimezone(tz) if hasattr(actual_delivery, "astimezone") else actual_delivery
                if adl <= eta:
                    violations.append(RuleViolation(
                        "SEM_NO_BREACH", "FAIL",
                        "actual_delivery is not later than committed_eta — no SLA breach exists"))
                else:
                    breach_h = (adl - eta).total_seconds() / 3600
                    if breach_h > DEFAULT_MAX_BREACH_HOURS:
                        violations.append(RuleViolation(
                            "SEM_BREACH_IMPLAUSIBLY_LARGE", "WARN",
                            f"breach of {breach_h:.1f}h exceeds {DEFAULT_MAX_BREACH_HOURS}h — verify timestamps"))
            except Exception:
                pass   # datetime comparison error — structural check already flagged None

        if penalty_rate_per_hour is not None and penalty_rate_per_hour < 0:
            violations.append(RuleViolation(
                "SEM_NEGATIVE_PENALTY_RATE", "FAIL",
                "penalty_rate_per_hour must be >= 0"))

        if penalty_cap is not None and penalty_cap < 0:
            violations.append(RuleViolation(
                "SEM_NEGATIVE_PENALTY_CAP", "FAIL",
                "penalty_cap must be >= 0"))

        # ── 3. Cross-record: duplicate shipment reference ─────────────────────
        if shipment_reference and not any(v.rule == "STRUCT_MISSING_SHIPMENT_REFERENCE" for v in violations):
            try:
                from shared.db import q1 as _q1
                dup = _q1(
                    """SELECT id FROM cases
                       WHERE  tenant_id=%s::uuid
                         AND  shipment_reference=%s
                         AND  state NOT IN ('ABORTED')
                       LIMIT 1""",
                    (tenant_id, shipment_reference),
                )
                if dup:
                    violations.append(RuleViolation(
                        "CROSS_DUPLICATE_SHIPMENT_REFERENCE", "WARN",
                        f"shipment_reference '{shipment_reference}' already exists in case {dup['id']}"))
            except Exception:
                pass   # never block on unexpected DB error

        # ── 4. Policy cap ─────────────────────────────────────────────────────
        policy_cap = self._resolve_policy_cap(tenant_id)
        try:
            if committed_eta is not None and actual_delivery is not None and penalty_rate_per_hour is not None:
                tz = timezone.utc
                eta = committed_eta.astimezone(tz) if hasattr(committed_eta, "astimezone") else committed_eta
                adl = actual_delivery.astimezone(tz) if hasattr(actual_delivery, "astimezone") else actual_delivery
                breach_h = max(0, (adl - eta).total_seconds() / 3600)
                calc_penalty = breach_h * penalty_rate_per_hour
                if penalty_cap is not None:
                    calc_penalty = min(calc_penalty, penalty_cap)
                if calc_penalty > policy_cap:
                    violations.append(RuleViolation(
                        "POLICY_CAP_EXCEEDED", "WARN",
                        f"calculated penalty ₹{calc_penalty:.2f} exceeds policy cap ₹{policy_cap:.2f}"))
        except Exception:
            pass

        # ── Determine status ──────────────────────────────────────────────────
        if any(v.severity == "FAIL" for v in violations):
            status = "FAIL"
        elif violations:
            status = "WARN"
        else:
            status = "PASS"

        result_id = self._persist(tenant_id, source_record_id, status, violations, shipment_reference)
        self._publish(tenant_id, source_record_id, status)

        return ValidationResult(status=status, rule_violations=violations, validation_result_id=result_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_policy_cap(self, tenant_id: str) -> float:
        try:
            from shared.db import q1 as _q1
            row = _q1(
                "SELECT max_claim_amount FROM claim_policy_caps WHERE tenant_id=%s::uuid LIMIT 1",
                (tenant_id,),
            )
            if row:
                return float(row["max_claim_amount"])
        except Exception:
            pass
        return DEFAULT_PENALTY_CAP

    def _persist(
        self, tenant_id: str, source_record_id: str,
        status: str, violations: list[RuleViolation], shipment_reference: str,
    ) -> str | None:
        result_id = str(uuid.uuid4())
        try:
            import json as _json
            from shared.db import q as _q
            import psycopg2, psycopg2.extras
            psycopg2.extras.register_uuid()

            # validation_results
            _q("""
                INSERT INTO validation_results
                    (id, tenant_id, source_record_id, rule_set_id, overall_status,
                     rule_violations, created_at)
                VALUES
                    (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, NOW())
                ON CONFLICT DO NOTHING
            """, (
                result_id, tenant_id, source_record_id,
                str(uuid.uuid4()),  # rule_set_id placeholder
                status,
                _json.dumps([{"rule": v.rule, "severity": v.severity, "message": v.message}
                              for v in violations]),
            ))

            # source_records validation_status
            _q("UPDATE source_records SET validation_status=%s WHERE id=%s::uuid AND tenant_id=%s::uuid",
               (status, source_record_id, tenant_id))

            # source_record_states (append-only)
            _q("""
                INSERT INTO source_record_states
                    (id, tenant_id, source_record_id, state, metadata, created_at)
                VALUES
                    (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, NOW())
            """, (
                str(uuid.uuid4()), tenant_id, source_record_id,
                "VALIDATED",
                _json.dumps({"validation_result_id": result_id,
                             "shipment_reference": shipment_reference,
                             "status": status}),
            ))
        except Exception:
            pass
        return result_id

    def _publish(self, tenant_id: str, source_record_id: str, status: str) -> None:
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic="zoiko.source.record.validated",
                key=source_record_id,
                payload={"source_record_id": source_record_id, "status": status},
                tenant_id=tenant_id,
            ))
        except Exception:
            pass
