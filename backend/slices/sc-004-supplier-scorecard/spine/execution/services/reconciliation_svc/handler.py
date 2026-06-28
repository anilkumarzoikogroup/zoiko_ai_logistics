"""
SC-004 Reconciliation — SCORE_OUTCOME strategy.

Compares `composite_score` from scorecard_periods against the breach threshold.
Writes reconciliation + outcome + variance if the score deviates from expectation.
"""
import uuid
import json
from datetime import datetime, timezone

import paths  # noqa: F401

from shared.db import q, q1, DB_URL as _DEFAULT_DB_URL


class ReconciliationHandler:

    def __init__(self, db_url: str | None = None, broker=None):
        self._db_url = db_url or _DEFAULT_DB_URL
        self._broker = broker

    def reconcile(
        self,
        tenant_id:   str,
        case_id:     str,
        envelope_id: str,
        actor_sub:   str,
    ) -> dict:
        sp = self._fetch_scorecard(tenant_id, case_id)
        if not sp:
            return {"status": "ERROR", "detail": f"No scorecard period found for case {case_id}"}

        recon_id    = self._write_reconciliation(tenant_id, case_id, envelope_id, sp, actor_sub)
        outcome_id  = self._write_outcome(tenant_id, case_id, recon_id, sp, actor_sub)
        variances   = self._detect_variances(tenant_id, case_id, recon_id, sp, actor_sub)
        self._advance_case(tenant_id, case_id, actor_sub)

        return {
            "status":          "RECONCILED",
            "reconciliation_id": str(recon_id),
            "outcome_id":      str(outcome_id),
            "variance_count":  len(variances),
            "variances":       variances,
            "strategy":        "SCORE_OUTCOME",
            "case_id":         case_id,
            "reconciled_at":   datetime.now(timezone.utc).isoformat(),
        }

    def _fetch_scorecard(self, tenant_id: str, case_id: str) -> dict | None:
        return q1(
            """SELECT sp.id, sp.carrier_id, sp.period_start, sp.period_end,
                      sp.composite_score, sp.contracted_threshold, sp.currency
               FROM scorecard_periods sp
               JOIN cases c ON c.id = sp.case_id
               WHERE c.id=%s::uuid AND c.tenant_id=%s::uuid
               LIMIT 1""",
            (case_id, tenant_id),
            db_url=self._db_url,
        )

    def _write_reconciliation(
        self, tenant_id: str, case_id: str, envelope_id: str, sp: dict, actor_sub: str
    ) -> uuid.UUID:
        recon_id = uuid.uuid4()
        summary  = {
            "strategy":        "SCORE_OUTCOME",
            "composite_score": float(sp["composite_score"] or 0),
            "breach_threshold": float(sp["contracted_threshold"] or 0),
        }
        q("""
            INSERT INTO reconciliations
                (id, tenant_id, case_id, envelope_id, strategy, summary, status, actor_sub, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, 'MATCHED', %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            recon_id, tenant_id, case_id, envelope_id,
            "SCORE_OUTCOME", json.dumps(summary), actor_sub,
        ), db_url=self._db_url)
        return recon_id

    def _write_outcome(
        self, tenant_id: str, case_id: str, recon_id: uuid.UUID, sp: dict, actor_sub: str
    ) -> uuid.UUID:
        outcome_id    = uuid.uuid4()
        composite     = float(sp["composite_score"] or 0)
        threshold     = float(sp["contracted_threshold"] or 0)
        outcome_type  = "FLAG_ISSUED" if composite < threshold else "NO_ACTION"
        details = {
            "composite_score":  composite,
            "breach_threshold": threshold,
            "outcome":          outcome_type,
            "carrier_id":       str(sp.get("carrier_id") or ""),
        }
        q("""
            INSERT INTO outcomes
                (id, tenant_id, case_id, reconciliation_id, outcome_type,
                 details, status, actor_sub, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, 'POSTED', %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            outcome_id, tenant_id, case_id, str(recon_id),
            outcome_type, json.dumps(details), actor_sub,
        ), db_url=self._db_url)
        return outcome_id

    def _detect_variances(
        self, tenant_id: str, case_id: str, recon_id: uuid.UUID, sp: dict, actor_sub: str
    ) -> list[dict]:
        composite = float(sp["composite_score"] or 0)
        threshold = float(sp["contracted_threshold"] or 0)
        variances = []
        if composite < threshold:
            vid  = uuid.uuid4()
            diff = round(threshold - composite, 4)
            q("""
                INSERT INTO reconciliation_variances
                    (id, tenant_id, case_id, reconciliation_id, variance_type,
                     expected_value, actual_value, delta, status, actor_sub, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, 'OPEN', %s, NOW())
                ON CONFLICT DO NOTHING
            """, (
                vid, tenant_id, case_id, str(recon_id),
                "SCORE_BELOW_THRESHOLD",
                str(threshold), str(composite), str(diff), actor_sub,
            ), db_url=self._db_url)
            variances.append({
                "id":            str(vid),
                "type":          "SCORE_BELOW_THRESHOLD",
                "expected":      threshold,
                "actual":        composite,
                "delta":         diff,
                "status":        "OPEN",
            })
        return variances

    def _advance_case(self, tenant_id: str, case_id: str, actor_sub: str) -> None:
        q("""
            UPDATE cases SET state='OUTCOME_RECORDED'
            WHERE id=%s::uuid AND tenant_id=%s::uuid AND state='DISPATCHED'
        """, (case_id, tenant_id), db_url=self._db_url)
        q("""
            INSERT INTO case_events
                (id, tenant_id, case_id, event_type, from_state, to_state,
                 actor_sub, payload, occurred_at)
            VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'STATE_TRANSITION',
                    'DISPATCHED', 'OUTCOME_RECORDED', %s,
                    '{"strategy":"SCORE_OUTCOME"}'::jsonb, NOW())
        """, (tenant_id, case_id, actor_sub), db_url=self._db_url)
