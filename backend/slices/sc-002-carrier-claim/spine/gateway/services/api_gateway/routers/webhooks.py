"""
Webhook router — Tier-0 spec §7.4 (Webhook Channel).

Manages webhook signing secrets for inbound carrier/ERP webhooks, and
receives inbound carrier settlement responses.

GET    /webhooks/secrets/{tenant_id}           — list webhook endpoint configs (admin)
POST   /webhooks/secrets/{tenant_id}           — create/rotate a webhook signing secret (admin)
POST   /webhooks/carrier/{source_type}         — inbound carrier settlement response (no JWT auth)
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, Header, HTTPException, Request

import paths  # noqa: F401
from services.api_gateway.auth import get_claims
from middleware.oidc.claims import ZoikoClaims
from shared.db import q, q1

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

DB_URL = os.getenv("DB_URL")

DB_URL = os.getenv("DB_URL")


# ── GET /webhooks/secrets/{tenant_id} ────────────────────────────────────────

@router.get("/webhooks/secrets/{target_tenant_id}")
def list_webhook_configs(
    target_tenant_id: str,
    claims: ZoikoClaims = Depends(get_claims),
):
    """List active webhook signing configurations (admin only)."""
    if getattr(claims, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="admin role required")

    if str(claims.tenant_id) != target_tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")

    rows = q("""
        SELECT id, source_type, is_active, ip_allowlist, created_at, rotated_at
        FROM webhook_signing_configs
        WHERE tenant_id = %s::uuid
        ORDER BY created_at DESC
    """, (target_tenant_id,))

    return {
        "tenant_id": target_tenant_id,
        "configs": [
            {
                "id":          str(r["id"]),
                "source_type": r["source_type"],
                "is_active":   r["is_active"],
                "ip_allowlist": r.get("ip_allowlist") or [],
                "created_at":  r["created_at"].isoformat() if r.get("created_at") else None,
                "rotated_at":  r["rotated_at"].isoformat() if r.get("rotated_at") else None,
                "signing_secret": "***",  # never expose in API response
            }
            for r in rows
        ],
    }


# ── POST /webhooks/secrets/{tenant_id} ───────────────────────────────────────

@router.post("/webhooks/secrets/{target_tenant_id}", status_code=201)
def create_webhook_secret(
    target_tenant_id: str,
    body: dict,
    claims: ZoikoClaims = Depends(get_claims),
):
    """
    Create or rotate a webhook signing secret for a tenant + source_type pair.
    Admin only. Returns the new secret (only time it is shown in plaintext).
    """
    if getattr(claims, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="admin role required")

    if str(claims.tenant_id) != target_tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")

    source_type  = body.get("source_type")
    ip_allowlist = body.get("ip_allowlist", [])
    if not source_type:
        raise HTTPException(status_code=400, detail="source_type required")

    # Generate a new 32-byte secret
    new_secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
    config_id  = uuid.uuid4()
    now        = datetime.now(timezone.utc)

    try:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()

        # Deactivate any existing config for this tenant + source_type
        cur.execute("""
            UPDATE webhook_signing_configs
            SET is_active = false, rotated_at = %s
            WHERE tenant_id = %s::uuid AND source_type = %s AND is_active = true
        """, (now, target_tenant_id, source_type))

        # Insert new config
        cur.execute("""
            INSERT INTO webhook_signing_configs
                (id, tenant_id, source_type, signing_secret, ip_allowlist, is_active, created_at)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, true, %s)
        """, (
            config_id, target_tenant_id, source_type,
            new_secret, json.dumps(ip_allowlist), now,
        ))
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to store webhook config: {exc}")

    return {
        "id":            str(config_id),
        "tenant_id":     target_tenant_id,
        "source_type":   source_type,
        "signing_secret": new_secret,  # shown once — caller must store securely
        "ip_allowlist":  ip_allowlist,
        "created_at":    now.isoformat(),
        "warning":       "Store this secret securely — it will not be shown again",
    }


# ── POST /webhooks/carrier/{source_type} ─────────────────────────────────────

@router.post("/webhooks/carrier/{source_type}", status_code=200)
async def receive_carrier_settlement(
    source_type: str,
    request: Request,
    x_webhook_tenant_id: str = Header(..., alias="X-Webhook-Tenant-ID"),
    x_webhook_signature: str = Header("", alias="X-Webhook-Signature"),
):
    """
    Inbound carrier settlement response — no JWT auth.

    Carriers POST here after processing a claim.  The request must:
      - Supply  X-Webhook-Tenant-ID  (tenant UUID)
      - Supply  X-Webhook-Signature  (HMAC-SHA256 of raw body, hex-encoded)
      - Body JSON:
          {
            "connector_ref":      "CONNECTOR-ABCD1234",   # reference from dispatch
            "settled_amount":     220.00,
            "status":             "ACCEPTED" | "PARTIAL" | "REJECTED",
            "carrier_reference":  "BDT-CLM-20260001",     # carrier's own claim ID
            "notes":              "Settled in full"        # optional
          }

    On success: writes connector_responses row and triggers reconciliation.
    """
    raw_body = await request.body()
    psycopg2.extras.register_uuid()

    # 1. Look up active signing config for this tenant + source_type
    cfg = q1("""
        SELECT signing_secret, ip_allowlist
        FROM   webhook_signing_configs
        WHERE  tenant_id = %s::uuid AND source_type = %s AND is_active = true
        LIMIT  1
    """, (x_webhook_tenant_id, source_type))

    # In DEV_MODE skip signature check if no config exists yet
    dev_mode = os.getenv("ZOIKO_DEV_MODE", "").lower() == "true"
    if not cfg:
        if not dev_mode:
            raise HTTPException(
                status_code=401,
                detail=f"No active webhook signing config for source_type '{source_type}'"
            )
        logger.warning("DEV_MODE: no webhook signing config — skipping HMAC verification")
    else:
        # 2. Verify HMAC-SHA256 signature
        secret = cfg["signing_secret"].encode()
        expected_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        provided_sig = x_webhook_signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(status_code=401, detail="Webhook signature verification failed")

    # 3. Parse body
    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    connector_ref   = body.get("connector_ref", "")
    settled_amount  = body.get("settled_amount")
    status_str      = (body.get("status") or "ACCEPTED").upper()
    carrier_ref     = body.get("carrier_reference", "")
    notes           = body.get("notes", "")

    if not connector_ref:
        raise HTTPException(status_code=400, detail="connector_ref is required")
    if settled_amount is None:
        raise HTTPException(status_code=400, detail="settled_amount is required")
    if status_str not in ("ACCEPTED", "PARTIAL", "REJECTED"):
        raise HTTPException(status_code=400, detail="status must be ACCEPTED, PARTIAL, or REJECTED")

    # 4. Resolve connector_ref → execution_envelope
    envelope = q1("""
        SELECT id, tenant_id, case_id, amount, currency, scope
        FROM   execution_envelopes
        WHERE  connector_ref = %s AND tenant_id = %s::uuid
        LIMIT  1
    """, (connector_ref, x_webhook_tenant_id))

    if not envelope:
        raise HTTPException(
            status_code=404,
            detail=f"No execution envelope found for connector_ref '{connector_ref}'"
        )

    envelope_id = str(envelope["id"])
    case_id     = str(envelope["case_id"]) if envelope["case_id"] else ""

    # 5. Idempotency — skip if a response already exists for this envelope
    existing = q1(
        "SELECT id FROM connector_responses WHERE envelope_id = %s::uuid LIMIT 1",
        (envelope_id,),
    )
    if existing:
        logger.info("Duplicate carrier webhook for envelope %s — skipped", envelope_id)
        return {"status": "duplicate", "envelope_id": envelope_id, "action_taken": "skipped"}

    # 6. Write connector_responses row
    status_code_map = {"ACCEPTED": 200, "PARTIAL": 206, "REJECTED": 422}
    http_status     = status_code_map[status_str]
    response_body   = {
        "settled_amount":    float(settled_amount),
        "status":            status_str,
        "carrier_reference": carrier_ref,
        "notes":             notes,
    }
    now = datetime.now(timezone.utc)

    try:
        conn = psycopg2.connect(DB_URL)
        psycopg2.extras.register_uuid()
        cur  = conn.cursor()
        response_id = uuid.uuid4()
        cur.execute("""
            INSERT INTO connector_responses
                (id, tenant_id, envelope_id, connector_id, status_code, response_body, received_at)
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
        """, (
            response_id,
            x_webhook_tenant_id,
            envelope_id,
            source_type,         # connector_id = source_type slug
            http_status,
            json.dumps(response_body),
            now,
        ))

        # 7. Write outbox event — zoiko.reconciliation.updated will be published post-reconcile
        cur.execute("""
            INSERT INTO outbox (id, tenant_id, topic, partition_key, payload, created_at)
            VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
        """, (
            uuid.uuid4(), x_webhook_tenant_id,
            "zoiko.claim.settled",
            case_id or envelope_id,
            json.dumps({
                "envelope_id":    envelope_id,
                "connector_ref":  connector_ref,
                "settled_amount": float(settled_amount),
                "status":         status_str,
                "carrier_ref":    carrier_ref,
            }),
            now,
        ))

        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to write connector_response: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to store carrier response: {exc}")

    # 8. Auto-trigger reconciliation if accepted/partial
    action_taken = "response_stored"
    if status_str in ("ACCEPTED", "PARTIAL"):
        try:
            from services.reconciliation_svc.handler import ReconciliationHandler
            from kafka.mock_kafka import MockKafkaBroker
            broker = MockKafkaBroker()
            handler = ReconciliationHandler(DB_URL, broker)
            handler.reconcile(
                envelope_id=envelope_id,
                tenant_id=x_webhook_tenant_id,
                actor_sub="carrier_webhook",
            )
            action_taken = "reconciliation_triggered"
        except Exception as exc:
            logger.warning("Auto-reconciliation failed for envelope %s: %s", envelope_id, exc)
            action_taken = "response_stored_reconcile_deferred"

    return {
        "webhook_id":   str(response_id),
        "status":       "ok",
        "envelope_id":  envelope_id,
        "case_id":      case_id,
        "action_taken": action_taken,
        "settled_amount": float(settled_amount),
        "carrier_status": status_str,
    }
