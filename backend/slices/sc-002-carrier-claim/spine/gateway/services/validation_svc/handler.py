"""
SC-002 — Claim Validation Service

Validates a carrier claim source record before it advances to canonical truth.
Mirrors sc-001's ValidationHandler structure but applies claim-specific rules:

  1. Structural validation  — required fields present?
  2. Semantic validation    — values make sense?
  3. Cross-record validation — no duplicate canonical claim?
  4. Claim-specific rules   — amount within policy cap, claim_type allowed?

Writes a validation_result row and advances source_record validation_status.
Publishes zoiko.source.record.validated Kafka event.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras

from shared.signer import sign

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "CNY", "AUD", "CAD",
    "SGD", "AED", "MYR", "THB", "IDR", "VND", "PHP",
}

VALID_CLAIM_TYPES = {"OVERCHARGE", "LOSS", "DAMAGE", "DELAY", "SHORT_DELIVERY", "OTHER"}

# Default policy cap: claims above this trigger a WARN (not a hard FAIL).
# In production, resolved per-tenant from claim_policy_caps table.
DEFAULT_POLICY_CAP = 500_000.00


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class ClaimViolation:
    rule:       str
    carrier_id: str
    field:      str
    expected:   str
    actual:     str
    delta:      float = 0.0


@dataclass
class ClaimValidationResult:
    validation_id:    uuid.UUID
    source_record_id: uuid.UUID
    tenant_id:        str
    status:           str              # PASS | FAIL | WARN
    rule_violations:  list[ClaimViolation] = field(default_factory=list)
    currency:         str = "USD"


# ── Handler ───────────────────────────────────────────────────────────────────

class ClaimValidationHandler:
    """Validates a carrier claim source record. Thread-safe — stateless after __init__."""

    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def validate(
        self,
        tenant_id:        str,
        source_record_id: uuid.UUID,
        carrier_id:       str,
        claim_reference:  str,
        claim_type:       str,
        claimed_amount:   float,
        currency:         str,
    ) -> ClaimValidationResult:
        tenant_id        = str(tenant_id)
        source_record_id = uuid.UUID(str(source_record_id))

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        conn.autocommit = True
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── 1. Load active rule set (or fall back to defaults) ─────────────
        rule_set_id, rule_set_version = _load_claim_rule_set(cur)

        # ── 2. Structural validation ───────────────────────────────────────
        structural = _structural_validate(carrier_id, claim_reference, claim_type, claimed_amount, currency)

        # ── 3. Semantic validation ─────────────────────────────────────────
        semantic   = _semantic_validate(carrier_id, claim_type, claimed_amount, currency)

        # ── 4. Cross-record validation ─────────────────────────────────────
        cross      = _cross_record_validate(cur, tenant_id, claim_reference, carrier_id)

        # ── 5. Claim-specific rule — policy cap ────────────────────────────
        policy_cap = _resolve_policy_cap(cur, tenant_id)
        policy     = _policy_validate(carrier_id, claimed_amount, currency, policy_cap)

        conn.close()

        all_violations = structural + semantic + cross + policy

        if structural:
            final_status = "FAIL"
        elif semantic or cross:
            final_status = "FAIL"
        elif policy:
            final_status = "WARN"   # over cap: warn, don't block
        else:
            final_status = "PASS"

        # ── 6. Sign the result ─────────────────────────────────────────────
        result_blob = json.dumps({
            "source_record_id": str(source_record_id),
            "status":           final_status,
            "claimed_amount":   float(claimed_amount),
            "currency":         currency,
            "rule_set_id":      rule_set_id,
            "rule_set_version": rule_set_version,
        }, sort_keys=True).encode()
        result_hash = hashlib.sha256(b"zoiko.validation.result.v1:" + result_blob).digest()
        signature, kid = sign(self.tenant_slug, result_hash)

        violations_json = json.dumps([
            {"rule": v.rule, "carrier_id": v.carrier_id, "field": v.field,
             "expected": v.expected, "actual": v.actual, "delta": v.delta}
            for v in all_violations
        ])

        val_id = uuid.uuid4()
        now    = datetime.now(timezone.utc)

        # ── 7. Persist validation_result + advance source_record ───────────
        conn2 = psycopg2.connect(self.db_url)
        try:
            cur2 = conn2.cursor()

            cur2.execute("""
                INSERT INTO validation_results
                    (id, tenant_id, source_record_id, status, rule_violations,
                     signature, kid, validated_at,
                     rule_set_id, rule_set_version, validation_service_version)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                val_id, tenant_id, source_record_id,
                final_status, violations_json,
                signature, kid, now,
                rule_set_id, rule_set_version, "sc002.1.0.0",
            ))

            new_vstatus = "VALIDATED" if final_status in ("PASS", "WARN") else "REJECTED"
            new_rstatus = new_vstatus

            cur2.execute("""
                UPDATE source_records
                SET validation_status = %s,
                    validation_result_id = %s,
                    record_status = %s
                WHERE id = %s AND tenant_id = %s
            """, (new_vstatus, val_id, new_rstatus, source_record_id, tenant_id))

            cur2.execute("""
                INSERT INTO source_record_states
                    (id, tenant_id, source_record_id, from_status, to_status, actor, detail, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                uuid.uuid4(), tenant_id, source_record_id,
                "PENDING_VALIDATION", new_rstatus,
                "spiffe://zoiko/sc002/validation",
                json.dumps({"rule_set_id": rule_set_id, "violations": len(all_violations)}),
                now,
            ))

            conn2.commit()
        except Exception:
            conn2.rollback()
            raise
        finally:
            conn2.close()

        # ── 8. Kafka ───────────────────────────────────────────────────────
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self.broker).publish(KafkaMessage(
                topic     = "zoiko.source.record.validated",
                key       = str(source_record_id),
                payload   = {
                    "claim_reference": claim_reference,
                    "status":          final_status,
                    "violations":      len(all_violations),
                    "currency":        currency,
                    "rule_set_id":     rule_set_id,
                },
                tenant_id = tenant_id,
            ))
        except Exception:
            pass

        return ClaimValidationResult(
            validation_id    = val_id,
            source_record_id = source_record_id,
            tenant_id        = tenant_id,
            status           = final_status,
            rule_violations  = all_violations,
            currency         = currency,
        )


# ── Rule set loader ────────────────────────────────────────────────────────────

def _load_claim_rule_set(cur) -> tuple[str, str]:
    try:
        cur.execute("""
            SELECT rule_set_id, version FROM validation_rule_sets
            WHERE source_type = 'CLAIM' AND status = 'ACTIVE'
            ORDER BY activated_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            return row["rule_set_id"], row["version"]
    except Exception:
        pass
    return "carrier_claim_validation", "v1.0.0"


# ── Structural validation ──────────────────────────────────────────────────────

def _structural_validate(
    carrier_id, claim_reference, claim_type, claimed_amount, currency
) -> list[ClaimViolation]:
    v = []
    if not carrier_id or not str(carrier_id).strip():
        v.append(ClaimViolation("STRUCT_MISSING_CARRIER_ID", "", "carrier_id", "non-empty", "", 0))
    if not claim_reference or not str(claim_reference).strip():
        v.append(ClaimViolation("STRUCT_MISSING_CLAIM_REFERENCE", carrier_id or "", "claim_reference", "non-empty", "", 0))
    if not claim_type or not str(claim_type).strip():
        v.append(ClaimViolation("STRUCT_MISSING_CLAIM_TYPE", carrier_id or "", "claim_type", "non-empty", "", 0))
    if claimed_amount is None:
        v.append(ClaimViolation("STRUCT_MISSING_AMOUNT", carrier_id or "", "claimed_amount", "numeric", "null", 0))
    if not currency or not str(currency).strip():
        v.append(ClaimViolation("STRUCT_MISSING_CURRENCY", carrier_id or "", "currency", "non-empty", "", 0))
    return v


# ── Semantic validation ────────────────────────────────────────────────────────

def _semantic_validate(
    carrier_id, claim_type, claimed_amount, currency
) -> list[ClaimViolation]:
    v = []
    if currency and currency.upper() not in VALID_CURRENCIES:
        v.append(ClaimViolation("SEM_INVALID_CURRENCY", carrier_id or "", "currency",
                                f"one of {sorted(VALID_CURRENCIES)}", currency, 0))
    if claimed_amount is not None and float(claimed_amount) < 0:
        v.append(ClaimViolation("SEM_NEGATIVE_AMOUNT", carrier_id or "", "claimed_amount",
                                ">= 0", str(claimed_amount), float(claimed_amount)))
    if claim_type and claim_type.upper() not in VALID_CLAIM_TYPES:
        v.append(ClaimViolation("SEM_INVALID_CLAIM_TYPE", carrier_id or "", "claim_type",
                                f"one of {sorted(VALID_CLAIM_TYPES)}", claim_type, 0))
    return v


# ── Cross-record validation ────────────────────────────────────────────────────

def _cross_record_validate(cur, tenant_id, claim_reference, carrier_id) -> list[ClaimViolation]:
    v = []
    try:
        cur.execute("""
            SELECT id FROM claims
            WHERE tenant_id = %s AND claim_reference = %s AND status != 'REJECTED'
            LIMIT 1
        """, (tenant_id, claim_reference))
        if cur.fetchone():
            v.append(ClaimViolation("CROSS_DUPLICATE_CLAIM_REFERENCE", carrier_id or "",
                                    "claim_reference", "unique", claim_reference, 0))
    except Exception:
        pass
    return v


# ── Claim-specific: policy cap ────────────────────────────────────────────────

def _resolve_policy_cap(cur, tenant_id: str) -> float:
    try:
        cur.execute("""
            SELECT max_claim_amount FROM claim_policy_caps
            WHERE tenant_id = %s AND is_active = true
            ORDER BY effective_from DESC LIMIT 1
        """, (tenant_id,))
        row = cur.fetchone()
        if row and row["max_claim_amount"]:
            return float(row["max_claim_amount"])
    except Exception:
        pass
    return DEFAULT_POLICY_CAP


def _policy_validate(carrier_id, claimed_amount, currency, policy_cap) -> list[ClaimViolation]:
    v = []
    if claimed_amount is not None and float(claimed_amount) > policy_cap:
        v.append(ClaimViolation(
            "POLICY_CAP_EXCEEDED", carrier_id or "", "claimed_amount",
            f"<= {policy_cap:.2f}", f"{float(claimed_amount):.2f}",
            float(claimed_amount) - policy_cap,
        ))
    return v
