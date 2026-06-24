"""
Webhook router — Tier-0 spec §7.4 (Webhook Channel).

Manages webhook signing secrets for inbound carrier/ERP webhooks.

GET    /webhooks/secrets/{tenant_id}       — list webhook endpoint configs (admin)
POST   /webhooks/secrets/{tenant_id}       — create/rotate a webhook signing secret (admin)
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import psycopg2
from fastapi import APIRouter, Depends, HTTPException

import paths  # noqa: F401
from services.api_gateway.auth import get_claims
from middleware.oidc.claims import ZoikoClaims
from shared.db import q

router = APIRouter(tags=["webhooks"])

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
