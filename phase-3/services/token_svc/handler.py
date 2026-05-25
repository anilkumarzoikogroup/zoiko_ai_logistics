"""
Token Service — mints a cryptographically signed Governance Token after an APPROVED decision.

Token fields (from DB schema):
  tenant_binding = SHA-256(tenant_id_utf8 || decision_id_utf8)
  token_hash     = SHA-256(b"zoiko.token.v1:" + JCS(token_payload))
  status         = ACTIVE (default; Phase 4 Execution Gateway sets CONSUMED)
  expires_at     = issued_at + 15 minutes (configurable via TOKEN_TTL_MINUTES env)

The token_hash + signature are what Phase 4 verifies at the 8-gate Execution Gateway.
"""
import hashlib, json, os, uuid
from datetime import datetime, timezone, timedelta

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401 — registers UUID adapter

from shared.signer import sign
from zoiko_common.crypto.jcs import canonicalize

from services.token_svc.models import TokenResult

TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "15"))


class TokenHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def mint(
        self,
        tenant_id:   str,
        decision_id: str,
        case_id:     str,
        scope:       str = "EXECUTE_CREDIT_MEMO",
        actor_sub:   str = "system",
    ) -> TokenResult:
        tenant_id   = str(tenant_id)
        decision_id = str(decision_id)
        case_id     = str(case_id)
        now         = datetime.now(timezone.utc)
        expires_at  = now + timedelta(minutes=TOKEN_TTL_MINUTES)

        # Verify the decision is APPROVED before minting
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT outcome FROM governance_decisions WHERE id=%s AND tenant_id=%s",
                (uuid.UUID(decision_id), tenant_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Governance decision {decision_id} not found for tenant {tenant_id}")
            if row["outcome"] != "EXECUTION_READY":
                raise ValueError(
                    f"Cannot mint token: decision {decision_id} outcome is {row['outcome']}, "
                    f"must be EXECUTION_READY"
                )

            # tenant_binding = SHA-256(tenant_id_utf8 || decision_id_utf8)
            tenant_binding = hashlib.sha256(
                tenant_id.encode("utf-8") + decision_id.encode("utf-8")
            ).digest()

            # JCS canonicalize token payload → domain-tagged SHA-256
            token_payload = {
                "case_id":     case_id,
                "decision_id": decision_id,
                "expires_at":  expires_at.isoformat(),
                "scope":       scope,
                "tenant_id":   tenant_id,
            }
            token_bytes = canonicalize(token_payload)
            token_hash  = hashlib.sha256(b"zoiko.token.v1:" + token_bytes).digest()
            token_sig, token_kid = sign(self.tenant_slug, token_hash)

            token_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO governance_tokens
                    (id, tenant_id, decision_id, scope, tenant_binding, status,
                     expires_at, token_hash, signature, kid, issued_at)
                VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s)
            """, (
                token_id, tenant_id, uuid.UUID(decision_id), scope,
                tenant_binding, expires_at,
                token_hash, token_sig, token_kid, now,
            ))
            conn.commit()
        finally:
            conn.close()

        from kafka.producer import ZoikoProducer, KafkaMessage
        ZoikoProducer(self.broker).publish(KafkaMessage(
            topic     = "zoiko.governance.token.issued",
            key       = str(token_id),
            payload   = {
                "token_id":    str(token_id),
                "decision_id": decision_id,
                "case_id":     case_id,
                "scope":       scope,
                "expires_at":  expires_at.isoformat(),
            },
            tenant_id = tenant_id,
        ))

        return TokenResult(
            token_id       = token_id,
            tenant_id      = tenant_id,
            decision_id    = decision_id,
            case_id        = case_id,
            scope          = scope,
            status         = "ACTIVE",
            token_hash     = token_hash.hex(),
            tenant_binding = tenant_binding.hex(),
            expires_at     = expires_at,
            issued_at      = now,
        )
