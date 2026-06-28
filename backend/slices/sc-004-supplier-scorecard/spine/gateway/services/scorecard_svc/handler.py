"""SC-004 — Supplier Performance Scorecard computation engine.

Metrics are auto-computed from live DB data:
  - SC-002 claims: overcharge rate, claim frequency, resolution turnaround
  - SC-003 cases: SLA on-time delivery rate (committed_eta vs actual_delivery)

Composite formula (deterministic weights — never change):
  0.40 × on_time_score    (% shipments delivered on time)
  0.30 × quality_score    (inverse overcharge rate)
  0.20 × frequency_score  (fewer claims = better)
  0.10 × resolution_score (faster resolution = better)

Confidence formula (deterministic — never change):
  _RULES = {
    "breach_detected_rule": {"confidence": 1.00, "weight": 0.70},
    "data_coverage_rule":   {"confidence": 0.88, "weight": 0.30},
  }
  SC004_CONFIDENCE = 0.9640  # = 1.00×0.70 + 0.88×0.30
"""
import paths  # noqa: F401
import uuid
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from shared.db import q, q1, DB_URL

# ── Formula weights — deterministic, never change ─────────────────────────────
WEIGHTS = {
    "on_time":    0.40,
    "quality":    0.30,
    "frequency":  0.20,
    "resolution": 0.10,
}

SC004_THRESHOLD_DEFAULT = 70.0

# ── Confidence score — deterministic, never change ────────────────────────────
SC004_CONFIDENCE = 0.9640  # = 1.00×0.70 + 0.88×0.30

_RULES = {
    "breach_detected_rule": {"confidence": 1.00, "weight": 0.70},
    "data_coverage_rule":   {"confidence": 0.88, "weight": 0.30},
}


class ScorecardHandler:
    def __init__(self, db_url: str):
        self.db_url = db_url

    # ── Raw metric queries ─────────────────────────────────────────────────────

    def _fetch_claim_metrics(self, tenant_id: str, carrier_id: str,
                              period_start: datetime, period_end: datetime) -> dict:
        row = q1("""
            SELECT
                COUNT(*)                                                       AS total_claims,
                COALESCE(SUM(claimed_amount), 0)                               AS total_claimed,
                COALESCE(SUM(COALESCE(approved_amount, claimed_amount)), 0)    AS total_approved,
                AVG(CASE WHEN resolved_at IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (resolved_at - filed_at)) / 86400
                    ELSE NULL END)                                             AS avg_turnaround_days
            FROM claims
            WHERE tenant_id = %s::uuid
              AND carrier_id = %s
              AND filed_at >= %s
              AND filed_at < %s
        """, (tenant_id, carrier_id, period_start, period_end), db_url=self.db_url)

        return {
            "total_claims":       int(row["total_claims"] or 0),
            "total_claimed":      float(row["total_claimed"] or 0),
            "total_approved":     float(row["total_approved"] or 0),
            "avg_turnaround_days": float(row["avg_turnaround_days"] or 0),
        }

    def _fetch_sla_metrics(self, tenant_id: str, carrier_id: str,
                            period_start: datetime, period_end: datetime) -> dict:
        try:
            row = q1("""
                SELECT
                    COUNT(*)                                                            AS sla_cases,
                    COUNT(CASE WHEN c.actual_delivery <= c.committed_eta THEN 1 END)   AS on_time
                FROM cases c
                JOIN canonical_shipment_exceptions cse
                    ON cse.shipment_reference = c.shipment_reference
                    AND cse.tenant_id = c.tenant_id
                WHERE c.tenant_id = %s::uuid
                  AND cse.carrier_id = %s
                  AND c.case_type = 'SHIPMENT_EXCEPTION'
                  AND c.committed_eta IS NOT NULL
                  AND c.opened_at >= %s
                  AND c.opened_at < %s
            """, (tenant_id, carrier_id, period_start, period_end), db_url=self.db_url)
            return {
                "sla_cases":     int(row["sla_cases"] or 0),
                "on_time_cases": int(row["on_time"] or 0),
            }
        except Exception:
            # canonical_shipment_exceptions table may not exist yet (created on first SC-003 run)
            return {"sla_cases": 0, "on_time_cases": 0}

    # ── Score derivation ───────────────────────────────────────────────────────

    def _derive_scores(self, claim_m: dict, sla_m: dict, threshold: float) -> dict:
        tc   = claim_m["total_claims"]
        sla  = sla_m["sla_cases"]
        days = claim_m["avg_turnaround_days"]

        # on_time_score: % on-time deliveries (100 if no SLA data yet)
        on_time_rate  = sla_m["on_time_cases"] / sla if sla else 1.0
        on_time_score = round(on_time_rate * 100, 2)

        # quality_score: 100 - (overcharge fraction × 100)
        if claim_m["total_claimed"] > 0:
            overcharge_frac = max(0.0, (claim_m["total_claimed"] - claim_m["total_approved"]) / claim_m["total_claimed"])
            quality_score   = round((1.0 - overcharge_frac) * 100, 2)
        else:
            quality_score = 100.0

        # frequency_score: 0 claims = 100, each claim costs 10 pts, floor 0
        frequency_score = round(max(0.0, 100.0 - tc * 10), 2)

        # resolution_score: turnaround in days mapped to 0-100
        if days <= 0:
            resolution_score = 100.0
        elif days <= 30:
            resolution_score = round(100.0 - (days / 30) * 30, 2)   # 100→70
        elif days <= 90:
            resolution_score = round(70.0 - ((days - 30) / 60) * 30, 2)  # 70→40
        elif days <= 180:
            resolution_score = round(40.0 - ((days - 90) / 90) * 40, 2)  # 40→0
        else:
            resolution_score = 0.0

        composite = round(
            WEIGHTS["on_time"]    * on_time_score +
            WEIGHTS["quality"]    * quality_score +
            WEIGHTS["frequency"]  * frequency_score +
            WEIGHTS["resolution"] * resolution_score,
            2,
        )

        breach = composite < threshold
        breach_amount = round(max(0.0, claim_m["total_claimed"] - claim_m["total_approved"]), 2) if breach else 0.0

        return {
            "on_time_score":    on_time_score,
            "quality_score":    quality_score,
            "frequency_score":  frequency_score,
            "resolution_score": resolution_score,
            "composite_score":  composite,
            "on_time_rate":     round(on_time_rate, 4),
            "damage_rate":      round(1.0 - min(1.0, quality_score / 100), 4),
            "claim_frequency":  float(tc),
            "dispute_turnaround_days": round(days, 1),
            "breach_detected":  breach,
            "breach_amount":    breach_amount,
        }

    # ── Public API ─────────────────────────────────────────────────────────────

    def compute(self, tenant_id: str, carrier_id: str,
                period_start: datetime, period_end: datetime,
                threshold: float = SC004_THRESHOLD_DEFAULT) -> dict:
        """Compute, persist, and return a scorecard for a carrier+period."""
        import psycopg2

        claim_m  = self._fetch_claim_metrics(tenant_id, carrier_id, period_start, period_end)
        sla_m    = self._fetch_sla_metrics(tenant_id, carrier_id, period_start, period_end)
        scores   = self._derive_scores(claim_m, sla_m, threshold)

        period_id = uuid.uuid4()
        now       = datetime.now(timezone.utc)

        raw_bytes   = json.dumps({
            "tenant_id": str(tenant_id), "carrier_id": carrier_id,
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "computed_at": now.isoformat(),
        }, sort_keys=True).encode()
        record_hash = hashlib.sha256(b"zoiko.scorecard.v1:" + raw_bytes).digest()

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO scorecard_periods (
                    id, tenant_id, carrier_id, supplier_id,
                    period_start, period_end,
                    on_time_rate, damage_rate, claim_frequency, dispute_turnaround_days,
                    composite_score, contracted_threshold, breach_detected, breach_amount,
                    currency, record_hash, created_at
                ) VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(period_id), str(tenant_id), carrier_id, carrier_id,
                period_start, period_end,
                scores["on_time_rate"], scores["damage_rate"],
                scores["claim_frequency"], scores["dispute_turnaround_days"],
                scores["composite_score"], threshold,
                scores["breach_detected"], scores["breach_amount"],
                "INR", record_hash, now,
            ))
            conn.commit()
        finally:
            conn.close()

        raw_metrics = {**claim_m, **sla_m}

        # Open a governed case for breach recovery
        case_id    = None
        finding_id = None
        if scores["breach_detected"]:
            case_id, finding_id = self._open_breach_case(
                conn_url    = self.db_url,
                tenant_id   = tenant_id,
                carrier_id  = carrier_id,
                period_id   = period_id,
                scores      = scores,
                threshold   = threshold,
                claim_m     = claim_m,
                sla_m       = sla_m,
                now         = now,
            )
            if case_id:
                conn2 = psycopg2.connect(self.db_url)
                try:
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "UPDATE scorecard_periods SET case_id=%s, finding_id=%s WHERE id=%s",
                        (str(case_id), str(finding_id) if finding_id else None, str(period_id)),
                    )
                    conn2.commit()
                finally:
                    conn2.close()

        detail = self._build_detail(period_id, tenant_id, carrier_id,
                                    period_start, period_end, scores, threshold, now,
                                    raw_metrics=raw_metrics)
        if case_id:
            detail["case_id"]    = str(case_id)
            detail["case_state"] = "FINDING_GENERATED"
            detail["finding_id"] = str(finding_id) if finding_id else None
        return detail

    # ── Governed case opening ──────────────────────────────────────────────────

    def _open_breach_case(
        self,
        conn_url: str,
        tenant_id: str,
        carrier_id: str,
        period_id: uuid.UUID,
        scores: dict,
        threshold: float,
        claim_m: dict,
        sla_m: dict,
        now: datetime,
    ) -> tuple:
        """Open a SCORECARD_BREACH governed case with evidence bundle and finding."""
        import psycopg2, psycopg2.extras
        from zoiko_common.crypto.jcs import canonicalize

        psycopg2.extras.register_uuid()
        case_id    = uuid.uuid4()
        finding_id = uuid.uuid4()
        bundle_id  = uuid.uuid4()
        item_id    = uuid.uuid4()

        # ── Evidence item: scorecard payload ──────────────────────────────────
        evidence_payload = json.dumps({
            "scorecard_period_id": str(period_id),
            "carrier_id":          carrier_id,
            "composite_score":     scores["composite_score"],
            "contracted_threshold": threshold,
            "breach_delta":        round(scores["composite_score"] - threshold, 2),
            "sub_scores":          {
                "on_time":    scores["on_time_score"],
                "quality":    scores["quality_score"],
                "frequency":  scores["frequency_score"],
                "resolution": scores["resolution_score"],
            },
            "raw_metrics": {**claim_m, **sla_m},
        }, sort_keys=True).encode()
        item_hash  = hashlib.sha256(b"zoiko.evidence.item.v1:" + evidence_payload).digest()

        # ── Bundle hash (single-item Merkle) ─────────────────────────────────
        bundle_hash = hashlib.sha256(b"zoiko/v1/evidence-item:" + item_hash).digest()

        # ── Finding hash ──────────────────────────────────────────────────────
        rule_traces = [
            {
                "rule":       "breach_detected_rule",
                "confidence": _RULES["breach_detected_rule"]["confidence"],
                "weight":     _RULES["breach_detected_rule"]["weight"],
                "passed":     True,
                "detail":     f"composite {scores['composite_score']} < threshold {threshold}",
            },
            {
                "rule":       "data_coverage_rule",
                "confidence": _RULES["data_coverage_rule"]["confidence"],
                "weight":     _RULES["data_coverage_rule"]["weight"],
                "passed":     claim_m["total_claims"] > 0,
                "detail":     f"total_claims={claim_m['total_claims']} sla_cases={sla_m['sla_cases']}",
            },
        ]
        finding_payload = {
            "case_id":            str(case_id),
            "finding_type":       "aggregation",
            "composite_score":    scores["composite_score"],
            "threshold":          threshold,
            "breach_delta":       round(scores["composite_score"] - threshold, 2),
            "confidence":         SC004_CONFIDENCE,
            "rule_traces":        rule_traces,
            "proposed_action":    "NOTIFY_FLAG",
        }
        finding_bytes = canonicalize(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()

        conn = psycopg2.connect(conn_url)
        try:
            cur = conn.cursor()

            # Open case — cases has scorecard_period_id not carrier_id
            cur.execute("""
                INSERT INTO cases
                    (id, tenant_id, case_type, state, scorecard_period_id, opened_at)
                VALUES (%s, %s::uuid, 'SCORECARD_BREACH', 'FINDING_GENERATED', %s::uuid, %s)
                ON CONFLICT DO NOTHING
            """, (str(case_id), tenant_id, str(period_id), now))

            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state,
                     actor_sub, payload, occurred_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid, 'CASE_OPENED',
                        'NEW', 'FINDING_GENERATED',
                        'system', %s::jsonb, %s)
            """, (
                tenant_id, str(case_id),
                json.dumps({"scorecard_id": str(period_id), "carrier_id": carrier_id}),
                now,
            ))

            # Evidence bundle — no item_count column in real schema
            from shared.signer import sign as _sign
            eb_sig, eb_kid = _sign("default", bundle_hash if isinstance(bundle_hash, bytes) else bundle_hash.encode())
            cur.execute("""
                INSERT INTO evidence_bundles
                    (id, tenant_id, case_id, bundle_hash, signature, kid, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (str(bundle_id), tenant_id, str(case_id), bundle_hash, eb_sig, eb_kid, now))

            entity_payload = json.dumps({
                "scorecard_period_id": str(period_id),
                "carrier_id":          carrier_id,
                "composite_score":     scores["composite_score"],
                "breach_amount":       scores["breach_amount"],
            })
            ei_hash = hashlib.sha256(b"zoiko.evidence.item.v1:" + entity_payload.encode()).hexdigest()
            ei_sig, ei_kid = _sign("default", ei_hash.encode())
            cur.execute("""
                INSERT INTO evidence_items
                    (id, tenant_id, bundle_id, item_type, entity_id, item_hash, signature, kid, added_at)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid,
                        'SCORECARD_METRICS', %s::uuid, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                tenant_id, str(bundle_id),
                str(period_id), ei_hash, ei_sig, ei_kid, now,
            ))

            # Aggregation finding — use real column names: confidence, rule_trace (not rule_traces)
            fi_sig, fi_kid = _sign("default", finding_hash if isinstance(finding_hash, bytes) else finding_hash.encode())
            cur.execute("""
                INSERT INTO findings
                    (id, tenant_id, case_id, bundle_id,
                     finding_type, confidence, finding_hash,
                     rule_trace, signature, kid, created_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid,
                        'aggregation', %s, %s,
                        %s::jsonb, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                str(finding_id), tenant_id, str(case_id), str(bundle_id),
                SC004_CONFIDENCE, finding_hash,
                json.dumps(rule_traces), fi_sig, fi_kid, now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            return None, None
        finally:
            conn.close()

        return case_id, finding_id

    def list_scorecards(self, tenant_id: str, carrier_id: str | None = None,
                         limit: int = 50, offset: int = 0) -> list[dict]:
        where  = "WHERE tenant_id = %s::uuid"
        params: list = [tenant_id]
        if carrier_id:
            where += " AND carrier_id = %s"
            params.append(carrier_id)
        rows = q(
            f"SELECT id, tenant_id, carrier_id, period_start, period_end, "
            f"on_time_rate, damage_rate, claim_frequency, dispute_turnaround_days, "
            f"composite_score, contracted_threshold, breach_detected, breach_amount, "
            f"currency, created_at "
            f"FROM scorecard_periods {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (limit, offset),
            db_url=self.db_url,
        )
        return [self._row_to_list(r) for r in rows]

    def get_scorecard(self, tenant_id: str, scorecard_id: str) -> dict:
        row = q1("""
            SELECT id, tenant_id, carrier_id, period_start, period_end,
                   on_time_rate, damage_rate, claim_frequency, dispute_turnaround_days,
                   composite_score, contracted_threshold, breach_detected, breach_amount,
                   currency, created_at, case_id, finding_id
            FROM scorecard_periods
            WHERE id = %s::uuid AND tenant_id = %s::uuid
        """, (scorecard_id, tenant_id), db_url=self.db_url)

        if not row:
            raise HTTPException(status_code=404, detail="Scorecard not found")

        on_time_rate = float(row["on_time_rate"] or 1.0)
        damage_rate  = float(row["damage_rate"] or 0)
        freq         = float(row["claim_frequency"] or 0)
        days         = float(row["dispute_turnaround_days"] or 0)
        threshold    = float(row["contracted_threshold"] or SC004_THRESHOLD_DEFAULT)

        on_time_score    = round(on_time_rate * 100, 2)
        quality_score    = round((1.0 - damage_rate) * 100, 2)
        frequency_score  = round(max(0.0, 100.0 - freq * 10), 2)
        if days <= 0:
            resolution_score = 100.0
        elif days <= 30:
            resolution_score = round(100.0 - (days / 30) * 30, 2)
        elif days <= 90:
            resolution_score = round(70.0 - ((days - 30) / 60) * 30, 2)
        elif days <= 180:
            resolution_score = round(40.0 - ((days - 90) / 90) * 40, 2)
        else:
            resolution_score = 0.0

        composite = float(row["composite_score"] or 0)
        scores = {
            "on_time_score": on_time_score, "quality_score": quality_score,
            "frequency_score": frequency_score, "resolution_score": resolution_score,
            "composite_score": composite,
            "on_time_rate": on_time_rate, "damage_rate": damage_rate,
            "claim_frequency": freq, "dispute_turnaround_days": days,
            "breach_detected": bool(row["breach_detected"]),
            "breach_amount": float(row["breach_amount"] or 0),
        }

        recent_claims = q("""
            SELECT id, claim_reference, claim_type, claimed_amount, approved_amount,
                   status, filed_at, currency
            FROM claims
            WHERE tenant_id = %s::uuid AND carrier_id = %s
              AND filed_at >= %s AND filed_at < %s
            ORDER BY filed_at DESC LIMIT 20
        """, (str(row["tenant_id"]), row["carrier_id"],
              row["period_start"], row["period_end"]),
            db_url=self.db_url)

        raw_metrics = {
            **self._fetch_claim_metrics(
                str(row["tenant_id"]), row["carrier_id"],
                row["period_start"], row["period_end"],
            ),
            **self._fetch_sla_metrics(
                str(row["tenant_id"]), row["carrier_id"],
                row["period_start"], row["period_end"],
            ),
        }
        detail = self._build_detail(
            row["id"], row["tenant_id"], row["carrier_id"],
            row["period_start"], row["period_end"],
            scores, threshold, row["created_at"],
            raw_metrics=raw_metrics,
        )
        detail["recent_claims"] = [
            {
                "id":              str(c["id"]),
                "claim_reference": c["claim_reference"],
                "claim_type":      c["claim_type"],
                "claimed_amount":  float(c["claimed_amount"] or 0),
                "approved_amount": float(c["approved_amount"]) if c["approved_amount"] is not None else None,
                "status":          c["status"],
                "filed_at":        c["filed_at"].isoformat() if c["filed_at"] else None,
                "currency":        c["currency"],
            }
            for c in recent_claims
        ]

        # Attach governed case info if a breach case was opened
        linked_case_id  = row.get("case_id")
        linked_finding_id = row.get("finding_id")
        if linked_case_id:
            case_row = q1(
                "SELECT state FROM cases WHERE id=%s::uuid AND tenant_id=%s::uuid",
                (str(linked_case_id), tenant_id),
                db_url=self.db_url,
            )
            detail["case_id"]    = str(linked_case_id)
            detail["case_state"] = case_row["state"] if case_row else "UNKNOWN"
            detail["finding_id"] = str(linked_finding_id) if linked_finding_id else None

            task_row = q1(
                "SELECT id, status, proposer_sub FROM governance_tasks "
                "WHERE case_id=%s::uuid AND tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
                (str(linked_case_id), tenant_id),
                db_url=self.db_url,
            )
            if task_row:
                detail["task_id"]     = str(task_row["id"])
                detail["task_status"] = task_row["status"]

            token_row = q1(
                """SELECT gt.id
                   FROM governance_tokens gt
                   JOIN governance_decisions gd ON gd.id = gt.decision_id
                   JOIN governance_tasks task   ON task.id = gd.proposal_id
                   WHERE task.case_id=%s::uuid AND gt.tenant_id=%s::uuid AND gt.status='ACTIVE'
                   ORDER BY gt.issued_at DESC LIMIT 1""",
                (str(linked_case_id), tenant_id),
                db_url=self.db_url,
            )
            if token_row:
                detail["token_id"] = str(token_row["id"])

        return detail

    def list_carriers(self, tenant_id: str) -> list[str]:
        rows = q(
            "SELECT DISTINCT carrier_id FROM claims WHERE tenant_id = %s::uuid ORDER BY carrier_id",
            (tenant_id,),
            db_url=self.db_url,
        )
        return [r["carrier_id"] for r in rows]

    # ── Serialisation helpers ──────────────────────────────────────────────────

    def _row_to_list(self, r: dict) -> dict:
        return {
            "id":                      str(r["id"]),
            "tenant_id":               str(r["tenant_id"]),
            "carrier_id":              r["carrier_id"],
            "period_start":            r["period_start"].isoformat() if r["period_start"] else None,
            "period_end":              r["period_end"].isoformat() if r["period_end"] else None,
            "on_time_rate":            float(r["on_time_rate"] or 0),
            "damage_rate":             float(r["damage_rate"] or 0),
            "claim_frequency":         float(r["claim_frequency"] or 0),
            "dispute_turnaround_days": float(r["dispute_turnaround_days"] or 0),
            "composite_score":         float(r["composite_score"] or 0),
            "contracted_threshold":    float(r["contracted_threshold"] or 0),
            "breach_detected":         bool(r["breach_detected"]),
            "breach_amount":           float(r["breach_amount"] or 0),
            "currency":                r["currency"],
            "created_at":              r["created_at"].isoformat(),
        }

    def _build_detail(self, pid, tenant_id, carrier_id,
                       period_start, period_end, scores, threshold, created_at,
                       raw_metrics: dict | None = None) -> dict:
        def _iso(v):
            return v.isoformat() if hasattr(v, "isoformat") else str(v)

        return {
            "id":                      str(pid),
            "tenant_id":               str(tenant_id),
            "carrier_id":              carrier_id,
            "period_start":            _iso(period_start),
            "period_end":              _iso(period_end),
            "on_time_rate":            scores["on_time_rate"],
            "damage_rate":             scores["damage_rate"],
            "claim_frequency":         scores["claim_frequency"],
            "dispute_turnaround_days": scores["dispute_turnaround_days"],
            "composite_score":         scores["composite_score"],
            "contracted_threshold":    threshold,
            "breach_detected":         scores["breach_detected"],
            "breach_amount":           scores["breach_amount"],
            "currency":                "INR",
            "created_at":              _iso(created_at),
            "sub_scores": {
                "on_time":    {"score": scores["on_time_score"],    "weight": WEIGHTS["on_time"],    "label": "On-Time Delivery"},
                "quality":    {"score": scores["quality_score"],    "weight": WEIGHTS["quality"],    "label": "Claim Quality"},
                "frequency":  {"score": scores["frequency_score"],  "weight": WEIGHTS["frequency"],  "label": "Claim Frequency"},
                "resolution": {"score": scores["resolution_score"], "weight": WEIGHTS["resolution"], "label": "Resolution Speed"},
            },
            "raw_metrics": raw_metrics or {},
        }
