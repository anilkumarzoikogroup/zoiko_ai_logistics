"""
Reasoning Service — production-ready version
"""

from dotenv import load_dotenv
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import psycopg2

from groq import Groq
from shared.signer import sign
from services.reasoning_svc.models import FindingResult

# =========================================================
# ENV
# =========================================================

load_dotenv(override=True)

DB_URL        = os.getenv("DB_URL")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
KAFKA_BROKER  = os.getenv("KAFKA_BROKER") or os.getenv("KAFKA_BOOTSTRAP")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() == "true"

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# =========================================================
# SAFE IMPORTS
# =========================================================

try:
    from zoiko_common.crypto.jcs import canonicalize
except ImportError:
    def canonicalize(data):
        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")

if not KAFKA_ENABLED:
    class KafkaMessage:
        def __init__(self, topic, key, payload, tenant_id):
            self.topic     = topic
            self.key       = key
            self.payload   = payload
            self.tenant_id = tenant_id

    class ZoikoProducer:
        def __init__(self, broker=None):
            self.broker = broker
        def publish(self, message):
            print(f"[WARN] Kafka disabled via env -> skipped topic: {message.topic}")
else:
    try:
        from kafka.producer import ZoikoProducer, KafkaMessage
    except Exception:
        class KafkaMessage:
            def __init__(self, topic, key, payload, tenant_id):
                self.topic     = topic
                self.key       = key
                self.payload   = payload
                self.tenant_id = tenant_id

        class ZoikoProducer:
            def __init__(self, broker=None):
                self.broker = broker
            def publish(self, message):
                print(f"[WARN] Kafka unavailable -> skipped topic: {message.topic}")

# =========================================================
# RULE ENGINE
# =========================================================

_RULES = {
    "fuel_charge": {"confidence": 1.00, "weight": 0.50},
    "accessorial":  {"confidence": 0.92, "weight": 0.50},
}

SC001_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in _RULES.values()),
    4
)

# =========================================================
# HANDLER
# =========================================================

class ReasoningHandler:

    def __init__(self, db_url=None, kafka_broker=None, tenant_slug="default"):
        self.db_url      = db_url or DB_URL
        self.broker      = kafka_broker or KAFKA_BROKER
        self.tenant_slug = tenant_slug
        if self.db_url:
            self._ensure_tables()

    # ---------------- DB ----------------

    def _get_conn(self):
        try:
            return psycopg2.connect(self.db_url)
        except Exception as e:
            print(f"[WARN] DB connection failed: {e}")
            return None

    def _ensure_tables(self):
        conn = self._get_conn()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id            UUID PRIMARY KEY,
                    tenant_id     TEXT,
                    case_id       UUID,
                    bundle_id     UUID,
                    confidence    DOUBLE PRECISION,
                    ai_confidence DOUBLE PRECISION,
                    risk_level    TEXT,
                    ai_reasoning  TEXT,
                    rule_trace    JSONB,
                    signature     BYTEA,
                    kid           TEXT,
                    created_at    TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS decision_proposals (
                    id              UUID PRIMARY KEY,
                    tenant_id       TEXT,
                    case_id         UUID,
                    finding_id      UUID,
                    proposed_action TEXT,
                    amount          DOUBLE PRECISION,
                    currency        TEXT,
                    proposer_sub    TEXT,
                    proposal_hash   BYTEA,
                    signature       BYTEA,
                    kid             TEXT,
                    created_at      TIMESTAMPTZ
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ---------------- AI ----------------

    def _run_ai_reasoning(
        self,
        case_id,
        bundle_id,
        amount,
        currency,
        carrier=None,        # ← NEW
        route=None,          # ← NEW
        contract_rate=None,  # ← NEW
    ):
        # ── Fallback if Groq not configured ──
        if client is None:
            return {
                "ai_confidence":      0.90,
                "risk_level":         "MEDIUM",
                "reasoning":          ["Groq not configured"],
                "recommended_action": "REVIEW",
            }

        # ── Compute overcharge independently ──
        overcharge_amount = None
        overcharge_pct    = None
        if contract_rate and contract_rate > 0:
            overcharge_amount = round(amount - contract_rate, 2)
            overcharge_pct    = round((overcharge_amount / contract_rate) * 100, 2)

        # ── Raw invoice prompt — NO pre-computed scores ──
        prompt = {
            "case_id":           str(case_id),
            "carrier":           carrier   or "Unknown",
            "route":             route     or "Unknown",
            "invoice_amount":    amount,
            "currency":          currency,
            "contract_rate":     contract_rate,
            "overcharge_amount": overcharge_amount,
            "overcharge_pct":    overcharge_pct,
        }

        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an independent logistics invoice auditor. "
                            "You receive raw invoice data only — no pre-computed scores. "
                            "Assess independently whether the overcharge is genuine "
                            "based on carrier, route, invoice amount, contract rate, "
                            "and overcharge percentage. "
                            "Be critical — do not just confirm the numbers. "
                            "Consider: Is this overcharge % realistic for this route? "
                            "Is the carrier known for this type of dispute? "
                            "Does the route justify these charges? "
                            "Respond ONLY with valid JSON — no markdown, no code fences: "
                            "{\"ai_confidence\": float, "
                            "\"risk_level\": \"LOW|MEDIUM|HIGH\", "
                            "\"reasoning\": [str], "
                            "\"recommended_action\": \"REVIEW|APPROVE|REJECT\"}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt),
                    },
                ],
                temperature=0.3,  # slightly higher for independent thinking
            )

            text = resp.choices[0].message.content
            try:
                return json.loads(text)
            except Exception:
                return {
                    "ai_confidence":      0.90,
                    "risk_level":         "MEDIUM",
                    "reasoning":          [text],
                    "recommended_action": "REVIEW",
                }

        except Exception as e:
            return {
                "ai_confidence":      0.85,
                "risk_level":         "MEDIUM",
                "reasoning":          [str(e)],
                "recommended_action": "REVIEW",
            }

    # ---------------- GET FINDINGS ----------------

    def get_findings(self, tenant_id, case_id):
        case_uuid = uuid.UUID(case_id)
        conn = self._get_conn()
        if not conn:
            raise ValueError("DB unavailable")
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    f.id, f.bundle_id, f.confidence, f.ai_confidence,
                    f.risk_level, f.ai_reasoning,
                    dp.proposed_action, dp.amount, dp.currency,
                    f.created_at
                FROM findings f
                LEFT JOIN decision_proposals dp ON dp.finding_id = f.id
                WHERE f.tenant_id = %s AND f.case_id = %s
                ORDER BY f.created_at DESC
            """, (tenant_id, str(case_uuid)))

            rows = cur.fetchall()
            if not rows:
                raise ValueError(f"No findings for case {case_id}")

            return [
                FindingResult(
                    finding_id      = str(r[0]),
                    bundle_id       = str(r[1]),
                    confidence      = r[2],
                    ai_confidence   = r[3],
                    risk_level      = r[4],
                    ai_reasoning    = r[5],
                    proposed_action = r[6] or "CREDIT_MEMO",
                    amount          = r[7] or 0.0,
                    currency        = r[8] or "USD",
                    created_at      = r[9],
                )
                for r in rows
            ]
        finally:
            conn.close()

    # ---------------- MAIN ----------------

    def analyze(
        self,
        tenant_id,
        case_id,
        bundle_id,
        proposer_sub,
        proposed_action = "CREDIT_MEMO",
        amount          = 0.0,
        currency        = "USD",
        carrier         = None,       # ← NEW
        route           = None,       # ← NEW
        contract_rate   = None,       # ← NEW
    ):
        now         = datetime.now(timezone.utc)
        case_uuid   = uuid.UUID(case_id)
        bundle_uuid = uuid.UUID(bundle_id)

        rule_trace = {
            r: {"confidence": v["confidence"], "weight": v["weight"]}
            for r, v in _RULES.items()
        }
        rule_trace["weighted_average"] = SC001_CONFIDENCE

        # ── AI gets raw invoice data — NOT rule scores ──
        ai = self._run_ai_reasoning(
            case_id       = case_id,
            bundle_id     = bundle_id,
            amount        = amount,
            currency      = currency,
            carrier       = carrier,
            route         = route,
            contract_rate = contract_rate,
        )

        ai_conf    = float(ai.get("ai_confidence", 0.90))
        risk       = ai.get("risk_level", "MEDIUM")

        # ── Blend: rule engine 60% + independent AI 40% ──
        final_conf = round((SC001_CONFIDENCE * 0.6) + (ai_conf * 0.4), 4)

        finding_id  = uuid.uuid4()
        proposal_id = uuid.uuid4()

        # ---------------- SIGN ----------------
        payload = canonicalize({
            "case_id":       str(case_uuid),
            "bundle_id":     str(bundle_uuid),
            "confidence":    final_conf,
            "ai_confidence": ai_conf,
        })
        sig, kid = sign(self.tenant_slug, hashlib.sha256(payload).digest())

        proposal_payload = canonicalize({
            "finding_id":      str(finding_id),
            "proposed_action": proposed_action,
            "amount":          amount,
            "currency":        currency,
        })
        proposal_hash = hashlib.sha256(proposal_payload).digest()

        # ---------------- DB ----------------
        conn = self._get_conn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO findings (
                        id, tenant_id, case_id, bundle_id,
                        confidence, ai_confidence, risk_level,
                        ai_reasoning, rule_trace,
                        signature, kid, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """, (
                    str(finding_id), tenant_id,
                    str(case_uuid), str(bundle_uuid),
                    final_conf, ai_conf, risk,
                    json.dumps(ai.get("reasoning", [])),
                    json.dumps(rule_trace),
                    sig, kid, now,
                ))
                cur.execute("""
                    INSERT INTO decision_proposals (
                        id, tenant_id, case_id, finding_id,
                        proposed_action, amount, currency,
                        proposer_sub, proposal_hash,
                        signature, kid, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(proposal_id), tenant_id,
                    str(case_uuid), str(finding_id),
                    proposed_action, amount, currency,
                    proposer_sub, proposal_hash,
                    sig, kid, now,
                ))
                conn.commit()
            finally:
                conn.close()

        # ---------------- KAFKA ----------------
        try:
            ZoikoProducer(self.broker).publish(
                KafkaMessage(
                    topic     = "zoiko.finding.generated",
                    key       = str(case_uuid),
                    payload   = {
                        "case_id":    str(case_uuid),
                        "finding_id": str(finding_id),
                        "confidence": final_conf,
                        "risk_level": risk,
                    },
                    tenant_id = str(tenant_id),
                )
            )
        except Exception as e:
            print(f"[WARN] Kafka publish failed: {e}")

        # ---------------- RETURN ----------------
        return FindingResult(
            finding_id      = finding_id,
            proposal_id     = proposal_id,
            tenant_id       = str(tenant_id),
            case_id         = str(case_uuid),
            bundle_id       = str(bundle_uuid),
            confidence      = final_conf,
            ai_confidence   = ai_conf,
            risk_level      = risk,
            ai_reasoning    = json.dumps(ai.get("reasoning", [])),
            rule_trace      = rule_trace,
            proposed_action = proposed_action,
            amount          = amount,
            currency        = currency,
            proposer_sub    = proposer_sub,
            created_at      = now,
        )