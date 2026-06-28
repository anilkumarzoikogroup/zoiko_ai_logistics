import paths  # noqa: F401
import uuid
from datetime import datetime, timezone
import json

from shared.db import q, q1, DB_URL


class CaseHandler:
    def __init__(self, db_url: str = DB_URL):
        self._db_url = db_url

    def open_case(
        self,
        tenant_id: str,
        canonical_invoice_id: str,
        carrier_id: str,
        dispute_total: float,
        currency: str,
    ) -> dict:
        case_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        q(
            """
            INSERT INTO cases (id, tenant_id, case_type, state, invoice_id, opened_at)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s::uuid, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(case_id),
                str(tenant_id),
                "ACCESSORIAL_DISPUTE",
                "FINDING_GENERATED",
                str(canonical_invoice_id),
                now,
            ),
            self._db_url,
        )

        # ON CONFLICT DO NOTHING silently skips if (tenant_id, invoice_id) already exists.
        # Fetch the actual persisted case_id so subsequent inserts use the correct FK.
        existing_case = q1(
            """
            SELECT id, state FROM cases
            WHERE tenant_id = %s::uuid AND invoice_id = %s::uuid
              AND case_type = 'ACCESSORIAL_DISPUTE'
            LIMIT 1
            """,
            (str(tenant_id), str(canonical_invoice_id)),
            self._db_url,
        )
        actual_case_id = str(existing_case["id"]) if existing_case else str(case_id)
        state = existing_case["state"] if existing_case else "FINDING_GENERATED"

        # Only insert CASE_OPENED event if we just created the case (not a duplicate)
        is_new = (actual_case_id == str(case_id))
        if is_new:
            q(
                """
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    str(tenant_id),
                    actual_case_id,
                    "CASE_OPENED",
                    "NEW",
                    "FINDING_GENERATED",
                    "system",
                    json.dumps(
                        {
                            "carrier_id": carrier_id,
                            "dispute_total": dispute_total,
                            "currency": currency,
                        }
                    ),
                    now,
                ),
                self._db_url,
            )

        return {
            "case_id": actual_case_id,
            "state": state,
            "carrier_id": carrier_id,
            "dispute_total": dispute_total,
            "is_new": is_new,
        }
