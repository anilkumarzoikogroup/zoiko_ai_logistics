import paths  # noqa: F401 — sys.path bootstrap, must be first
import uuid
import json
from datetime import datetime, timezone

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL


class ReconciliationHandler:
    """SC-005 Accessorial Dispute — PARTIAL_ACCEPTANCE reconciliation strategy.

    Three-way split:
      accepted_amount    — sum of capped (contracted_cap) portions across all lines
      disputed_amount    — sum of excess over cap (billed_amount - contracted_cap per line)
      written_off_amount — currently always 0.0; reserved for future write-off logic
    """

    def __init__(self, db_url=None, broker=None):
        self.db_url = db_url or _DEFAULT_DB_URL
        self.broker = broker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile(
        self,
        tenant_id: str,
        case_id: str,
        envelope_id: str,
        actor_sub: str,
    ) -> dict:
        """Run PARTIAL_ACCEPTANCE reconciliation for an SC-005 case.

        Returns a dict with keys:
            status, reconciliation_id, outcome_id, strategy,
            accepted_amount, disputed_amount, written_off_amount, variance_count
        """

        now = datetime.now(timezone.utc)

        # ----------------------------------------------------------------
        # 1. Fetch canonical invoice data for this case
        # ----------------------------------------------------------------
        ci_row = q1(
            """
            SELECT ci.carrier_id,
                   ci.invoice_number,
                   ci.total_amount AS dispute_total,
                   ci.currency
            FROM   canonical_invoices ci
            JOIN   cases c
                   ON  c.id          = %s::uuid
                   AND c.tenant_id   = %s::uuid
                   AND ci.id         = c.invoice_id
            LIMIT  1
            """,
            (case_id, tenant_id),
            db_url=self.db_url,
        )

        # ----------------------------------------------------------------
        # 2. Fetch per-line accessorial charges to compute 3-way split
        # ----------------------------------------------------------------
        charge_rows = q(
            """
            SELECT billed_amount, contracted_cap
            FROM   accessorial_charges
            WHERE  case_id   = %s::uuid
              AND  tenant_id = %s::uuid
            """,
            (case_id, tenant_id),
            db_url=self.db_url,
        )

        if charge_rows:
            accepted_amount = sum(
                float(min(row["billed_amount"], row["contracted_cap"]))
                for row in charge_rows
            )
            disputed_amount = sum(
                float(max(0, row["billed_amount"] - row["contracted_cap"]))
                for row in charge_rows
            )
        else:
            # No granular charge rows — fall back to treating full invoice as disputed
            accepted_amount = 0.0
            disputed_amount = float(ci_row["dispute_total"]) if ci_row else 0.0

        written_off_amount = 0.0

        summary = {
            "strategy": "PARTIAL_ACCEPTANCE",
            "accepted_amount": accepted_amount,
            "disputed_amount": disputed_amount,
            "written_off_amount": written_off_amount,
            "total_billed": accepted_amount + disputed_amount,
        }

        # ----------------------------------------------------------------
        # 3. Insert reconciliation record
        # ----------------------------------------------------------------
        recon_id = uuid.uuid4()
        q(
            """
            INSERT INTO reconciliations
                (id, tenant_id, case_id, envelope_id, strategy, summary, status, actor_sub, created_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(recon_id),
                str(tenant_id),
                str(case_id),
                str(envelope_id),
                "PARTIAL_ACCEPTANCE",
                json.dumps(summary),
                "COMPLETED",
                actor_sub,
                now,
            ),
            db_url=self.db_url,
        )

        # ----------------------------------------------------------------
        # 4. Insert outcome record
        # ----------------------------------------------------------------
        outcome_id = uuid.uuid4()
        outcome_type = "PARTIAL_CREDIT_ISSUED" if disputed_amount > 0 else "NO_DISPUTE"
        q(
            """
            INSERT INTO outcomes
                (id, tenant_id, case_id, reconciliation_id, outcome_type, details, status, actor_sub, created_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                str(outcome_id),
                str(tenant_id),
                str(case_id),
                str(recon_id),
                outcome_type,
                json.dumps(summary),
                "FINAL",
                actor_sub,
                now,
            ),
            db_url=self.db_url,
        )

        # ----------------------------------------------------------------
        # 5. Write variance if disputed_amount > 0
        # ----------------------------------------------------------------
        variance_count = 0
        if disputed_amount > 0:
            variance_id = uuid.uuid4()
            q(
                """
                INSERT INTO reconciliation_variances
                    (id, tenant_id, case_id, reconciliation_id,
                     variance_type, expected_value, actual_value, delta,
                     status, actor_sub, created_at)
                VALUES
                    (%s::uuid, %s::uuid, %s::uuid, %s::uuid,
                     %s, %s, %s, %s,
                     %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(variance_id),
                    str(tenant_id),
                    str(case_id),
                    str(recon_id),
                    "ACCESSORIAL_OVERCHARGE",
                    str(accepted_amount),                        # what the cap allows
                    str(accepted_amount + disputed_amount),      # what was billed
                    str(disputed_amount),                        # excess
                    "OPEN",
                    actor_sub,
                    now,
                ),
                db_url=self.db_url,
            )
            variance_count = 1

        # ----------------------------------------------------------------
        # 6. Advance case FSM: → OUTCOME_RECORDED
        # ----------------------------------------------------------------
        q(
            """
            UPDATE cases
            SET    state = 'OUTCOME_RECORDED'
            WHERE  id        = %s::uuid
              AND  tenant_id = %s::uuid
            """,
            (str(case_id), str(tenant_id)),
            db_url=self.db_url,
        )

        # Append-only case event (never UPDATE/DELETE this table)
        q(
            """
            INSERT INTO case_events
                (id, case_id, tenant_id, event_type, payload, actor_sub, created_at)
            VALUES
                (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                str(case_id),
                str(tenant_id),
                "STATE_TRANSITION",
                json.dumps({
                    "from": "DISPATCHED",
                    "to": "OUTCOME_RECORDED",
                    "strategy": "PARTIAL_ACCEPTANCE",
                }),
                actor_sub,
                now,
            ),
            db_url=self.db_url,
        )

        # ----------------------------------------------------------------
        # 7. Return result dict
        # ----------------------------------------------------------------
        return {
            "status": "RECONCILED",
            "reconciliation_id": str(recon_id),
            "outcome_id": str(outcome_id),
            "strategy": "PARTIAL_ACCEPTANCE",
            "accepted_amount": accepted_amount,
            "disputed_amount": disputed_amount,
            "written_off_amount": written_off_amount,
            "variance_count": variance_count,
        }
