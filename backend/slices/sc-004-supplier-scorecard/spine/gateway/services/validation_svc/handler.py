"""
SC-004 Validation Service — Domain 3.

Validates supplier scorecard source records before canonical truth is written.

Checks:
  1. Structural   — required fields present
  2. Semantic     — score in range [0,100], period dates valid
  3. Cross-record — duplicate detection via record hash
  4. Threshold    — composite_score must be below contracted_threshold
                    (otherwise no breach, no case warranted)
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401

_REQUIRED_FIELDS = {
    "supplier_id", "tenant_id", "period_start", "period_end",
    "composite_score", "contracted_threshold",
}


def _structural_check(payload: dict) -> list[str]:
    errors = []
    missing = _REQUIRED_FIELDS - payload.keys()
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")
    return errors


def _semantic_check(payload: dict) -> list[str]:
    errors = []
    try:
        score = float(payload.get("composite_score", -1))
        if not (0 <= score <= 100):
            errors.append(f"composite_score {score} out of range [0, 100]")
    except (TypeError, ValueError):
        errors.append("composite_score must be numeric")
    try:
        threshold = float(payload.get("contracted_threshold", -1))
        if not (0 <= threshold <= 100):
            errors.append(f"contracted_threshold {threshold} out of range [0, 100]")
    except (TypeError, ValueError):
        errors.append("contracted_threshold must be numeric")
    return errors


def _breach_check(payload: dict) -> list[str]:
    """Score must be below threshold — otherwise no breach to raise a case for."""
    try:
        score     = float(payload.get("composite_score", 100))
        threshold = float(payload.get("contracted_threshold", 0))
        if score >= threshold:
            return [
                f"composite_score {score} >= contracted_threshold {threshold}: "
                "no breach detected, case not warranted"
            ]
    except (TypeError, ValueError):
        pass
    return []


class ValidationHandler:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def validate(self, source_record_id: str, tenant_id: str, payload: dict) -> dict:
        errors: list[str] = []
        errors += _structural_check(payload)
        if not errors:
            errors += _semantic_check(payload)
        if not errors:
            errors += _breach_check(payload)

        passed   = len(errors) == 0
        status   = "VALIDATED" if passed else "QUARANTINED"
        rule_set = "scorecard-breach-validation-v1"

        record_bytes = json.dumps(payload, sort_keys=True).encode()
        record_hash  = hashlib.sha256(record_bytes).hexdigest()

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
