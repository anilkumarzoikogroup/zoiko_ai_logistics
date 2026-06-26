"""SC-004 — Supplier Performance Scorecard computation engine.

Metrics are auto-computed from live DB data:
  - SC-002 claims: overcharge rate, claim frequency, resolution turnaround
  - SC-003 cases: SLA on-time delivery rate (committed_eta vs actual_delivery)

Composite formula (deterministic weights — never change):
  0.40 × on_time_score    (% shipments delivered on time)
  0.30 × quality_score    (inverse overcharge rate)
  0.20 × frequency_score  (fewer claims = better)
  0.10 × resolution_score (faster resolution = better)
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
        return self._build_detail(period_id, tenant_id, carrier_id,
                                   period_start, period_end, scores, threshold, now,
                                   raw_metrics=raw_metrics)

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
                   currency, created_at
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
