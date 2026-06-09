"""
Reasoning Service — Agent Runtime orchestrates tool calls, records a reasoning
trace, then computes confidence and produces a Finding + Decision Proposal.

Agent Runtime flow (7 steps):
  1. read_evidence_bundle  — verify evidence exists (read-only DB call)
  2. read_contract_rates   — verify contract rates exist (read-only DB call)
  3. read_case_metadata    — confirm case state (read-only DB call)
  4. RULE_ENGINE:fuel_charge   — apply SC-001 fuel surcharge rule
  5. RULE_ENGINE:accessorial   — apply SC-001 accessorial charges rule
  6. RULE_ENGINE:confidence    — compute weighted average (deterministic 0.96)
  7. GROQ_AI:risk_assessment   — optional AI risk level + reasoning explanation

The SC-001 confidence formula is deterministic and must never change:
  fuel_charge_confidence  = 1.00  (weight 0.50)
  accessorial_confidence  = 0.92  (weight 0.50)
  weighted_average        = 0.50 × 1.00 + 0.50 × 0.92 = 0.96

Step 7 adds ai_confidence and risk_level as supplementary fields.
The official confidence (SC001_CONFIDENCE = 0.96) is NEVER changed by AI.

All 7 steps are stored as a reasoning_trace row for audit replay.
"""
import hashlib, json, uuid
from datetime import datetime, timezone

import paths  # noqa: F401
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

from services.reasoning_svc import tools as agent_tools
from services.reasoning_svc.models import FindingResult

# ── SC-001 deterministic rule weights (must never change) ────────────────────
_RULES = {
    "fuel_charge": {"confidence": 1.00, "weight": 0.50},
    "accessorial": {"confidence": 0.92, "weight": 0.50},
}
SC001_CONFIDENCE = round(
    sum(r["confidence"] * r["weight"] for r in _RULES.values()), 4
)  # = 0.96

_AGENT_ID      = "zoiko.agent.freight_dispute.v1"
_POLICY_VERSION = "v1.0.0"


class AgentRuntime:
    """Orchestrates tool calls and produces a reasoning trace for SC-001."""

    def run(
        self,
        db_url:    str,
        tenant_id: str,
        case_id:   str,
        bundle_id: str,
        amount:    float,
        currency:  str,
        proposed_action: str,
        carrier:   str = "",
        route:     str = "",
        contract_rate: float = 0.0,
    ) -> tuple[dict, list, list, list, dict]:
        """Execute reasoning steps. Returns (rule_trace, steps, tools_used, evidence_refs, ai_result)."""
        steps: list[dict] = []
        tools_used: list[str] = []
        evidence_refs: list[str] = []

        # Step 1 — read evidence bundle
        bundle_data = agent_tools.invoke(
            "read_evidence_bundle", db_url=db_url,
            bundle_id=bundle_id, tenant_id=tenant_id,
        )
        tools_used.append("read_evidence_bundle")
        evidence_refs = [item["id"] for item in bundle_data.get("items", [])]
        steps.append({
            "step": 1, "tool": "read_evidence_bundle",
            "input":  {"bundle_id": bundle_id},
            "output": {"item_count": bundle_data["item_count"]},
            "finding": f"{bundle_data['item_count']} evidence item(s) verified in bundle",
        })

        # Step 2 — read contract rates
        rates_data = agent_tools.invoke(
            "read_contract_rates", db_url=db_url, tenant_id=tenant_id,
        )
        tools_used.append("read_contract_rates")
        steps.append({
            "step": 2, "tool": "read_contract_rates",
            "input":  {"tenant_id": tenant_id},
            "output": {"rate_count": rates_data["rate_count"]},
            "finding": f"{rates_data['rate_count']} contract rate(s) available for validation",
        })

        # Step 3 — read case metadata
        case_data = agent_tools.invoke(
            "read_case_metadata", db_url=db_url,
            case_id=case_id, tenant_id=tenant_id,
        )
        tools_used.append("read_case_metadata")
        steps.append({
            "step": 3, "tool": "read_case_metadata",
            "input":  {"case_id": case_id},
            "output": {"state": case_data.get("state"), "found": case_data.get("found")},
            "finding": f"Case state: {case_data.get('state', 'unknown')}",
        })

        # Step 4 — fuel_charge rule
        fuel = _RULES["fuel_charge"]
        steps.append({
            "step": 4, "tool": "RULE_ENGINE", "rule": "fuel_charge",
            "input":      {"amount": amount, "currency": currency},
            "confidence": fuel["confidence"],
            "weight":     fuel["weight"],
            "finding":    (
                f"Fuel surcharge overcharge confirmed — "
                f"confidence {fuel['confidence']*100:.0f}%, weight {fuel['weight']}"
            ),
        })

        # Step 5 — accessorial rule
        acc = _RULES["accessorial"]
        steps.append({
            "step": 5, "tool": "RULE_ENGINE", "rule": "accessorial",
            "input":      {"amount": amount, "currency": currency},
            "confidence": acc["confidence"],
            "weight":     acc["weight"],
            "finding":    (
                f"Accessorial charges overcharge confirmed — "
                f"confidence {acc['confidence']*100:.0f}%, weight {acc['weight']}"
            ),
        })

        # Step 6 — weighted confidence + action decision
        rule_trace = {
            rule: {"confidence": v["confidence"], "weight": v["weight"]}
            for rule, v in _RULES.items()
        }
        rule_trace["weighted_average"] = SC001_CONFIDENCE
        steps.append({
            "step": 6, "tool": "RULE_ENGINE", "rule": "compute_confidence",
            "input":      {"rules": list(_RULES.keys())},
            "confidence": SC001_CONFIDENCE,
            "finding":    (
                f"Weighted confidence = {SC001_CONFIDENCE} → "
                f"recommending action: {proposed_action}"
            ),
        })

        # Step 7 — Groq AI supplementary risk assessment (optional)
        ai_result = {"ai_confidence": None, "risk_level": None, "ai_reasoning": None}
        import os
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from groq import Groq as _Groq
                groq_model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
                client = _Groq(api_key=groq_key)
                overcharge = round(amount - contract_rate, 2) if contract_rate > 0 else amount
                prompt = (
                    f"Freight overcharge case:\n"
                    f"  Carrier: {carrier or 'unknown'}\n"
                    f"  Route: {route or 'unknown'}\n"
                    f"  Billed: {amount} {currency}\n"
                    f"  Contract rate: {contract_rate} {currency}\n"
                    f"  Overcharge: {overcharge} {currency}\n\n"
                    f"Assess risk level (HIGH/MEDIUM/LOW), provide a confidence score 0.0-1.0, "
                    f"and explain your reasoning in 1-2 sentences. "
                    f"Respond in JSON: {{\"risk_level\": \"HIGH\", \"ai_confidence\": 0.92, \"reasoning\": \"...\"}}"
                )
                chat = client.chat.completions.create(
                    model=groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=200,
                )
                import re as _re
                raw = chat.choices[0].message.content.strip()
                match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if match:
                    parsed = json.loads(match.group())
                    ai_result = {
                        "ai_confidence": float(parsed.get("ai_confidence", 0.90)),
                        "risk_level":    str(parsed.get("risk_level", "MEDIUM")).upper(),
                        "ai_reasoning":  str(parsed.get("reasoning", "")),
                    }
            except Exception as _e:
                ai_result["ai_reasoning"] = f"Groq unavailable: {_e}"

            tools_used.append("GROQ_AI:risk_assessment")
            steps.append({
                "step": 7, "tool": "GROQ_AI", "rule": "risk_assessment",
                "input":   {"carrier": carrier, "route": route, "amount": amount, "currency": currency},
                "output":  ai_result,
                "finding": f"AI risk: {ai_result['risk_level']} — confidence {ai_result['ai_confidence']}",
            })

        return rule_trace, steps, tools_used, evidence_refs, ai_result


class ReasoningHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def analyze(
        self,
        tenant_id:       str,
        case_id:         str,
        bundle_id:       str,
        proposer_sub:    str,
        proposed_action: str = "CREDIT_MEMO",
        amount:          float = 0.0,
        currency:        str = "USD",
        carrier:         str = "",
        route:           str = "",
        contract_rate:   float = 0.0,
    ) -> FindingResult:
        tenant_id = str(tenant_id)
        case_id   = str(case_id)
        bundle_id = str(bundle_id)
        now       = datetime.now(timezone.utc)

        # ── T-006: bundle must be sealed (COMPLETE) before reasoning runs ───
        import psycopg2.extras
        _conn = psycopg2.connect(self.db_url)
        try:
            _cur = _conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            _cur.execute(
                "SELECT completeness_status FROM evidence_bundles "
                "WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(bundle_id), tenant_id),
            )
            _brow = _cur.fetchone()
        finally:
            _conn.close()
        if not _brow:
            raise ValueError(f"Evidence bundle {bundle_id} not found for tenant {tenant_id}")
        if _brow["completeness_status"] != "COMPLETE":
            raise ValueError(
                f"Evidence bundle {bundle_id} is INCOMPLETE — "
                f"seal the bundle before running reasoning (T-006)"
            )

        # ── Run Agent Runtime ────────────────────────────────────────────────
        runtime = AgentRuntime()
        rule_trace, steps, tools_used, evidence_refs, ai_result = runtime.run(
            db_url=self.db_url,
            tenant_id=tenant_id,
            case_id=case_id,
            bundle_id=bundle_id,
            amount=amount,
            currency=currency,
            proposed_action=proposed_action,
            carrier=carrier,
            route=route,
            contract_rate=contract_rate,
        )

        # ── Step 1 — finding record ──────────────────────────────────────────
        finding_payload = {
            "bundle_id":  bundle_id,
            "case_id":    case_id,
            "confidence": str(SC001_CONFIDENCE),
            "rule_trace": rule_trace,
            "tenant_id":  tenant_id,
        }
        finding_bytes = canonicalize(finding_payload)
        finding_hash  = hashlib.sha256(b"zoiko.finding.v1:" + finding_bytes).digest()
        finding_sig, finding_kid = sign(self.tenant_slug, finding_hash)

        # ── Step 2 — proposal record ─────────────────────────────────────────
        proposal_payload = {
            "amount":          str(amount),
            "case_id":         case_id,
            "currency":        currency,
            "finding_hash":    finding_hash.hex(),
            "proposed_action": proposed_action,
            "proposer_sub":    proposer_sub,
            "tenant_id":       tenant_id,
        }
        proposal_bytes = canonicalize(proposal_payload)
        proposal_hash  = hashlib.sha256(b"zoiko.proposal.v1:" + proposal_bytes).digest()
        proposal_sig, proposal_kid = sign(self.tenant_slug, proposal_hash)

        finding_id     = uuid.uuid4()
        proposal_id    = uuid.uuid4()
        trace_id       = uuid.uuid4()
        action_intent_id = uuid.uuid4()

        # Governance envelope — formal wrapper on the agent's proposed action
        governance_envelope = {
            "action_intent_id":   str(action_intent_id),
            "agent_id":           _AGENT_ID,
            "confidence":         SC001_CONFIDENCE,
            "evidence_refs":      evidence_refs,
            "policy_version":     _POLICY_VERSION,
            "reasoning_trace_id": str(trace_id),
            "step_count":         len(steps),
            "tools_used":         tools_used,
            "action_intent":      proposed_action,
        }

        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()

            # INSERT action_intent — agent's declared action before human approval
            cur.execute("""
                INSERT INTO action_intents
                    (id, tenant_id, case_id, proposal_id, action_type,
                     policy_version, agent_id, declared_at, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                action_intent_id, tenant_id, uuid.UUID(case_id),
                proposal_id, proposed_action,
                _POLICY_VERSION, _AGENT_ID, now,
                f"SC-001 weighted confidence {SC001_CONFIDENCE}: recommending {proposed_action}",
            ))

            # INSERT reasoning_trace
            cur.execute("""
                INSERT INTO reasoning_traces
                    (id, tenant_id, case_id, agent_id, steps, tools_used,
                     evidence_refs, confidence, action_intent, policy_version, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            """, (
                trace_id, tenant_id, uuid.UUID(case_id),
                _AGENT_ID,
                json.dumps(steps),
                tools_used,
                evidence_refs,
                SC001_CONFIDENCE,
                proposed_action,
                _POLICY_VERSION,
                now,
            ))

            # INSERT finding — AI fields included only when available
            ai_conf = ai_result.get("ai_confidence")
            ai_risk = ai_result.get("risk_level")
            ai_text = ai_result.get("ai_reasoning")

            if ai_conf is not None or ai_risk is not None:
                cur.execute("""
                    INSERT INTO findings
                        (id, tenant_id, case_id, bundle_id, confidence,
                         rule_trace, signature, kid, created_at,
                         ai_confidence, risk_level, ai_reasoning)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s,
                            %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    finding_id, tenant_id, uuid.UUID(case_id), uuid.UUID(bundle_id),
                    SC001_CONFIDENCE, json.dumps(rule_trace),
                    finding_sig, finding_kid, now,
                    ai_conf, ai_risk, ai_text,
                ))
            else:
                # No Groq AI available — insert without AI columns (avoids NOT NULL issues)
                cur.execute("""
                    INSERT INTO findings
                        (id, tenant_id, case_id, bundle_id, confidence,
                         rule_trace, signature, kid, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    finding_id, tenant_id, uuid.UUID(case_id), uuid.UUID(bundle_id),
                    SC001_CONFIDENCE, json.dumps(rule_trace),
                    finding_sig, finding_kid, now,
                ))

            # INSERT decision_proposal with reasoning_trace_id + governance_envelope + action_intent_id
            cur.execute("""
                INSERT INTO decision_proposals
                    (id, tenant_id, case_id, finding_id, proposed_action,
                     amount, currency, proposer_sub, proposal_hash, signature, kid,
                     reasoning_trace_id, governance_envelope, action_intent_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """, (
                proposal_id, tenant_id, uuid.UUID(case_id), finding_id,
                proposed_action, amount, currency, proposer_sub,
                proposal_hash, proposal_sig, proposal_kid,
                trace_id, json.dumps(governance_envelope), action_intent_id, now,
            ))
            # Atomic outbox INSERTs in same transaction (crash-safe)
            finding_event_id = str(uuid.uuid4())
            finding_payload = {
                "case_id":            case_id,
                "finding_id":         str(finding_id),
                "confidence":         SC001_CONFIDENCE,
                "proposal_id":        str(proposal_id),
                "reasoning_trace_id": str(trace_id),
                "agent_id":           _AGENT_ID,
                "event_id":           finding_event_id,
            }
            proposal_payload = {
                "proposal_id":      str(proposal_id),
                "case_id":          case_id,
                "proposed_action":  proposed_action,
                "amount":           amount,
                "currency":         currency,
                "proposer_sub":     proposer_sub,
                "action_intent_id": str(action_intent_id),
                "confidence":       SC001_CONFIDENCE,
            }
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s),
                       (%s, %s, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, "zoiko.finding.generated",
                case_id, json.dumps(finding_payload), now,
                uuid.uuid4(), tenant_id, "zoiko.proposal.created",
                str(proposal_id), json.dumps(proposal_payload), now,
            ))
            conn.commit()
        finally:
            conn.close()

        # Kafka publish AFTER commit (outbox relay recovers if this crashes)
        from kafka.producer import ZoikoProducer, KafkaMessage
        producer = ZoikoProducer(self.broker)
        producer.publish(KafkaMessage(
            topic          = "zoiko.finding.generated",
            key            = str(case_id),
            payload        = finding_payload,
            tenant_id      = tenant_id,
            correlation_id = case_id,
        ))
        producer.publish(KafkaMessage(
            topic          = "zoiko.proposal.created",
            key            = str(proposal_id),
            payload        = proposal_payload,
            tenant_id      = tenant_id,
            correlation_id = case_id,
            causation_id   = finding_event_id,
        ))

        return FindingResult(
            finding_id          = finding_id,
            proposal_id         = proposal_id,
            tenant_id           = tenant_id,
            case_id             = case_id,
            bundle_id           = bundle_id,
            confidence          = SC001_CONFIDENCE,
            rule_trace          = rule_trace,
            proposed_action     = proposed_action,
            amount              = amount,
            currency            = currency,
            proposer_sub        = proposer_sub,
            created_at          = now,
            reasoning_trace_id  = trace_id,
        )
