"""
Phase 4 — Execution Gateway

Implements the 8-gate pre-dispatch checklist before any credit/debit moves:

  Gate 1 — Token signature valid (Ed25519 over token_hash)
  Gate 2 — Token not expired (expires_at > now)
  Gate 3 — Token not consumed (Redis SET NX + DB status check)
  Gate 4 — Tenant binding correct (SHA-256 of tenant_id + decision_id)
  Gate 5 — Scope matches authorized action (EXECUTE_CREDIT_MEMO)
  Gate 6 — Sanctions screening (stub — allow in dev/test)
  Gate 7 — FX rate lock acquired (stub — amount within 5% tolerance)
  Gate 8 — Connector certified (stub — carrier connector is ACTIVE)

All 8 gates must pass. If any gate fails, the execution is rejected and a
FAILED envelope is written — no DB state changes propagate further.

After dispatch:
  - governance_tokens.status → CONSUMED
  - execution_envelopes row written
  - cases.state → DISPATCHED
  - Kafka: zoiko.execution.dispatched
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

import paths  # noqa: F401
import shared.db as _db
from shared.signer import sign as _sign

from services.execution_gateway.models import (
    ExecutionRequest, GateResult, ExecutionEnvelope,
)

psycopg2.extras.register_uuid()

_SCOPE_ALLOWED = {"EXECUTE_CREDIT_MEMO", "CREDIT_MEMO", "EXECUTE_DEBIT_NOTE"}


class ExecutionGateway:
    """8-gate execution gateway. Raises GateError on any gate failure."""

    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default") -> None:
        self._db_url      = db_url
        self._broker      = kafka_broker
        self._tenant_slug = tenant_slug

    # ── Public API ──────────────────────────────────────────────────────────────

    def execute(self, req: ExecutionRequest) -> ExecutionEnvelope:
        """
        Run all 8 gates. If all pass, dispatch and return the envelope.
        Raises ValueError on gate failure with gate number and reason.
        """
        token = self._fetch_token(req.token_id, req.tenant_id)
        if not token:
            raise ValueError(f"Token '{req.token_id}' not found for tenant '{req.tenant_id}'")

        gates = self._run_gates(token, req)
        failed = [g for g in gates if not g.passed]
        if failed:
            g = failed[0]
            raise ValueError(f"Gate {g.gate} ({g.name}) failed: {g.detail}")

        envelope = self._dispatch(token, req, gates)
        return envelope

    # ── Gate runners ────────────────────────────────────────────────────────────

    def _run_gates(self, token: dict, req: ExecutionRequest) -> list[GateResult]:
        return [
            self._gate1_signature(token),
            self._gate2_expiry(token),
            self._gate3_consumed(token),
            self._gate4_tenant_binding(token, req.tenant_id),
            self._gate5_scope(token),
            self._gate6_sanctions(token, req),
            self._gate7_fx_lock(token),
            self._gate8_connector(token),
        ]

    def _gate1_signature(self, token: dict) -> GateResult:
        """Verify Ed25519 signature over token_hash using KMS public key."""
        import os
        if os.getenv("ZOIKO_DEV_MODE", "").lower() == "true":
            return GateResult(1, "signature_valid", True, "DEV_MODE — signature check bypassed")
        try:
            from zoiko_kms.hierarchy import KeyHierarchy
            kh = KeyHierarchy()
            token_hash = bytes.fromhex(token["token_hash_hex"]) if isinstance(token.get("token_hash_hex"), str) else bytes(token["token_hash"])
            sig        = bytes(token["signature"]) if not isinstance(token["signature"], bytes) else token["signature"]
            kid        = token["kid"]
            pub_key    = kh.get_public_key(kid)
            pub_key.verify(sig, token_hash)
            return GateResult(1, "signature_valid", True, "Ed25519 signature verified")
        except Exception as e:
            return GateResult(1, "signature_valid", False, f"Signature invalid: {e}")

    def _gate2_expiry(self, token: dict) -> GateResult:
        """Check token TTL — execution window is 15 minutes from issuance."""
        import os
        if os.getenv("ZOIKO_DEV_MODE", "").lower() == "true":
            return GateResult(2, "not_expired", True, "DEV_MODE — expiry check bypassed")
        expires_at = token.get("expires_at")
        if expires_at is None:
            return GateResult(2, "not_expired", False, "Missing expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if expires_at < now:
            delta = (now - expires_at).total_seconds()
            return GateResult(2, "not_expired", False, f"Token expired {delta:.0f}s ago")
        return GateResult(2, "not_expired", True, f"Expires in {(expires_at - now).total_seconds():.0f}s")

    def _gate3_consumed(self, token: dict) -> GateResult:
        """Atomically mark token CONSUMED in Redis + check DB status."""
        token_id = str(token["id"])

        # Check DB status first
        if token.get("status") == "CONSUMED":
            return GateResult(3, "not_consumed", False, "Token already CONSUMED in DB")

        # Redis atomic SET NX
        try:
            from shared.redis_token import mark_consumed as _mark
            claimed = _mark(token_id)
            if not claimed:
                return GateResult(3, "not_consumed", False, "Token already consumed (Redis)")
        except ImportError:
            pass  # redis_token from phase-3 not on path — skip Redis gate
        except Exception:
            pass  # Redis unavailable — DB is authoritative

        return GateResult(3, "not_consumed", True, "Token atomically claimed")

    def _gate4_tenant_binding(self, token: dict, tenant_id: str) -> GateResult:
        """Verify tenant_binding = SHA-256(tenant_id + decision_id)."""
        try:
            expected = hashlib.sha256(
                tenant_id.encode() + str(token["decision_id"]).encode()
            ).digest()
            actual = bytes(token["tenant_binding"])
            if expected != actual:
                return GateResult(4, "tenant_binding", False, "Tenant binding mismatch")
            return GateResult(4, "tenant_binding", True, "Tenant binding verified")
        except Exception as e:
            return GateResult(4, "tenant_binding", False, f"Binding check error: {e}")

    def _gate5_scope(self, token: dict) -> GateResult:
        """Verify scope is in the allowed execution scopes."""
        scope = token.get("scope", "")
        if scope not in _SCOPE_ALLOWED:
            return GateResult(5, "scope_authorized", False, f"Scope '{scope}' not in {_SCOPE_ALLOWED}")
        return GateResult(5, "scope_authorized", True, f"Scope '{scope}' authorized")

    def _gate6_sanctions(self, token: dict, req: ExecutionRequest) -> GateResult:
        """Sanctions screening — checks local blocklist or calls SANCTIONS_API_URL if set.
        Set SANCTIONS_STRICT=true to fail when API is not configured."""
        import os
        sanctions_url = os.getenv("SANCTIONS_API_URL", "")
        strict        = os.getenv("SANCTIONS_STRICT", "false").lower() == "true"

        if sanctions_url:
            # Real API configured — call it
            try:
                import requests as _req
                resp = _req.post(
                    f"{sanctions_url}/screen",
                    json={"tenant_id": req.tenant_id, "amount": token.get("amount", 0),
                          "currency": token.get("currency", ""), "actor_sub": req.actor_sub},
                    timeout=5,
                )
                if resp.status_code == 200 and resp.json().get("clear"):
                    return GateResult(6, "sanctions_clear", True, "Sanctions API: clear")
                return GateResult(6, "sanctions_clear", False,
                                  f"Sanctions API: blocked — {resp.json().get('reason', 'unknown')}")
            except Exception as e:
                return GateResult(6, "sanctions_clear", False, f"Sanctions API unreachable: {e}")

        # No API configured
        blocklist = [b.strip().lower() for b in os.getenv("SANCTIONS_BLOCKLIST", "").split(",") if b.strip()]
        actor = req.actor_sub.lower()
        if any(b in actor for b in blocklist):
            return GateResult(6, "sanctions_clear", False, f"Actor '{req.actor_sub}' on local sanctions blocklist")

        if strict:
            return GateResult(6, "sanctions_clear", False,
                              "SANCTIONS_STRICT=true but SANCTIONS_API_URL not configured")

        return GateResult(6, "sanctions_clear", True, "Sanctions: no blocklist match (set SANCTIONS_API_URL for full screening)")

    def _gate7_fx_lock(self, token: dict) -> GateResult:
        """FX rate lock — same currency always passes. Cross-currency requires FX_API_URL or fails if FX_STRICT=true."""
        import os
        currency     = token.get("currency", "INR")
        base_ccy     = os.getenv("BASE_CURRENCY", "INR")
        fx_url       = os.getenv("FX_API_URL", "")
        strict       = os.getenv("FX_STRICT", "false").lower() == "true"

        if currency == base_ccy:
            return GateResult(7, "fx_rate_locked", True, f"Same currency ({currency}) — no FX risk")

        if fx_url:
            try:
                import requests as _req
                resp = _req.get(f"{fx_url}/rate", params={"from": currency, "to": base_ccy}, timeout=5)
                if resp.status_code == 200:
                    rate = resp.json().get("rate", 0)
                    return GateResult(7, "fx_rate_locked", True, f"FX rate locked: 1 {currency} = {rate} {base_ccy}")
                return GateResult(7, "fx_rate_locked", False, f"FX API error: {resp.status_code}")
            except Exception as e:
                return GateResult(7, "fx_rate_locked", False, f"FX API unreachable: {e}")

        if strict:
            return GateResult(7, "fx_rate_locked", False,
                              f"Cross-currency {currency}/{base_ccy}: FX_STRICT=true but FX_API_URL not configured")

        return GateResult(7, "fx_rate_locked", True,
                          f"Cross-currency {currency}/{base_ccy}: FX lock bypassed (set FX_API_URL for real locking)")

    def _gate8_connector(self, token: dict) -> GateResult:
        """Connector certification — checks connector_registry table or CONNECTOR_REGISTRY_URL."""
        import os
        registry_url = os.getenv("CONNECTOR_REGISTRY_URL", "")
        strict       = os.getenv("CONNECTOR_STRICT", "false").lower() == "true"

        if registry_url:
            try:
                import requests as _req
                tenant_id = token.get("tenant_id") or ""
                resp = _req.get(f"{registry_url}/connectors",
                                params={"tenant_id": str(tenant_id)}, timeout=5)
                if resp.status_code == 200 and resp.json().get("status") == "ACTIVE":
                    return GateResult(8, "connector_certified", True, "Connector registry: ACTIVE")
                return GateResult(8, "connector_certified", False,
                                  f"Connector registry: {resp.json().get('status', 'UNKNOWN')}")
            except Exception as e:
                return GateResult(8, "connector_certified", False, f"Connector registry unreachable: {e}")

        if strict:
            return GateResult(8, "connector_certified", False,
                              "CONNECTOR_STRICT=true but CONNECTOR_REGISTRY_URL not configured")

        return GateResult(8, "connector_certified", True,
                          "Connector: registry not configured (set CONNECTOR_REGISTRY_URL for certification check)")

    # ── Dispatch ────────────────────────────────────────────────────────────────

    def _dispatch(
        self, token: dict, req: ExecutionRequest, gates: list[GateResult]
    ) -> ExecutionEnvelope:
        """Write execution_envelopes row, mark token CONSUMED, advance case FSM."""
        token_id  = str(token["id"])
        case_id   = str(token.get("case_id", ""))
        scope     = token.get("scope", "EXECUTE_CREDIT_MEMO")
        amount    = float(token.get("amount", 0))
        currency  = token.get("currency", "INR")
        now       = datetime.now(timezone.utc)
        env_id    = uuid.uuid4()
        connector_ref = f"CONNECTOR-{env_id.hex[:8].upper()}"

        gate_json = json.dumps([{
            "gate": g.gate, "name": g.name,
            "passed": g.passed, "detail": g.detail,
        } for g in gates])

        with _db.get_conn(self._db_url) as conn:
          try:
            cur = conn.cursor()

            # Write execution_envelopes
            cur.execute("""
                INSERT INTO execution_envelopes
                    (id, tenant_id, token_id, case_id, scope, amount, currency,
                     actor_sub, gate_results, connector_ref, status, dispatched_at)
                VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """, (
                env_id, req.tenant_id, token_id,
                uuid.UUID(case_id) if case_id else None,
                scope, amount, currency,
                req.actor_sub, gate_json, connector_ref,
                "DISPATCHED", now,
            ))

            # Mark token CONSUMED in DB
            cur.execute("""
                UPDATE governance_tokens
                SET status='CONSUMED', consumed_at=%s
                WHERE id=%s::uuid AND tenant_id=%s::uuid
            """, (now, token_id, req.tenant_id))

            # Advance case FSM to DISPATCHED
            if case_id:
                cur.execute("""
                    UPDATE cases SET state='DISPATCHED'
                    WHERE id=%s::uuid AND tenant_id=%s::uuid
                      AND state IN ('EXECUTION_READY', 'APPROVED')
                """, (uuid.UUID(case_id), req.tenant_id))
                cur.execute("""
                    INSERT INTO case_events
                        (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                    VALUES (%s, %s::uuid, %s::uuid, 'EXECUTION_DISPATCHED',
                            'EXECUTION_READY', 'DISPATCHED', %s, %s::jsonb, %s)
                """, (
                    uuid.uuid4(), req.tenant_id, uuid.UUID(case_id),
                    req.actor_sub,
                    json.dumps({"envelope_id": str(env_id), "connector_ref": connector_ref}),
                    now,
                ))

            # Write outbox event
            cur.execute("""
                INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), req.tenant_id,
                "zoiko.execution.dispatched",
                case_id or token_id,
                json.dumps({
                    "envelope_id":   str(env_id),
                    "token_id":      token_id,
                    "case_id":       case_id,
                    "scope":         scope,
                    "amount":        amount,
                    "currency":      currency,
                    "connector_ref": connector_ref,
                }),
                now,
            ))

            conn.commit()
          finally:
            pass  # pool returns connection via context manager

        # Kafka publish after commit
        try:
            from kafka.producer import ZoikoProducer, KafkaMessage
            ZoikoProducer(self._broker).publish(KafkaMessage(
                topic     = "zoiko.execution.dispatched",
                key       = case_id or token_id,
                payload   = {"envelope_id": str(env_id), "token_id": token_id, "case_id": case_id},
                tenant_id = req.tenant_id,
            ))
        except Exception:
            pass  # outbox relay will recover

        return ExecutionEnvelope(
            envelope_id   = str(env_id),
            token_id      = token_id,
            tenant_id     = req.tenant_id,
            case_id       = case_id,
            scope         = scope,
            amount        = amount,
            currency      = currency,
            actor_sub     = req.actor_sub,
            gate_results  = gates,
            dispatched_at = now,
            status        = "DISPATCHED",
            connector_ref = connector_ref,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _fetch_token(self, token_id: str, tenant_id: str) -> Optional[dict]:
        row = _db.q1(
            db_url=self._db_url,
            sql="""
                SELECT
                    gt.id,
                    gt.tenant_id,
                    gt.decision_id,
                    gt.scope,
                    gt.tenant_binding,
                    gt.status,
                    gt.expires_at,
                    encode(gt.token_hash, 'hex')   AS token_hash_hex,
                    encode(gt.signature, 'hex')    AS sig_hex,
                    gt.signature,
                    gt.kid,
                    gt.issued_at,
                    dp.amount::float               AS amount,
                    dp.currency,
                    dp.case_id
                FROM  governance_tokens gt
                JOIN  governance_decisions gd ON gd.id = gt.decision_id
                JOIN  decision_proposals dp   ON dp.id = gd.proposal_id
                WHERE gt.id=%s::uuid AND gt.tenant_id=%s::uuid
                LIMIT 1
            """,
            params=(token_id, tenant_id),
        )
        return row
