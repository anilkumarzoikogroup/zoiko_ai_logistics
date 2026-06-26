"""
Validation Service — Tier-0 spec §12.

Validation pipeline:
  1. Load ACTIVE versioned rule set for source_type        (§12.5)
  2. Structural validation — is the record well-formed?    (§12.2)
  3. Semantic validation — do values make sense?           (§12.3)
  4. Cross-record validation — does it agree with DB state?(§12.4)
  5. Contract rate check (original overcharge detection)
  6. Produce validation_result with rule_set_id + version  (§12.5)
  7. Advance source_record validation_status               (§21)
  8. Quarantine or reject on failure; update source record  (§13)

Every validation_result records the rule_set_id and rule_set_version so
that validation can be replayed later with the archived rule set.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone, date

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from services.validation_svc.models import ValidationResult, RateViolation

VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "CNY", "AUD", "CAD",
    "SGD", "AED", "MYR", "THB", "IDR", "VND", "PHP",
}


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
        currency: str = "INR",
        event_date: date = None,
    ) -> ValidationResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))
        # as_of_event: use the invoice's own date so replay returns the same
        # contract rates that were active when the invoice was received, not
        # today's rates. Falls back to today only if no event_date is provided.
        as_of = event_date or date.today()

        conn = psycopg2.connect(self.db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── 1. Load active rule set ────────────────────────────────────────
        rule_set_id, rule_set_version, rules = _load_active_rule_set(cur, "INVOICE")

        # ── 2. Structural validation ───────────────────────────────────────
        structural_violations = _structural_validate(
            invoice_number=invoice_number,
            carrier_id=carrier_id,
            total_amount=total_amount,
            currency=currency,
        )

        # ── 3. Semantic validation ─────────────────────────────────────────
        semantic_violations = _semantic_validate(
            currency=currency,
            total_amount=total_amount,
            carrier_id=carrier_id,
        )

        # ── 4. Cross-record validation ─────────────────────────────────────
        cross_violations = _cross_record_validate(cur, tenant_id, invoice_number, carrier_id, currency)

        # ── 5. Contract rate check (original overcharge detection) ─────────
        lane_hash = "sha256:" + hashlib.sha256(
            ("zoiko/v1/lane:" + carrier_id + "|" + currency).encode()
        ).hexdigest()

        cur.execute("""
            SELECT id, carrier_id, rate_type, COALESCE(base_rate, rate_value) AS rate_value,
                   currency, effective_on, expires_on, payload_hash
            FROM   contract_rates
            WHERE  tenant_id = %s
              AND  lane_hash = %s
              AND  superseded_at IS NULL
              AND  COALESCE(effective_from, effective_on) <= %s
              AND  (COALESCE(effective_to, expires_on) IS NULL
                    OR COALESCE(effective_to, expires_on) >= %s)
        """, (tenant_id, lane_hash, as_of, as_of))
        rates = cur.fetchall()

        if not rates:
            cur.execute("""
                SELECT id, carrier_id, rate_type, rate_value, currency,
                       effective_on, expires_on, payload_hash
                FROM   contract_rates
                WHERE  tenant_id  = %s
                  AND  carrier_id = %s
                  AND  superseded_at IS NULL
                  AND  effective_on <= %s
                  AND  (expires_on IS NULL OR expires_on >= %s)
            """, (tenant_id, carrier_id, as_of, as_of))
            rates = cur.fetchall()

        conn.close()

        # Rate version binding — detect a direct DB mutation. Recompute the
        # content hash from what's in the row right now and compare against
        # payload_hash, which was pinned at creation time (POST /contract-rates).
        # A mismatch means the row's monetary fields were changed by something
        # other than the API after creation — fail closed rather than silently
        # trusting a contract rate that may have been tampered with.
        for r in rates:
            if not r.get("payload_hash"):
                continue  # pre-existing row created before this column was wired up
            expected_hash = "sha256:" + hashlib.sha256(
                f"zoiko.contract_rate.v1:{tenant_id}:{r['carrier_id']}:{r['rate_type']}:"
                f"{float(r['rate_value']):.4f}:{r['currency']}:{r['effective_on']}:{r['expires_on'] or ''}".encode()
            ).hexdigest()
            if expected_hash != r["payload_hash"]:
                raise ValueError(
                    f"Contract rate '{r['id']}' (carrier={r['carrier_id']}, "
                    f"type={r['rate_type']}) failed integrity check — its payload_hash "
                    f"no longer matches its content. This rate may have been mutated "
                    f"directly in the database, bypassing the contract-rates API."
                )

        # Witness pack — pin the exact rate content actually used right now,
        # independent of the live row. If the rate is later legitimately
        # superseded (a new version), this snapshot still proves exactly
        # what was relied upon at this moment. Best-effort: must never block
        # validation if it fails.
        for r in rates:
            try:
                from services.witness_pack_svc.handler import WitnessPackHandler
                WitnessPackHandler(self.db_url, self.tenant_slug).create(
                    tenant_id=tenant_id,
                    source_record_id=str(source_record_id),
                    subject_type="CONTRACT_RATE",
                    subject_id=str(r["id"]),
                    snapshot_payload={
                        "carrier_id":   r["carrier_id"],
                        "rate_type":    r["rate_type"],
                        "rate_value":   f"{float(r['rate_value']):.4f}",
                        "currency":     r["currency"],
                        "effective_on": str(r["effective_on"]),
                        "expires_on":   str(r["expires_on"]) if r["expires_on"] else None,
                        "payload_hash": r.get("payload_hash"),
                    },
                )
            except Exception:
                pass

        rate_violations: list[RateViolation] = []
        expected_total  = 0.0
        status          = "PASS"

        if not rates:
            rate_violations.append(RateViolation(
                rule="R003_NO_CONTRACT_RATE",
                carrier_id=carrier_id,
                rate_type="*",
                expected=0.0,
                actual=float(total_amount),
                delta=float(total_amount),
            ))
            status = "WARN"
        else:
            expected_total = sum(float(r["rate_value"]) for r in rates)
            if total_amount > expected_total + 0.005:
                delta = round(float(total_amount) - expected_total, 4)
                for r in rates:
                    if float(total_amount) > float(r["rate_value"]) + 0.005:
                        rate_violations.append(RateViolation(
                            rule="R001_CARRIER_RATE_EXCEEDED",
                            carrier_id=carrier_id,
                            rate_type=r["rate_type"],
                            expected=float(r["rate_value"]),
                            actual=float(total_amount),
                            delta=delta,
                        ))
                        break
                status = "FAIL"

        overcharge = max(0.0, round(float(total_amount) - expected_total, 4)) if rates else float(total_amount)

        # Collect all violations
        all_violations = structural_violations + semantic_violations + cross_violations + rate_violations

        # Structural failures → REJECTED; semantic/cross failures → status FAIL (quarantinable)
        if structural_violations:
            final_status = "FAIL"  # Hard structural failure
        else:
            final_status = status if not (semantic_violations or cross_violations) else "FAIL"

        # ── 6. Sign the result ─────────────────────────────────────────────
        result_blob = json.dumps({
            "source_record_id": str(source_record_id),
            "status":           final_status,
            "total_amount":     float(total_amount),
            "expected_total":   expected_total,
            "rule_set_id":      rule_set_id,
            "rule_set_version": rule_set_version,
        }, sort_keys=True).encode()
        result_hash = hashlib.sha256(b"zoiko.validation.result.v1:" + result_blob).digest()
        signature, kid = sign(self.tenant_slug, result_hash)

        violations_json = json.dumps([
            {"rule": v.rule, "carrier_id": v.carrier_id, "rate_type": v.rate_type,
             "expected": v.expected, "actual": v.actual, "delta": v.delta}
            for v in all_violations
        ])

        val_id = uuid.uuid4()
        now    = datetime.now(timezone.utc)

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO validation_results
                    (id, tenant_id, source_record_id, status, rule_violations,
                     signature, kid, validated_at,
                     rule_set_id, rule_set_version, validation_service_version)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            """, (
                val_id, tenant_id, source_record_id,
                final_status, violations_json,
                signature, kid, now,
                rule_set_id, rule_set_version, "2.0.0",
            ))

            # Determine new validation_status for the source record
            if structural_violations:
                new_vstatus = "REJECTED"
                new_rstatus = "REJECTED"
            elif final_status == "FAIL" and (semantic_violations or cross_violations):
                new_vstatus = "QUARANTINED"
                new_rstatus = "QUARANTINED"
            else:
                new_vstatus = "VALIDATED"
                new_rstatus = "VALIDATED"

            # Update source_record validation_status + validation_result_id
            cur.execute("""
                UPDATE source_records
                SET validation_status = %s,
                    validation_result_id = %s,
                    record_status = %s
                WHERE id = %s AND tenant_id = %s
            """, (new_vstatus, val_id, new_rstatus, source_record_id, tenant_id))

            # Write FSM transition to source_record_states
            cur.execute("""
                INSERT INTO source_record_states
                    (id, tenant_id, source_record_id, from_status, to_status, actor, detail, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4(), tenant_id, source_record_id,
                "PENDING_VALIDATION", new_rstatus,
                "spiffe://zoiko/system/validation",
                json.dumps({"rule_set_id": rule_set_id, "rule_set_version": rule_set_version,
                            "violations": len(all_violations)}),
                now,
            ))

            # If quarantined, write to quarantine_items
            if new_vstatus == "QUARANTINED":
                cur.execute("""
                    INSERT INTO quarantine_items
                        (id, tenant_id, source_record_id, reason, quarantined_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    uuid.uuid4(), tenant_id, source_record_id,
                    "; ".join(v.rule for v in (semantic_violations + cross_violations)),
                    now,
                ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Publish validation event
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "zoiko.source.record.validated",
                key       = str(source_record_id),
                payload   = {
                    "invoice_number":    invoice_number,
                    "status":            final_status,
                    "overcharge_amount": overcharge,
                    "currency":          currency,
                    "violations":        len(all_violations),
                    "rule_set_id":       rule_set_id,
                    "rule_set_version":  rule_set_version,
                },
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return ValidationResult(
            validation_id     = val_id,
            source_record_id  = source_record_id,
            tenant_id         = tenant_id,
            status            = final_status,
            rule_violations   = all_violations,
            overcharge_amount = overcharge,
            currency          = currency,
        )


# ── Rule set loader ────────────────────────────────────────────────────────────

def _load_active_rule_set(cur, source_type: str) -> tuple[str, str, list]:
    """Load the ACTIVE rule set for this source_type. Returns (id, version, rules)."""
    cur.execute("""
        SELECT rule_set_id, version, rules
        FROM validation_rule_sets
        WHERE source_type = %s AND status = 'ACTIVE'
        ORDER BY activated_at DESC
        LIMIT 1
    """, (source_type,))
    row = cur.fetchone()
    if row:
        rules = row["rules"] if isinstance(row["rules"], list) else []
        return row["rule_set_id"], row["version"], rules
    # Fallback when no rule set exists (e.g., on a fresh DB before migration 0020 seed)
    return "carrier_invoice_validation", "v1.0.0", []


# ── Structural validation (§12.2) ─────────────────────────────────────────────

def _structural_validate(invoice_number, carrier_id, total_amount, currency) -> list[RateViolation]:
    violations = []
    if not invoice_number or not invoice_number.strip():
        violations.append(RateViolation(
            rule="STRUCT_MISSING_INVOICE_NUMBER", carrier_id=carrier_id,
            rate_type="", expected=0, actual=0, delta=0,
        ))
    if not carrier_id or not carrier_id.strip():
        violations.append(RateViolation(
            rule="STRUCT_MISSING_CARRIER_ID", carrier_id="",
            rate_type="", expected=0, actual=0, delta=0,
        ))
    if total_amount is None:
        violations.append(RateViolation(
            rule="STRUCT_MISSING_AMOUNT", carrier_id=carrier_id,
            rate_type="", expected=0, actual=0, delta=0,
        ))
    if not currency or not currency.strip():
        violations.append(RateViolation(
            rule="STRUCT_MISSING_CURRENCY", carrier_id=carrier_id,
            rate_type="", expected=0, actual=0, delta=0,
        ))
    return violations


# ── Semantic validation (§12.3) ───────────────────────────────────────────────

def _semantic_validate(currency, total_amount, carrier_id) -> list[RateViolation]:
    violations = []
    if currency and currency.upper() not in VALID_CURRENCIES:
        violations.append(RateViolation(
            rule="R002_INVALID_CURRENCY", carrier_id=carrier_id,
            rate_type="", expected=0, actual=0, delta=0,
        ))
    if total_amount is not None and float(total_amount) < 0:
        violations.append(RateViolation(
            rule="R004_NEGATIVE_AMOUNT", carrier_id=carrier_id,
            rate_type="", expected=0, actual=float(total_amount), delta=float(total_amount),
        ))
    return violations


# ── Cross-record validation (§12.4) ───────────────────────────────────────────

def _cross_record_validate(cur, tenant_id, invoice_number, carrier_id, currency) -> list[RateViolation]:
    violations = []
    # Check for duplicate canonical invoice (already finalised)
    cur.execute("""
        SELECT id FROM canonical_invoices
        WHERE tenant_id = %s AND invoice_number = %s
        LIMIT 1
    """, (tenant_id, invoice_number))
    if cur.fetchone():
        violations.append(RateViolation(
            rule="CROSS_DUPLICATE_CANONICAL_INVOICE", carrier_id=carrier_id,
            rate_type="", expected=0, actual=0, delta=0,
        ))
    return violations
