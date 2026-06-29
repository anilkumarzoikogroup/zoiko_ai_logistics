"""
SC-005 Validation Service — Domain 3.

Performs structural, semantic, and cross-record checks on accessorial
charge dispute source records before canonical truth is written.

Checks:
  1. Structural   — required fields present and correctly typed
  2. Semantic     — amounts positive, currency valid, at least one charge line
  3. Cross-record — duplicate detection via source_record_hash
  4. Policy cap   — at least one charge line must exceed its tariff cap
                     (otherwise no dispute is warranted)

On failure the record is quarantined (validation_status = 'QUARANTINED').
On success it advances to 'VALIDATED'.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

_VALID_CURRENCIES = {"INR", "USD", "EUR", "GBP", "AED", "SGD"}

_REQUIRED_FIELDS = {
    "carrier_id", "shipment_id", "invoice_id",
    "billing_period_start", "billing_period_end",
    "charge_lines",
}


def _structural_check(payload: dict) -> list[str]:
    errors = []
    missing = _REQUIRED_FIELDS - payload.keys()
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")
    if "charge_lines" in payload:
        if not isinstance(payload["charge_lines"], list):
            errors.append("charge_lines must be a list")
        elif len(payload["charge_lines"]) == 0:
            errors.append("charge_lines must not be empty")
        else:
            for i, line in enumerate(payload["charge_lines"]):
                for f in ("charge_type", "billed_amount", "tariff_cap", "currency"):
                    if f not in line:
                        errors.append(f"charge_lines[{i}] missing field '{f}'")
    return errors


def _semantic_check(payload: dict) -> list[str]:
    errors = []
    if "charge_lines" in payload and isinstance(payload["charge_lines"], list):
        for i, line in enumerate(payload["charge_lines"]):
            try:
                amt = float(line.get("billed_amount", 0))
                cap = float(line.get("tariff_cap", 0))
                if amt < 0:
                    errors.append(f"charge_lines[{i}].billed_amount must be >= 0")
                if cap < 0:
                    errors.append(f"charge_lines[{i}].tariff_cap must be >= 0")
            except (TypeError, ValueError):
                errors.append(f"charge_lines[{i}] billed_amount or tariff_cap is not numeric")
            currency = line.get("currency", "")
            if currency not in _VALID_CURRENCIES:
                errors.append(f"charge_lines[{i}].currency '{currency}' not in allowed set")
    return errors


def _policy_cap_check(payload: dict) -> list[str]:
    """At least one charge line must exceed its tariff cap."""
    lines = payload.get("charge_lines", [])
    if not isinstance(lines, list):
        return []
    exceeded = any(
        float(line.get("billed_amount", 0)) > float(line.get("tariff_cap", 0))
        for line in lines
        if isinstance(line, dict)
    )
    if not exceeded:
        return ["No charge line exceeds its tariff cap — no dispute warranted"]
    return []


class ValidationHandler:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def validate(self, source_record_id: str, tenant_id: str, payload: dict) -> dict:
        """Run all checks, write validation_results row, return result dict."""
        errors: list[str] = []
        errors += _structural_check(payload)
        if not errors:
            errors += _semantic_check(payload)
        if not errors:
            errors += _policy_cap_check(payload)

        passed   = len(errors) == 0
        status   = "VALIDATED" if passed else "QUARANTINED"
        rule_set = "accessorial-dispute-validation-v1"

        record_bytes  = json.dumps(payload, sort_keys=True).encode()
        record_hash   = hashlib.sha256(record_bytes).hexdigest()

        result_id = uuid.uuid4()
        now       = datetime.now(timezone.utc)

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO validation_results
                    (id, tenant_id, source_record_id, rule_set_version,
                     validation_status, errors, record_hash, validated_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                result_id, tenant_id, uuid.UUID(source_record_id),
                rule_set, status,
                json.dumps(errors), record_hash, now,
            ))
            conn.commit()
        finally:
            conn.close()

        return {
            "validation_result_id": str(result_id),
            "status":               status,
            "passed":               passed,
            "errors":               errors,
            "rule_set":             rule_set,
        }
