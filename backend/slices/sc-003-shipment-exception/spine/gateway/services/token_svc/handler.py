"""
SC-003 Token Service — issues 15-minute governance tokens for SLA credit execution.

Token binds: case_id + tenant_id + proposed_action + amount.
Token TTL: 15 minutes (configurable via TOKEN_TTL_MINUTES env var).
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import paths  # noqa: F401
import psycopg2
import psycopg2.extras
import shared.db  # noqa: F401
from zoiko_common.crypto.jcs import canonicalize
from shared.signer import sign

TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "15"))


class TokenHandler:
    def __init__(self, db_url: str, kafka_broker, tenant_slug: str = "default"):
        self.db_url      = db_url
        self.broker      = kafka_broker
        self.tenant_slug = tenant_slug

    def issue_token(
        self,
        tenant_id: str,
        case_id: str,
        decision_id: str,
        amount: float,
        currency: str,
        actor_sub: str,
    ) -> dict:
        """Issue a governance token. Returns token_id and expires_at."""
        now        = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
        token_id   = uuid.uuid4()
        case_uuid  = uuid.UUID(case_id)

        token_dict = {
            "action":      "ISSUE_SLA_CREDIT",
            "amount":      str(amount),
            "case_id":     case_id,
            "currency":    currency,
            "decision_id": decision_id,
            "expires_at":  expires_at.isoformat(),
            "tenant_id":   tenant_id,
            "token_id":    str(token_id),
        }
        token_bytes = canonicalize(token_dict)
        token_hash  = hashlib.sha256(b"zoiko.token.v1:" + token_bytes).digest()
        t_sig, t_kid = sign(self.tenant_slug, token_hash)

        psycopg2.extras.register_uuid()
        conn = psycopg2.connect(self.db_url)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO governance_tokens
                    (id, tenant_id, case_id, decision_id, action, amount, currency,
                     issued_to, token_hash, signature, kid, status, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                token_id, tenant_id, case_uuid,
                uuid.UUID(decision_id) if decision_id else None,
                "ISSUE_SLA_CREDIT", amount, currency,
                actor_sub, token_hash, t_sig, t_kid,
                "ACTIVE", expires_at, now,
            ))

            # Advance case to EXECUTION_READY
            cur.execute(
                "UPDATE cases SET state='EXECUTION_READY' WHERE id=%s AND tenant_id=%s",
                (case_uuid, tenant_id),
            )
            cur.execute("""
                INSERT INTO case_events
                    (id, tenant_id, case_id, event_type, from_state, to_state, actor_sub, payload, occurred_at)
                VALUES (%s, %s, %s, 'TOKEN_ISSUED', 'APPROVAL_PENDING', 'EXECUTION_READY', %s, %s::jsonb, %s)
            """, (
                uuid.uuid4(), tenant_id, case_uuid, actor_sub,
                json.dumps({"token_id": str(token_id), "expires_at": expires_at.isoformat()}),
                now,
            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "token_id":   str(token_id),
            "expires_at": expires_at.isoformat(),
            "action":     "ISSUE_SLA_CREDIT",
            "amount":     amount,
            "currency":   currency,
        }
